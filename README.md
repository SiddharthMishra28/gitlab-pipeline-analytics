# GitLab Pipeline Monitoring Service

Production-oriented Flask + FastMCP service that accepts monitoring jobs, tails GitLab job traces via `Range` headers, classifies failed jobs with an LLM adapter, persists diagnostics, and exports Prometheus metrics.

## Features
- `POST /api/monitor` returns `202` immediately and enqueues monitoring jobs.
- Bounded priority queue + worker pool (`WORKER_COUNT`) with LLM concurrency guard (`MAX_LLM_CONCURRENT`).
- GitLab polling and trace tailing with `Range: bytes=<offset>-` (incremental reads only).
- LLM adapter with strict prompt template, token budget, retries, and JSON output validation.
- Persistence to `pipeline_failures` table via SQLAlchemy (Postgres-ready).
- `/metrics` for Prometheus + `/health` endpoint.
- FastMCP tools (`monitor_service/mcp_tools.py`) for controlled access to job status/trace.

## Environment variables
- `GITLAB_URL` (e.g. `https://gitlab.example.com`)
- `GITLAB_PAT` (PAT, **never log this**)
- `GITLAB_PROJECT_ID`
- `DATABASE_URL` (e.g. `postgresql+psycopg2://monitor:monitor@localhost:5432/monitor`)
- `WORKER_COUNT` (default `4`)
- `MAX_LLM_CONCURRENT` (default `2`)
- `MAX_LOG_CHUNK_SIZE` (default `4000` chars)
- `LLM_TOKEN_BUDGET` (default `1024`)
- `POLL_INTERVAL_SECONDS` (default `0.5`)

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m monitor_service.app
```

## Docker compose
```bash
docker compose up --build
```

## API example
```bash
curl -X POST http://localhost:8000/api/monitor \
  -H 'Content-Type: application/json' \
  -d '{
    "flowExecutionUuid":"d3925853-c27b-45ce-8ebe-0b71089eb76d",
    "pipelineId":3152489,
    "jobIds":[317293,812038,578934,312323],
    "jobObserveId":812038,
    "priority":10,
    "callbacks":{"onComplete":"https://hook.example.com/monitor-callback"}
  }'
```

Response:
```json
{"status":"scheduled","flowExecutionUuid":"d3925853-c27b-45ce-8ebe-0b71089eb76d","jobObserveId":812038}
```

## Postgres schema
```sql
CREATE TABLE pipeline_failures (
  id SERIAL PRIMARY KEY,
  flow_execution_uuid UUID NOT NULL,
  pipeline_id BIGINT NOT NULL,
  job_observe_id BIGINT NOT NULL,
  job_ids BIGINT[] NOT NULL,
  failure_category VARCHAR(64),
  suggested_fix TEXT,
  diagnostic_confidence FLOAT,
  log_excerpt TEXT,
  llm_metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON pipeline_failures (flow_execution_uuid);
CREATE INDEX ON pipeline_failures (pipeline_id);
```

## Tests
```bash
pytest -q
```

## Security notes / TODOs
- TODO: move PAT retrieval to Vault / Secrets Manager.
- TODO: enforce tenant-aware quotas and callback signing.
- TODO: add Redis-backed distributed queue + dedupe locks for horizontal scaling.
