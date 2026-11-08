import httpx

USER_AGENT = "cinesync (self-hosted)"

_client: httpx.AsyncClient | None = None


def http() -> httpx.AsyncClient:
    """Client HTTP partagé (pool de connexions)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
    return _client


async def close_http() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
