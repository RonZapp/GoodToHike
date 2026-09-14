"""The shared HTTP client that every upstream client is built on."""

from importlib.metadata import version

import httpx2

USER_AGENT_PRODUCT = f"GoodToHike/{version('goodtohike')}"
USER_AGENT_COMMENT = "(github.com/RonZapp/GoodToHike)"
DEFAULT_TIMEOUT = 5.0


def make_http_client() -> httpx2.Client:
    return httpx2.Client(
        headers={"User-Agent": f"{USER_AGENT_PRODUCT} {USER_AGENT_COMMENT}"},
        timeout=DEFAULT_TIMEOUT,
    )
