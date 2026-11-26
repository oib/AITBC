#!/usr/bin/env python3
"""DOCS-RELEASES-TOPIC-REORG-1 (#2974): version-organized -> topic-organized release docs.

One-shot transformer plus a durable verifier.

``--apply`` reads the pre-reorg tree (docs/releases/v*/), splits sectioned
release logs into per-topic running logs under ``docs/releases/2026/``,
moves non-log artifacts into ``docs/releases/2026/versions/<dir>/``,
rewrites inbound markdown links, and writes ``docs/releases/2026/MANIFEST.csv``.

``--verify`` is the zero-content-loss proof: it re-derives the expected new
content for every manifest row from the recorded ``@source_commit`` and
compares against the working tree. Runnable any time after the reorg lands.

Link-target rewriting is the only content mutation allowed inside moved or
split material: markdown link *targets* are recomputed for the new layout;
link text, bodies, and prose are verbatim. ``--verify`` applies the same
rewrite before comparing, so the check remains honest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import posixpath
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REL = "docs/releases"
NEW_ROOT = f"{REL}/2026"
MANIFEST = f"{NEW_ROOT}/MANIFEST.csv"

TOPIC_ORDER = [
    "consensus",
    "bridge",
    "market",
    "escrow",
    "agent",
    "wallet",
    "cli",
    "deploy_ops",
    "security",
    "website",
    "testing",
    "performance",
    "docs_meta",
    "general",
]

TOPIC_TITLE = {
    "consensus": "Consensus",
    "bridge": "Bridge & Trading",
    "market": "Market",
    "escrow": "Escrow & Payments",
    "agent": "Agent",
    "wallet": "Wallet",
    "cli": "CLI",
    "deploy_ops": "Deploy & Ops",
    "security": "Security",
    "website": "Website",
    "testing": "Testing",
    "performance": "Performance",
    "docs_meta": "Docs & Meta",
    "general": "General",
}

_TOPIC_RES = [
    (
        "consensus",
        re.compile(
            r"\b(consensus|attestation|finalit\w*|fork|mempool|validator|epoch|"
            r"domain separation|governance|state[- ]transition|p2p|gossip|hardfork|"
            r"slashing|reorg|checkpoint|genesis)\b",
            re.I,
        ),
    ),
    (
        "bridge",
        re.compile(
            r"\b(bridge|cross[- ]chain|atomic settlement|trading|exchange|"
            r"order ?books?|swap|settlement)\b",
            re.I,
        ),
    ),
    (
        "market",
        re.compile(
            r"\b(market\w*|offer\w*|listing|discover\w*|shop|storefront|ipfs|"
            r"hosting|rental|bond\w*|provider|miner|gpu)\b",
            re.I,
        ),
    ),
    (
        "escrow",
        re.compile(
            r"\b(escrow|payment\w*|refund|lock\w*|dispute|payout|billing|"
            r"invoice|receipt)\b",
            re.I,
        ),
    ),
    (
        "agent",
        re.compile(
            r"\b(agent|bounty|autonomous|\btee\b|spend|staking|coordinator|"
            r"task)\b",
            re.I,
        ),
    ),
    ("wallet", re.compile(r"\b(wallet|custody|seed|mnemonic|keystore|key management)\b", re.I)),
    ("cli", re.compile(r"\b(cli|command[- ]line|exit codes?|argparse)\b", re.I)),
    (
        "deploy_ops",
        re.compile(
            r"\b(deploy\w*|systemd|fleet|host(s|ing)?\b|backup|restore|failover|"
            r"monitor\w*|alert\w*|infra\w*|incident|runbook|node\w*|service\w*|"
            r"update\.sh|setup\.sh|cron)\b",
            re.I,
        ),
    ),
    (
        "security",
        re.compile(
            r"\b(auth\w*|secret|credential|encrypt\w*|audit|harden\w*|nosec|"
            r"bandit|access control|compliance|vulnerab\w*|cve|"
            r"pen ?test|security|exploit|xss|csrf|injection)\b",
            re.I,
        ),
    ),
    (
        "website",
        re.compile(
            r"\b(website|web ui|explorer|frontend|front-end|css|html|"
            r"landing|pages?)\b",
            re.I,
        ),
    ),
    (
        "testing",
        re.compile(
            r"\b(tests?|testing|coverage|\bci\b|pytest|lint|mypy|gates?|"
            r"scenarios?|ratchet|quality|e2e)\b",
            re.I,
        ),
    ),
    (
        "performance",
        re.compile(
            r"\b(performance|latency|memory|footprint|cach\w+|benchmark|"
            r"optimi[sz]\w+|throughput|slow|speed)\b",
            re.I,
        ),
    ),
    (
        "docs_meta",
        re.compile(
            r"\b(documentation|docs?\b|release process|agent harness|skills?|"
            r"repo split|changelog|readme|agents\.md)\b",
            re.I,
        ),
    ),
]

_META_HEADING_RE = re.compile(
    r"^\W*(overview|summary|highlights?|task (status|breakdown)|"
    r"detailed findings|files changed|commit log|commits|breaking changes|"
    r"success criteria|verification|verified|next steps|notes?|related|"
    r"release (theme|gate|notes?|highlights?)|motivation|planned work|"
    r"remaining work|migration notes?|changes by agent|additional (fixes|"
    r"findings|cleanup)|suggested fix priorities|post-implementation|"
    r"documentation (&|and) operational|status|dependencies|"
    r"deployment (notes?|guide|plan)|risk|scope|date|prerequisites?|"
    r"key focus areas?|table of contents|contents)\W*$",
    re.I,
)

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_MD_LINK_RE = re.compile(r"(!?\[[^\]]*\]\(\s*<?)([^)\s>]+)(>?[^)]*\))")
_REF_DEF_RE = re.compile(r"^(\s*\[[^\]]+\]:\s*)(\S+)(.*)$", re.M)
_FENCE_BLOCK_RE = re.compile(r"(```.*?```|~~~.*?~~~)", re.S)
_KEEP_ROOT = {"README.md", "STATUS.md", "MAINTENANCE.md", "RELEASE_PREP.md"}


def _slug(version: str) -> str:
    return "v" + re.sub(r"[^0-9]", "", version)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _norm_path(p: str) -> str:
    parts = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


def section_headings(text: str):
    """(level, heading_text, char_offset) for headings outside code fences."""
    out = []
    off = 0
    in_fence = False
    for line in text.splitlines(keepends=True):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            m = _HEADING_RE.match(line)
            if m:
                out.append((len(m.group(1)), m.group(2).strip(), off))
        off += len(line)
    return out


def split_file_sections(text: str):
    """(preamble, [(level, heading, body)]) or None if unsectioned."""
    heads = [h for h in section_headings(text) if h[0] >= 2]
    if not heads:
        return None
    counts = {}
    for lvl, _, _ in heads:
        counts[lvl] = counts.get(lvl, 0) + 1
    level = min((lv for lv, c in counts.items() if c >= 2), default=min(counts))
    chosen = [h for h in heads if h[0] == level]
    starts = [h[2] for h in chosen]
    preamble = text[: starts[0]]
    sections = []
    for i, (lvl, htext, start) in enumerate(chosen):
        # body excludes the heading line itself (start is its offset)
        nl = text.find("\n", start)
        body_start = nl + 1 if nl != -1 else len(text)
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        sections.append((lvl, htext, text[body_start:end]))
    return preamble, sections


def strip_fences(text: str) -> str:
    return _FENCE_BLOCK_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def clean_heading(text: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", text).strip()


def classify(heading: str) -> str:
    h = clean_heading(heading)
    if _META_HEADING_RE.match(h):
        return "general"
    for topic, rx in _TOPIC_RES:
        if rx.search(h):
            return topic
    return "general"


def version_of(path: str, dir_name: str) -> str:
    m = re.search(r"v?(\d+\.\d+(?:\.\d+)?)", Path(path).name)
    if m:
        return m.group(1)
    m = re.search(r"v?(\d+\.\d+)", dir_name)
    return m.group(1) if m else dir_name.lstrip("v")


def version_key(v: str) -> tuple:
    parts = [int(x) for x in v.split(".")]
    parts += [0] * (3 - len(parts))
    return tuple(parts[:3])


def is_split_candidate(path: str, text: str) -> bool:
    name = Path(path).name
    is_log = name.endswith("_change.log") or name.endswith("_release.log") or name == "release.log"
    is_relmd = name.startswith("RELEASE_v") and path.endswith(".md")
    if not (is_log or is_relmd):
        return False
    return split_file_sections(text) is not None


def preamble_block(preamble: str, fallback: str) -> str:
    """Emit the preamble as a general-topic section. Returns '### head\\nbody'."""
    m = re.search(r"^#\s+(.*)$", strip_fences(preamble), flags=re.M)
    phead = m.group(1).strip() if m else fallback
    # drop a leading '# ' title line from the body so it isn't duplicated
    body = re.sub(r"\A#[^\n]*\n?", "", preamble, count=1)
    return "### " + phead + "\n" + body


def section_block(htext: str, body: str) -> str:
    return "### " + htext.strip() + "\n" + body


def _link_old_abs(path_part: str, old_src: str) -> str:
    if path_part.startswith("/"):
        return _norm_path(path_part.lstrip("/"))
    return _norm_path(f"{Path(old_src).parent}/{path_part}")


def _link_new_abs(old_abs: str, split_map: dict, old_to_new: dict, index_target: str) -> str:
    if old_abs in split_map:
        return index_target + "#" + _slug(split_map[old_abs])
    if old_abs in old_to_new:
        return old_to_new[old_abs]
    if old_abs.startswith(f"{REL}/"):
        return old_abs if Path(old_abs).name in _KEEP_ROOT else index_target
    return old_abs


def _resolve_link_target(target: str, old_src: str, new_src_dir: str, old_to_new: dict, split_map: dict, index_target: str):
    """Resolve one link target to its post-reorg relative path, or None."""
    path_part, _, frag = target.partition("#")
    if not path_part or path_part.startswith(("http://", "https://", "mailto:", "//")):
        return None
    new_abs = _link_new_abs(_link_old_abs(path_part, old_src), split_map, old_to_new, index_target)
    new_rel = posixpath.relpath(new_abs, new_src_dir or ".")
    if "#" in new_abs:
        return new_rel  # anchor already embedded
    if new_rel == path_part:
        return None
    return new_rel + ("#" + frag if frag else "")


def rewrite_links(text: str, old_src: str, new_src_dir: str, old_to_new: dict, split_map: dict, index_target: str) -> str:
    """Rewrite md link targets outside code fences for the new layout."""

    def fix(m):
        new = _resolve_link_target(m.group(2), old_src, new_src_dir, old_to_new, split_map, index_target)
        return m.group(0) if new is None else m.group(1) + new + m.group(3)

    def sub_segment(seg: str) -> str:
        seg = _MD_LINK_RE.sub(fix, seg)
        return _REF_DEF_RE.sub(fix, seg)

    parts = _FENCE_BLOCK_RE.split(text)
    for i in range(0, len(parts), 2):  # even indices are non-fence
        parts[i] = sub_segment(parts[i])
    return "".join(parts)


def _load_old(repo: Path, commit: str, path: str) -> str | None:
    r = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _iter_old_files(repo: Path) -> list:
    rel = repo / REL
    out = []
    for p in sorted(rel.rglob("*")):
        if not p.is_file():
            continue
        rp = str(p.relative_to(repo))
        rel_in = str(p.relative_to(rel))
        # section-root docs stay put (rewritten by hand); archive/ folds
        # into the 2026/ index by hand — neither enters the manifest.
        if rp.startswith(f"{NEW_ROOT}/") or "/" not in rel_in or rel_in.startswith("archive/"):
            continue
        out.append(p)
    return out


def _parse_old_files(repo: Path, old_files: list):
    parsed, split_map = {}, {}
    for p in old_files:
        rp = str(p.relative_to(repo))
        text = p.read_text(encoding="utf-8", errors="replace")
        if is_split_candidate(rp, text):
            parsed[rp] = {"kind": "split", "text": text, "sections": split_file_sections(text)}
            split_map[rp] = version_of(rp, str(Path(rp).relative_to(REL)).split("/")[0])
        else:
            parsed[rp] = {"kind": "move", "text": text}
    return parsed, split_map


def _build_old_to_new(parsed: dict) -> dict:
    old_to_new = {}
    for rp, info in parsed.items():
        if info["kind"] == "move":
            dir_name = str(Path(rp).relative_to(REL)).split("/")[0]
            old_to_new[rp] = f"{NEW_ROOT}/versions/{dir_name}/{Path(rp).name}"
    return old_to_new


def _emit_split_entries(parsed: dict):
    """Returns (entries, manifest_rows). entries[topic] = (vkey, ver, rp, seq, block)."""
    entries = {t: [] for t in TOPIC_ORDER}
    manifest_rows = []
    seq = 0
    for rp in sorted(parsed):
        info = parsed[rp]
        if info["kind"] != "split":
            continue
        rel_in = str(Path(rp).relative_to(REL))
        ver = version_of(rp, rel_in.split("/")[0])
        preamble, sections = info["sections"]
        entries["general"].append((version_key(ver), ver, rp, seq, preamble_block(preamble, Path(rp).name)))
        seq += 1
        for _lvl, htext, body in sections:
            entries[classify(htext)].append((version_key(ver), ver, rp, seq, section_block(htext, body)))
            seq += 1
        manifest_rows.append(
            {
                "old_path": rp,
                "disposition": "split",
                "version": ver,
                "new_paths": "",
                "sections": str(len(sections) + 1),
                "sha256": _sha256(info["text"].encode()),
            }
        )
    return entries, manifest_rows


def _write_moves(repo: Path, parsed: dict, old_to_new: dict, split_map: dict, index_target: str, manifest_rows: list) -> None:
    for rp in sorted(parsed):
        info = parsed[rp]
        if info["kind"] != "move":
            continue
        new_path = old_to_new[rp]
        text = info["text"]
        fixed = rewrite_links(text, rp, str(Path(new_path).parent), old_to_new, split_map, index_target)
        dest = repo / new_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(fixed, encoding="utf-8")
        rel_in = str(Path(rp).relative_to(REL))
        manifest_rows.append(
            {
                "old_path": rp,
                "disposition": "move",
                "version": version_of(rp, rel_in.split("/")[0]),
                "new_paths": new_path,
                "sections": "0",
                "sha256": _sha256(fixed.encode()),
                "sha256_old": _sha256(text.encode()),
                "linkfixed": "1" if fixed != text else "0",
            }
        )


def _write_topic_files(repo: Path, entries: dict, old_to_new: dict, split_map: dict, index_target: str) -> None:
    for topic in TOPIC_ORDER:
        if not entries[topic]:
            continue
        header = (
            f"# {TOPIC_TITLE[topic]} — consolidated release log\n\n"
            "> Reorganized 2026-11-26 under DOCS-RELEASES-TOPIC-REORG-1 (#2974).\n"
            f"> Running history of {TOPIC_TITLE[topic].lower()} changes across\n"
            "> releases; versions are sections, newest first. Section bodies are\n"
            "> verbatim from the pre-reorg tree except markdown link targets,\n"
            "> which were rewritten for the new paths (git history preserves\n"
            "> the old layout).\n"
        )
        out = []
        cur = None
        for _vkey, ver, rp, _seq, block in sorted(entries[topic], key=lambda e: (tuple(-x for x in e[0]), e[2], e[3])):
            if ver != cur:
                out.append(f"\n## v{ver}\n")
                cur = ver
            fixed = rewrite_links(block, rp, NEW_ROOT, old_to_new, split_map, index_target)
            out.append("\n" + fixed)
        content = (header + "".join(out)).rstrip("\n") + "\n"
        (repo / f"{NEW_ROOT}/{topic}_release.log").write_text(content, encoding="utf-8")


def _write_manifest(repo: Path, manifest_rows: list) -> None:
    mf = repo / MANIFEST
    mf.parent.mkdir(parents=True, exist_ok=True)
    with mf.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["old_path", "disposition", "version", "new_paths", "sections", "sha256", "sha256_old", "linkfixed"]
        )
        w.writeheader()
        w.writerow(
            {
                "old_path": "@source_commit",
                "disposition": "meta",
                "version": "",
                "new_paths": "PENDING",
                "sections": "",
                "sha256": "",
                "sha256_old": "",
                "linkfixed": "",
            }
        )
        for row in manifest_rows:
            w.writerow(row)


def _delete_old_tree(repo: Path, old_files: list) -> None:
    for p in old_files:
        p.unlink()
    rel = repo / REL
    for d in sorted((d for d in rel.rglob("*") if d.is_dir()), key=lambda p: -len(p.parts)):
        try:
            d.rmdir()
        except OSError:
            pass


def apply(repo: Path) -> int:
    old_files = _iter_old_files(repo)
    parsed, split_map = _parse_old_files(repo, old_files)
    old_to_new = _build_old_to_new(parsed)
    index_target = f"{NEW_ROOT}/README.md"
    entries, manifest_rows = _emit_split_entries(parsed)
    _write_moves(repo, parsed, old_to_new, split_map, index_target, manifest_rows)
    _write_topic_files(repo, entries, old_to_new, split_map, index_target)
    _write_manifest(repo, manifest_rows)
    _delete_old_tree(repo, old_files)
    return 0


def _manifest_maps(rows: list):
    data_rows = [r for r in rows if r["old_path"] != "@source_commit"]
    old_to_new, split_map = {}, {}
    for r in data_rows:
        if r["disposition"] == "move":
            old_to_new[r["old_path"]] = r["new_paths"]
        elif r["disposition"] == "split":
            split_map[r["old_path"]] = r["version"]
    return data_rows, old_to_new, split_map


def _verify_split_row(
    repo: Path, r: dict, old: str, old_to_new: dict, split_map: dict, index_target: str, topic_text, errors: list
) -> None:
    sp = split_file_sections(old)
    if sp is None or not is_split_candidate(r["old_path"], old):
        errors.append(f"{r['old_path']} unexpectedly unsectioned")
        return
    preamble, sections = sp
    ver = r["version"]
    blocks = [("general", preamble_block(preamble, Path(r["old_path"]).name))]
    blocks += [(classify(h), section_block(h, b)) for _, h, b in sections]
    for topic, block in blocks:
        fixed = rewrite_links(block, r["old_path"], NEW_ROOT, old_to_new, split_map, index_target)
        content = topic_text(topic)
        if f"## v{ver}" not in content:
            errors.append(f"{r['old_path']}: no '## v{ver}' in {topic}")
        elif fixed.rstrip("\n") not in content:
            errors.append(f"{r['old_path']}: block missing in {topic}_release.log")


def _check_tree(repo: Path, data_rows: list, errors: list) -> int:
    expected_new = {r["new_paths"] for r in data_rows if r["disposition"] == "move"}
    expected_new |= {f"{NEW_ROOT}/{t}_release.log" for t in TOPIC_ORDER if (repo / f"{NEW_ROOT}/{t}_release.log").exists()}
    for p in (repo / NEW_ROOT).rglob("*"):
        if p.is_file():
            rp = str(p.relative_to(repo))
            if rp in (MANIFEST, f"{NEW_ROOT}/README.md"):
                continue
            if rp not in expected_new:
                errors.append(f"orphan file {rp}")
    for r in data_rows:
        if (repo / r["old_path"]).exists():
            errors.append(f"old file still present {r['old_path']}")
    return len(expected_new)


def _verify_move_content(
    repo: Path, r: dict, old: str, old_to_new: dict, split_map: dict, index_target: str, errors: list
) -> None:
    new_path = r["new_paths"]
    disk = repo / new_path
    if not disk.exists():
        errors.append(f"missing moved file {new_path}")
        return
    expected = rewrite_links(old, r["old_path"], str(Path(new_path).parent), old_to_new, split_map, index_target)
    expected = expected.rstrip("\n") + "\n"
    if disk.read_text(encoding="utf-8") != expected:
        errors.append(f"content mismatch {new_path}")


def _verify_row(
    repo: Path, r: dict, src: str, old_to_new: dict, split_map: dict, index_target: str, topic_text, errors: list
) -> None:
    old = _load_old(repo, src, r["old_path"])
    if old is None:
        errors.append(f"cannot read {r['old_path']} @ {src}")
        return
    if r["disposition"] == "move":
        _verify_move_content(repo, r, old, old_to_new, split_map, index_target, errors)
    else:
        _verify_split_row(repo, r, old, old_to_new, split_map, index_target, topic_text, errors)


def verify(repo: Path) -> int:
    mf = repo / MANIFEST
    if not mf.exists():
        print("MANIFEST.csv missing", file=sys.stderr)
        return 1
    rows = list(csv.DictReader(mf.open(encoding="utf-8")))
    src = next((r["new_paths"] for r in rows if r["old_path"] == "@source_commit"), None)
    if not src or src == "PENDING":
        print("manifest @source_commit not stamped", file=sys.stderr)
        return 1

    data_rows, old_to_new, split_map = _manifest_maps(rows)
    index_target = f"{NEW_ROOT}/README.md"
    errors = []
    topic_cache = {}

    def topic_text(t):
        if t not in topic_cache:
            p = repo / f"{NEW_ROOT}/{t}_release.log"
            topic_cache[t] = p.read_text(encoding="utf-8") if p.exists() else ""
        return topic_cache[t]

    for r in data_rows:
        _verify_row(repo, r, src, old_to_new, split_map, index_target, topic_text, errors)

    n_new = _check_tree(repo, data_rows, errors)

    if errors:
        for e in errors[:60]:
            print("VERIFY FAIL:", e)
        print(f"{len(errors)} errors")
        return 1
    print(f"verify OK: {len(data_rows)} old files accounted, {n_new} generated files")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    repo = REPO
    if args.apply:
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        rc = apply(repo)
        mf = repo / MANIFEST
        if rc == 0 and mf.exists():
            txt = mf.read_text(encoding="utf-8")
            mf.write_text(txt.replace(",PENDING,", f",{head},", 1), encoding="utf-8")
        return rc
    if args.verify:
        return verify(repo)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
