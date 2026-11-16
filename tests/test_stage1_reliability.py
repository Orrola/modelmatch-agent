"""Offline regressions for verified timeout, stage and safe-output defects."""

import asyncio
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from agents import ModelSettings
from agents.usage import Usage
from agents.agent_output import AgentOutputSchema
from modelmatch_agents import create_team
from modelmatch_schemas import ParsedPlan

from modelmatch_schemas import OrchestrationLimits
from orchestration import ModelMatchWorkflow
from tests.fake_modelmatch import ScriptedModel, USER_INPUT, default_plan
from tools.artificial_analysis import load_mock_snapshot
from tools.run_diagnostics import (ModelRequestTimeout, failure_details, inspect_lead_output)
from vertex_runtime import PROVIDER_METADATA, CallBudget, MeteredModel, VertexConfig


def public_response(text, finish_reason=None):
    return SimpleNamespace(finish_reason=finish_reason,
        output=[SimpleNamespace(type="reasoning", text="SIMULATED_PRIVATE_REASONING"),
                SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text=text)])])


class SafeOutputTests(unittest.TestCase):
    def test_live_defaults_and_eight_field_contract_remain_unchanged(self):
        config = VertexConfig("synthetic-project")
        team = create_team(ScriptedModel(), ScriptedModel(), config.settings())
        self.assertEqual(config.model, "gemini-3.5-flash")
        self.assertEqual(team.lead.model_settings.max_tokens, 2048)
        self.assertIsNone(team.lead.model_settings.reasoning)
        self.assertEqual(config.timeout_seconds, 30)
        schema = AgentOutputSchema(ParsedPlan).json_schema()
        self.assertEqual(len(schema["required"]), 8)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(ParsedPlan.model_fields))

    def test_low_thinking_candidate_maps_offline_without_changing_runtime_defaults(self):
        from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import VertexGeminiConfig
        mapped = VertexGeminiConfig._map_reasoning_effort_to_thinking_level("low", "gemini-3.5-flash")
        self.assertEqual(mapped["thinkingLevel"], "low")
        self.assertIsNone(VertexConfig("synthetic-project").settings().reasoning)

    def test_malformed_json_is_distinct_from_schema_failure(self):
        syntax = inspect_lead_output(public_response('{"task_quote": '), "stop")
        schema = inspect_lead_output(public_response('{}'), "stop")
        self.assertEqual(syntax["failure_category"], "malformed_json")
        self.assertIn("json_offset", syntax)
        self.assertEqual(schema["failure_category"], "schema_validation_error")
        self.assertIn("task_type", schema["missing_contract_fields"])
        self.assertTrue(schema["schema_errors"])

    def test_length_termination_retains_the_underlying_validation_category(self):
        diagnostic = inspect_lead_output(public_response('{"task_quote": '), "length")
        self.assertEqual(diagnostic["failure_category"], "incomplete_generation")
        self.assertEqual(diagnostic["validation_category"], "malformed_json")
        self.assertEqual(diagnostic["finish_reason"], "length")

    def test_valid_output_is_not_rejected_only_because_of_a_length_finish(self):
        diagnostic = inspect_lead_output(public_response(default_plan().model_dump_json()), "length")
        self.assertEqual(diagnostic["validation_category"], "valid")
        self.assertIsNone(diagnostic["failure_category"])

    def test_fences_are_observed_and_never_removed_or_repaired(self):
        diagnostic = inspect_lead_output(public_response('```json\n{}\n```'), "stop")
        self.assertTrue(diagnostic["markdown_fence_present"])
        self.assertEqual(diagnostic["validation_category"], "malformed_json")

    def test_missing_finish_reason_does_not_invent_truncation(self):
        diagnostic = inspect_lead_output(public_response('{'), None)
        self.assertEqual(diagnostic["generation_status"], "unknown")
        self.assertEqual(diagnostic["failure_category"], "malformed_json")

    def test_schema_paths_and_syntax_diagnostics_never_include_response_values(self):
        plan = default_plan().model_dump()
        plan["SIMULATED_PRIVATE_FIELD"] = "SIMULATED_PRIVATE_VALUE"
        diagnostic = inspect_lead_output(public_response(json.dumps(plan)), "stop")
        serialized = json.dumps(diagnostic)
        for private in ("SIMULATED_PRIVATE_FIELD", "SIMULATED_PRIVATE_VALUE", "SIMULATED_PRIVATE_REASONING"):
            self.assertNotIn(private, serialized)
        self.assertIn("[field]", serialized)

    def test_provider_refusal_is_not_guessed_to_be_a_json_formatting_fault(self):
        response = SimpleNamespace(output=[SimpleNamespace(type="message", content=[SimpleNamespace(type="refusal", refusal="SIMULATED_PRIVATE_REFUSAL")])])
        diagnostic = inspect_lead_output(response, "content_filter")
        self.assertEqual(diagnostic["failure_category"], "provider_error")
        self.assertTrue(diagnostic["refusal_present"])
        self.assertNotIn("SIMULATED_PRIVATE_REFUSAL", json.dumps(diagnostic))

    def test_outer_timeout_is_principal_and_cancellation_cause_remains_visible(self):
        timeout = TimeoutError("SIMULATED_PRIVATE_TIMEOUT")
        timeout.__cause__ = asyncio.CancelledError("SIMULATED_PRIVATE_CANCELLATION")
        result = failure_details(timeout)
        self.assertEqual(result["category"], "timeout")
        self.assertEqual(result["exception_type"], "TimeoutError")
        self.assertEqual([e["exception_type"] for e in result["cause_chain"]], ["TimeoutError", "CancelledError"])
        self.assertNotIn("SIMULATED_PRIVATE", json.dumps(result))

    def test_actual_cancellation_is_not_overridden_by_its_cause(self):
        cancellation = asyncio.CancelledError()
        cancellation.__cause__ = TimeoutError()
        self.assertEqual(failure_details(cancellation)["category"], "cancelled")

    def test_cyclic_exception_chains_are_bounded(self):
        error = RuntimeError()
        error.__cause__ = error
        self.assertEqual(len(failure_details(error)["cause_chain"]), 1)

    def test_verified_provider_status_is_not_overridden_by_an_older_timeout(self):
        class ProviderError(RuntimeError):
            status_code = 429
        error = ProviderError()
        error.__cause__ = TimeoutError()
        result = failure_details(error)
        self.assertEqual(result["category"], "quota_or_rate_limit")
        self.assertEqual(result["status_code"], 429)


class StageOneWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def workflow(self, model, timeout=10):
        snapshot = load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        self.loader = AsyncMock(return_value=snapshot)
        return ModelMatchWorkflow(model, model, snapshot_loader=self.loader,
                                  limits=OrchestrationLimits(timeout_seconds=timeout))

    async def test_single_request_deadline_is_not_a_workflow_deadline(self):
        async def slow(*args, **kwargs):
            await asyncio.Event().wait()
        budget = CallBudget()
        model = MeteredModel(SimpleNamespace(get_response=slow), "gemini-synthetic", budget,
                             VertexConfig("synthetic-project", timeout_seconds=.01))
        result = await self.workflow(model).run(USER_INPUT)
        self.assertEqual(result["error"], "model_request_timeout")
        self.assertNotEqual(result["error"], "workflow_timeout")
        failure = result["diagnostics"]["blocking_failure"]["error"]
        self.assertEqual(failure["category"], "timeout")
        self.assertEqual(failure["exception_type"], "TimeoutError")
        self.assertIn("CancelledError", [e["exception_type"] for e in failure["cause_chain"]])
        self.assertEqual(budget.calls, 1)
        self.loader.assert_not_awaited()

    async def test_unwrapped_sdk_timeout_is_also_scoped_to_the_model_call(self):
        class TimeoutModel(ScriptedModel):
            async def get_response(self, *args, **kwargs):
                raise TimeoutError("SIMULATED_PRIVATE_PROVIDER_ERROR")
        result = await self.workflow(TimeoutModel()).run(USER_INPUT)
        self.assertEqual(result["error"], "model_request_timeout")
        self.assertNotIn("SIMULATED_PRIVATE", json.dumps(result))

    async def test_total_workflow_deadline_remains_distinct(self):
        class WaitingModel(ScriptedModel):
            async def get_response(self, *args, **kwargs):
                await asyncio.Event().wait()
        result = await self.workflow(WaitingModel(), timeout=.01).run(USER_INPUT)
        self.assertEqual(result["error"], "workflow_timeout")
        self.assertNotEqual(result["error"], "model_request_timeout")
        self.assertEqual(result["diagnostics"]["blocking_failure"]["error"]["category"], "timeout")
        self.assertEqual(result["diagnostics"]["blocking_failure"]["error"]["exception_type"], "TimeoutError")

    async def test_user_cancellation_propagates_without_becoming_a_timeout(self):
        entered = asyncio.Event()
        class WaitingModel(ScriptedModel):
            async def get_response(self, *args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
        workflow = self.workflow(WaitingModel())
        task = asyncio.create_task(workflow.run(USER_INPUT))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(workflow.diagnostics.states["parse"]["status"], "cancelled")

    async def test_parse_failure_retains_finish_usage_and_syntax_without_raw_text(self):
        class IncompleteModel(ScriptedModel):
            async def get_response(self, *args, **kwargs):
                response = self.text({})
                response.output[0].content[0].text = '{"task_description":"SIMULATED_PRIVATE_INPUT"'
                return response
        # A small wrapper supplies explicit synthetic finish metadata, not a live result.
        class ObservedIncomplete(IncompleteModel):
            async def get_response(self, *args, **kwargs):
                response = await super().get_response(*args, **kwargs)
                response.usage = Usage(input_tokens=10, output_tokens=20)
                PROVIDER_METADATA.get().update(finish_reason="length", reasoning_tokens=8)
                return response
        budget = CallBudget()
        model = MeteredModel(ObservedIncomplete(), "gemini-synthetic", budget, VertexConfig("synthetic-project"))
        result = await self.workflow(model).run(USER_INPUT)
        self.assertEqual(result["error"], "lead_output_contract_failed")
        error = result["diagnostics"]["blocking_failure"]["error"]
        self.assertEqual(error["category"], "incomplete_generation")
        self.assertEqual(error["output_diagnostics"]["validation_category"], "malformed_json")
        self.assertEqual(budget.records[0]["finish_reason"], "length")
        self.assertEqual(budget.records[0]["usage"]["output_tokens"], 20)
        self.assertEqual(budget.records[0]["reasoning_tokens"], 8)
        self.assertNotIn("SIMULATED_PRIVATE_INPUT", json.dumps(result) + json.dumps(budget.records))
        self.assertEqual(budget.calls, 1)
        self.loader.assert_not_awaited()

    async def test_provider_error_is_not_relabelled_as_malformed_output(self):
        class ProviderError(RuntimeError):
            status_code = 503
        model = MeteredModel(SimpleNamespace(get_response=AsyncMock(side_effect=ProviderError("SIMULATED_PRIVATE"))),
                             "gemini-synthetic", CallBudget(), VertexConfig("synthetic-project"))
        result = await self.workflow(model).run(USER_INPUT)
        failure = result["diagnostics"]["first_failure"]["error"]
        self.assertEqual(failure["category"], "provider_error")
        self.assertNotIn("output_diagnostics", failure)
