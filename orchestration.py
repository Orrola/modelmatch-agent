"""Bounded ModelMatch backend orchestration using the instructor's Agents SDK pattern."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from copy import deepcopy
from dataclasses import asdict, replace

from agents import ModelBehaviorError, RunConfig, RunHooks, Runner
from pydantic import ValidationError

from modelmatch_agents import create_team
from modelmatch_schemas import (
    AgentCallContext, LEAD_OUTPUT_TYPES, OrchestrationLimits, ParsedPlan, ResearcherOutput, WriterOutput,
)
from tools.artificial_analysis import numeric, utc_now
from tools.decision import TASK_DEFAULTS, decide, evaluate_operations, resolve_weights
from tools.model_evidence import OperationalRequirement, RelevanceDecision, Workload, build_candidates


class WorkflowError(RuntimeError):
    """Errors use stable public codes; provider exception text is never returned."""


def _quoted(raw: str, quote: str | None) -> bool:
    return bool(quote and quote.strip() and quote.casefold() in raw.casefold())


def _number_in_quote(value: float, quote: str) -> bool:
    for match in re.finditer(r"(?<![\w.])([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*(%|[kKmM]\b)?", quote):
        number = float(match[1].replace(",", ""))
        suffix = (match[2] or "").lower()
        number *= {"k": 1000, "m": 1000000, "%": 0.01}.get(suffix, 1)
        if numeric(value) and abs(number - value) <= 1e-9:
            return True
    return False


def validate_plan(plan: ParsedPlan, raw: str):
    """Require explicit input anchors; never invent workload, alpha or hardness."""
    if not _quoted(raw, plan.task_quote) or not plan.task_description.strip():
        raise ValueError("A concrete task anchored in the user input is required.")
    vague = re.sub(r"[^a-z ]", "", plan.task_quote.lower()).strip()
    if vague in {"best llm", "best model", "llm", "model", "hello", "help", "recommend a model", "which model is best"}:
        raise ValueError("The request needs a concrete task.")
    if plan.industry and plan.task_quote.strip().casefold() == plan.industry.strip().casefold():
        raise ValueError("Please describe a concrete task, not only an industry.")
    for stated in [plan.user_alpha, *[getattr(plan.workload, key) for key in ("monthly_requests", "avg_input_tokens", "avg_output_tokens")]]:
        if stated is not None and (not _quoted(raw, stated.source_quote) or not _number_in_quote(stated.value, stated.source_quote)):
            raise ValueError("A numeric extraction is not supported by the quoted input.")
    for constraint in plan.constraints:
        if not _quoted(raw, constraint.source_quote):
            raise ValueError("A constraint is not supported by the input.")
        if numeric(constraint.target) and not _number_in_quote(constraint.target, constraint.source_quote):
            raise ValueError("A constraint target is not stated in its quote.")
        if isinstance(constraint.target, str) and constraint.target.casefold() not in constraint.source_quote.casefold():
            raise ValueError("A categorical constraint is not stated in its quote.")
        if constraint.hard and (not _quoted(raw, constraint.hard_source_quote) or not re.search(
            r"\b(must|hard|strict|mandatory|required|maximum|minimum|only|cannot)\b|at most|at least|no more than|on-prem", constraint.hard_source_quote or "", re.I
        )):
            raise ValueError("A hard constraint requires an explicit mandatory condition.")
    requirements = tuple(OperationalRequirement(c.metric, c.target, c.hard, c.statistic) for c in plan.constraints)
    workload = Workload(**{key: getattr(plan.workload, key).value if getattr(plan.workload, key) else None
                          for key in ("monthly_requests", "avg_input_tokens", "avg_output_tokens")})
    if any(c.metric == "monthly_cost_usd" for c in requirements) and any(value is None for value in asdict(workload).values()):
        raise ValueError("Monthly cost requires request volume and average input/output tokens.")
    weights = resolve_weights(plan.task_type, plan.user_alpha.value if plan.user_alpha else None)
    return requirements, workload, weights


class WorkflowHooks(RunHooks):
    """Forward SDK callbacks to PanelHooks and capture same-turn dispatch batches."""

    def __init__(self, workflow, panel):
        self.workflow, self.panel = workflow, panel
        self.llm_started = {}

    async def _forward(self, name, *args):
        method = getattr(self.panel, name, None)
        if method:
            await method(*args)

    async def on_agent_start(self, context, agent):
        await self._forward("on_agent_start", context, agent)

    async def on_agent_end(self, context, agent, output):
        await self._forward("on_agent_end", context, agent, output)

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        self.llm_started[context.context.context_id] = time.monotonic()
        self.workflow.event("llm_started", agent.name, context_id=context.context.context_id, stage=context.context.stage)
        await self._forward("on_llm_start", context, agent, system_prompt, input_items)

    async def on_llm_end(self, context, agent, response):
        usage = getattr(response, "usage", None)
        self.workflow.event("llm_completed", agent.name, context_id=context.context.context_id,
            elapsed_seconds=round(time.monotonic() - self.llm_started.get(context.context.context_id, time.monotonic()), 3),
            usage={key: getattr(usage, key, None) for key in ("input_tokens", "output_tokens", "total_tokens")})
        calls = [getattr(item, "name", "") for item in response.output if getattr(item, "type", None) == "function_call"]
        if context.context.role == "Lead" and calls:
            self.workflow.batches.append({"stage": context.context.stage, "calls": calls})
            self.workflow.event("dispatch_batch", "Lead", stage=context.context.stage, calls=calls)
        await self._forward("on_llm_end", context, agent, response)

    async def on_tool_start(self, context, agent, tool):
        self.workflow.event("tool_start", agent.name, context_id=context.context.context_id, tool=tool.name)
        await self._forward("on_tool_start", context, agent, tool)

    async def on_tool_end(self, context, agent, tool, result):
        self.workflow.event("tool_end", agent.name, context_id=context.context.context_id, tool=tool.name)
        await self._forward("on_tool_end", context, agent, tool, result)


class ModelMatchWorkflow:
    def __init__(self, model, researcher_model, *, settings=None, hooks=None,
                 snapshot_loader=None, limits=None, runner=Runner, official_service=None):
        self.team = create_team(model, researcher_model, settings)
        self.panel = hooks
        self.hooks = WorkflowHooks(self, hooks)
        self.snapshot_loader = snapshot_loader
        self.limits = limits or OrchestrationLimits()
        self.runner = runner
        self.trace, self.batches, self.reviews = [], [], []
        self.lead_context = AgentCallContext(self, "Lead", str(uuid.uuid4()), stage="parse")
        self.history = None
        self.snapshot = None
        self.plan = None
        self.relevance = None
        self.requirements = ()
        self.workload = Workload()
        self.weights = None
        self.prepared_cache = {}
        self.role_results, self.payloads, self.errors = {}, {}, {}
        self.allowed = {}
        self.dispatched = set()
        self.researcher_count = 0
        self.started = False
        self.official_service = official_service
        self.official_evidence, self.official_reports = {}, []
        self.official_revision = 0
        self._stage = None
        self._completed_stage = None
        self._lead_running = False
        self._closed = False
        self._authorized_followups = ()
        self.clarification_suggestions = []

    def event(self, kind, agent, **fields):
        event = {"seq": len(self.trace), "type": kind, "agent": agent,
                 "timestamp": utc_now(), "monotonic": time.monotonic(), **fields}
        self.trace.append(event)
        if self.panel is not None:
            self.panel.activity(agent, kind.replace("_", " "))

    async def _run(self, agent, prompt, context, output_type):
        result = await self.runner.run(agent, prompt, context=context, hooks=self.hooks,
                                       max_turns=self.limits.max_agent_turns,
                                       run_config=RunConfig(tracing_disabled=True))
        output = result.final_output
        parsed = output if isinstance(output, output_type) else output_type.model_validate_json(output) if isinstance(output, str) else output_type.model_validate(output)
        return parsed, result

    def research_tool_enabled(self, role):
        """SDK tool visibility follows controller state, not a model's stage claim."""
        return (not self._closed and self._lead_running and self._stage in ("dispatch", "followup")
                and self.lead_context.stage == self._stage and role in self.allowed
                and self.plan is not None and self.snapshot is not None)

    def _enter_lead_stage(self, stage):
        transitions = {None: {"parse"}, "parse": {"dispatch"}, "dispatch": {"review"},
                       "review": {"followup"}, "followup": {"review_final"}, "review_final": set()}
        if self._closed or self._lead_running or stage not in transitions.get(self._completed_stage, set()):
            raise WorkflowError("invalid_lead_stage_transition")
        if stage != "parse" and (self.plan is None or self.snapshot is None or self.weights is None):
            raise WorkflowError("lead_stage_prerequisites_missing")
        if stage == "followup" and (not self._authorized_followups or not self.limits.max_followup_rounds):
            raise WorkflowError("followup_not_authorized")
        self._stage = stage
        self.lead_context.stage = stage

    async def lead(self, stage, payload):
        self._enter_lead_stage(stage)
        self._lead_running = True
        agent = self.team.lead
        output_type = LEAD_OUTPUT_TYPES[stage]
        # These are installed SDK Agent fields, not invented Runner parameters.
        # A workflow owns one Lead and never runs its stages concurrently.
        agent.output_type = output_type
        agent.model_settings = replace(agent.model_settings,
            parallel_tool_calls=stage in ("dispatch", "followup"), tool_choice=None)
        message = {"role": "user", "content": json.dumps({**payload, "stage": stage}, allow_nan=False)}
        inputs = [*(self.history or []), message]
        self.event("lead_stage_started", "Lead", stage=stage, output_schema=output_type.__name__)
        try:
            try:
                output, result = await self._run(agent, inputs, self.lead_context, output_type)
            except (ModelBehaviorError, ValidationError) as error:
                raise WorkflowError("lead_output_contract_failed") from error
            if self._stage != stage or self.lead_context.stage != stage:
                raise WorkflowError("lead_stage_mismatch")
            self.history = result.to_input_list()
            self._completed_stage = stage
            self.event("lead_stage_completed", "Lead", stage=stage)
            return output
        finally:
            self._lead_running = False

    def prepared(self):
        relevance = self.relevance or RelevanceDecision(self.plan.task_description, None, "none", "Researcher B has not established a relevant index.")
        key = (relevance.domain, relevance.match_status, relevance.rationale, self.official_revision)
        if key not in self.prepared_cache:
            self.prepared_cache[key] = build_candidates(self.snapshot, relevance, self.requirements,
                workload=self.workload, shortlist_size=self.limits.shortlist_size,
                official_evidence=self.official_evidence)
        return self.prepared_cache[key]

    async def research_operations(self, context):
        """Run relevant, explicitly enabled grounded lookups separately from tools."""
        if context.tool_calls >= self.limits.max_data_calls_per_researcher:
            return self.retrieve(context, "C")
        if self.official_service is not None:
            from tools.official_specs import OFFICIAL_DOMAINS, SPEC_METRICS, SpecEvidence, SpecRequest
            metrics = {r.metric for r in self.requirements} & SPEC_METRICS
            if metrics:
                if metrics & {"context_window", "max_input_tokens", "max_output_tokens"}:
                    metrics |= {"max_input_tokens", "max_output_tokens"}
                prepared = self.prepared()
                scope = context.model_ids or (prepared["shortlists"]["fully_evaluable"] + prepared["shortlists"]["provisional"] + prepared["shortlists"]["unverified"])
                catalog = {row["id"]: row for page in self.snapshot["pages"] for row in page["data"]}
                scope = [mid for mid in scope if (catalog[mid].get("model_creator") or {}).get("name", "").casefold() in OFFICIAL_DOMAINS]
                for model_id in scope[:self.official_service.max_candidates]:
                    row = catalog[model_id]
                    request = SpecRequest(model_id, row.get("name", ""), row.get("slug", ""),
                        (row.get("model_creator") or {}).get("name", "unknown"), self.snapshot["snapshot_id"], tuple(sorted(metrics)))
                    report = await self.official_service.lookup(request)
                    self.official_reports.append(report)
                    self.official_evidence[model_id] = {metric: SpecEvidence(**data) for metric, data in report["records"].items()}
                    self.official_revision += 1
                    self.event("official_specification_review", "Researcher C", model_id=model_id,
                               verified_metrics=[k for k, v in report["records"].items() if v["verification_status"] == "verified"])
        return self.retrieve(context, "C")

    def retrieve(self, context, role, domain=None, match_status=None, rationale=None):
        if context.role != role or context.stage != "research":
            raise WorkflowError("tool_role_not_allowed")
        if context.tool_calls >= self.limits.max_data_calls_per_researcher:
            context.retrieved = False
            self.event("data_call_rejected", f"Researcher {role}", reason="data_call_limit")
            raise WorkflowError("researcher_data_call_limit")
        context.tool_calls += 1
        if role == "B":
            proposed = RelevanceDecision(self.plan.task_description, domain, match_status, rationale)
            if context.round_number and context.model_ids and self.relevance and proposed != self.relevance:
                raise WorkflowError("mapping_change_requires_full_catalog_review")
            self.relevance = proposed
        prepared = self.prepared()
        scope = context.model_ids or list(prepared["candidates"])
        models = {mid: prepared["researcher_evidence"][role][mid] for mid in scope}
        ids = {eid for result in models.values() for eid in result["evidence_ids"]}
        valid = {eid: prepared["evidence"][eid] for eid in sorted(ids) if prepared["evidence"][eid]["evidence_status"] == "observed"}
        missing = [{"model_id": item["model_id"], "missing_fields": [f for f in item["missing_fields"] if f["role"] == role]}
                   for item in prepared["missing_manifest"] if item["model_id"] in models and any(f["role"] == role for f in item["missing_fields"])]
        payload = {"role": role, "snapshot_id": prepared["snapshot_id"], "models": deepcopy(models),
                   "valid_evidence": deepcopy(valid), "missing_manifest": deepcopy(missing)}
        if role == "C":
            payload["operations"] = evaluate_operations(prepared, scope)
        self.payloads[context.context_id] = payload
        context.retrieved = True
        context.evidence_ids = set(valid)
        size = self.limits.evidence_preview_size
        preview = {"role": role, "snapshot_id": prepared["snapshot_id"], "model_count": len(models),
                   "valid_model_count": sum(m["valid"] for m in models.values()),
                   "valid_evidence": list(valid.values())[:size], "valid_evidence_count": len(valid),
                   "missing_manifest": missing[:size], "missing_model_count": len(missing),
                   "preview_limit": size, "complete_evidence_retained_server_side": True}
        if role == "C":
            preview["operations"] = dict(list(payload["operations"].items())[:size])
        context.evidence_ids = {e["evidence_id"] for e in preview["valid_evidence"]}
        self.event("evidence_retrieved", f"Researcher {role}", context_id=context.context_id,
                   role=role, model_count=len(models), snapshot_id=prepared["snapshot_id"])
        return json.dumps(preview, allow_nan=False)

    async def launch(self, role, task, model_ids):
        if not self.research_tool_enabled(role) or role in self.dispatched:
            self.event("dispatch_rejected", "Lead", role=role, reason="stage_role_or_duplicate")
            raise WorkflowError("research_dispatch_not_allowed")
        if self.researcher_count >= self.limits.max_researcher_runs:
            raise WorkflowError("researcher_run_limit")
        if self.lead_context.stage == "dispatch" and model_ids:
            raise WorkflowError("initial_round_requires_shared_catalog")
        expected = self.allowed[role]
        if expected and (task != expected.task or set(model_ids) != set(expected.model_ids)):
            raise WorkflowError("followup_scope_mismatch")
        catalog_ids = {row["id"] for page in self.snapshot["pages"] for row in page["data"]}
        if not set(model_ids) <= catalog_ids:
            raise WorkflowError("unknown_model_id")
        self.dispatched.add(role)
        self.researcher_count += 1
        context = AgentCallContext(self, role, str(uuid.uuid4()), round_number=int(self.lead_context.stage == "followup"), model_ids=sorted(set(model_ids)))
        name = f"Researcher {role} {self.researcher_count}"
        agent = self.team.researchers[role].clone(name=name)
        self.event("researcher_start", name, role=role, context_id=context.context_id,
                   parent_context_id=self.lead_context.context_id, round_number=context.round_number,
                   model_ids=context.model_ids, task=task)
        try:
            prompt = json.dumps({"task": task, "requirements": self.plan.model_dump(), "snapshot_id": self.snapshot["snapshot_id"],
                                 "target_model_ids": context.model_ids, "fresh_context": True, "research_run_id": context.context_id})
            output, _ = await self._run(agent, prompt, context, ResearcherOutput)
            if not context.retrieved or not set(output.evidence_ids) <= context.evidence_ids:
                raise WorkflowError("researcher_evidence_not_grounded")
            payload = self.payloads[context.context_id]
            previous = self.role_results.get(role)
            if previous is not None:
                replaced_eids = {eid for mid in payload["models"] if mid in previous["models"] for eid in previous["models"][mid]["evidence_ids"]}
                payload = {**payload, "models": {**previous["models"], **payload["models"]},
                           "valid_evidence": {**{eid: e for eid, e in previous["valid_evidence"].items() if eid not in replaced_eids}, **payload["valid_evidence"]},
                           "missing_manifest": [m for m in previous["missing_manifest"] if m["model_id"] not in payload["models"]] + payload["missing_manifest"]}
                if role == "C":
                    payload["operations"] = {**previous["operations"], **payload["operations"]}
            self.role_results[role] = payload
            self.errors.pop(role, None)
            self.event("researcher_end", name, role=role, context_id=context.context_id, status="completed", data_calls=context.tool_calls)
            return json.dumps({"role": role, "status": "completed", "model_count": len(payload["models"]),
                               "valid_evidence_count": len(payload["valid_evidence"]), "missing_model_count": len(payload["missing_manifest"])})
        except asyncio.CancelledError:
            self.event("researcher_end", name, role=role, context_id=context.context_id, status="cancelled")
            raise
        except Exception:
            self.errors[role] = "researcher_run_failed"
            self.event("researcher_end", name, role=role, context_id=context.context_id, status="failed", data_calls=context.tool_calls)
            return json.dumps({"role": role, "status": "failed", "error": "researcher_run_failed"})

    def review_payload(self):
        prepared = self.prepared()
        role_counts = {role: {"models": len(result["models"]), "missing_models": len(result["missing_manifest"])} for role, result in self.role_results.items()}
        reasons = sorted({f["reason"] for m in prepared["missing_manifest"] for f in m["missing_fields"] if f["required"]})
        return {"counts": prepared["counts_before_shortlist"], "role_counts": role_counts,
                "failed_roles": dict(self.errors), "relevance": prepared["relevance"],
                "snapshot_id": prepared["snapshot_id"], "catalog_complete": prepared["catalog_complete"],
                "general_index_versions": sorted({str(e["index_version"]) for e in prepared["evidence"].values() if e["index_version"] is not None}),
                "capability_index_version": "unknown unless separately verified",
                "required_gap_reasons": reasons, "unknown_specifications_retrievable": self.official_service is not None,
                "stopping_rule": "Fixed snapshot; no new source for null indices or official specifications. At most one targeted follow-up round."}

    async def _dispatch(self, stage, tasks):
        if stage == "dispatch" and tasks or stage == "followup" and (
            not tasks or tuple(t.model_dump_json() for t in tasks) != self._authorized_followups):
            raise WorkflowError("research_dispatch_not_authorized")
        if stage not in ("dispatch", "followup"):
            raise WorkflowError("research_dispatch_not_allowed")
        self.allowed = {task.role: task for task in tasks} if tasks else {role: None for role in ("A", "B", "C")}
        self.dispatched = set()
        start = len(self.batches)
        await self.lead(stage, {"plan": self.plan.model_dump(), "tasks": [t.model_dump() for t in tasks],
                                "required_roles": list(self.allowed)})
        expected = {f"research_{role.lower()}" for role in self.allowed}
        if self.dispatched != set(self.allowed) or not any(set(batch["calls"]) == expected and len(batch["calls"]) == len(expected)
                                                         for batch in self.batches[start:]):
            raise WorkflowError("researchers_not_dispatched_in_one_model_turn")

    async def _workflow(self, user_input):
        self.plan = await self.lead("parse", {"user_input": user_input, "task_weight_policy": TASK_DEFAULTS})
        questions = []
        try:
            self.requirements, self.workload, self.weights = validate_plan(self.plan, user_input)
        except ValueError as error:
            # All messages originate in local schema/input validators, not provider
            # exception bodies. Optional model suggestions cannot create requirements.
            questions = [str(error)]
        if questions:
            self.event("clarification_requested", "Lead")
            return {"status": "clarification_needed", "questions": questions,
                    "markdown": "Please clarify:\n\n" + "\n".join(f"- {q}" for q in questions)}
        self.clarification_suggestions = list(self.plan.clarification_questions)
        if self.clarification_suggestions:
            self.event("optional_clarifications_deferred", "Lead", count=len(self.clarification_suggestions))
        if self.snapshot_loader is None:
            raise WorkflowError("snapshot_loader_missing")
        try:
            self.snapshot = await self.snapshot_loader()
            self.prepared()
        except Exception:
            raise WorkflowError("snapshot_unavailable") from None
        await self._dispatch("dispatch", [])
        for round_number in range(self.limits.max_followup_rounds + 1):
            stage = "review" if round_number == 0 else "review_final"
            payload = self.review_payload()
            output = await self.lead(stage, {"evidence_review": payload})
            self.reviews.append({"stage": stage, **output.model_dump(), "audit": payload})
            tasks = getattr(output, "followups", [])
            self.event("evidence_review", "Lead", round_number=round_number,
                       followup_roles=[t.role for t in tasks])
            if not tasks:
                self.event("research_stopped", "Lead", reason="lead_review_complete")
                break
            if round_number == self.limits.max_followup_rounds:
                self.event("research_stopped", "Lead", reason="followup_round_limit")
                break
            if len({t.role for t in tasks}) != len(tasks) or len(tasks) + self.researcher_count > self.limits.max_researcher_runs or any(not t.reason.strip() or not t.task.strip() for t in tasks):
                raise WorkflowError("invalid_or_over_budget_followup")
            self._authorized_followups = tuple(t.model_dump_json() for t in tasks)
            await self._dispatch("followup", tasks)
        prepared = self.prepared()
        complete_roles = not self.errors and all(role in self.role_results and set(self.role_results[role]["models"]) == set(prepared["candidates"]) for role in ("A", "B", "C"))
        if not complete_roles:
            return {"status": "insufficient_evidence", "error": "researcher_evidence_incomplete",
                    "markdown": "No reliable recommendation is available because researcher evidence is incomplete. Retry the failed research before making a decision."}
        for role, result in self.role_results.items():
            if result["models"] != prepared["researcher_evidence"][role]:
                raise WorkflowError("researcher_evidence_conflict")
        self.event("decision_started", "Decision Tool")
        decision = decide(prepared, task_type=self.plan.task_type, user_alpha=self.plan.user_alpha.value if self.plan.user_alpha else None)
        if decision["weights"] != self.weights:
            raise WorkflowError("weight_policy_changed_during_research")
        self.event("decision_completed", "Decision Tool")
        from recommendation import render_recommendation, writer_payload, validate_writer
        payload = writer_payload(decision)
        writer_context = AgentCallContext(self, "Writer", str(uuid.uuid4()), stage="write")
        fallback = False
        try:
            intent, _ = await self._run(self.team.writer, json.dumps(payload), writer_context, WriterOutput)
            validate_writer(intent, payload)
        except Exception:
            fallback = True
            self.event("writer_rejected", "Writer", reason="invalid_or_unavailable_writer_output")
            intent = WriterOutput(candidate_ids=payload["candidate_ids"], evidence_ids=payload["evidence_ids"], validation_steps=["task_pilot", "check_index_versions"])
        return {"status": payload["status"], "decision": decision, "markdown": render_recommendation(decision, intent),
                "writer_fallback": fallback, "plan": self.plan.model_dump()}

    async def run(self, user_input: str):
        if self.started:
            raise ValueError("Create a fresh workflow per user request.")
        self.started = True
        try:
            result = await asyncio.wait_for(self._workflow(user_input), timeout=self.limits.timeout_seconds)
        except asyncio.TimeoutError:
            self.event("workflow_failed", "Lead", reason="workflow_timeout")
            result = {"status": "error", "error": "workflow_timeout",
                      "markdown": "Research reached its execution deadline. No incomplete recommendation is supplied."}
        except asyncio.CancelledError:
            self.event("workflow_cancelled", "Lead")
            raise
        except Exception as error:
            code = str(error) if isinstance(error, WorkflowError) else "agent_or_tool_execution_failed"
            self.event("workflow_failed", "Lead", reason=code)
            result = {"status": "error", "error": code, "markdown": "Research could not complete safely. Check configuration and retry; no unverified recommendation is supplied."}
        finally:
            self._closed = True
        return {**result, "trace": deepcopy(self.trace), "reviews": deepcopy(self.reviews),
                "researcher_runs": self.researcher_count, "researcher_results": deepcopy(self.role_results),
                "official_specifications": deepcopy(self.official_reports),
                "clarification_suggestions": list(self.clarification_suggestions)}
