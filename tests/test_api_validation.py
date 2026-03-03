from monitor_service.app import create_app


class TestConfig:
    GITLAB_URL = "http://localhost:9"
    GITLAB_PAT = ""
    GITLAB_PROJECT_ID = 1
    DATABASE_URL = "sqlite:///test_api.db"
    WORKER_COUNT = 0
    MAX_LLM_CONCURRENT = 1
    MAX_LOG_CHUNK_SIZE = 1000
    LLM_TOKEN_BUDGET = 256
    POLL_INTERVAL_SECONDS = 0.1
    REQUEST_TIMEOUT_SECONDS = 1


def test_monitor_validation_missing_fields():
    app = create_app(TestConfig)
    client = app.test_client()
    r = client.post("/api/monitor", json={"flowExecutionUuid": "a"})
    assert r.status_code == 400


def test_monitor_accepts_valid_payload():
    app = create_app(TestConfig)
    client = app.test_client()
    payload = {
        "flowExecutionUuid": "d3925853-c27b-45ce-8ebe-0b71089eb76d",
        "pipelineId": 1,
        "jobIds": [1],
        "jobObserveId": 1,
    }
    r = client.post("/api/monitor", json=payload)
    assert r.status_code == 202
    assert r.get_json()["status"] == "scheduled"
