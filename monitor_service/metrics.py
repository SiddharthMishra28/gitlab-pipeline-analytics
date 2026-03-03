from prometheus_client import Counter, Gauge

monitor_queue_length = Gauge("monitor_queue_length", "Monitor job queue length")
active_workers = Gauge("active_workers", "Active worker count")
llm_calls_total = Counter("llm_calls_total", "Total LLM calls")
llm_errors_total = Counter("llm_errors_total", "Total LLM errors")
gitlab_api_calls_total = Counter("gitlab_api_calls_total", "Total GitLab API calls")
gitlab_api_rate_limited_total = Counter(
    "gitlab_api_rate_limited_total", "GitLab API 429 responses"
)
processed_success_total = Counter("monitor_processed_success_total", "Processed success")
processed_failure_total = Counter("monitor_processed_failure_total", "Processed failure")
