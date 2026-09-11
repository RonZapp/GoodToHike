from src.goodtohike.http import make_http_client


def test_make_http_client_sets_user_agent():
    client = make_http_client()
    assert client.headers["User-Agent"].startswith("GoodToHike/")
    assert client.timeout.read == 5.0
