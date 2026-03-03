import os


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


class Config:
    GITLAB_URL = os.getenv("GITLAB_URL", "http://localhost:5001")
    GITLAB_PAT = os.getenv("GITLAB_PAT", "")
    GITLAB_PROJECT_ID = env_int("GITLAB_PROJECT_ID", 1)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///monitor.db")
    WORKER_COUNT = env_int("WORKER_COUNT", 4)
    MAX_LLM_CONCURRENT = env_int("MAX_LLM_CONCURRENT", 2)
    MAX_LOG_CHUNK_SIZE = env_int("MAX_LOG_CHUNK_SIZE", 4000)
    LLM_TOKEN_BUDGET = env_int("LLM_TOKEN_BUDGET", 1024)
    POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "0.5"))
    REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))
