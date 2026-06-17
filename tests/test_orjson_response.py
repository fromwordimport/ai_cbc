from fastapi.testclient import TestClient


def test_api_uses_orjson_response():
    from aicbc.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    # ORJSONResponse is a subclass of JSONResponse but uses orjson under the hood.
    # We verify the response class name indirectly via the app config.
    from fastapi.responses import ORJSONResponse

    assert app.router.default_response_class is ORJSONResponse
