"""LOG-1 — the deployed logrotate stanza must not lose lines or widen modes.

``scripts/deployment/aitbc-logrotate.conf`` is the canonical
``/etc/logrotate.d/aitbc``. The fleet audit found:

* top-level ``/var/log/aitbc/*.log`` files are appended open-per-write by
  monitor scripts, except ``alerts.log`` which the prometheus watch writer
  holds open — so the wildcard stanza must ``copytruncate`` (a ``create``
  there would strand the watcher's writes on the rotated inode);
* file owners differ per host (``deploys.log``/``health_check.log`` are
  root-owned on some nodes, aitbc-owned on others) — ``copytruncate``
  preserves whatever owner/mode is in place, where ``create`` would force
  one owner and could widen ``secrets-audit.log`` past its 0600;
* service logs under ``/var/log/aitbc/<service>/`` self-rotate via
  ``TimedRotatingFileHandler`` and must stay out of the file entirely.

These tests are static — logrotate itself runs only on the nodes.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONF = REPO_ROOT / "scripts" / "deployment" / "aitbc-logrotate.conf"
SETUP = REPO_ROOT / "scripts" / "deployment" / "setup.sh"
UPDATE = REPO_ROOT / "scripts" / "deployment" / "update.sh"
HARDENING = REPO_ROOT / "scripts" / "utils" / "security_hardening.sh"
MONITORING_SETUP = REPO_ROOT / "scripts" / "workflow" / "16_monitoring_setup.sh"
EVENT_MONITORING = REPO_ROOT / "scripts" / "workflow" / "37_contract_event_monitoring.sh"


def _stanzas(text: str) -> dict[str, str]:
    """Map each stanza's path expression to its ``{ ... }`` body."""
    return {m.group(1).strip(): m.group(2) for m in re.finditer(r"^([^\s#{][^\n{]*)\{([^}]*)\}", text, re.M)}


def _body(stanzas: dict[str, str], pattern: str) -> str:
    body = stanzas.get(pattern)
    assert body is not None, f"missing stanza for {pattern}"
    return body


def test_conf_exists_and_parses():
    stanzas = _stanzas(CONF.read_text())
    assert "/var/log/aitbc/*.log" in stanzas
    assert "/var/log/aitbc/events/*.log" in stanzas


def test_top_level_stanza_uses_copytruncate_not_create():
    body = _body(_stanzas(CONF.read_text()), "/var/log/aitbc/*.log")
    assert "copytruncate" in body
    # 'create <owner>' cannot express the per-host owner mix and would
    # widen secrets-audit.log past 0600 — it must not appear here.
    assert not re.search(r"^\s*create\b", body, re.M)


def test_retention_and_hygiene_options_kept():
    body = _body(_stanzas(CONF.read_text()), "/var/log/aitbc/*.log")
    for directive in ("size 20M", "rotate 14", "compress", "delaycompress", "missingok", "notifempty"):
        assert re.search(rf"^\s*{directive}$", body, re.M), directive


def test_wildcard_stanza_is_size_triggered_not_daily():
    """alerts.log is capped at 5 MiB by its own RotatingFileHandler and the
    explorer history endpoint reads only the live file — a daily rotation
    would empty it at midnight. 'size 20M' means logrotate never touches it."""
    body = _body(_stanzas(CONF.read_text()), "/var/log/aitbc/*.log")
    assert not re.search(r"^\s*daily$", body, re.M)
    assert re.search(r"^\s*size 20M$", body, re.M)


def test_alerts_log_rationale_documented():
    text = CONF.read_text()
    assert "alerts.log" in text
    assert "RotatingFileHandler" in text
    assert "20M" in text


def test_events_stanza_remains_daily():
    # events/*.log are script-written; daily rotation is correct there.
    body = _body(_stanzas(CONF.read_text()), "/var/log/aitbc/events/*.log")
    assert re.search(r"^\s*daily$", body, re.M)


def test_no_postrotate_or_sharedscripts():
    body = CONF.read_text()
    assert "postrotate" not in body
    assert "sharedscripts" not in body


def test_service_subdirs_not_covered():
    # /var/log/aitbc/<service>/*.log self-rotate via TimedRotatingFileHandler;
    # the only second-level stanza allowed is the script-written events/ dir.
    for pattern in _stanzas(CONF.read_text()):
        if "/" in pattern[len("/var/log/aitbc/") :]:
            assert pattern == "/var/log/aitbc/events/*.log", pattern


def test_events_stanza_mode_no_wider_than_0640():
    body = _body(_stanzas(CONF.read_text()), "/var/log/aitbc/events/*.log")
    m = re.search(r"^\s*create\s+(\d{4})\s+(\S+)\s+(\S+)", body, re.M)
    assert m is not None, "events stanza must create files with explicit owner/group"
    assert int(m.group(1), 8) <= 0o640
    assert m.group(3) == "adm"


def test_setup_and_update_install_the_conf():
    for script in (SETUP, UPDATE):
        text = script.read_text()
        assert "aitbc-logrotate.conf" in text
        assert "/etc/logrotate.d/aitbc" in text
        assert "-m 0644" in text


def test_hardening_and_monitoring_stanzas_fixed():
    # The old security_hardening stanza globbed '/var/log/aitbc*.log'
    # (missing slash — matched nothing); 16_monitoring_setup used
    # 'create 644 root root' — world-readable logs.
    assert "/var/log/aitbc*.log" not in HARDENING.read_text()
    assert "create 644" not in MONITORING_SETUP.read_text()
    assert "create 644" not in EVENT_MONITORING.read_text()
    # 37 must not recreate aitbc-events when the canonical conf covers it.
    assert "logrotate.d/aitbc-events" in EVENT_MONITORING.read_text()
