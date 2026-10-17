#!/usr/bin/env python3
"""Export presence of critical env-var NAMES (never values) for Prometheus.

A var dropped from a service's env file stays invisible for days: the
running process keeps its old environment, so neither the process nor its
logs reveal the gap until the next restart. (RECEIPT_SIGNING_KEY_HEX sat
missing from the coordinator env for ~4.5 days in Oct 2026 exactly this
way.) This exporter greps the declared env files for assignment lines and
emits, per watched var:

    aitbc_env_var_present{service,var}   1 when ``^VAR=`` appears in ANY of
                                         the service's env files (matching
                                         systemd EnvironmentFile= stacking:
                                         later files add/override), else 0
    aitbc_env_watch_scrape_success{file} per-file readability
    aitbc_env_watch_timestamp_seconds    when this run finished

Watched vars come from AITBC_ENV_WATCH, a space-separated list of

    service=VAR:file[,file...]

entries, e.g.::

    aitbc-coordinator-api=RECEIPT_SIGNING_KEY_HEX:/etc/aitbc/aitbc-coordinator-api.env,/etc/aitbc/aitbc-coordinator-api-override.env

Only variable NAMES are matched against ``^VAR=``; values are never read,
printed, or exported. A run that cannot read a file still writes the
metrics for the others and reports scrape_success=0 for it, so the alert
sees blindness rather than stale health. Run by aitbc-env-watch.timer;
stdlib only.

Environment:
    AITBC_ENV_WATCH      watch spec as above (empty spec writes a
                         minimal failure file)
    AITBC_TEXTFILE_DIR   default /var/lib/prometheus/node-exporter
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from pathlib import Path

OUTPUT_NAME = "aitbc_env_watch.prom"

_LABEL_SAFE = re.compile(r"[^a-zA-Z0-9_.-]")


def _label(value: str) -> str:
    return _LABEL_SAFE.sub("_", value)


def parse_spec(spec: str) -> list[tuple[str, str, list[str]]]:
    """Parse AITBC_ENV_WATCH into (service, var, [files]) entries.

    Malformed tokens are skipped — a bad entry must not blind the watch on
    the good ones.
    """
    entries = []
    for token in spec.split():
        service, sep, rest = token.partition("=")
        var, sep2, files = rest.partition(":")
        if not (sep and sep2 and service and var and files):
            continue
        paths = [p for p in files.split(",") if p]
        if paths:
            entries.append((service, var, paths))
    return entries


def _assigns_var(line: str, var: str) -> bool:
    return line.lstrip().startswith(f"{var}=")


def scan_entries(entries: list[tuple[str, str, list[str]]]) -> tuple[dict[tuple[str, str], int], dict[str, int]]:
    """Return ({(service,var): present}, {file_basename: readable}).

    File contents are scanned line-wise for ``^VAR=`` only.
    """
    present: dict[tuple[str, str], int] = {}
    file_ok: dict[str, int] = {}
    # Read each file once even when several vars watch it.
    path_cache: dict[str, list[str] | None] = {}

    def lines_of(path: str) -> list[str] | None:
        if path not in path_cache:
            try:
                path_cache[path] = Path(path).read_text().splitlines()
            except OSError:
                path_cache[path] = None
        return path_cache[path]

    for service, var, paths in entries:
        found = 0
        for path in paths:
            lines = lines_of(path)
            file_ok[os.path.basename(path)] = 1 if lines is not None else 0
            if lines is not None and any(_assigns_var(line, var) for line in lines):
                found = 1
        present[(service, var)] = found
    return present, file_ok


def render(entries: list[tuple[str, str, list[str]]], now: float) -> str:
    present, file_ok = scan_entries(entries)
    lines = [
        "# HELP aitbc_env_var_present 1 when ^VAR= appears in any of the service's env files.",
        "# TYPE aitbc_env_var_present gauge",
    ]
    for (service, var), value in present.items():
        lines.append(f'aitbc_env_var_present{{service="{_label(service)}",var="{_label(var)}"}} {value}')
    lines += [
        "# HELP aitbc_env_watch_scrape_success 1 when this env file was readable.",
        "# TYPE aitbc_env_watch_scrape_success gauge",
    ]
    for basename, ok in file_ok.items():
        lines.append(f'aitbc_env_watch_scrape_success{{file="{_label(basename)}"}} {ok}')
    lines += [
        "# HELP aitbc_env_watch_timestamp_seconds Unix time the last exporter run finished.",
        "# TYPE aitbc_env_watch_timestamp_seconds gauge",
        f"aitbc_env_watch_timestamp_seconds {int(now)}",
    ]
    return "\n".join(lines) + "\n"


def _failure_render(now: float) -> str:
    return (
        "# HELP aitbc_env_watch_scrape_success 1 when this env file was readable.\n"
        "# TYPE aitbc_env_watch_scrape_success gauge\n"
        'aitbc_env_watch_scrape_success{file="exporter"} 0\n'
        "# HELP aitbc_env_watch_timestamp_seconds Unix time the last exporter run finished.\n"
        "# TYPE aitbc_env_watch_timestamp_seconds gauge\n"
        f"aitbc_env_watch_timestamp_seconds {int(now)}\n"
    )


def write_atomic(directory: str, text: str) -> None:
    """Write beside the target and rename: node_exporter never reads a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aitbc_env_watch.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(directory, OUTPUT_NAME))
    except BaseException:
        os.unlink(tmp)
        raise


def main() -> int:
    spec = os.environ.get("AITBC_ENV_WATCH", "")
    directory = os.environ.get("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
    now = time.time()

    entries = parse_spec(spec)
    try:
        text = render(entries, now) if entries else _failure_render(now)
    except Exception:
        text = _failure_render(now)
    try:
        write_atomic(directory, text)
    except OSError as e:
        print(f"aitbc-env-watch: cannot write {directory}/{OUTPUT_NAME}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
