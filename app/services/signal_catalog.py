"""Shared deterministic signal lexicon for parser and node profiling."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SignalLexicon:
    name: str
    phrases: tuple[str, ...]
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class SignalMatch:
    signal_name: str
    matched_text: str
    match_type: str


SIGNAL_LEXICONS: dict[str, SignalLexicon] = {
    "mental_load": SignalLexicon(
        name="mental_load",
        phrases=(
            "heavy debugging session",
            "brain feels empty",
            "feel drained",
            "feel tired",
            "\u5b66\u4e86\u5f88\u4e45",
            "\u8111\u529b\u6d3b",
            "\u8111\u5b50\u5f88\u7d2f",
            "\u8111\u5b50\u9ebb\u4e86",
            "\u70e7\u8111",
        ),
        tokens=(
            "debug",
            "debugging",
            "study",
            "coding",
            "drained",
            "burned",
            "tired",
            "\u8c03\u8bd5",
            "\u5f88\u7d2f",
        ),
    ),
    "recovery": SignalLexicon(
        name="recovery",
        phrases=(
            "took a nap",
            "feel recovered",
            "\u7f13\u8fc7\u6765\u4e86",
            "\u6062\u590d\u4e86",
            "\u6b47\u4e00\u4e0b",
        ),
        tokens=(
            "sleep",
            "nap",
            "rest",
            "break",
            "recovered",
            "\u7761\u4e86",
            "\u5348\u7761",
            "\u4f11\u606f",
        ),
    ),
    "movement": SignalLexicon(
        name="movement",
        phrases=(
            "went for a walk",
            "\u8d70\u4e86\u8d70",
        ),
        tokens=(
            "walk",
            "ride",
            "run",
            "exercise",
            "workout",
            "\u6563\u6b65",
            "\u9a91\u8f66",
            "\u8dd1\u6b65",
            "\u8fd0\u52a8",
            "\u953b\u70bc",
        ),
    ),
    "light_admin": SignalLexicon(
        name="light_admin",
        phrases=(
            "clean up inbox",
            "clean up email",
        ),
        tokens=(
            "organize",
            "cleanup",
            "inbox",
            "tidy",
            "archive",
            "\u6574\u7406",
            "\u6536\u62fe",
            "\u6e05\u7406",
            "\u5f52\u6863",
            "\u6536\u90ae\u4ef6",
        ),
    ),
    "coordination": SignalLexicon(
        name="coordination",
        phrases=(
            "team sync",
            "\u6253\u7535\u8bdd",
        ),
        tokens=(
            "call",
            "meeting",
            "sync",
            "discussion",
            "\u5f00\u4f1a",
            "\u6c9f\u901a",
            "\u540c\u6b65",
            "\u8ba8\u8bba",
            "\u7535\u8bdd",
        ),
    ),
    "deep_focus": SignalLexicon(
        name="deep_focus",
        phrases=(
            "write report",
            "write proposal",
        ),
        tokens=(
            "study",
            "coding",
            "debug",
            "writing",
            "research",
            "review",
            "report",
            "plan",
            "proposal",
            "\u590d\u4e60",
            "\u5199\u62a5\u544a",
            "\u62a5\u544a",
            "\u8c03\u8bd5",
            "\u7814\u7a76",
            "\u590d\u76d8",
            "\u65b9\u6848",
        ),
    ),
}

PARSER_SIGNAL_PRIORITY = (
    "mental_load",
    "recovery",
    "movement",
    "coordination",
    "light_admin",
)


def normalize_signal_text(text: str) -> str:
    """Lowercase and collapse whitespace for deterministic matching."""

    return re.sub(r"\s+", " ", text.strip().lower())


def _contains_ascii_token(normalized_text: str, token: str) -> bool:
    pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def _contains_token(normalized_text: str, token: str) -> bool:
    if token.isascii():
        return _contains_ascii_token(normalized_text, token)
    return token in normalized_text


def _match_signal_type(
    normalized_text: str,
    signal_name: str,
    *,
    match_type: str,
) -> SignalMatch | None:
    lexicon = SIGNAL_LEXICONS[signal_name]
    candidates = lexicon.phrases if match_type == "phrase" else lexicon.tokens

    for candidate in candidates:
        matched = candidate in normalized_text if match_type == "phrase" else _contains_token(normalized_text, candidate)
        if matched:
            return SignalMatch(signal_name=signal_name, matched_text=candidate, match_type=match_type)

    return None


def find_first_parser_signal(text: str) -> SignalMatch | None:
    """Find the highest-priority parser signal, preferring phrases before tokens."""

    normalized_text = normalize_signal_text(text)
    if not normalized_text:
        return None

    for match_type in ("phrase", "token"):
        for signal_name in PARSER_SIGNAL_PRIORITY:
            match = _match_signal_type(normalized_text, signal_name, match_type=match_type)
            if match is not None:
                return match

    return None


def collect_signal_names(*values: str) -> set[str]:
    """Collect every matched signal from one or more text fragments."""

    normalized_text = normalize_signal_text(" ".join(value for value in values if value))
    if not normalized_text:
        return set()

    matched_signals: set[str] = set()
    for signal_name in SIGNAL_LEXICONS:
        if _match_signal_type(normalized_text, signal_name, match_type="phrase") is not None:
            matched_signals.add(signal_name)
            continue
        if _match_signal_type(normalized_text, signal_name, match_type="token") is not None:
            matched_signals.add(signal_name)

    return matched_signals
