"""Notification texts, in the language of Home Assistant."""

from collections.abc import Sequence
from dataclasses import dataclass
import re

PROBLEMS = ("critical", "low", "not_responding", "stale")
RECOVERED = "recovered"
# Characters that Markdown could read as formatting or links.
MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~])")

CATALOGUE: dict[str, dict[str, str]] = {
    "en": {
        "title": "Battery Care",
        "critical": "battery critical",
        "low": "battery low",
        "not_responding": "not responding",
        "stale": "data may be outdated",
        "recovered": "back to normal",
        "level": "{level}% left",
        "attention_one": "1 battery needs attention:",
        "attention_other": "{count} batteries need attention:",
        "recovered_title": "Back to normal:",
        "open": "Open Battery Care",
        "test": "Battery Care can reach this device. Alerts will look like this.",
    },
    "fr": {
        "title": "Battery Care",
        "critical": "batterie critique",
        "low": "batterie faible",
        "not_responding": "ne répond plus",
        "stale": "données peut-être anciennes",
        "recovered": "de retour à la normale",
        "level": "{level}\u202f% restants",
        "attention_one": "1 batterie demande votre attention :",
        "attention_other": "{count} batteries demandent votre attention :",
        "recovered_title": "De retour à la normale :",
        "open": "Ouvrir Battery Care",
        "test": "Battery Care peut joindre cet appareil. Les alertes ressembleront "
        "à ce message.",
    },
}


@dataclass(frozen=True, slots=True)
class Line:
    """One battery in a notification."""

    name: str
    status: str
    level: float | None = None
    area: str | None = None
    battery: str | None = None


def language_of(code: str) -> str:
    """Return the catalogue for a Home Assistant language, English by default."""
    base = code.partition("-")[0].lower()
    return base if base in CATALOGUE else "en"


def escape_markdown(text: str) -> str:
    """Make text from devices show literally in a Markdown notification."""
    return MARKDOWN.sub(r"\\\1", text)


def _line(line: Line, words: dict[str, str], markdown: bool) -> str:
    def literal(text: str) -> str:
        return escape_markdown(text) if markdown else text

    text = f"{literal(line.name)}: {words[line.status]}"
    # A silent device's last level would read as a current one.
    if line.level is not None and line.status in ("critical", "low"):
        text += ", " + words["level"].format(level=round(line.level))
    extras = [literal(extra) for extra in (line.area, line.battery) if extra]
    return " · ".join([text, *extras])


def compose(lines: Sequence[Line], language: str, *, markdown: bool) -> str:
    """Return the body of a notification about one or more batteries.

    Args:
        lines: the batteries, problems first, then those back to normal.
        language: a catalogue language.
        markdown: escape device texts for Home Assistant notifications.
    """
    words = CATALOGUE[language]
    problems = [line for line in lines if line.status != RECOVERED]
    recovered = [line for line in lines if line.status == RECOVERED]
    if len(lines) == 1:
        parts = [_line(lines[0], words, markdown)]
    else:
        parts = []
        if problems:
            header = (
                words["attention_one"]
                if len(problems) == 1
                else words["attention_other"].format(count=len(problems))
            )
            parts.append(
                "\n".join(
                    [
                        header,
                        *(f"• {_line(line, words, markdown)}" for line in problems),
                    ]
                )
            )
        if recovered:
            parts.append(
                "\n".join(
                    [
                        words["recovered_title"],
                        *(f"• {_line(line, words, markdown)}" for line in recovered),
                    ]
                )
            )
    if markdown:
        parts.append(f"[{words['open']}](/battery-care)")
    return "\n\n".join(parts)
