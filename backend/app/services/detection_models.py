from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from bs4 import Tag


@dataclass
class ExtractedField:
    type: str
    label: Optional[str] = None
    name: Optional[str] = None
    selector_hint: Optional[str] = None
    required: bool = False


@dataclass
class ExtractedAction:
    type: str
    label: str
    provider: Optional[str] = None
    selector_hint: Optional[str] = None


@dataclass
class AuthComponent:
    type: str
    surface_type: Optional[str]
    confidence: float
    selector_hint: Optional[str]
    signals: list[str]
    providers: list[str]
    fields: list[ExtractedField]
    snippet: Optional[str]
    summary: str


@dataclass
class DetectionResult:
    found: bool
    confidence: float
    signals: list[str]
    snippet: Optional[str]
    message: str
    status: str = "not_found"
    surface_type: Optional[str] = None
    fields: list[ExtractedField] = field(default_factory=list)
    actions: list[ExtractedAction] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    components: list[AuthComponent] = field(default_factory=list)
    partial_html_markup: Optional[str] = None


@dataclass
class CandidateSignals:
    text_blob: str
    fields: list[ExtractedField]
    actions: list[ExtractedAction]
    providers: list[str]
    has_password: bool
    has_identity: bool
    has_submit: bool
    has_continue: bool
    has_passwordless: bool
    has_challenge: bool
    has_secondary: bool
    has_negative: bool
    has_auth_text: bool
    has_password_followup: bool
    meaningful_field_types: set[str]


@dataclass
class CandidateAnalysis:
    candidate: "CandidateModel"
    status: str
    component_type: str
    surface_type: str
    confidence: float
    score: int
    signals: list[str]
    snippet: str
    message: str
    selector_hint: Optional[str]


@dataclass
class CandidateModel:
    element: Tag
    text_blob: str
    attr_blob: str
    visible_text: str
    fields: list[ExtractedField]
    actions: list[ExtractedAction]
    providers: list[str]
    signals: CandidateSignals
