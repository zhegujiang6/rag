from smart_doc_search.api.main import app


def test_expected_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert "/health" in paths
    assert "/api/rag/search" in paths
    assert "/api/rag/chat/stream" in paths
