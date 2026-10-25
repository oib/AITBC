"""Mask secret-bearing argument values in echoed command lines (MCP-ECHO-1).

Every result and dry-run envelope echoes the command that ran or would run,
so a secret passed on argv lands in the agent transcript, the client log and
the dry-run preview. :func:`mask_envelope` is applied by
``aitbc_mcp_server._json`` -- the one serialisation step every tool module
returns through -- so it only ever sees the echoed copy: the argv handed to
``subprocess`` is built and executed before serialisation and never passes
through here.

Masking is by name and position: the value after a secret-named option
(``--api-key=v`` / ``--password v``), ``NAME=value`` pairs (env prefixes,
``env-set`` positionals, query strings, ``--params``), URL userinfo
passwords, ``Authorization``/``X-API-Key``-style header values, ``Bearer``
tokens and secret-named keys inside JSON blobs. Option names stay, so the
echo still shows what ran. Value shapes alone never trigger a mask: a bare
64-hex string is a tx/block hash unless a secret-named option sits next to it.

``_scrub_secrets`` in ``aitbc_mcp_rpc_tools`` stays separate on purpose: it
replaces *known values* anywhere in the serialized output (stdout included),
while this module masks by pattern in the echo fields only.
"""

from __future__ import annotations

import json
import re
import shlex
from typing import Any

# --- secret-name patterns ----------------------------------------------------
# Copied from ``aitbc_cli.commands.system`` (the env-set/field deny list) so
# the MCP server does not need ``aitbc_cli`` on its path to start.
# ``tests/test_aitbc_mcp_echo_mask.py`` imports the CLI originals and fails
# when this copy drifts from them.
_FIELD_DENY_NAMES = frozenset({"private_key", "secret", "password", "token", "mnemonic", "seed", "key", "api_key"})
_FIELD_DENY_NORMALIZED = frozenset({"privatekey", "apikey", "secretkey", "passphrase", "passwd", "credential", "credentials"})
_FIELD_DENY_KEY_PREFIXES = ("private", "secret", "api", "auth", "signing", "access")
_FIELD_DENY_TOKENS = frozenset(
    {
        "pass",
        "password",
        "passwd",
        "pwd",
        "passphrase",
        "secret",
        "token",
        "key",
        "keys",
        "private",
        "credential",
        "credentials",
        "auth",
        "signing",
        "mnemonic",
        "seed",
        "dsn",
        "url",
        "uri",
        "secrets",
        "passwords",
        "tokens",
        "apikeys",
        "pw",
        "bearer",
        "cookie",
        "cookies",
        "privkey",
        "seedphrase",
        "salt",
    }
)
_FIELD_DENY_SUFFIXES = (
    "password",
    "passwd",
    "passphrase",
    "pwd",
    "secret",
    "token",
    "private",
    "credential",
    "credentials",
    "mnemonic",
    "seed",
    "dsn",
    "secrets",
    "passwords",
    "tokens",
    "apikeys",
    "cookie",
    "cookies",
    "bearer",
    "authorization",
    "privkey",
    "seedphrase",
)
_FIELD_DENY_TAIL = ("_url", "_uri", "_dsn")
_CONN_STRING_TOKENS = frozenset({"url", "uri", "dsn"})
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _field_tokens(name: str) -> list[str]:
    return [t.lower() for t in re.split(r"[_-]+", _CAMEL_BOUNDARY.sub("_", name)) if t]


def _deny_token_hit(tokens: list[str], deny_conn_strings: bool) -> bool:
    return any(token in _FIELD_DENY_TOKENS and (deny_conn_strings or token not in _CONN_STRING_TOKENS) for token in tokens)


def _field_name_denied(name: str, *, deny_conn_strings: bool = True) -> bool:
    lowered = name.lower()
    normalized = lowered.replace("-", "").replace("_", "")
    tokens = _field_tokens(name)
    return (
        lowered in _FIELD_DENY_NAMES
        or normalized in _FIELD_DENY_NORMALIZED
        or (deny_conn_strings and lowered.endswith(_FIELD_DENY_TAIL))
        or _deny_token_hit(tokens, deny_conn_strings)
        or (normalized.endswith("key") and normalized[:-3] in _FIELD_DENY_KEY_PREFIXES)
        or (len(tokens) == 1 and normalized.endswith(_FIELD_DENY_SUFFIXES))
    )


MARKER = "<redacted>"

# Envelope keys that carry a command line (string or argv list).
ECHO_KEYS = frozenset({"command", "cmd", "argv", "remote_command", "would_run"})
# Envelope keys whose free text may quote a command token (e.g. the
# ``_safe_command`` refusal names the offending token).
TEXT_KEYS = frozenset({"error", "details"})

# Shell-safe placeholder: ``shlex.quote`` leaves it bare, so the marker is
# swapped in after quoting and never shows up wrapped in quotes.
_SENTINEL = "AITBCMCPREDACTED0"
_SHELL_OPERATORS = frozenset({"&&", "||", "|", ";"})

# Public identifiers whose names trip the deny patterns (the "key" token)
# but whose values must stay visible: ``access_key`` is the public half of a
# key/secret pair (kept by MCP-SECRETS-1), public keys are public.
_KEEP_NAMES = frozenset({"access_key", "public_key", "pubkey", "pub_key"})
# A name ending in one of these takes a path or is a flag (``--password-stdin``,
# ``--private-key-file``, ``AITBC_WALLET_DIR``): the value is not the secret.
_KEEP_LAST_TOKENS = frozenset({"file", "path", "dir", "stdin"})

_USERINFO_RE = re.compile(r"(?P<head>[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]*):(?P<pw>[^/\s@]+)@")
_PAIR_RE = re.compile(r"(?P<lead>^|[?&;])(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)=(?P<value>[^&#;\s]*)")
_HEADER_RE = re.compile(
    r"(?P<name>\b(?:proxy-)?authorization|\bset-cookie|\bcookie|\bx-[a-z0-9-]*(?:key|token|secret|auth)[a-z0-9-]*)"
    r"(?P<sep>\s*:\s*)(?P<value>[^\r\n\"']+)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"\b(?P<scheme>bearer|basic|token)(?P<sep>\s+)(?P<value>[A-Za-z0-9._~+/=-]+)", re.IGNORECASE)
_QUOTED_PAIR_RE = re.compile(r"(?P<q>[\"'])(?P<name>[A-Za-z0-9_.-]+)(?P=q)(?P<sep>\s*:\s*)(?P<vq>[\"'])(?P<value>.*?)(?P=vq)")
# Fallback only: a quoted key whose value may be cut off by an unbalanced quote
# (``--body={"api_key": "zzz``).
_LOOSE_PAIR_RE = re.compile(r"(?P<q>[\"'])(?P<name>[A-Za-z0-9_.-]+)(?P=q)(?P<sep>\s*:\s*)(?P<vq>[\"']?)(?P<value>[^\"',}\s]+)")
_OPTION_TEXT_RE = re.compile(r"(?P<name>(?<![\w-])--?[A-Za-z][A-Za-z0-9_-]*)(?P<sep>=|\s+)(?P<value>[^\s\"']+)")


def secret_name(name: str) -> bool:
    """True when an option, env or key name marks its value as a secret."""
    bare = name.lstrip("-")
    if not bare:
        return False
    if bare.lower().replace("-", "_") in _KEEP_NAMES:
        return False
    tokens = [t for t in re.split(r"[_.-]+", bare.lower()) if t]
    if not tokens or tokens[-1] in _KEEP_LAST_TOKENS:
        return False
    return _field_name_denied(bare, deny_conn_strings=False)


def _mask_json(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: (_SENTINEL if isinstance(key, str) and secret_name(key) and value not in (None, "") else _mask_json(value))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_mask_json(item) for item in node]
    if isinstance(node, str):
        return _mask_value(node)
    return node


def _mask_value(value: str) -> str:
    """Mask secrets embedded in a single argument value."""
    stripped = value.strip()
    if stripped[:1] in ("{", "["):
        try:
            parsed = json.loads(stripped)
        except ValueError:
            pass
        else:
            masked = _mask_json(parsed)
            return value if masked == parsed else json.dumps(masked)
    value = _USERINFO_RE.sub(lambda m: f"{m['head']}:{_SENTINEL}@", value)
    value = _PAIR_RE.sub(
        lambda m: f"{m['lead']}{m['name']}={_SENTINEL}" if m["value"] and secret_name(m["name"]) else m.group(0),
        value,
    )
    value = _QUOTED_PAIR_RE.sub(
        lambda m: (
            f"{m['q']}{m['name']}{m['q']}{m['sep']}{m['vq']}{_SENTINEL}{m['vq']}"
            if m["value"] and secret_name(m["name"])
            else m.group(0)
        ),
        value,
    )
    value = _HEADER_RE.sub(lambda m: f"{m['name']}{m['sep']}{_SENTINEL}", value)
    value = _BEARER_RE.sub(lambda m: f"{m['scheme']}{m['sep']}{_SENTINEL}", value)
    return value


def _is_option(token: str) -> bool:
    return token.startswith("-") and len(token) > 1 and not token[1:2].isdigit() and token != "--"


def _mask_tokens(tokens: list[str]) -> list[str]:
    out: list[str] = []
    value_is_secret = False
    for token in tokens:
        if value_is_secret and not _is_option(token) and token not in _SHELL_OPERATORS:
            out.append(_SENTINEL)
            value_is_secret = False
            continue
        value_is_secret = False
        if _is_option(token):
            name, eq, value = token.partition("=")
            if not eq:
                value_is_secret = secret_name(name)
                out.append(token)
            elif value and secret_name(name):
                out.append(f"{name}={_SENTINEL}")
            else:
                out.append(f"{name}={_mask_value(value)}")
            continue
        out.append(_mask_value(token))
    return out


def _join(tokens: list[str]) -> str:
    return " ".join(token if token in _SHELL_OPERATORS else shlex.quote(token) for token in tokens)


def _mask_text_fallback(text: str) -> str:
    """Regex-only masking for strings ``shlex`` cannot split (unbalanced quotes)."""
    text = _OPTION_TEXT_RE.sub(
        lambda m: f"{m['name']}{m['sep']}{_SENTINEL}" if secret_name(m["name"]) else m.group(0),
        text,
    )
    text = _LOOSE_PAIR_RE.sub(
        lambda m: f"{m['q']}{m['name']}{m['q']}{m['sep']}{m['vq']}{_SENTINEL}" if secret_name(m["name"]) else m.group(0),
        text,
    )
    return " ".join(_mask_value(part) for part in text.split(" "))


def mask_command(command: str | list[str]) -> str | list[str]:
    """Return the echo copy of *command* with secret values replaced by ``<redacted>``.

    A string is tokenised with ``shlex`` and re-joined only when something was
    masked, so an echo without secrets is returned unchanged. A list stays a
    list, masked per element. The caller's object is never modified.
    """
    if isinstance(command, list):
        masked_list = _mask_tokens([str(item) for item in command])
        return [item.replace(_SENTINEL, MARKER) for item in masked_list]
    try:
        tokens = shlex.split(command)
    except ValueError:
        fallback = _mask_text_fallback(command)
        return command if _SENTINEL not in fallback else fallback.replace(_SENTINEL, MARKER)
    masked = _mask_tokens(tokens)
    if masked == tokens:
        return command
    return _join(masked).replace(_SENTINEL, MARKER)


def _mask_text(value: Any) -> Any:
    if isinstance(value, str):
        return mask_command(value)
    if isinstance(value, list):
        return [_mask_text(item) if isinstance(item, str) else mask_envelope(item) for item in value]
    return mask_envelope(value)


def mask_envelope(result: Any) -> Any:
    """Return a copy of *result* with every echoed command and quoted token masked."""
    if isinstance(result, dict):
        masked: dict[Any, Any] = {}
        for key, value in result.items():
            if key in ECHO_KEYS and (
                isinstance(value, str) or (isinstance(value, list) and all(isinstance(v, str) for v in value))
            ):
                masked[key] = mask_command(value)
            elif key in TEXT_KEYS:
                masked[key] = _mask_text(value)
            else:
                masked[key] = mask_envelope(value)
        return masked
    if isinstance(result, list):
        return [mask_envelope(item) for item in result]
    return result
