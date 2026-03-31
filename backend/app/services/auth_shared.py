from __future__ import annotations

import re

AUTH_STATUSES = (
    "found",
    "partial_auth_surface",
    "blocked_or_inconclusive",
    "not_found",
)

AUTH_COMPONENT_TYPES = (
    "traditional",
    "oauth",
    "passwordless",
    "multi_step",
    "challenge",
    "unknown_auth_surface",
)

STATUS_PRIORITY = {
    "found": 3,
    "partial_auth_surface": 2,
    "blocked_or_inconclusive": 1,
    "not_found": 0,
}

COMPONENT_PRIORITY = {
    "traditional": 4,
    "multi_step": 3,
    "oauth": 2,
    "passwordless": 2,
    "challenge": 1,
    "unknown_auth_surface": 0,
}

STATUS_LABELS = {
    "found": "Auth surface found",
    "partial_auth_surface": "Partial auth surface found",
    "blocked_or_inconclusive": "Analysis was limited",
    "not_found": "No auth surface found",
}

ANALYSIS_MODE_LABELS = {
    "static_html": "Static HTML",
    "browser_primary": "Rendered browser pass",
}

BLOCKED_MESSAGE = "This site appears to block automated access or scraping, so auth extraction is limited."

AUTH_RE = re.compile(
    r"\b(log ?in|sign ?in|signin|authentication|auth|account access|member login|continue with email|use email|continue as|continue shopping|verify mobile number)\b",
    re.IGNORECASE,
)
PASSWORD_RE = re.compile(r"\b(password|passcode)\b", re.IGNORECASE)
CONTINUE_RE = re.compile(r"\b(continue|next|proceed|verify|use email|email me a link|request otp|send code)\b", re.IGNORECASE)
SUBMIT_RE = re.compile(r"\b(log ?in|sign ?in|submit|continue|next|request otp|send code)\b", re.IGNORECASE)
PASSWORDLESS_RE = re.compile(
    r"\b(passkey|magic link|email me a link|webauthn|verification code|one-time code|one time code|otp|one-time password)\b",
    re.IGNORECASE,
)
CHALLENGE_RE = re.compile(
    r"\b(captcha|verify you are human|access denied|request blocked|unusual activity|checkpoint)\b",
    re.IGNORECASE,
)
SECONDARY_RE = re.compile(r"\b(forgot password|reset password|recovery code|recover account)\b", re.IGNORECASE)
NEGATIVE_RE = re.compile(r"\b(search|newsletter|subscribe|coupon|promo|contact|feedback|comment|cart)\b", re.IGNORECASE)
PASSWORD_FOLLOWUP_RE = re.compile(r"\b(sign in with password|use password|password instead)\b", re.IGNORECASE)
HIDDEN_TOKEN_RE = re.compile(r"(^|[\s:_-])(hidden|sr-only|visually-hidden)($|[\s:_-])", re.IGNORECASE)
NOISE_TOKEN_RE = re.compile(r"\b(flash|alert|notice|banner|toast|message|template)\b", re.IGNORECASE)
WRAPPER_TOKEN_RE = re.compile(r"\b(wrapper|container|layout|shell|page|root|main|content)\b", re.IGNORECASE)
METADATA_INPUT_RE = re.compile(
    r"\b(authenticity_token|csrf|timestamp|timestamp_secret|return_to|allow_signup|client_id|integration|required_field_)\b",
    re.IGNORECASE,
)

AUTH_TRIGGER_PATTERN = re.compile(
    r"(log in|login|sign in|sign-in|join|get started|continue with email|use email|continue as|sign in with|continue with)",
    re.IGNORECASE,
)
ACCOUNT_TRIGGER_PATTERN = re.compile(
    r"(my account|account|profile|avatar|user menu|menu|open account|open profile)",
    re.IGNORECASE,
)
CONTINUE_TRIGGER_PATTERN = re.compile(r"(continue|next|log in|login|sign in|sign-in)", re.IGNORECASE)
BLOCKED_TEXT_RE = re.compile(
    r"blocked by network security|block automated access|access denied|captcha|unusual activity|verify you are human|request blocked|protected page",
    re.IGNORECASE,
)
AUTH_TEXT_RE = re.compile(
    r"log in|login|sign in|signin|continue with email|continue with google|passkey|magic link|verification code",
    re.IGNORECASE,
)

USERNAME_KEYWORDS = ("user", "username", "email", "login", "identifier", "member id")
PROVIDER_KEYWORDS = (
    "google",
    "apple",
    "facebook",
    "github",
    "linkedin",
    "microsoft",
    "twitter",
    "x",
    "discord",
    "slack",
    "amazon",
)


def default_message_for_status(status: str) -> str:
    return {
        "found": "Authentication component detected.",
        "partial_auth_surface": "Partial authentication surface detected.",
        "blocked_or_inconclusive": "The page appears to show a challenge or blocked auth surface.",
        "not_found": "Authentication component not found.",
    }[status]


def status_label_for(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " ").title())


def analysis_mode_label_for(mode: str) -> str:
    return ANALYSIS_MODE_LABELS.get(mode, mode.replace("_", " ").title())


def is_protected_page(status: str, message: str) -> bool:
    return status == "blocked_or_inconclusive" and bool(BLOCKED_TEXT_RE.search(message or ""))
