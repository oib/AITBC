"""MSG-4b — one display rule for chain-sourced text, both implementations.

``aitbc.textsafety.sanitize_chain_text`` (CLI, MCP) and
``website/messages.js`` ``sanitizeChainText`` (browser) must agree: every
Unicode format character (Cf) plus U+061C, U+180E and the tag block becomes a
visible ``[U+XXXX]`` placeholder. The parity test extracts the real regex and
replacement function from the shipped JS file and runs them in ``node`` on the
same vector list (skipped when no JS engine is on PATH).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from aitbc.textsafety import sanitize_chain_obj, sanitize_chain_text

REPO = Path(__file__).resolve().parents[2]
MSG_JS = REPO / "website" / "messages.js"


# Hostile vectors, one per class from the MSG-4b finding. Each entry is
# (label, input, expected_output) — expected is what BOTH implementations
# must produce.
def _c(n: int) -> str:
    return chr(n)


def _tag(n: int) -> str:
    return chr(0xE0000 + n)


# literal invisible chars would be invisible here too — every vector spells
# its codepoints explicitly so the table stays reviewable.
VECTORS: list[tuple[str, str, str]] = [
    ("soft hyphen", f"soft{_c(0x00AD)}hyphen", "soft[U+00AD]hyphen"),
    ("word joiner", f"a{_c(0x2060)}b", "a[U+2060]b"),
    ("invisible plus", f"1{_c(0x2063)}2", "1[U+2063]2"),
    ("invisible times", f"1{_c(0x2062)}2", "1[U+2062]2"),
    ("arabic letter mark", f"mix{_c(0x061C)}ed", "mix[U+061C]ed"),
    ("mongolian vowel sep", f"a{_c(0x180E)}b", "a[U+180E]b"),
    ("bidi override", f"x{_c(0x202E)}y{_c(0x202C)}z", "x[U+202E]y[U+202C]z"),
    ("bidi isolate", f"x{_c(0x2066)}y{_c(0x2069)}z", "x[U+2066]y[U+2069]z"),
    ("zero-width space", f"a{_c(0x200B)}b", "a[U+200B]b"),
    ("bom", f"a{_c(0xFEFF)}b", "a[U+FEFF]b"),
    ("interlinear anchor", f"a{_c(0xFFF9)}b", "a[U+FFF9]b"),
    ("language tag char", f"a{_tag(1)}b", "a[U+E0001]b"),
    (
        "tag-spelled hidden word",
        f"see {_tag(0x73)}{_tag(0x65)}{_tag(0x63)}{_tag(0x72)}{_tag(0x65)}{_tag(0x74)}",
        "see [U+E0073][U+E0065][U+E0063][U+E0072][U+E0065][U+E0074]",
    ),
    ("tag char mid-word", f"wo{_tag(0x41)}rd", "wo[U+E0041]rd"),
    ("cancel tag", f"a{_tag(0x7F)}b", "a[U+E007F]b"),
    ("mixed bidi+tag", f"{_c(0x202E)}secret{_tag(0x21)}{_c(0x202C)}", "[U+202E]secret[U+E0021][U+202C]"),
    ("c1 NEL", f"a{_c(0x0085)}b", "a[U+0085]b"),
    ("c1 padding", f"a{_c(0x0080)}b", "a[U+0080]b"),
    ("plain text untouched", "hello world 123", "hello world 123"),
    ("emoji untouched", "vote \u2705", "vote \u2705"),
    ("newline untouched", "line1\nline2", "line1\nline2"),
]


def _extract_js_sanitizer() -> str:
    """Slice NEUTRAL_RE + sanitizeChainText verbatim out of messages.js."""
    src = MSG_JS.read_text(encoding="utf-8")
    m = re.search(
        r"const NEUTRAL_RE = [^;]+;[\s\S]*?function sanitizeChainText[\s\S]*?\n    \}",
        src,
    )
    if not m:
        raise AssertionError("could not extract sanitizer from messages.js")
    return m.group(0)


class TestSanitizeChainText(unittest.TestCase):
    def test_vectors_python(self) -> None:
        for label, raw, expected in VECTORS:
            with self.subTest(label=label):
                self.assertEqual(expected, sanitize_chain_text(raw))

    def test_every_cf_char_replaced(self) -> None:
        import unicodedata

        # every BMP Cf char must produce a placeholder (astral Cf covered by
        # the tag-block vectors above)
        for cp in range(0x10000):
            ch = chr(cp)
            if unicodedata.category(ch) == "Cf":
                with self.subTest(cp=hex(cp)):
                    self.assertEqual(f"[U+{cp:04X}]", sanitize_chain_text(ch))

    def test_obj_recursion(self) -> None:
        obj = {"body": "a​b", "items": [{"topic": "x⁠y"}, "⁠"], "n": 5}
        out = sanitize_chain_obj(obj)
        self.assertEqual("a[U+200B]b", out["body"])
        self.assertEqual("x[U+2060]y", out["items"][0]["topic"])
        self.assertEqual("[U+2060]", out["items"][1])
        self.assertEqual(5, out["n"])

    @unittest.skipUnless(shutil.which("node"), "skipped: no node on PATH")
    def test_js_parity(self) -> None:
        """Feed the same vector list to the shipped JS sanitizer via node."""
        js = _extract_js_sanitizer()
        script = (
            js
            + "\nconst vec = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
            + "\nprocess.stdout.write(JSON.stringify(vec.map(sanitizeChainText)));"
        )
        inputs = [raw for _label, raw, _exp in VECTORS]
        proc = subprocess.run(
            ["node", "-e", script],
            input=json.dumps(inputs),
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        js_out = json.loads(proc.stdout)
        for (label, _raw, expected), got in zip(VECTORS, js_out, strict=True):
            with self.subTest(label=label):
                self.assertEqual(expected, got, f"JS disagrees on {label}")

    def test_js_regex_is_the_pinned_rule(self) -> None:
        src = MSG_JS.read_text(encoding="utf-8")
        self.assertIn(r"\p{Cf}", src)
        self.assertIn(r"\u0080-\u009F", src)
        self.assertIn(r"\u061C", src)
        self.assertIn(r"\u180E", src)
        self.assertIn("E0000", src)
        self.assertIn("gu;", src, "the regex needs the unicode + global flags")


if __name__ == "__main__":
    unittest.main()
