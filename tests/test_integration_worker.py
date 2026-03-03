import threading
import time
from uuid import uuid4

from flask import Flask, Response, jsonify, request
from werkzeug.serving import make_server

from monitor_service.db.models import Database, PipelineFailure
from monitor_service.gitlab_client import GitLabClient
from monitor_service.llm_adapter import HeuristicProvider, LLMAdapter
from monitor_service.scheduler.locker import InMemoryLocker
from monitor_service.scheduler.queue import JobQueue
from monitor_service.scheduler.workers import WorkerPool


class ServerThread(threading.Thread):
    def __init__(self, app, port):
        super().__init__(daemon=True)
        self.srv = make_server("127.0.0.1", port, app)

    def run(self):
        self.srv.serve_forever()

    def shutdown(self):
        self.srv.shutdown()


def test_end_to_end_failure_persist(tmp_path):
    job_state = {"status_calls": 0}
    trace = "start\n"

    gapp = Flask("mock-gitlab")

    @gapp.get("/api/v4/projects/1/jobs/123")
    def job_status():
        job_state["status_calls"] += 1
        status = "running" if job_state["status_calls"] < 3 else "failed"
        return jsonify({"status": status})

    @gapp.get("/api/v4/projects/1/jobs/123/trace")
    def job_trace():
        nonlocal trace
        if job_state["status_calls"] >= 2:
            trace += "Traceback: RuntimeError invalid token\n"
        rng = request.headers.get("Range", "bytes=0-")
        offset = int(rng.replace("bytes=", "").replace("-", ""))
        body = trace.encode()[offset:]
        return Response(body, status=206, mimetype="text/plain")

    server = ServerThread(gapp, 5015)
    server.start()

    db = Database(f"sqlite:///{tmp_path}/it.db")
    db.init()
    queue = JobQueue()
    pool = WorkerPool(
        worker_count=1,
        queue=queue,
        locker=InMemoryLocker(),
        gitlab_client=GitLabClient("http://127.0.0.1:5015", "", 1),
        llm_adapter=LLMAdapter(provider=HeuristicProvider(), max_concurrent=1, token_budget=256),
        db=db,
        poll_interval=0.05,
        max_log_chunk_size=1000,
    )
    pool.start()

    flow_id = str(uuid4())
    queue.put(
        {
            "flowExecutionUuid": flow_id,
            "pipelineId": 11,
            "jobIds": [123],
            "jobObserveId": 123,
        }
    )

    for _ in range(40):
        with db.SessionLocal() as s:
            row = s.query(PipelineFailure).filter_by(flow_execution_uuid=flow_id).first()
            if row:
                assert row.failure_category == "RUNTIME_EXCEPTION"
                break
        time.sleep(0.1)
    else:
        raise AssertionError("failure row not written")

    pool.shutdown()
    server.shutdown()
