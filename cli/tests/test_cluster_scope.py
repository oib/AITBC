"""#2222: `aitbc cluster` must not present fabricated fleet state as live.

There is no cluster/swarm backend (the coordinator's /v1/swarm/* mock
routes were deliberately removed). `status` used to print a hardcoded
{"healthy", nodes: 3} that operators could read as fleet truth; `sync`
and `balance` printed a fabricated "completed" for actions that never
ran. Status now reports its static-placeholder scope explicitly; the
mutating-sounding commands fail loudly.
"""

from click.testing import CliRunner

from aitbc_cli.commands import cluster as cluster_mod


def test_cluster_status_labels_static_scope():
    result = CliRunner().invoke(cluster_mod.cluster, ["status"], obj={"output_format": "table"})
    assert result.exit_code == 0
    assert "static-placeholder" in result.output
    assert "No Live Backend" in result.output
    assert "live_fleet_membership" in result.output
    # The fabricated live-looking counts must be gone.
    assert '"nodes": 3' not in result.output
    assert "healthy" not in result.output.lower().replace("cluster_health", "")


def test_cluster_status_json_reports_scope():
    result = CliRunner().invoke(cluster_mod.cluster, ["status"], obj={"output_format": "json"})
    assert result.exit_code == 0
    assert '"scope": "static-placeholder"' in result.output
    assert '"live_fleet_membership": false' in result.output


def test_cluster_sync_fails_loudly():
    result = CliRunner().invoke(cluster_mod.cluster, ["sync"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "not implemented" in result.output


def test_cluster_balance_fails_loudly():
    result = CliRunner().invoke(cluster_mod.cluster, ["balance"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "not implemented" in result.output
