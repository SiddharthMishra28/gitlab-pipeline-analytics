import logging
import threading
import time
from datetime import datetime, timezone

import requests

LOGGER = logging.getLogger(__name__)


class WorkerPool:
    def __init__(
        self,
        worker_count: int,
        queue,
        locker,
        gitlab_client,
        llm_adapter,
        db,
        poll_interval: float = 0.5,
        max_log_chunk_size: int = 4000,
    ):
        self.worker_count = worker_count
        self.queue = queue
        self.locker = locker
        self.gitlab_client = gitlab_client
        self.llm_adapter = llm_adapter
        self.db = db
        self.poll_interval = poll_interval
        self.max_log_chunk_size = max_log_chunk_size
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self):
        for i in range(self.worker_count):
            t = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            t.start()
            self._threads.append(t)

    def shutdown(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2)

    def _extract_relevant_excerpt(self, text: str) -> str:
        lines = text.splitlines()
        err = [
            ln
            for ln in lines
            if any(k in ln.lower() for k in ["error", "exception", "traceback", "failed", "timeout"])
        ]
        chosen = err[-40:] if err else lines[-40:]
        excerpt = "\n".join(chosen)
        return excerpt[-self.max_log_chunk_size :]

    def _notify_callback(self, payload: dict, result: dict):
        cb = payload.get("callbacks", {}).get("onComplete")
        if cb and cb.startswith("https://"):
            try:
                requests.post(cb, json=result, timeout=5)
            except Exception:
                LOGGER.warning("callback_failed", extra={"flowExecutionUuid": payload.get("flowExecutionUuid")})

    def _worker_loop(self, worker_id: int):
        while not self._stop.is_set():
            try:
                payload = self.queue.get(timeout=0.5)
            except Exception:
                continue
            key = payload["flowExecutionUuid"]
            if not self.locker.claim(key):
                self.queue.task_done()
                continue
            try:
                self._process(payload, worker_id)
            finally:
                self.locker.release(key)
                self.queue.task_done()

    def _process(self, payload: dict, worker_id: int):
        offset = 0
        collected = ""
        job_id = payload["jobObserveId"]

        while not self._stop.is_set():
            status = self.gitlab_client.get_job_status(job_id)
            tail = self.gitlab_client.tail_trace(job_id, offset)
            offset = tail.new_offset
            collected += tail.chunk
            if len(collected) > self.max_log_chunk_size * 3:
                collected = collected[-self.max_log_chunk_size * 3 :]

            if status in {"success", "failed", "canceled"}:
                break
            time.sleep(self.poll_interval)

        if status == "failed":
            excerpt = self._extract_relevant_excerpt(collected)
            cls = self.llm_adapter.classify(
                excerpt,
                {
                    "flowExecutionUuid": payload["flowExecutionUuid"],
                    "pipelineId": payload["pipelineId"],
                    "jobObserveId": payload["jobObserveId"],
                },
            )
            result = {
                "flowExecutionUuid": payload["flowExecutionUuid"],
                "pipelineId": payload["pipelineId"],
                "jobIds": payload["jobIds"],
                "jobObserveId": payload["jobObserveId"],
                "failureCategory": cls.failure_category,
                "suggestedFix": cls.suggested_fix,
                "diagnosticConfidence": cls.confidence,
                "logExcerpt": excerpt,
                "llmMetadata": cls.llm_metadata,
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "flowId": payload.get("flowId", 0),
                "flowStepId": payload.get("flowStepId", 0),
                "isReplay": payload.get("isReplay", False),
            }
            self.db.save_failure(result)
            self._notify_callback(payload, result)
            LOGGER.info("job_failed", extra={"flowExecutionUuid": payload["flowExecutionUuid"], "workerId": worker_id})
        else:
            LOGGER.info("job_success", extra={"flowExecutionUuid": payload["flowExecutionUuid"], "workerId": worker_id})
