"""FastMCP tool registration for internal GitLab reads."""


def build_mcp_server(gitlab_client):
    try:
        from fastmcp import FastMCP
    except Exception:
        return None

    mcp = FastMCP("gitlab-monitor-tools")

    @mcp.tool
    def get_job_status(job_id: int) -> str:
        return gitlab_client.get_job_status(job_id)

    @mcp.tool
    def get_trace_chunk(job_id: int, offset: int) -> dict:
        r = gitlab_client.tail_trace(job_id, offset)
        return {"chunk": r.chunk, "new_offset": r.new_offset}

    return mcp
