"""Explicit synthetic web demonstration using the real Agents SDK runner."""

import asyncio
import json
import uuid

from agents import Model
from agents.items import ModelResponse
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText


class OfflineModel(Model):
    """Scripted protocol demo, never a live model evaluation or classifier."""

    def __init__(self):
        self.seen = set()
        self.domain = None

    def stream_response(self, *args, **kwargs):
        raise NotImplementedError("The offline demo uses non-streaming model responses.")

    def response(self, value=None, calls=()):
        output = [ResponseFunctionToolCall(type="function_call", name=name, arguments=json.dumps(args),
                  call_id=str(uuid.uuid4())) for name, args in calls]
        if not calls:
            output = [ResponseOutputMessage(id=str(uuid.uuid4()), type="message", role="assistant", status="completed",
                      content=[ResponseOutputText(type="output_text", text=json.dumps(value), annotations=[])])]
        return ModelResponse(output=output, usage=Usage(), response_id=str(uuid.uuid4()))

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **kwargs):
        await asyncio.sleep(0)
        messages = input if isinstance(input, list) else [{"role": "user", "content": input}]
        payload = json.loads(next(m["content"] for m in reversed(messages) if m.get("role") == "user"))
        stage = payload.get("stage")
        if stage == "parse":
            task = payload["user_input"].split("\n\nStructured requirements")[0]
            self.domain = next((d for d, words in {"finance": ("finance", "financial"),
                "engineering": ("engineering",), "healthcare": ("healthcare", "medical")}.items()
                if any(w in task.lower() for w in words)), None)
            vague = task.lower().strip(" .?!") in {"help", "hello", "best model", "best llm", "finance", ""}
            return self.response({"industry": self.domain, "task_description": "" if vague else task,
                "task_quote": "" if vague else task, "task_type": "mixed_or_unknown", "constraints": [],
                "workload": {}, "clarification_questions": []})
        if stage in ("dispatch", "followup"):
            if messages[-1].get("role") == "user":
                return self.response(calls=[(t.name, {"task": "Retrieve synthetic demonstration evidence", "model_ids": []}) for t in tools])
            return self.response({"completed": True})
        if stage in ("review", "review_final"):
            result = {"summary": "Reviewed synthetic evidence only. No live verification occurred.",
                      "stopping_reason": "The fixed synthetic snapshot has no additional sources."}
            if stage == "review":
                result["followups"] = []
            return self.response(result)
        if "candidate_ids" in payload:
            return self.response({"candidate_ids": payload["candidate_ids"], "evidence_ids": payload["evidence_ids"],
                                  "validation_steps": ["task_pilot", "check_index_versions"]})
        run_id = payload["research_run_id"]
        if run_id not in self.seen:
            self.seen.add(run_id)
            name = tools[0].name
            args = {"domain": self.domain, "match_status": "partial" if self.domain else "none",
                    "rationale": "Scripted synthetic demo mapping; not live task evaluation."} if name == "get_domain_evidence" else {}
            return self.response(calls=[(name, args)])
        return self.response({"evidence_ids": [], "observations": ["evidence_available"]})
