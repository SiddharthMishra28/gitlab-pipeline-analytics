from monitor_service.gitlab_client import GitLabClient


class FakeResponse:
    def __init__(self, status_code=206, text="abc"):
        self.status_code = status_code
        self.text = text
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("bad")

    def json(self):
        return {"status": "running"}


def test_tail_trace_uses_range_header(monkeypatch):
    client = GitLabClient("http://gitlab", "", 1)
    seen = {}

    def fake_request(method, url, timeout=None, **kwargs):
        seen["headers"] = kwargs.get("headers", {})
        return FakeResponse(text="hello")

    monkeypatch.setattr(client.session, "request", fake_request)
    out = client.tail_trace(11, 5)
    assert seen["headers"]["Range"] == "bytes=5-"
    assert out.new_offset == 10
