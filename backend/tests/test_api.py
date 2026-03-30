from fastapi.testclient import TestClient

from app.main import app
from app.services.analysis import AnalysisResult
from app.services.detector import DetectionResult, ExtractedAction, ExtractedField

client = TestClient(app)


def test_analyze_valid_url(monkeypatch) -> None:
    async def fake_analyze_url(_: str) -> AnalysisResult:
        return AnalysisResult(
            detection=DetectionResult(
                found=True,
                confidence=1.0,
                status="found",
                signals=["password_input", "username_or_email_input", "submit_button"],
                snippet="<form>...</form>",
                message="Authentication component detected.",
                surface_type="form",
                fields=[ExtractedField(type="email", label="Email")],
                actions=[ExtractedAction(type="submit", label="Sign in")],
                providers=[],
            ),
            analysis_mode="static",
            fallback_used=False,
            interaction_used=False,
        )

    monkeypatch.setattr("app.api.routes.analyze.analyze_url", fake_analyze_url)

    response = client.post("/api/v1/analyze", json={"url": "https://example.com"})

    assert response.status_code == 200
    data = response.json()
    assert data["found"] is True
    assert data["status"] == "found"
    assert data["analysis_mode"] == "static"
    assert data["interaction_used"] is False
    assert data["fields"][0]["type"] == "email"


def test_analyze_invalid_url() -> None:
    response = client.post("/api/v1/analyze", json={"url": "ftp://example.com"})

    assert response.status_code == 400
    assert "http://" in response.json()["detail"]


def test_analyze_partial_auth_surface(monkeypatch) -> None:
    async def fake_analyze_url(_: str) -> AnalysisResult:
        return AnalysisResult(
            detection=DetectionResult(
                found=False,
                confidence=0.62,
                status="partial_auth_surface",
                signals=["sso_provider", "auth_keyword"],
                snippet="<section>...</section>",
                message="Partial authentication surface detected.",
                surface_type="sso_only",
                actions=[ExtractedAction(type="provider", label="Continue with Google", provider="Google")],
                providers=["Google"],
            ),
            analysis_mode="browser_fallback",
            fallback_used=True,
            interaction_used=True,
        )

    monkeypatch.setattr("app.api.routes.analyze.analyze_url", fake_analyze_url)

    response = client.post("/api/v1/analyze", json={"url": "https://example.com/login"})

    assert response.status_code == 200
    data = response.json()
    assert data["found"] is False
    assert data["status"] == "partial_auth_surface"
    assert data["fallback_used"] is True
    assert data["interaction_used"] is True
    assert data["providers"] == ["Google"]
