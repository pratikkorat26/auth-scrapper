from fastapi.testclient import TestClient

from app.main import app
from app.services.analysis import AnalysisResult
from app.services.detector import AuthComponent, DetectionResult

client = TestClient(app)


def test_analyze_valid_url(monkeypatch) -> None:
    async def fake_analyze_url(_: str) -> AnalysisResult:
        return AnalysisResult(
            detection=DetectionResult(
                found=True,
                confidence=0.94,
                status="found",
                signals=["password_input", "username_or_email_input"],
                snippet="<form>...</form>",
                message="Authentication component detected.",
                components=[
                    AuthComponent(
                        type="traditional",
                        surface_type="form",
                        confidence=0.94,
                        selector_hint="form",
                        signals=["password_input", "username_or_email_input"],
                        providers=[],
                        fields=[{"type": "email"}],
                        snippet="<form>...</form>",
                        summary="Traditional login form",
                    )
                ],
            ),
            analysis_mode="static",
            fallback_used=False,
            interaction_used=False,
            ai_used=False,
            ai_refined=False,
            ai_provider=None,
            ai_model=None,
        )

    monkeypatch.setattr("app.api.routes.analyze.analyze_url", fake_analyze_url)
    response = client.post("/api/v1/analyze", json={"url": "https://example.com"})

    assert response.status_code == 200
    data = response.json()
    assert data["found"] is True
    assert data["ai_used"] is False
    assert data["components"][0]["type"] == "traditional"


def test_analyze_invalid_url() -> None:
    response = client.post("/api/v1/analyze", json={"url": "ftp://example.com"})
    assert response.status_code == 400


def test_analyze_partial_auth_surface(monkeypatch) -> None:
    async def fake_analyze_url(_: str) -> AnalysisResult:
        return AnalysisResult(
            detection=DetectionResult(
                found=True,
                confidence=0.72,
                status="partial_auth_surface",
                signals=["sso_provider", "ai_gemini"],
                snippet="<section>...</section>",
                message="Gemini identified multiple auth components.",
                components=[
                    AuthComponent(
                        type="oauth",
                        surface_type="sso_only",
                        confidence=0.72,
                        selector_hint="button:has-text('Continue with Google')",
                        signals=["sso_provider", "ai_gemini"],
                        providers=["Google"],
                        fields=[],
                        snippet="<section>...</section>",
                        summary="OAuth provider cluster",
                    )
                ],
            ),
            analysis_mode="browser_fallback",
            fallback_used=True,
            interaction_used=True,
            ai_used=True,
            ai_refined=True,
            ai_provider="gemini",
            ai_model="gemini-2.5-flash",
        )

    monkeypatch.setattr("app.api.routes.analyze.analyze_url", fake_analyze_url)
    response = client.post("/api/v1/analyze", json={"url": "https://example.com/login"})

    assert response.status_code == 200
    data = response.json()
    assert data["ai_used"] is True
    assert data["ai_provider"] == "gemini"
    assert data["components"][0]["providers"] == ["Google"]
