from importlib.metadata import version

import httpx

DEFAULT_TIMEOUT = 5.0


def make_http_client() -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": f"GoodToHike/{version('goodtohike')} (github.com/RonZapp/GoodToHike)"
        },
        timeout=DEFAULT_TIMEOUT,
    )
