import json
import threading
import time
from uuid import uuid4

from monitor_service.db.models import Database, PipelineExecution
from monitor_service.llm_adapter import BaseProvider, LLMAdapter
from monitor_service.scheduler.locker import InMemoryLocker
from monitor_service.scheduler.queue import JobQueue
from monitor_service.scheduler.workers import WorkerPool


class TrackingProvider(BaseProvider):
    def __init__(self):
        self.lock = threading.Lock()
        self.inflight = 0
        self.max_inflight = 0

    def complete_json(self, system_prompt: str, user_prompt: str, token_budget: int) -> str:
        with self.lock:
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
        time.sleep(0.03)
        with self.lock:
            self.inflight -= 1
        return json.dumps({"failureCategory": "OTHER", "suggestedFix": "retry", "confidence": 0.5})


class DummyGitLab:
    def get_job_status(self, job_id):
        return "failed"

    def tail_trace(self, job_id, offset):
        class R:
            chunk = "ERROR timeout"
            new_offset = offset + len(chunk)

        return R()


def test_llm_concurrency_bounded(tmp_path):
    provider = TrackingProvider()
    db = Database(f"sqlite:///{tmp_path}/load.db")
    db.init()
    queue = JobQueue()
    pool = WorkerPool(
        worker_count=4,
        queue=queue,
        locker=InMemoryLocker(),
        gitlab_client=DummyGitLab(),
        llm_adapter=LLMAdapter(provider=provider, max_concurrent=2, token_budget=128),
        db=db,
        poll_interval=0.01,
        max_log_chunk_size=500,
    )
    pool.start()
    for i in range(20):
        queue.put(
            {
                "flowExecutionUuid": str(uuid4()),
                "pipelineId": 1,
                "jobIds": [i],
                "jobObserveId": i,
            }
        )
    deadline = time.time() + 6
    while time.time() < deadline:
        with db.SessionLocal() as s:
            count = s.query(PipelineExecution).count()
        if count >= 20:
            break
        time.sleep(0.1)
    pool.shutdown()
    assert provider.max_inflight <= 2
