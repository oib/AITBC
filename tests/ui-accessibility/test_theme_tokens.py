"""Programmatic contrast validation for AITBC theme tokens (v0.17.0 §B4)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest


def _parse_hex(color: str) -> tuple[int, int, int]:
    """Convert a hex color string to an (r, g, b) tuple."""
    color = color.strip().lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Return the relative luminance of an sRGB color."""

    def channel(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast_ratio(a: str, b: str) -> float:
    """Return the WCAG contrast ratio between two hex colors."""
    lum_a = _relative_luminance(_parse_hex(a))
    lum_b = _relative_luminance(_parse_hex(b))
    lighter = max(lum_a, lum_b)
    darker = min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def _parse_tokens(css_path: Path) -> dict[str, dict[str, str]]:
    """Parse theme blocks from tokens.css into {selector: {var: value}}."""
    text = css_path.read_text(encoding="utf-8")
    # Remove comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    blocks: dict[str, dict[str, str]] = {}
    current_selector: str | None = None
    current_declarations: dict[str, str] = {}

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.endswith("{"):
            if current_selector is not None:
                if current_selector in blocks:
                    blocks[current_selector].update(current_declarations)
                else:
                    blocks[current_selector] = current_declarations
            current_selector = stripped[:-1].strip()
            current_declarations = {}
        elif stripped == "}":
            if current_selector is not None:
                if current_selector in blocks:
                    blocks[current_selector].update(current_declarations)
                else:
                    blocks[current_selector] = current_declarations
            current_selector = None
            current_declarations = {}
        elif current_selector is not None and stripped.endswith(";"):
            match = re.match(r"(--[\w-]+)\s*:\s*([^;]+);?", stripped)
            if match:
                current_declarations[match.group(1)] = match.group(2).strip()

    return blocks


@pytest.fixture()
def tokens() -> dict[str, dict[str, str]]:
    css_path = Path(__file__).parents[2] / "packages" / "theme-provider" / "src" / "tokens.css"
    return _parse_tokens(css_path)


def _value_for(block: dict[str, str], variable: str) -> str | None:
    raw = block.get(variable)
    if raw and raw.startswith("var("):
        inner = raw[4:-1].strip()
        raw = block.get(inner, raw)
    return raw


def _assert_contrast(
    tokens: dict[str, dict[str, str]],
    selector: str,
    foreground_var: str,
    background_var: str,
    min_ratio: float,
) -> None:
    block = tokens.get(selector)
    assert block, f"Missing theme block {selector}"
    fg = _value_for(block, foreground_var)
    bg = _value_for(block, background_var)
    assert fg and bg, f"Missing colors in {selector}: {foreground_var}={fg}, {background_var}={bg}"
    assert fg.startswith("#") and bg.startswith("#")
    ratio = _contrast_ratio(fg, bg)
    assert ratio >= min_ratio, (
        f"{selector}: {foreground_var} ({fg}) on {background_var} ({bg}) has contrast {ratio:.2f}, required {min_ratio}"
    )


@pytest.mark.parametrize(
    "selector",
    [":root", '[data-aitbc-theme="light"]', '[data-aitbc-theme="high-contrast"]'],
)
def test_primary_text_contrast(tokens: dict[str, Any], selector: str) -> None:
    _assert_contrast(tokens, selector, "--color-text-primary", "--color-bg-primary", 4.5)


@pytest.mark.parametrize(
    "selector",
    [":root", '[data-aitbc-theme="light"]', '[data-aitbc-theme="high-contrast"]'],
)
def test_accent_text_contrast(tokens: dict[str, Any], selector: str) -> None:
    _assert_contrast(tokens, selector, "--color-text-accent", "--color-bg-primary", 4.5)
