"""Notification texts in English and French."""

from custom_components.battery_care.core.messages import (
    Line,
    compose,
    escape_markdown,
    language_of,
)


def test_one_critical_battery() -> None:
    """Name, status, level, then the area and the battery when known."""
    battery = "2 \N{MULTIPLICATION SIGN} CR123A"
    line = Line("Front door", "critical", 6.4, "Entrance", battery)

    assert compose([line], "en", markdown=False) == (
        f"Front door: battery critical, 6% left · Entrance · {battery}"
    )
    assert compose([line], "fr", markdown=False) == (
        f"Front door: batterie critique, 6\u202f% restants · Entrance · {battery}"
    )


def test_a_digest_lists_problems_then_recoveries() -> None:
    """Problems under a counted header, then what is back to normal."""
    lines = [
        Line("Garage", "low", 17),
        Line("Attic", "not_responding", 60),
        Line("Kitchen", "recovered", 100),
    ]

    assert compose(lines, "en", markdown=False) == (
        "2 batteries need attention:\n"
        "• Garage: battery low, 17% left\n"
        "• Attic: not responding\n\n"
        "Back to normal:\n"
        "• Kitchen: back to normal"
    )
    assert compose(lines[:1] + lines[2:], "fr", markdown=False).startswith(
        "1 batterie demande votre attention :\n• Garage: batterie faible"
    )


def test_markdown_shows_device_texts_literally() -> None:
    """Names cannot add links or formatting; a link opens the panel."""
    line = Line("[Click](http://x) *now*", "stale", area="Hall_1")

    body = compose([line], "en", markdown=True)

    assert body == (
        r"\[Click\]\(http://x\) \*now\*: data may be outdated · Hall\_1"
        "\n\n[Open Battery Care](/battery-care)"
    )
    assert escape_markdown("v2.0 - #1") == r"v2\.0 \- \#1"


def test_the_language_follows_home_assistant() -> None:
    """Regional variants use their language; others fall back to English."""
    assert language_of("fr") == "fr"
    assert language_of("fr-CA") == "fr"
    assert language_of("de") == "en"
