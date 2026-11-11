"""ADC-only Vertex configuration, safe diagnostics and metered SDK models."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field, replace
from importlib.metadata import version
from pathlib import Path

from agents import Model, ModelSettings
from dotenv import load_dotenv


def safe_error(error) -> dict:
    """Classify errors without exposing messages, headers, URLs or credentials."""
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    status = status if isinstance(status, int) else None
    name = type(error).__name__
    categories = {400: "invalid_request_or_unsupported_combination", 401: "authentication_failed",
                  403: "permission_or_service_access_denied", 404: "model_or_resource_not_found",
                  429: "quota_or_rate_limit", 500: "provider_error", 503: "provider_unavailable"}
    category = categories.get(status, "request_failed")
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        category = "request_timeout"
    if isinstance(error, BudgetExceeded):
        category = "execution_budget_exceeded"
    messages = {
        "authentication_failed": "ADC authentication failed; refresh credentials before retrying.",
        "permission_or_service_access_denied": "The identity cannot access this resource or service.",
        "model_or_resource_not_found": "The configured model or resource is unavailable or inaccessible.",
        "invalid_request_or_unsupported_combination": "The provider rejected this request or feature combination.",
        "quota_or_rate_limit": "Provider quota or rate limit was reached; no automatic retry is performed.",
        "request_timeout": "The request exceeded its configured deadline.",
        "execution_budget_exceeded": "Execution stopped at the configured request or prompt limit.",
    }
    return {"category": category, "exception_type": name, "status_code": status,
            "message": messages.get(category, "The request failed; raw provider details are withheld.")}


def _gcloud(*args):
    if not shutil.which("gcloud"):
        return None
    try:
        env = {**os.environ, "CLOUDSDK_CORE_DISABLE_FILE_LOGGING": "true"}
        result = subprocess.run(["gcloud", *args, "--quiet"], env=env, capture_output=True, text=True, timeout=10)
        value = result.stdout.strip()
        return value if result.returncode == 0 and value != "(unset)" else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def diagnose() -> dict:
    """Local metadata only: no token printing, refresh, cloud mutation or model call."""
    project = _gcloud("config", "get-value", "project")
    region = _gcloud("config", "get-value", "ai/region")
    adc = Path(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", Path.home() / ".config/gcloud/application_default_credentials.json"))
    metadata = {}
    if adc.is_file():
        try:
            data = json.loads(adc.read_text())
            metadata = {key: data.get(key) for key in ("type", "quota_project_id")}
        except (OSError, ValueError):
            metadata = {"readable": False}
    accounts = _gcloud("auth", "list", "--format=json")
    try:
        active_accounts = sum(a.get("status") == "ACTIVE" for a in json.loads(accounts or "[]"))
    except (ValueError, TypeError):
        active_accounts = None
    return {"gcloud_available": bool(shutil.which("gcloud")), "gcloud_project": project,
            "gcloud_region": region, "active_cli_account_count": active_accounts,
            "adc_file_present": adc.is_file(), "adc_metadata": metadata,
            "adc_authenticated": "unverified_until_refresh_or_provider_request",
            "versions": {p: version(p) for p in ("openai-agents", "litellm", "google-genai", "google-auth", "pydantic")}}


@dataclass(frozen=True)
class VertexConfig:
    project: str
    location: str = "global"
    model: str = "gemini-3.5-flash"
    researcher_model: str = "gemini-3.5-flash-lite"
    grounding_model: str = "gemini-3.5-flash"
    timeout_seconds: float = 30
    max_output_tokens: int = 2048

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", self.project):
            raise ValueError("Configure an existing Google Cloud project ID.")
        if not re.fullmatch(r"[a-z0-9-]+", self.location):
            raise ValueError("Invalid Vertex location.")
        for model in (self.model, self.researcher_model, self.grounding_model):
            if not re.fullmatch(r"gemini-[a-zA-Z0-9_.-]+", model):
                raise ValueError("Only explicit Gemini publisher model IDs are accepted.")
        if not 0 < self.timeout_seconds <= 120 or not 1 <= self.max_output_tokens <= 4096:
            raise ValueError("Request timeout/output limits exceed the live test envelope.")

    @classmethod
    def from_environment(cls, *, root=None, diagnostics=None):
        if root:
            load_dotenv(Path(root) / ".env", override=False)
        diagnostics = diagnostics if diagnostics is not None else diagnose()
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEXAI_PROJECT") or diagnostics.get("gcloud_project")
        location = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("VERTEXAI_LOCATION") or diagnostics.get("gcloud_region") or "global"
        return cls(project=project or "", location=location,
                   model=os.getenv("MODELMATCH_VERTEX_MODEL", "gemini-3.5-flash"),
                   researcher_model=os.getenv("MODELMATCH_RESEARCHER_MODEL", "gemini-3.5-flash-lite"),
                   grounding_model=os.getenv("MODELMATCH_GROUNDING_MODEL", "gemini-3.5-flash"))

    def settings(self):
        return ModelSettings(max_tokens=self.max_output_tokens,
            extra_args={"vertex_project": self.project, "vertex_location": self.location,
                        "timeout": self.timeout_seconds, "num_retries": 0})


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class CallBudget:
    max_calls: int = 24
    max_prompt_chars: int = 60000
    calls: int = 0
    records: list[dict] = field(default_factory=list)
    capture_responses: bool = False

    def reserve(self, prompt_chars):
        if self.calls >= self.max_calls or prompt_chars > self.max_prompt_chars:
            raise BudgetExceeded("Call or prompt budget exceeded.")
        self.calls += 1
        return self.calls


def token_usage(usage) -> dict:
    return {key: getattr(usage, key, None) for key in ("input_tokens", "output_tokens", "total_tokens")}


class MeteredModel(Model):
    def __init__(self, inner, model_name, budget: CallBudget, config: VertexConfig):
        self.inner, self.model_name, self.budget, self.config = inner, model_name, budget, config

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **kwargs):
        size = len(json.dumps(input, default=str)) + len(system_instructions or "")
        size += len(str(getattr(output_schema, "json_schema", lambda: {})()))
        size += sum(len(str(getattr(t, "params_json_schema", {}))) for t in tools)
        number = self.budget.reserve(size)
        started = time.monotonic()
        record = {"call": number, "model": self.model_name, "prompt_chars": size}
        try:
            settings = replace(model_settings, max_tokens=min(model_settings.max_tokens or self.config.max_output_tokens, self.config.max_output_tokens),
                               extra_args={**(model_settings.extra_args or {}), "num_retries": 0})
            response = await asyncio.wait_for(self.inner.get_response(system_instructions, input, settings, tools,
                output_schema, handoffs, tracing, **kwargs), timeout=self.config.timeout_seconds)
            record.update(status="success", usage=token_usage(response.usage),
                          tool_calls=[getattr(item, "name", None) for item in response.output if getattr(item, "type", None) == "function_call"])
            if self.budget.capture_responses:
                outputs = []
                for item in response.output:
                    kind = getattr(item, "type", None)
                    if kind == "function_call":
                        outputs.append({"type": kind, "name": item.name, "arguments": item.arguments,
                                        "call_id": item.call_id})
                    elif kind == "message":
                        outputs.append({"type": kind, "role": getattr(item, "role", "assistant"),
                                        "text": "".join(getattr(part, "text", "") for part in item.content)})
                record["provider_response"] = {"response_id": response.response_id,
                    "request_id": getattr(response, "request_id", None), "output": outputs}
            return response
        except Exception as error:
            record.update(status="failed", error=safe_error(error))
            raise
        finally:
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            self.budget.records.append(record)

    def stream_response(self, *args, **kwargs):
        raise BudgetExceeded("Live integration tests do not permit streaming provider requests.")

    async def _cleanup_on_run_end(self, owner):
        cleanup = getattr(self.inner, "_cleanup_on_run_end", None)
        if cleanup:
            await cleanup(owner)

    async def close(self):
        close = getattr(self.inner, "close", None)
        if close:
            await close()


def create_models(config: VertexConfig, budget: CallBudget):
    # LiteLLM's cost-map refresh is unrelated to AA operational scoring.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    os.environ.setdefault("CLOUDSDK_CORE_DISABLE_FILE_LOGGING", "true")
    from agents.extensions.models.litellm_model import LitellmModel
    import litellm
    litellm.suppress_debug_info = True
    return tuple(MeteredModel(LitellmModel(model=f"vertex_ai/{name}", api_key="unused"), name, budget, config)
                 for name in (config.model, config.researcher_model))


def check_permissions(config: VertexConfig) -> dict:
    """Read-only OAuth/IAM/service checks. Never enable APIs, alter IAM or save tokens."""
    try:
        os.environ.setdefault("CLOUDSDK_CORE_DISABLE_FILE_LOGGING", "true")
        import google.auth
        from google.auth.transport.requests import AuthorizedSession, Request
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        request = Request()
        def bounded_auth_request(*args, **kwargs):
            kwargs["timeout"] = 15
            return request(*args, **kwargs)
        credentials.refresh(bounded_auth_request)
        session = AuthorizedSession(credentials)
        permissions = ["aiplatform.endpoints.predict", "serviceusage.services.use"]
        with session:
            response = session.post(f"https://cloudresourcemanager.googleapis.com/v1/projects/{config.project}:testIamPermissions",
                                    json={"permissions": permissions}, timeout=15)
            iam = {"status_code": response.status_code, "granted": response.json().get("permissions", []) if response.status_code == 200 else None}
            response = session.get(f"https://serviceusage.googleapis.com/v1/projects/{config.project}/services/aiplatform.googleapis.com", timeout=15)
            service = {"status_code": response.status_code,
                       "state": response.json().get("state", "unknown") if response.status_code == 200 else "unknown"}
        return {"adc_refresh": "success", "iam": iam, "vertex_service": service}
    except Exception as error:
        return {"adc_refresh": "unverified_or_failed", "error": safe_error(error)}
