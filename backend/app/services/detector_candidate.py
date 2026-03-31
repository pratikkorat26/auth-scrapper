from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import Tag

from ..core.config import get_settings
from .auth_shared import (
    AUTH_RE,
    CHALLENGE_RE,
    CONTINUE_RE,
    HIDDEN_TOKEN_RE,
    METADATA_INPUT_RE,
    NEGATIVE_RE,
    NOISE_TOKEN_RE,
    PASSWORDLESS_RE,
    PASSWORD_FOLLOWUP_RE,
    PASSWORD_RE,
    PROVIDER_KEYWORDS,
    SECONDARY_RE,
    SUBMIT_RE,
    USERNAME_KEYWORDS,
    WRAPPER_TOKEN_RE,
)
from .detection_models import CandidateModel, CandidateSignals, ExtractedAction, ExtractedField

PARTIAL_MARKUP_MAX_CHARS = 5000

logger = logging.getLogger(__name__)


def candidate_from_tag(element: Tag) -> CandidateModel:
    visible_text = _visible_text(element)
    attr_blob = _element_attr_blob(element)
    text_blob = _element_text_blob(element, visible_text)
    fields = _extract_fields(element)
    actions = _extract_actions(element)
    providers = _extract_sso_providers(text_blob, actions)
    meaningful_field_types = {field.type for field in fields if field.type != "unknown"}
    signals = CandidateSignals(
        text_blob=text_blob,
        fields=fields,
        actions=actions,
        providers=providers,
        has_password="password" in meaningful_field_types,
        has_identity=bool({"email", "username", "phone"} & meaningful_field_types),
        has_submit=any(action.type == "submit" for action in actions),
        has_continue=any(action.type == "continue" for action in actions),
        has_passwordless=bool(PASSWORDLESS_RE.search(text_blob)),
        has_challenge=bool(CHALLENGE_RE.search(text_blob)),
        has_secondary=bool(SECONDARY_RE.search(text_blob)),
        has_negative=bool(NEGATIVE_RE.search(text_blob)),
        has_auth_text=bool(AUTH_RE.search(text_blob) or PASSWORD_RE.search(text_blob)),
        has_password_followup=bool(PASSWORD_FOLLOWUP_RE.search(text_blob)),
        meaningful_field_types=meaningful_field_types,
    )
    return CandidateModel(
        element=element,
        text_blob=text_blob,
        attr_blob=attr_blob,
        visible_text=visible_text,
        fields=fields,
        actions=actions,
        providers=providers,
        signals=signals,
    )


def is_hidden_element(element: Tag) -> bool:
    if not isinstance(element, Tag):
        return False
    if element.has_attr("hidden"):
        return True
    if str(element.get("aria-hidden", "")).lower() == "true":
        return True
    style = str(element.get("style", "")).replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    return bool(HIDDEN_TOKEN_RE.search(_element_attr_blob(element)))


def is_noise_container(element: Tag) -> bool:
    if not isinstance(element, Tag):
        return False
    if element.name == "template":
        return True
    text_blob = " ".join(
        filter(None, [element.get("id"), " ".join(element.get("class", [])) if element.get("class") else None])
    ).lower()
    return bool(NOISE_TOKEN_RE.search(_element_attr_blob(element)) or NOISE_TOKEN_RE.search(text_blob))


def candidate_size(candidate: CandidateModel) -> int:
    return len(candidate.element.prettify(formatter="minimal"))


def serialize_partial_markup(candidate: CandidateModel) -> str:
    raw = candidate.element.prettify(formatter="minimal").strip()
    if len(raw) > PARTIAL_MARKUP_MAX_CHARS:
        truncated = raw[: PARTIAL_MARKUP_MAX_CHARS - 3].rstrip()
        last_newline = truncated.rfind("\n")
        if last_newline > 0:
            truncated = truncated[:last_newline].rstrip()
        raw = truncated + "\n..."
    return raw


def build_snippet(candidate: CandidateModel) -> str:
    snippet_element = select_snippet_element(candidate)
    snippet = snippet_element.prettify(formatter="minimal").strip()
    if len(snippet) <= get_settings().max_snippet_length:
        return snippet
    truncated = snippet[: get_settings().max_snippet_length - 3].rstrip()
    last_newline = truncated.rfind("\n")
    if last_newline > 0:
        truncated = truncated[:last_newline].rstrip()
    return truncated + "\n..."


def select_snippet_element(candidate: CandidateModel) -> Tag:
    if candidate.signals.has_password and candidate.signals.has_identity:
        return candidate.element

    descendants = [
        node
        for node in candidate.element.find_all(["form", "section", "div", "dialog", "aside", "main", "article"], recursive=True)
        if node is not candidate.element and not is_hidden_element(node) and not is_noise_container(node) and is_auth_bearing_node(candidate_from_tag(node))
    ]
    if not descendants:
        return candidate.element
    selected = sorted(descendants, key=lambda node: snippet_selection_key(candidate_from_tag(node)))[0]
    logger.info(
        "snippet focus selected",
        extra={
            "candidate": candidate_descriptor(candidate),
            "selected": candidate_descriptor(candidate_from_tag(selected)),
            "selected_size": candidate_size(candidate_from_tag(selected)),
        },
    )
    return selected


def snippet_selection_key(candidate: CandidateModel) -> tuple[int, int, int, int]:
    signals = candidate.signals
    credential_complete = 1 if signals.has_password and signals.has_identity else 0
    credential_action_complete = 1 if credential_complete and (signals.has_submit or signals.has_continue) else 0
    return (
        -credential_action_complete,
        -credential_complete,
        -candidate_focus_score(candidate),
        candidate_size(candidate),
    )


def candidate_focus_score(candidate: CandidateModel) -> int:
    element = candidate.element
    score = 0
    nested_forms = len(element.find_all("form"))
    visible_actions = len(candidate.actions)
    visible_fields = len(candidate.fields)
    child_auth_units = len(
        [
            child
            for child in element.find_all(["form", "section", "div", "dialog", "aside"], recursive=False)
            if not is_hidden_element(child)
            and not is_noise_container(child)
            and is_auth_bearing_node(candidate_from_tag(child))
        ]
    )
    if element.name == "form":
        score += 4
    if candidate.signals.has_password and candidate.signals.has_identity:
        score += 9
    elif candidate.signals.has_password:
        score += 5
    elif candidate.signals.has_identity:
        score += 3
    if candidate.signals.has_password and candidate.signals.has_identity and (candidate.signals.has_submit or candidate.signals.has_continue):
        score += 4
    if visible_fields:
        score += min(visible_fields, 3)
    if visible_actions:
        score += min(visible_actions, 3)
    if PASSWORD_FOLLOWUP_RE.search(candidate.text_blob):
        score += 2
    if any(provider in candidate.text_blob for provider in PROVIDER_KEYWORDS):
        score += 2
    if "passkey" in candidate.text_blob or "webauthn" in candidate.text_blob or "magic link" in candidate.text_blob:
        score += 2
    if element.name != "form" and nested_forms:
        score -= min(nested_forms * 3, 9)
    if element.name != "form" and child_auth_units:
        score -= min(child_auth_units * 2, 6)
    if element.name != "form" and WRAPPER_TOKEN_RE.search(candidate.attr_blob):
        score -= 2
    score -= min(candidate_size(candidate) // 1500, 4)
    return score


def is_auth_bearing_node(candidate: CandidateModel) -> bool:
    signals = candidate.signals
    if signals.has_password and signals.has_identity and (signals.has_submit or signals.has_continue or signals.has_auth_text):
        return True
    if signals.has_password and (signals.has_identity or signals.has_submit or signals.has_auth_text):
        return True
    if signals.providers and any(action.type == "provider" for action in signals.actions):
        return True
    if signals.has_passwordless and has_visible_passwordless_trigger(candidate):
        return True
    if signals.has_identity and (signals.has_continue or signals.has_password_followup):
        return True
    return False


def has_auth_bearing_descendant(candidate: CandidateModel) -> bool:
    for node in candidate.element.find_all(["form", "section", "div", "dialog", "aside", "main", "article"], recursive=True):
        if node is candidate.element or is_hidden_element(node) or is_noise_container(node):
            continue
        if is_auth_bearing_node(candidate_from_tag(node)):
            return True
    return False


def is_smallest_credential_complete_container(candidate: CandidateModel) -> bool:
    signals = candidate.signals
    if not (signals.has_password and signals.has_identity and (signals.has_submit or signals.has_continue or signals.has_auth_text)):
        return False
    for child in candidate.element.find_all(["form", "section", "div", "dialog", "aside", "main", "article"], recursive=False):
        if is_hidden_element(child) or is_noise_container(child):
            continue
        child_signals = candidate_from_tag(child).signals
        if child_signals.has_password and child_signals.has_identity and (
            child_signals.has_submit or child_signals.has_continue or child_signals.has_auth_text
        ):
            return False
    return True


def has_visible_passwordless_trigger(candidate: CandidateModel) -> bool:
    return any(
        action.type in {"continue", "action"} and PASSWORDLESS_RE.search(action.label.lower())
        for action in candidate.actions
    ) or "passkey" in candidate.text_blob or "magic link" in candidate.text_blob


def build_selector_hint(candidate: CandidateModel) -> Optional[str]:
    element = candidate.element
    if element.name == "form":
        if element.get("id"):
            return f"form#{element.get('id')}"
        return "form"
    if element.get("id"):
        return f"#{element.get('id')}"
    if candidate.fields and candidate.fields[0].selector_hint and " " not in candidate.fields[0].selector_hint:
        hint = candidate.fields[0].selector_hint
        return f"input[name='{hint}'], input[id='{hint}']"
    if candidate.actions and candidate.actions[0].selector_hint:
        return candidate.actions[0].selector_hint
    return None


def candidate_descriptor(candidate: CandidateModel) -> str:
    identifier = candidate.element.get("id") or candidate.element.get("data-testid")
    if identifier:
        return f"{candidate.element.name}#{identifier}"
    classes = ".".join(candidate.element.get("class", [])[:2])
    return f"{candidate.element.name}.{classes}" if classes else candidate.element.name


def _extract_fields(element: Tag) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    for input_tag in element.find_all(["input", "textarea"]):
        if _is_hidden_input(input_tag):
            continue
        field_type = _classify_input(input_tag)
        if field_type == "hidden":
            continue
        fields.append(
            ExtractedField(
                type=field_type,
                label=_extract_label(input_tag),
                name=input_tag.get("name") or input_tag.get("id"),
                selector_hint=input_tag.get("name") or input_tag.get("id") or input_tag.get("placeholder"),
                required=input_tag.has_attr("required") or input_tag.get("aria-required") == "true",
            )
        )
    return _unique_fields(fields)


def _extract_actions(element: Tag) -> list[ExtractedAction]:
    actions: list[ExtractedAction] = []
    for action_tag in element.find_all(["button", "input", "a"]):
        if is_hidden_element(action_tag):
            continue
        label = " ".join(
            filter(
                None,
                [
                    action_tag.get("value"),
                    action_tag.get("aria-label"),
                    action_tag.get_text(" ", strip=True),
                ],
            )
        ).strip()
        if not label:
            continue
        lowered = label.lower()
        provider = next((item.title() for item in PROVIDER_KEYWORDS if re.search(rf"\b{re.escape(item)}\b", lowered)), None)
        action_type = "action"
        if provider:
            action_type = "provider"
        elif CONTINUE_RE.search(lowered):
            action_type = "continue"
        elif SUBMIT_RE.search(lowered):
            action_type = "submit"
        actions.append(
            ExtractedAction(
                type=action_type,
                label=label,
                provider=provider,
                selector_hint=action_tag.get("id") or action_tag.get("name") or label,
            )
        )
    return _unique_actions(actions)


def _extract_sso_providers(text_blob: str, actions: list[ExtractedAction]) -> list[str]:
    action_providers = [action.provider for action in actions if action.provider]
    if action_providers:
        return sorted(set(action_providers))
    providers = [provider.title() for provider in PROVIDER_KEYWORDS if re.search(rf"\b{re.escape(provider)}\b", text_blob)]
    return sorted(set(providers))


def _classify_input(input_tag: Tag) -> str:
    input_type = (input_tag.get("type") or "text").lower()
    descriptor = " ".join(
        filter(
            None,
            [
                input_type,
                input_tag.get("name"),
                input_tag.get("id"),
                input_tag.get("placeholder"),
                input_tag.get("autocomplete"),
                input_tag.get("aria-label"),
                input_tag.get("data-testid"),
                input_tag.get("inputmode"),
            ],
        )
    ).lower()

    if input_type == "hidden":
        return "hidden"
    if input_type == "password":
        return "password"
    if "otp" in descriptor or "verification code" in descriptor or "one-time" in descriptor:
        return "otp"
    if input_type == "email" or "email" in descriptor:
        return "email"
    if input_type == "tel" or "phone" in descriptor:
        return "phone"
    if any(keyword in descriptor for keyword in USERNAME_KEYWORDS):
        return "username"
    return "unknown"


def _extract_label(input_tag: Tag) -> Optional[str]:
    if input_tag.get("aria-label"):
        return input_tag.get("aria-label")
    if input_tag.get("placeholder"):
        return input_tag.get("placeholder")
    input_id = input_tag.get("id")
    if input_id and input_tag.find_parent():
        label = input_tag.find_parent().find("label", attrs={"for": input_id})
        if label:
            return label.get_text(" ", strip=True)
    parent_label = input_tag.find_parent("label")
    if parent_label:
        return parent_label.get_text(" ", strip=True)
    return None


def _visible_text(element: Tag) -> str:
    texts: list[str] = []
    for node in element.descendants:
        if isinstance(node, Tag):
            if node.name in {"script", "style", "template"}:
                continue
            if is_hidden_element(node) or is_noise_container(node):
                continue
        elif getattr(node, "strip", None):
            parent = getattr(node, "parent", None)
            if isinstance(parent, Tag) and (
                parent.name in {"script", "style", "template"} or is_hidden_element(parent) or is_noise_container(parent)
            ):
                continue
            text = str(node).strip()
            if text:
                texts.append(text)
    return " ".join(texts).lower()


def _element_text_blob(element: Tag, visible_text: str) -> str:
    texts = [visible_text]
    for attr in ("id", "class", "name", "aria-label", "data-testid", "placeholder", "title"):
        value = element.get(attr)
        if isinstance(value, list):
            texts.append(" ".join(value))
        elif value:
            texts.append(str(value))
    return " ".join(texts).lower()


def _element_attr_blob(element: Tag) -> str:
    texts = []
    for attr in ("id", "class", "name", "aria-label", "data-testid", "title", "style"):
        value = element.get(attr)
        if isinstance(value, list):
            texts.append(" ".join(str(item) for item in value))
        elif value:
            texts.append(str(value))
    return " ".join(texts).lower()


def _is_hidden_input(input_tag: Tag) -> bool:
    if (input_tag.get("type") or "").lower() == "hidden" or is_hidden_element(input_tag):
        return True
    identifier = " ".join(filter(None, [input_tag.get("name"), input_tag.get("id"), input_tag.get("autocomplete")]))
    return bool(METADATA_INPUT_RE.search(identifier))


def _unique_fields(fields: list[ExtractedField]) -> list[ExtractedField]:
    unique: list[ExtractedField] = []
    seen: set[tuple[str, Optional[str], Optional[str]]] = set()
    for field in fields:
        key = (field.type, field.label, field.name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(field)
    return unique


def _unique_actions(actions: list[ExtractedAction]) -> list[ExtractedAction]:
    unique: list[ExtractedAction] = []
    seen: set[tuple[str, str, Optional[str]]] = set()
    for action in actions:
        key = (action.type, action.label, action.provider)
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
    return unique
