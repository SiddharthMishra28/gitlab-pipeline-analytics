import json

from monitor_service.llm_adapter import BaseProvider, LLMAdapter


class FakeProvider(BaseProvider):
    def complete_json(self, system_prompt: str, user_prompt: str, token_budget: int) -> str:
        return json.dumps(
            {
                "failureCategory": "RUNTIME_EXCEPTION",
                "suggestedFix": "Refresh token",
                "confidence": 0.9,
                "tags": ["auth"],
                "evidence": "Traceback",
            }
        )


def test_classify_parses_json():
    adapter = LLMAdapter(provider=FakeProvider(), max_concurrent=1, token_budget=100)
    out = adapter.classify("Traceback ...", {"flowExecutionUuid": "u", "pipelineId": 1, "jobObserveId": 2})
    assert out.failure_category == "RUNTIME_EXCEPTION"
    assert out.confidence == 0.9
