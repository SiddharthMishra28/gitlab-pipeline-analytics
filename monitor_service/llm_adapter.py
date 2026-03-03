import hashlib
import json
import re
import threading
from dataclasses import dataclass

from monitor_service.metrics import llm_calls_total, llm_errors_total

SYSTEM_PROMPT = """You are an expert SDET assistant. Given a job log excerpt, classify the root cause into one of these categories:
FLAKINESS, ASSERTION_ERROR, RUNTIME_EXCEPTION, ENVIRONMENT_ERROR, TIMEOUT, ARTIFACT_MISSING, CONFIG_ERROR, NETWORK_ERROR, OTHER.

Return a JSON object only (no extra commentary) with keys:
- failureCategory: one of the categories above
- suggestedFix: a short actionable fix (1-2 sentences)
- confidence: number between 0 and 1
- tags: array of short tag strings (optional)
- evidence: up to 300 characters pulled verbatim from the log that justify the classification"""

USER_TEMPLATE = """flowExecutionUuid: {flowExecutionUuid}
pipelineId: {pipelineId}
jobObserveId: {jobObserveId}

Log excerpt (bounded to N tokens): 
{log_excerpt}

Constraints:
- Use the smallest explanation possible.
- If uncertain, set failureCategory to OTHER and include why in suggestedFix.
- Make suggestedFix actionable and precise."""


class BaseProvider:
    def complete_json(self, system_prompt: str, user_prompt: str, token_budget: int) -> str:
        raise NotImplementedError


class HeuristicProvider(BaseProvider):
    def complete_json(self, system_prompt: str, user_prompt: str, token_budget: int) -> str:
        lowered = user_prompt.lower()
        category = "OTHER"
        fix = "Review the log evidence and rerun with debug output."
        if "traceback" in lowered or "exception" in lowered:
            category = "RUNTIME_EXCEPTION"
            fix = "Inspect the stack trace and patch the failing code path or dependency versions."
        elif "assert" in lowered:
            category = "ASSERTION_ERROR"
            fix = "Update the assertion or test fixture to match expected behavior."
        elif "timeout" in lowered:
            category = "TIMEOUT"
            fix = "Increase timeout and optimize slow setup/network calls."
        return json.dumps(
            {
                "failureCategory": category,
                "suggestedFix": fix,
                "confidence": 0.7,
                "tags": ["heuristic"],
                "evidence": user_prompt[-300:],
            }
        )


@dataclass
class ClassificationResult:
    failure_category: str
    suggested_fix: str
    confidence: float
    llm_metadata: dict


class LLMAdapter:
    def __init__(self, provider: BaseProvider | None = None, max_concurrent: int = 2, token_budget: int = 1024):
        self.provider = provider or HeuristicProvider()
        self.token_budget = token_budget
        self.sem = threading.BoundedSemaphore(value=max_concurrent)

    def _truncate_excerpt(self, text: str) -> str:
        return text[: self.token_budget * 4]

    def _extract_json(self, raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def classify(self, excerpt: str, meta: dict) -> ClassificationResult:
        short_excerpt = self._truncate_excerpt(excerpt)
        user_prompt = USER_TEMPLATE.format(log_excerpt=short_excerpt, **meta)
        prompt_checksum = "sha256:" + hashlib.sha256(user_prompt.encode()).hexdigest()

        with self.sem:
            for attempt in range(3):
                llm_calls_total.inc()
                raw = self.provider.complete_json(SYSTEM_PROMPT, user_prompt, self.token_budget)
                try:
                    parsed = self._extract_json(raw)
                    category = parsed["failureCategory"]
                    suggested = parsed["suggestedFix"]
                    confidence = float(parsed.get("confidence", 0))
                    if not 0 <= confidence <= 1:
                        raise ValueError("confidence out of bounds")
                    return ClassificationResult(
                        failure_category=category,
                        suggested_fix=suggested,
                        confidence=confidence,
                        llm_metadata={
                            "model": self.provider.__class__.__name__,
                            "tokensUsed": min(len(user_prompt) // 4, self.token_budget),
                            "promptChecksum": prompt_checksum,
                            "attempt": attempt + 1,
                        },
                    )
                except Exception:
                    llm_errors_total.inc()
                    user_prompt = user_prompt + "\nReturn valid JSON only."
            raise ValueError("LLM failed to return valid JSON")
