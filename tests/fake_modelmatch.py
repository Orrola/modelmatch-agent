"""Scripted Model implementation for the REAL Agents SDK Runner, without a provider."""

import asyncio
import json
import uuid

from agents import Model, Runner
from agents.items import ModelResponse
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from modelmatch_schemas import (
    DispatchComplete, FinalReview, ParsedPlan, ResearcherOutput, Review, WriterOutput,
)

USER_INPUT = "Analyze financial documents for a finance team."


def default_plan():
    return ParsedPlan(industry="finance", task_description="Analyze financial documents",
                      task_quote="Analyze financial documents", task_type="specialized_domain")


class CapturingRunner:
    def __init__(self):
        self.calls = []

    async def run(self, agent, inputs, **kwargs):
        self.calls.append({"agent": agent, "input": inputs, "context": kwargs["context"],
                           "stage": kwargs["context"].stage, "output_type": agent.output_type})
        return await Runner.run(agent, inputs, **kwargs)


class ScriptedModel(Model):
    def __init__(self, *, plan=None, followups=(), repeat_followups=False, barrier=True,
                 domain="finance", match_status="strong", fail_roles=(), fail_once_roles=(),
                 writer_tamper=False, duplicate_dispatch=False, sequential_dispatch=False,
                 data_call_count=1, skip_data=False):
        self.plan = plan or default_plan()
        self.followups = list(followups)
        self.repeat_followups = repeat_followups
        self.barrier_enabled = barrier
        self.barrier = asyncio.Event()
        self.initial_roles_started = set()
        self.counts = {}
        self.domain, self.match_status = domain, match_status
        self.fail_roles, self.fail_once_roles = set(fail_roles), set(fail_once_roles)
        self.failed = set()
        self.writer_tamper = writer_tamper
        self.duplicate_dispatch, self.sequential_dispatch = duplicate_dispatch, sequential_dispatch
        self.data_call_count = data_call_count
        self.skip_data = skip_data
        self.model_requests = []

    def stream_response(self, *args, **kwargs):
        raise NotImplementedError("Offline tests use non-streaming SDK calls.")

    def response(self, output):
        return ModelResponse(output=output, usage=Usage(), response_id=str(uuid.uuid4()))

    def text(self, value):
        text = value.model_dump_json() if hasattr(value, "model_dump_json") else json.dumps(value)
        return self.response([ResponseOutputMessage(id=str(uuid.uuid4()), type="message", role="assistant", status="completed",
            content=[ResponseOutputText(type="output_text", text=text, annotations=[])])])

    def tools(self, calls):
        return self.response([ResponseFunctionToolCall(type="function_call", name=name, arguments=json.dumps(args),
                            call_id=str(uuid.uuid4()), id=str(uuid.uuid4())) for name, args in calls])

    @staticmethod
    def payload(inputs):
        if isinstance(inputs, str):
            return json.loads(inputs)
        for item in reversed(inputs):
            if item.get("role") == "user":
                content = item["content"]
                if isinstance(content, list):
                    content = "".join(part.get("text", "") for part in content)
                return json.loads(content)
        raise AssertionError("The SDK did not provide the expected user stage payload.")

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, **kwargs):
        payload = self.payload(input)
        self.model_requests.append({"payload": payload, "tools": [t.name for t in tools],
                                    "schema_name": output_schema.name() if output_schema else None,
                                    "schema": output_schema.json_schema() if output_schema else None,
                                    "parallel_tool_calls": model_settings.parallel_tool_calls})
        if "ModelMatch AI's Lead" in system_instructions:
            stage = payload["stage"]
            key = ("Lead", stage)
            count = self.counts.get(key, 0)
            self.counts[key] = count + 1
            if stage == "parse":
                return self.text(self.plan)
            if stage in ("dispatch", "followup"):
                tasks = payload["tasks"] or [{"role": role, "task": f"Inspect role {role} evidence", "model_ids": []} for role in ("A", "B", "C")]
                if self.sequential_dispatch and stage == "dispatch" and count < len(tasks):
                    task = tasks[count]
                    return self.tools([(f"research_{task['role'].lower()}", {"task": task["task"], "model_ids": task["model_ids"]})])
                if count == 0:
                    calls = [(f"research_{task['role'].lower()}", {"task": task["task"], "model_ids": task["model_ids"]}) for task in tasks]
                    if self.duplicate_dispatch:
                        calls.append(calls[0])
                    return self.tools(calls)
                return self.text(DispatchComplete(completed=True))
            followups = self.followups if stage == "review" or self.repeat_followups else []
            if stage == "review_final" and not self.repeat_followups:
                return self.text(FinalReview(summary="Reviewed remaining canonical gaps.", stopping_reason="The targeted follow-up round is complete."))
            return self.text(Review(summary="Reviewed canonical gaps, versions and relevance.",
                followups=followups, stopping_reason="Stop after sufficient evidence or the configured follow-up cap."))
        if "Select an evidence-grounded recommendation" in system_instructions:
            output = WriterOutput(candidate_ids=payload["candidate_ids"], evidence_ids=payload["evidence_ids"],
                                  validation_steps=["task_pilot", "check_index_versions"])
            if self.writer_tamper:
                value = output.model_dump()
                value["candidate_ids"] = ["invented-model"]
                return self.text(value)
            return self.text(output)
        role = "A" if "Retrieve original General Intelligence" in system_instructions else "B" if "Map the concrete task" in system_instructions else "C"
        key = (role, payload["research_run_id"])
        count = self.counts.get(key, 0)
        self.counts[key] = count + 1
        if count == 0:
            if role not in self.initial_roles_started:
                self.initial_roles_started.add(role)
                if len(self.initial_roles_started) == 3:
                    self.barrier.set()
                if self.barrier_enabled:
                    await self.barrier.wait()
            if role in self.fail_roles or (role in self.fail_once_roles and role not in self.failed):
                self.failed.add(role)
                raise RuntimeError("SIMULATED_SECRET_MUST_NOT_ESCAPE")
            if not self.skip_data:
                name = {"A": "get_general_evidence", "B": "get_domain_evidence", "C": "get_operational_evidence"}[role]
                args = {"domain": self.domain, "match_status": self.match_status,
                        "rationale": "Explicit synthetic task mapping for offline orchestration tests."} if role == "B" else {}
                return self.tools([(name, args)] * self.data_call_count)
        return self.text(ResearcherOutput(evidence_ids=[], observations=["evidence_available"]))
