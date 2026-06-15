from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import spacy
from spacy.language import Language

from .patterns import PATTERNS

# SpaCy entity labels that map to PII
_NER_LABEL_MAP = {
    "PERSON": "[REDACTED_NAME]",
    "GPE":    "[REDACTED_LOCATION]",
    "LOC":    "[REDACTED_LOCATION]",
    "ORG":    "[REDACTED_ORG]",
}


@lru_cache(maxsize=1)
def _load_nlp() -> Language:
    return spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])


@dataclass
class RedactionResult:
    text: str
    redacted_types: list[str] = field(default_factory=list)
    pii_detected: bool = False


def _redact_text(text: str) -> RedactionResult:
    result = RedactionResult(text=text)

    # Pass 1 — deterministic regex (fast, zero false-positives for known patterns)
    for pattern, label in PATTERNS:
        if pattern.search(result.text):
            result.text = pattern.sub(label, result.text)
            tag = label.strip("[]")
            if tag not in result.redacted_types:
                result.redacted_types.append(tag)

    # Pass 2 — SpaCy NER for names, locations, orgs regex can't catch
    nlp = _load_nlp()
    doc = nlp(result.text)
    # Iterate in reverse so char offsets stay valid after substitution
    for ent in reversed(doc.ents):
        replacement = _NER_LABEL_MAP.get(ent.label_)
        if replacement:
            result.text = result.text[: ent.start_char] + replacement + result.text[ent.end_char :]
            tag = replacement.strip("[]")
            if tag not in result.redacted_types:
                result.redacted_types.append(tag)

    result.pii_detected = bool(result.redacted_types)
    return result


def redact_messages(messages: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Mutates message dicts in-place. Returns (messages, all_redacted_types).
    Call this before litellm.acompletion() — no PII ever reaches the HTTP layer.
    """
    all_types: list[str] = []
    for msg in messages:
        if not isinstance(msg.get("content"), str):
            continue
        result = _redact_text(msg["content"])
        msg["content"] = result.text
        for t in result.redacted_types:
            if t not in all_types:
                all_types.append(t)
    return messages, all_types
