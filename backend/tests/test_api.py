from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_analyze_valid_url(monkeypatch) -> None:
    async def fake_fetch_html(_: str) -> str:
        return """
        <form>
          <input type="email" name="email" />
          <input type="password" name="password" />
          <button type="submit">Login</button>
        </form>
        """

    monkeypatch.setattr("app.api.routes.analyze.fetch_html", fake_fetch_html)

    response = client.post("/api/v1/analyze", json={"url": "https://example.com"})

    assert response.status_code == 200
    data = response.json()
    assert data["found"] is True
    assert data["url"] == "https://example.com"


def test_analyze_invalid_url() -> None:
    response = client.post("/api/v1/analyze", json={"url": "ftp://example.com"})

    assert response.status_code == 400
    assert "http://" in response.json()["detail"]


def test_analyze_not_found(monkeypatch) -> None:
    async def fake_fetch_html(_: str) -> str:
        return "<html><body><h1>Plain marketing site</h1></body></html>"

    monkeypatch.setattr("app.api.routes.analyze.fetch_html", fake_fetch_html)

    response = client.post("/api/v1/analyze", json={"url": "https://example.com"})

    assert response.status_code == 200
    data = response.json()
    assert data["found"] is False
    assert data["message"] == "Authentication component not found."

