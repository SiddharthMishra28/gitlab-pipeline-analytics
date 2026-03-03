import atexit
import logging

from flask import Flask, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from monitor_service.config import Config
from monitor_service.db.models import Database
from monitor_service.gitlab_client import GitLabClient
from monitor_service.llm_adapter import LLMAdapter
from monitor_service.scheduler.locker import InMemoryLocker
from monitor_service.scheduler.queue import JobQueue
from monitor_service.scheduler.workers import WorkerPool

logging.basicConfig(level=logging.INFO)


def create_app(config_cls=Config):
    app = Flask(__name__)

    db = Database(config_cls.DATABASE_URL)
    db.init()
    queue = JobQueue()
    locker = InMemoryLocker()
    gitlab_client = GitLabClient(
        config_cls.GITLAB_URL,
        config_cls.GITLAB_PAT,
        config_cls.GITLAB_PROJECT_ID,
        timeout=config_cls.REQUEST_TIMEOUT_SECONDS,
    )
    llm_adapter = LLMAdapter(
        max_concurrent=config_cls.MAX_LLM_CONCURRENT,
        token_budget=config_cls.LLM_TOKEN_BUDGET,
    )
    pool = WorkerPool(
        worker_count=config_cls.WORKER_COUNT,
        queue=queue,
        locker=locker,
        gitlab_client=gitlab_client,
        llm_adapter=llm_adapter,
        db=db,
        poll_interval=config_cls.POLL_INTERVAL_SECONDS,
        max_log_chunk_size=config_cls.MAX_LOG_CHUNK_SIZE,
    )
    pool.start()
    atexit.register(pool.shutdown)

    app.extensions["monitor_queue"] = queue

    @app.post("/api/monitor")
    def monitor():
        payload = request.get_json(silent=True) or {}
        required = ["flowExecutionUuid", "pipelineId", "jobIds", "jobObserveId"]
        missing = [k for k in required if k not in payload]
        if missing:
            return jsonify({"error": f"missing fields: {','.join(missing)}"}), 400
        if not isinstance(payload["jobIds"], list) or not payload["jobIds"]:
            return jsonify({"error": "jobIds must be non-empty array"}), 400
        queue.put(payload)
        return (
            jsonify(
                {
                    "status": "scheduled",
                    "flowExecutionUuid": payload["flowExecutionUuid"],
                    "jobObserveId": payload["jobObserveId"],
                }
            ),
            202,
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/metrics")
    def metrics():
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=8000)
