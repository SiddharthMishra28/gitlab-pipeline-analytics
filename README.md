# GitLab Pipeline Monitoring Service (Beginner-Friendly Guide)

This project is a Python service that:
1. Accepts monitor jobs through an HTTP API (`POST /api/monitor`).
2. Polls GitLab job status and tails logs incrementally using `Range: bytes=<offset>-`.
3. Detects failed jobs, sends a compact log excerpt to an LLM classifier.
4. Stores diagnostics in the existing `PIPELINE_EXECUTIONS` table (no column removals).

---

## 1) What this service does (in plain language)

When your test/job runs in GitLab, this service keeps checking the job.
If the job fails, it reads only new log bytes (not the full file repeatedly), asks an LLM what failed, and writes the diagnosis into `PIPELINE_EXECUTIONS.RUNTIME_TEST_DATA` JSON.

---

## 2) Prerequisites

- Python 3.12+
- Access to a GitLab instance
- A GitLab Personal Access Token (PAT)
- A database URL for your environment (SQLite for local tests, Postgres/H2-compatible DB in real deployments)

---

## 3) Quick start (first-time user)

### Step A: Create venv and install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step B: Set environment variables
```bash
export GITLAB_URL="https://gitlab.example.com"
export GITLAB_PAT="<your_pat_here>"
export GITLAB_PROJECT_ID="12345"
export DATABASE_URL="sqlite:///monitor.db"
export WORKER_COUNT="4"
export MAX_LLM_CONCURRENT="2"
export MAX_LOG_CHUNK_SIZE="4000"
export LLM_TOKEN_BUDGET="1024"
export POLL_INTERVAL_SECONDS="0.5"
```

### Step C: Run service
```bash
python -m monitor_service.app
```

Service starts on `http://localhost:8000`.

### Step D: Health check
```bash
curl http://localhost:8000/health
```

Expected:
```json
{"status":"ok"}
```

---

## 4) API usage

### Submit monitor request
```bash
curl -X POST http://localhost:8000/api/monitor \
  -H 'Content-Type: application/json' \
  -d '{
    "flowExecutionUuid": "d3925853-c27b-45ce-8ebe-0b71089eb76d",
    "pipelineId": 3152489,
    "jobIds": [317293, 812038, 578934, 312323],
    "jobObserveId": 812038,
    "priority": 10,
    "flowId": 101,
    "flowStepId": 202,
    "isReplay": false,
    "callbacks": {"onComplete": "https://hook.example.com/monitor-callback"}
  }'
```

Immediate response:
```json
{"status":"scheduled","flowExecutionUuid":"...","jobObserveId":812038}
```

---

## 5) Database mapping to your existing DDL (`PIPELINE_EXECUTIONS`)

This service **does not require deleting any existing column**.

### How diagnostics are saved now
- `STATUS` set to `FAILED`
- `END_TIME` updated on failure
- `RUNTIME_TEST_DATA` JSON contains:
  - `failureCategory`
  - `suggestedFix`
  - `diagnosticConfidence`
  - `logExcerpt`
  - `llmMetadata`
  - `jobIds`
  - `timestamp`

### Suggested non-breaking schema improvements (optional)
If you want indexed/first-class reporting fields while keeping compatibility, add columns (do not drop existing):

```sql
ALTER TABLE PUBLIC.PIPELINE_EXECUTIONS ADD COLUMN IF NOT EXISTS FAILURE_CATEGORY VARCHAR(64);
ALTER TABLE PUBLIC.PIPELINE_EXECUTIONS ADD COLUMN IF NOT EXISTS SUGGESTED_FIX VARCHAR(2000);
ALTER TABLE PUBLIC.PIPELINE_EXECUTIONS ADD COLUMN IF NOT EXISTS DIAGNOSTIC_CONFIDENCE DOUBLE;
ALTER TABLE PUBLIC.PIPELINE_EXECUTIONS ADD COLUMN IF NOT EXISTS LLM_METADATA JSON;
ALTER TABLE PUBLIC.PIPELINE_EXECUTIONS ADD COLUMN IF NOT EXISTS LOG_EXCERPT CLOB;

CREATE INDEX IF NOT EXISTS IDX_PIPE_EXEC_FLOW_EXEC ON PUBLIC.PIPELINE_EXECUTIONS(FLOW_EXECUTION_ID);
CREATE INDEX IF NOT EXISTS IDX_PIPE_EXEC_PIPELINE_ID ON PUBLIC.PIPELINE_EXECUTIONS(PIPELINE_ID);
CREATE INDEX IF NOT EXISTS IDX_PIPE_EXEC_STATUS ON PUBLIC.PIPELINE_EXECUTIONS(STATUS);
```

If you add these columns, you can extend persistence to fill them directly in addition to `RUNTIME_TEST_DATA`.

---

## 6) Running tests

```bash
pytest -q
```

What tests cover:
- API payload validation
- GitLab trace tailing with `Range` header
- LLM JSON classification parsing
- End-to-end mocked GitLab failure -> DB persistence
- Worker/LLM concurrency bounds

---

## 7) Docker usage

```bash
docker compose up --build
```

`docker-compose.yml` starts:
- service
- postgres
- redis (reserved for future distributed queue)

---

## 8) Security checklist

- Never hardcode PATs in source code.
- Store PAT in environment variables or secret manager.
- Callback URL requires HTTPS.
- Avoid logging sensitive credentials.

---

## 9) Production TODOs

- Replace in-memory queue/lock with Redis-backed distributed queue + lock.
- Add request authentication and per-tenant quota controls.
- Add stronger structured logging and tracing pipeline.
- Add DB migrations for managed schema evolution.
