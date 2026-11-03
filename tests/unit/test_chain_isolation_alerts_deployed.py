"""#916: the chain-isolation alert groups are in a loaded rule file and
the sticky counter alert is time-windowed.

On base the four alerts lived only in config/chain_isolation_alerts.yml,
which no prometheus.yml or deploy fallback listed — nothing loaded them.
The raw-counter rule (`violations_total > 0, for: 0s`) would also never
clear after one event; it is now `increase(...[15m]) > 0`.
"""

import yaml
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RULES = yaml.safe_load((REPO / "scripts" / "monitoring" / "aitbc_rules.yml").read_text())

NAMES = {
    "ChainIsolationViolationDetected",
    "CrossChainTransactionAttempt",
    "ChainIdValidationFailure",
    "BridgeRequestChainMismatch",
}


def test_alerts_live_in_the_deployed_rules_file():
    loaded = {r["alert"] for g in RULES["groups"] for r in g["rules"] if "alert" in r}
    assert NAMES <= loaded


def test_violation_alert_uses_a_windowed_increase():
    rule = next(r for g in RULES["groups"] for r in g["rules"] if r.get("alert") == "ChainIsolationViolationDetected")
    assert "increase(chain_isolation_violations_total[15m])" in rule["expr"]


def test_orphan_config_file_is_gone():
    assert not (REPO / "scripts" / "monitoring" / "config" / "chain_isolation_alerts.yml").exists()
