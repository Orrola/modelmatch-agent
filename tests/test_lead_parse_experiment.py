"""LOW is parse-only; live experiment entry points require explicit authorization."""

import asyncio
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from agents import ModelSettings
from openai.types.shared import Reasoning
from modelmatch_web import WebInput
from orchestration import ModelMatchWorkflow
from modelmatch_schemas import OrchestrationLimits
from scripts import lead_parse_experiment as experiment
from tests.fake_modelmatch import ScriptedModel, USER_INPUT
from tools.artificial_analysis import load_mock_snapshot
from vertex_runtime import MeteredModel, VertexConfig


class RecordingModel(ScriptedModel):
    def __init__(self, failure=None):
        super().__init__()
        self.settings_seen = []
        self.failure = failure
        self.entered = asyncio.Event()

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, *args, **kwargs):
        payload = self.payload(input)
        self.settings_seen.append({"stage": payload.get("stage", "research_or_writer"),
            "reasoning": getattr(model_settings.reasoning, "effort", None), "max_tokens": model_settings.max_tokens,
            "extra_args": model_settings.extra_args,
            "tools": [tool.name for tool in tools]})
        if payload.get("stage") == "parse":
            self.entered.set()
            if self.failure == "schema":
                return self.text({})
            if self.failure == "timeout":
                raise TimeoutError("Synthetic timeout")
            if self.failure == "wait":
                await asyncio.Event().wait()
        return await super().get_response(system_instructions, input, model_settings, tools, output_schema, *args, **kwargs)


class ParseIsolationTests(unittest.IsolatedAsyncioTestCase):
    def workflow(self, model, settings=None):
        snapshot = load_mock_snapshot(Path(__file__).parent / "fixtures/phase2a_synthetic.json")
        return ModelMatchWorkflow(model, model, settings=settings or ModelSettings(max_tokens=2048),
            snapshot_loader=AsyncMock(return_value=snapshot), limits=OrchestrationLimits(timeout_seconds=10))

    async def test_only_parse_uses_low_and_restores_the_same_lead_settings(self):
        model = RecordingModel()
        workflow = self.workflow(model)
        lead = workflow.team.lead
        original = lead.model_settings
        result = await workflow.run(USER_INPUT)
        self.assertFalse(result["writer_fallback"])
        self.assertIs(workflow.team.lead, lead)
        self.assertIs(lead.model_settings, original)
        self.assertTrue(all(r["reasoning"] == ("low" if r["stage"] == "parse" else None) for r in model.settings_seen))
        parse = next(r for r in model.settings_seen if r["stage"] == "parse")
        self.assertEqual(parse["max_tokens"], 2048)
        self.assertEqual(parse["tools"], [])
        self.assertEqual(parse["extra_args"]["allowed_openai_params"], ["reasoning_effort"])
        self.assertTrue(all(not (r["extra_args"] or {}).get("allowed_openai_params")
                            for r in model.settings_seen if r["stage"] != "parse"))

    async def test_parse_permission_preserves_existing_settings_without_mutation(self):
        model = RecordingModel()
        extra_args = {"allowed_openai_params": ["seed"], "timeout": 30, "num_retries": 0}
        workflow = self.workflow(model, ModelSettings(max_tokens=2048, extra_args=extra_args))
        original = workflow.team.lead.model_settings
        await workflow.run(USER_INPUT)
        self.assertIs(workflow.team.lead.model_settings, original)
        self.assertEqual(extra_args["allowed_openai_params"], ["seed"])
        for record in model.settings_seen:
            self.assertEqual(record["extra_args"]["allowed_openai_params"],
                             ["seed", "reasoning_effort"] if record["stage"] == "parse" else ["seed"])
            self.assertEqual(record["extra_args"]["timeout"], 30)
            self.assertEqual(record["extra_args"]["num_retries"], 0)

    async def test_existing_non_parse_reasoning_configuration_is_preserved(self):
        model = RecordingModel()
        workflow = self.workflow(model, ModelSettings(max_tokens=2048, reasoning=Reasoning(effort="high")))
        await workflow.run(USER_INPUT)
        self.assertTrue(all(r["reasoning"] == ("low" if r["stage"] == "parse" else "high") for r in model.settings_seen))

    async def test_schema_and_timeout_failures_restore_settings(self):
        for failure, code in (("schema", "lead_output_contract_failed"), ("timeout", "model_request_timeout")):
            model = RecordingModel(failure)
            workflow = self.workflow(model)
            original = workflow.team.lead.model_settings
            result = await workflow.run(USER_INPUT)
            self.assertEqual(result["error"], code)
            self.assertIs(workflow.team.lead.model_settings, original)
            self.assertIsNone(workflow.team.lead.model_settings.reasoning)

    async def test_cancellation_restores_settings(self):
        model = RecordingModel("wait")
        workflow = self.workflow(model)
        original = workflow.team.lead.model_settings
        task = asyncio.create_task(workflow.run(USER_INPUT))
        await model.entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIs(workflow.team.lead.model_settings, original)

    async def test_controlled_case_uses_one_generation_and_no_pipeline_or_aa(self):
        model = RecordingModel()
        def factory(config, budget):
            metered = MeteredModel(model, config.model, budget, config)
            return metered, metered
        row = {"case_id": "financial", "request": {"question": USER_INPUT}, "baseline": None}
        with patch("tools.artificial_analysis.ArtificialAnalysisClient.fetch_snapshot", new_callable=AsyncMock) as aa, \
             patch.object(ModelMatchWorkflow, "_workflow", new_callable=AsyncMock) as pipeline:
            result = await experiment.run_case(row, VertexConfig("synthetic-project"), model_factory=factory)
        aa.assert_not_awaited()
        pipeline.assert_not_awaited()
        self.assertEqual(result["model_requests"], 1)
        self.assertTrue(result["schema_accepted"])
        self.assertTrue(result["business_validation_passed"])
        self.assertEqual(result["extraction_correctness"]["status"], "manual_review_required")
        self.assertEqual(result["model_records"][0]["settings"]["reasoning_effort"], "low")
        self.assertEqual(result["model_records"][0]["settings"]["max_output_tokens"], 2048)

    async def test_batch_stops_at_first_failed_case_without_retry(self):
        failed = {"schema_accepted": False, "business_validation_passed": False, "extraction_correctness": {"status": "not_evaluated"}, "model_requests": 1}
        with patch.object(experiment, "run_case", new_callable=AsyncMock, return_value=failed) as run:
            result = await experiment.run_cases([{"case_id": "financial"}, {"case_id": "coding"}], VertexConfig("synthetic-project"))
        run.assert_awaited_once()
        self.assertEqual(result["model_requests"], 1)
        self.assertEqual(result["stopping_reason"], "first_failed_case")

    async def test_budget_and_model_changes_are_rejected_before_calls(self):
        with patch.object(experiment, "run_case", new_callable=AsyncMock) as run:
            for config in (VertexConfig("synthetic-project", max_output_tokens=4096),
                           VertexConfig("synthetic-project", timeout_seconds=60),
                           VertexConfig("synthetic-project", model="gemini-other")):
                with self.assertRaises(ValueError):
                    await experiment.run_cases([{"case_id": "financial"}], config)
        run.assert_not_awaited()


class ExperimentPreflightTests(unittest.TestCase):
    def manifest(self):
        rows = []
        for case_id in sorted(experiment.CASE_IDS):
            question = ("\u200b\u200b" if case_id == "customer_support" else "") + USER_INPUT
            digest = hashlib.sha256(question.encode()).hexdigest()
            rows.append({"case_id": case_id, "request": {"question": question}, "provenance": "Synthetic offline test input, not historical production evidence.",
                         "expected_input_hash": digest, "baseline": {"input_hash": digest, "model": "gemini-3.5-flash", "max_output_tokens": 2048, "timeout_seconds": 30}})
        return {"cases": rows}

    def test_preflight_never_constructs_models_or_loads_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(self.manifest()))
            with patch.object(experiment, "create_models") as models, patch.object(experiment.VertexConfig, "from_environment") as config, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(experiment.main(["--manifest", str(path)]), 0)
            models.assert_not_called()
            config.assert_not_called()

    def test_live_flag_alone_cannot_authorize_billable_calls(self):
        with patch.object(experiment, "create_models") as models, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            experiment.main(["--manifest", "missing-original-input.json", "--live"])
        models.assert_not_called()

    def test_original_input_hash_is_enforced_including_invisible_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            manifest = self.manifest()
            path.write_text(json.dumps(manifest))
            rows = experiment.load_cases(path)
            support = next(r for r in rows if r["case_id"] == "customer_support")
            self.assertTrue(support["request"]["question"].startswith("\u200b\u200b"))
            support["request"]["question"] = support["request"]["question"].lstrip("\u200b")
            path.write_text(json.dumps({"cases": rows}))
            with self.assertRaises(ValueError):
                experiment.load_cases(path)

    def test_mismatched_historical_baseline_is_not_silently_compared(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            manifest = self.manifest()
            manifest["cases"][0]["baseline"]["input_hash"] = "0" * 64
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                experiment.load_cases(path)

    def test_unknown_baseline_metrics_remain_unknown(self):
        result = experiment.baseline_comparison({"baseline": {"reasoning_tokens": None}}, {"reasoning_tokens": 10})
        self.assertIsNone(result["deltas"]["reasoning_tokens"])

    def test_semantic_correctness_is_not_implied_by_schema_acceptance(self):
        from tests.fake_modelmatch import default_plan
        plan = default_plan()
        self.assertEqual(experiment.extraction_checks(plan, None)["status"], "manual_review_required")
        result = experiment.extraction_checks(plan, {"task_type": "tool_agent", "industry_terms": ["finance"]})
        self.assertEqual(result["status"], "failed")
