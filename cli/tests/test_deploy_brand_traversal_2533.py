"""AUDIT-DEPLOY-BRAND-TRAVERSAL-1 (#2533): ``aitbc deploy deploy-brand``
built ``<storage>/<network>/<brand_id>`` from ``--network`` and the manifest
``brand_id`` unconfined — ``../`` and absolute paths escaped ``--storage``.
Both are now slug-validated and the resolved target must stay under storage.
"""

import json

from click.testing import CliRunner

from aitbc_cli.commands.deploy import deploy


def _manifest(tmp_path, brand_id="acme"):
    path = tmp_path / "brand.json"
    path.write_text(json.dumps({"brand_id": brand_id, "name": "Acme"}))
    return str(path)


def test_network_dotdot_rejected(tmp_path):
    storage = tmp_path / "store"
    result = CliRunner().invoke(
        deploy,
        ["deploy-brand", "--config", _manifest(tmp_path), "--network", "../escape", "--storage", str(storage)],
        obj={"output": "table"},
    )
    assert result.exit_code != 0
    assert "Invalid --network" in result.output
    assert not (tmp_path / "escape").exists()


def test_network_absolute_rejected(tmp_path):
    result = CliRunner().invoke(
        deploy,
        [
            "deploy-brand",
            "--config",
            _manifest(tmp_path),
            "--network",
            "/tmp/evil-net",
            "--storage",
            str(tmp_path / "store"),
        ],
        obj={"output": "table"},
    )
    assert result.exit_code != 0
    assert "Invalid --network" in result.output


def test_brand_id_dotdot_rejected(tmp_path):
    storage = tmp_path / "store"
    result = CliRunner().invoke(
        deploy,
        [
            "deploy-brand",
            "--config",
            _manifest(tmp_path, brand_id="../../outside"),
            "--network",
            "net1",
            "--storage",
            str(storage),
        ],
        obj={"output": "table"},
    )
    assert result.exit_code != 0
    assert "Invalid manifest brand_id" in result.output
    assert not (tmp_path / "outside").exists()


def test_brand_id_non_string_rejected(tmp_path):
    path = tmp_path / "brand.json"
    path.write_text(json.dumps({"brand_id": 42}))
    result = CliRunner().invoke(
        deploy,
        ["deploy-brand", "--config", str(path), "--storage", str(tmp_path / "store")],
        obj={"output": "table"},
    )
    assert result.exit_code != 0
    assert "Invalid manifest brand_id" in result.output


def test_valid_deploy_still_works(tmp_path):
    storage = tmp_path / "store"
    result = CliRunner().invoke(
        deploy,
        [
            "deploy-brand",
            "--config",
            _manifest(tmp_path, brand_id="acme-brand_2"),
            "--network",
            "ait-mainnet",
            "--storage",
            str(storage),
        ],
        obj={"output": "table"},
    )
    assert result.exit_code == 0, result.output
    deployed = storage / "ait-mainnet" / "acme-brand_2" / "brand-manifest.json"
    assert deployed.exists()
    assert json.loads(deployed.read_text())["brand_id"] == "acme-brand_2"
