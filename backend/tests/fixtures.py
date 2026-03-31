from __future__ import annotations

from app.services.browser import BrowserMarkupSnapshot, BrowserRenderResult


def login_form_html(submit_label: str = "Login") -> str:
    return (
        "<html><body><form>"
        '<input type="email" name="email" />'
        '<input type="password" name="password" />'
        f'<button type="submit">{submit_label}</button>'
        "</form></body></html>"
    )


def oauth_html(*providers: str) -> str:
    buttons = "".join(f'<button type="button">Continue with {provider}</button>' for provider in providers)
    return f'<html><body><section aria-label="Sign in">{buttons}</section></body></html>'


def challenge_html() -> str:
    return "<html><body><section><h2>Verify you are human</h2><div>Request blocked</div></section></body></html>"


def browser_result(
    html: str,
    *,
    interaction_used: bool = False,
    typing_used: bool = False,
    snapshots: list[BrowserMarkupSnapshot] | None = None,
) -> BrowserRenderResult:
    return BrowserRenderResult(
        html=html,
        interaction_used=interaction_used,
        typing_used=typing_used,
        snapshots=snapshots or [BrowserMarkupSnapshot("passive_wait", html, interaction_used, typing_used)],
    )
