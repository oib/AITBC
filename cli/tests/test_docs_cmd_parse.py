"""DOCS-CMD-PARSE-1: every `aitbc ...` line in live docs resolves in the click tree.

The extractor iterates document LINES (not a multi-line regex capture), so every
`aitbc ...` command line inside a fenced block is checked individually — the old
block capture only ever saw the first command of each block.

The resolver is click-aware: it walks subcommands, skips declared options
together with their values, and consumes positional ``click.Argument`` slots
(validating ``click.Choice`` values), so argument values like dispute ids or
tx hashes are not flagged — but a wrong subcommand, a stale option, or an
invalid choice value still fails.
"""

import re
import shlex
from pathlib import Path

import click

import aitbc_cli.core.main as main

REPO = Path(__file__).resolve().parents[2]
ALLOW_DIRS = {"releases", "archive"}
# Lines the extractor can't classify (continuation/pipe fragments).
ALLOW_SUBSTR = ("|", "&&", "\\")

# True parser fragments only — tokens that are not commands at all but get
# captured by the line extractor (fences, placeholders, the bare `aitbc`
# binary name). Generic words (list, add, test, dev, hello, 1, 2, ...) are
# deliberately NOT allowlisted here: a doc line `aitbc node bridge list`
# must fail when `list` is not a real subcommand.
# (file, lineno) whose quoting shlex can't parse — each must carry a reason
# in the ledger; a mutated token inside still fails via a sibling check.
UNPARSEABLE_ALLOW: set[tuple[str, int]] = set()

KNOWN_MISSES = {
    "```",  # fenced-block marker glued to an aitbc line
    "<COMMAND>",  # literal placeholder in usage docs
    "#",  # comment line inside a fenced block
    "aitbc",  # `aitbc aitbc ...` / aitbc-alone fragment
}

# Per-(command-path, option) stale-option allowlist — the old global
# KNOWN_OPTS word-mask let a stale flag pass on ANY command; each entry
# here pins the exact command path and carries its reason.
#   ("<space-separated command path>", "--flag"): "reason"
KNOWN_OPTS: dict[tuple[str, str], str] = {}

# Per-line allowlist for misses that must stay in the docs
# (planned/historical examples). Key: (doc-relpath, line-number, token).
KNOWN_LINE_MISSES: dict[tuple[str, int, str], str] = {}


def _doc_lines():
    """Yield (relpath, lineno, cmdline) for every line starting an `aitbc` cmd."""
    for f in sorted(REPO.glob("docs/**/*.md")):
        if ALLOW_DIRS & set(f.parts):
            continue
        for lineno, line in enumerate(f.read_text().splitlines(), 1):
            # cut shell plumbing (`2>&1`, `| grep`, `&&`, line continuations)
            # so a truncated fragment isn't parsed as part of the command.
            # `>` only counts as a redirect after whitespace — an unspaced
            # `>` is the closing bracket of a <placeholder>.
            line = re.sub(r"\d*>&?\d+", "", line)
            line = re.split(r"[|&\\]|(?<=\s)>", line, maxsplit=1)[0]
            # a `→`-joined line carries two commands; check each fragment.
            for frag in line.split("→"):
                m = re.match(
                    r"\s*(?:\$\s*)?(aitbc\s+(?:--[a-z\-]+\s.*|[a-z][a-z0-9_\-].*))",
                    frag,
                )
                if m:
                    # strip markdown/backtick decorations and inline comments
                    cmd = re.split(r"\s{2,}#|#\s", m.group(1))[0].rstrip("` ")
                    yield f.relative_to(REPO), lineno, cmd


def _find_option(node, tok):
    """Return the click.Option matching `--name` / `-n` token, else None."""
    want = tok.split("=")[0]
    pname = want.lstrip("-").replace("-", "_")
    for p in getattr(node, "params", []):
        if not isinstance(p, click.Option):
            continue
        # secondary_opts carries the negative half of `--pin/--no-pin` pairs
        if want in p.opts or want in getattr(p, "secondary_opts", []) or pname == p.name:
            return p
    return None


def _consume_option(node, tok, path):
    """Handle an option token: return (miss, tokens-consumed).

    ``miss`` is the offending flag for an unknown option (``--help`` and
    KNOWN_OPTS entries pass); ``tokens-consumed`` includes the option's
    declared value slots.
    """
    opt = _find_option(node, tok)
    if opt is None:
        if tok == "--help" or (path, tok.split("=")[0]) in KNOWN_OPTS:
            return None, 1
        return tok.split("=")[0], 0
    step = 1
    if not opt.is_flag and "=" not in tok:
        step += opt.nargs  # skip the option's value tokens
    return None, step


def _bare_token(node, tok, arg_slots, val_re):
    """Handle a non-option token: return the offending token or None.

    A doc-syntax value fills an open positional slot or is ignored; a bare
    word fills a positional slot (``click.Choice`` checked); only a bare
    token that lands on a GROUP still offering subcommands is a real
    command-path error.
    """
    if arg_slots:
        arg = arg_slots.pop(0)
        if not val_re.match(tok) and isinstance(arg.type, click.Choice) and tok not in arg.type.choices:
            return tok
        return None
    if val_re.match(tok):
        return None  # a doc-syntax value never resolves as a command
    if getattr(node, "commands", {}):
        return tok
    return None


def _resolve(cmdline):
    """Return (offending token, command path) or (None, path).

    Walks the click tree token by token: subcommand names descend, declared
    options are skipped with their values, remaining bare tokens must fill a
    positional ``click.Argument`` slot (``click.Choice`` values checked).
    `path` is the space-joined chain of resolved subcommands.
    """
    try:
        toks = shlex.split(cmdline)[1:]
    except ValueError:
        return "unparseable", ""
    # doc-syntax values: <placeholder>, trailing-bracket fragments, ellipsis,
    # hex/numbers, file paths — values, never command names. They are matched
    # in the walk below (not pre-filtered): removing them here would desync
    # the option-value skip (`--args '--verbose'` keeps a real token).
    _VAL = re.compile(r"^(<.*|.*\]$|.*….*|0x\w*|\d+[\w]*|/.*|[a-f0-9]{6,}$)", re.I)
    toks = [t for t in toks if t]

    node = main.cli
    path: list[str] = []
    arg_slots: list[click.Argument] = []  # unfilled positional Arguments on the leaf
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.startswith("-"):
            miss, step = _consume_option(node, t, " ".join(path))
            if miss:
                return miss, " ".join(path)
            i += step
            continue
        kids = getattr(node, "commands", {})
        if t in kids:
            node = kids[t]
            path.append(t)
            arg_slots = [p for p in getattr(node, "params", []) if isinstance(p, click.Argument)]
            i += 1
            continue
        miss = _bare_token(node, t, arg_slots, _VAL)
        if miss:
            return miss, " ".join(path)
        i += 1
        continue
    return None, " ".join(path)


def test_docs_commands_resolve():
    bad = []
    for f, lineno, cmd in _doc_lines():
        if any(s in cmd for s in ALLOW_SUBSTR):
            continue
        miss, path = _resolve(cmd)
        if not miss:
            continue
        if miss == "unparseable" and (str(f), lineno) not in UNPARSEABLE_ALLOW:
            bad.append((str(f), lineno, path, "unparseable"))
            continue
        if miss in KNOWN_MISSES:
            continue
        if miss.startswith("-") and (path, miss) in KNOWN_OPTS:
            continue
        if (str(f), lineno, miss) in KNOWN_LINE_MISSES:
            continue
        bad.append((str(f), lineno, path, miss))
    assert bad == [], f"unknown docs commands: {bad}"


def test_extractor_finds_lines():
    assert len(list(_doc_lines())) > 50
