"""Exercise LiteLLM's public validation gate without contacting a provider."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from agents import AgentOutputSchema
from agents.models.chatcmpl_converter import Converter
from litellm import UnsupportedParamsError, BadRequestError
from litellm.utils import get_optional_params

from modelmatch_schemas import ParsedPlan
from tools.run_diagnostics import failure_details
from vertex_runtime import safe_error


class LeadLowCompatibilityTests(unittest.TestCase):
    def validate(self, **overrides):
        params = dict(model="gemini-3.5-flash", custom_llm_provider="vertex_ai",
                      reasoning_effort="low", max_tokens=2048,
                      response_format=Converter.convert_response_format(AgentOutputSchema(ParsedPlan)))
        with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \
             patch("socket.getaddrinfo", side_effect=AssertionError("Network forbidden")):
            return get_optional_params(**{**params, **overrides})

    def test_public_validator_reproduces_the_production_adapter_rejection(self):
        with self.assertRaises(UnsupportedParamsError) as caught:
            self.validate()
        self.assertEqual(safe_error(caught.exception)["category"], "adapter_rejection")
        self.assertEqual(failure_details(caught.exception)["category"], "adapter_rejection")
        self.assertNotIn("reasoning_effort", str(safe_error(caught.exception)))

    def test_public_validator_accepts_low_without_dropping_strict_json(self):
        result = self.validate(allowed_openai_params=["reasoning_effort"])
        self.assertEqual(result["thinkingConfig"]["thinkingLevel"], "low")
        self.assertEqual(result["max_output_tokens"], 2048)
        self.assertEqual(result["response_mime_type"], "application/json")
        schema = result["response_json_schema"]
        self.assertEqual(schema["required"], AgentOutputSchema(ParsedPlan).json_schema()["required"])
        self.assertEqual(len(schema["required"]), 8)
        self.assertFalse(schema["additionalProperties"])

    def test_permission_does_not_disable_other_parameter_validation(self):
        with self.assertRaises(UnsupportedParamsError):
            self.validate(allowed_openai_params=["reasoning_effort"], logit_bias={"0": 1})

    def test_provider_bad_request_is_not_adapter_rejection(self):
        error = BadRequestError(message="Synthetic private provider body", model="gemini-3.5-flash",
                                llm_provider="vertex_ai")
        self.assertEqual(safe_error(error)["category"], "invalid_request_or_unsupported_combination")
        self.assertEqual(failure_details(error)["category"], "provider_error")
        self.assertNotIn("private", str(failure_details(error)))

    def test_wrapped_adapter_error_preserves_the_cause_chain(self):
        try:
            self.validate()
        except UnsupportedParamsError as cause:
            error = RuntimeError("Synthetic wrapper")
            error.__cause__ = cause
        details = failure_details(error)
        self.assertEqual(details["category"], "adapter_rejection")
        self.assertEqual(details["exception_type"], "UnsupportedParamsError")
        self.assertEqual(len(details["cause_chain"]), 2)
