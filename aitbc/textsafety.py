"""Display-layer sanitiser for chain-sourced text (MSG-4b).

One rule, applied wherever a forum/message body or topic reaches a human or
an agent: every Unicode format character (general category ``Cf``) plus the
explicitly listed extras is replaced by a visible ``[U+XXXX]`` placeholder —
the full code point, uppercase hex, minimum four digits. Invisible or
reordering code points (soft hyphen, word joiner, invisible operators, bidi
controls, the astral tag block U+E0000-U+E007F, …) can make rendered text lie
about its bytes and can smuggle hidden instructions to agents reading bodies
through the CLI/MCP tools. Replacing them keeps the byte content inspectable
instead of silently dropped or trusted.

Display only: the wire format, admission predicates and stored bodies are
unchanged; raw bodies stay raw in RPC responses.

The JavaScript copy of this rule lives in ``website/messages.js``
(``sanitizeChainText``) and is pinned to the same vector list by
``tests/unit/test_textsafety.py``.
"""

from __future__ import annotations

import unicodedata
from typing import Any

# U+061C (Arabic letter mark) and U+180E (Mongolian vowel separator) are Cf in
# current Unicode; the tag block U+E0000-U+E007F is Cf too. Listing them
# explicitly keeps the rule stable even if a Unicode update reclassifies one.
# The C1 control range U+0080-U+009F is category Cc — the MSG-FIX-2 admission
# surface neutralised them and they are kept here so this rule never regresses.
_EXTRA_CODEPOINTS = frozenset(
    {0x061C, 0x180E} | set(range(0x0080, 0x00A0)) | set(range(0xE0000, 0xE0080))
)


def _is_invisible(ch: str) -> bool:
    return unicodedata.category(ch) == "Cf" or ord(ch) in _EXTRA_CODEPOINTS


def sanitize_chain_text(value: object) -> str:
    """Return ``value`` as a string with invisible code points made visible."""
    return "".join(f"[U+{ord(ch):04X}]" if _is_invisible(ch) else ch for ch in str(value))


def sanitize_chain_obj(obj: Any) -> Any:
    """Recursively sanitise every string inside a JSON-shaped object."""
    if isinstance(obj, str):
        return sanitize_chain_text(obj)
    if isinstance(obj, dict):
        return {k: sanitize_chain_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_chain_obj(v) for v in obj]
    return obj
