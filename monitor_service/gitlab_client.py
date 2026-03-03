import time
from dataclasses import dataclass

import requests

from monitor_service.metrics import gitlab_api_calls_total, gitlab_api_rate_limited_total


@dataclass
class TailResult:
    chunk: str
    new_offset: int


class GitLabClient:
    def __init__(self, base_url: str, token: str, project_id: int, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self.timeout = timeout
        self.session = requests.Session()
        if token:
            self.session.headers.update({"PRIVATE-TOKEN": token})

    def _request_with_backoff(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        backoff = 0.25
        for _ in range(5):
            gitlab_api_calls_total.inc()
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            if response.status_code in (429, 500, 502, 503, 504):
                if response.status_code == 429:
                    gitlab_api_rate_limited_total.inc()
                retry_after = response.headers.get("Retry-After")
                sleep_for = float(retry_after) if retry_after else backoff
                time.sleep(sleep_for)
                backoff = min(backoff * 2, 4)
                continue
            response.raise_for_status()
            return response
        response.raise_for_status()

    def get_job_status(self, job_id: int) -> str:
        r = self._request_with_backoff(
            "GET", f"/api/v4/projects/{self.project_id}/jobs/{job_id}"
        )
        return r.json().get("status", "unknown")

    def tail_trace(self, job_id: int, offset: int) -> TailResult:
        headers = {"Range": f"bytes={offset}-"}
        r = self._request_with_backoff(
            "GET", f"/api/v4/projects/{self.project_id}/jobs/{job_id}/trace", headers=headers
        )
        content = r.text
        new_offset = offset + len(content.encode("utf-8"))
        return TailResult(chunk=content, new_offset=new_offset)
