"""key-audit.py lists backup copies without touching its verdict, and finds a key by value (2026-10-01).

On 2026-10-01 the old hub key turned up in 33 backup files across the fleet. The audit had not seen them: it read
``*.env`` only, and it recognised a key by its variable name, so two hub backups with other names were missed even by
a name-based look at the backups. These tests pin the two fixes and the property the audit exists for: a private key
never reaches its report.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from aitbc.crypto.crypto import derive_ethereum_address

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "key-audit.py"
PK = "0x" + "11" * 32
OTHER_PK = "0x" + "22" * 32
ADDR = derive_ethereum_address(PK).lower()
OTHER_ADDR = derive_ethereum_address(OTHER_PK).lower()


@pytest.fixture(scope="module")
def key_audit() -> ModuleType:
    spec = importlib.util.spec_from_file_location("key_audit_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tree(tmp_path: Path) -> dict[str, Path]:
    etc = tmp_path / "etc"
    wallets = tmp_path / "wallets"
    etc.mkdir()
    wallets.mkdir()
    return {"etc": etc, "wallets": wallets, "keystore": tmp_path / "keystore"}


def _report(key_audit: ModuleType, tree: dict[str, Path], find: list[str] | None = None) -> dict:
    return key_audit.build_report(tree["etc"], (tree["keystore"], tree["wallets"]), find)


def test_a_live_env_key_is_found_by_name_and_matches_its_declared_address(key_audit, tree) -> None:
    (tree["etc"] / "node.env").write_text(f"ESCROW_RELEASE_PRIVATE_KEY={PK}\nESCROW_RELEASE_ADDRESS={ADDR}\n")
    report = _report(key_audit, tree)
    assert report["ok"] is True
    [finding] = report["findings"]
    assert finding["derived"] == ADDR and finding["match"] is True and "backup" not in finding


def test_a_backup_copy_is_listed_and_flagged_but_never_changes_the_verdict(key_audit, tree) -> None:
    (tree["etc"] / "node.env").write_text(f"ESCROW_RELEASE_PRIVATE_KEY={PK}\nESCROW_RELEASE_ADDRESS={ADDR}\n")
    # A stale backup whose declared address no longer matches its key: it is reported, but it is not a live fault.
    (tree["etc"] / "node.env.bak-20260926").write_text(
        f"ESCROW_RELEASE_PRIVATE_KEY={OTHER_PK}\nESCROW_RELEASE_ADDRESS={ADDR}\n"
    )
    report = _report(key_audit, tree)
    backups = [f for f in report["findings"] if f.get("backup")]
    assert len(backups) == 1 and backups[0]["source"].endswith("node.env.bak-20260926")
    assert backups[0]["match"] is False
    assert report["ok"] is True and report["mismatches"] == []


@pytest.mark.parametrize(
    "name", ["node.env.bak-1", "node.env.bak.20260913T175406Z", "x.env.orig", "x.env.old", "x.env~", "x.env.save"]
)
def test_the_usual_backup_names_are_recognised(key_audit, name) -> None:
    assert key_audit._is_backup_name(name)


@pytest.mark.parametrize("name", ["node.env", "default.json", "readme.txt", "validator-secrets.env"])
def test_live_sources_are_not_backups(key_audit, name) -> None:
    assert not key_audit._is_backup_name(name)


def test_a_live_mismatch_still_fails_the_verdict(key_audit, tree) -> None:
    (tree["etc"] / "node.env").write_text(f"ESCROW_RELEASE_PRIVATE_KEY={PK}\nESCROW_RELEASE_ADDRESS={OTHER_ADDR}\n")
    report = _report(key_audit, tree)
    assert report["ok"] is False and len(report["mismatches"]) == 1


def test_find_by_value_ignores_the_variable_name_and_finds_comments_and_json(key_audit, tree) -> None:
    (tree["etc"] / "live.env").write_text(f"SOME_ODD_NAME={PK}\n")  # no PRIVATE_KEY in the name
    (tree["etc"] / "rpc.env.bak-1").write_text(f"# old value: {PK[2:]}\nOTHER={OTHER_PK}\n")  # bare hex, in a comment
    (tree["wallets"] / "default.json.bak").write_text(json.dumps({"secret_blob": {"k": PK}}))
    (tree["etc"] / "unrelated.env").write_text("GENESIS_HASH=" + "ab" * 32 + "\n")  # a 64-hex value that is not our key
    hits = {Path(h["source"]).name: h for h in _report(key_audit, tree, [ADDR])["found_by_value"]}
    assert set(hits) == {"live.env", "rpc.env.bak-1", "default.json.bak"}
    assert hits["live.env"]["backup"] is False
    assert hits["rpc.env.bak-1"]["backup"] is True and hits["rpc.env.bak-1"]["occurrences"] == 1
    assert hits["default.json.bak"]["backup"] is True
    assert all(h["addresses"] == [ADDR] for h in hits.values())


def test_a_redacted_backup_is_clean(key_audit, tree) -> None:
    (tree["etc"] / "node.env.bak-1").write_text("ESCROW_RELEASE_PRIVATE_KEY=REDACTED_OLD_0x02B8_KEY\n")
    report = _report(key_audit, tree, [ADDR])
    assert report["found_by_value"] == [] and report["findings"] == []


def test_a_report_never_contains_a_private_key(key_audit, tree, tmp_path, monkeypatch, capsys) -> None:
    (tree["etc"] / "node.env").write_text(f"ESCROW_RELEASE_PRIVATE_KEY={PK}\nESCROW_RELEASE_ADDRESS={ADDR}\n")
    (tree["etc"] / "node.env.bak-1").write_text(f"X={PK}\n")
    blob = json.dumps(_report(key_audit, tree, [ADDR]))
    assert PK[2:] not in blob and ADDR in blob

    # The command line prints file names, modes and counts, and still no key.
    out = tmp_path / "report.json"
    monkeypatch.setattr(key_audit, "ETC_DIR", tree["etc"])
    monkeypatch.setattr(key_audit, "WALLET_DIRS", (tree["keystore"], tree["wallets"]))
    real_build_report = key_audit.build_report
    monkeypatch.setattr(
        key_audit,
        "build_report",
        lambda find_addresses=None: real_build_report(tree["etc"], (tree["keystore"], tree["wallets"]), find_addresses),
    )
    monkeypatch.setattr("sys.argv", ["key-audit.py", "--report", str(out), "--find-address", ADDR])
    key_audit.main()
    printed = capsys.readouterr().out
    assert PK[2:] not in printed and PK[2:] not in out.read_text()
    assert "2 file(s) hold its key (1 of them backups)" in printed


def test_find_address_accepts_the_ait_prefixed_form(key_audit, monkeypatch, tmp_path) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(
        key_audit,
        "build_report",
        lambda find_addresses=None: seen.append(find_addresses) or {"findings": [], "mismatches": [], "found_by_value": []},
    )
    monkeypatch.setattr(
        "sys.argv", ["key-audit.py", "--report", str(tmp_path / "r.json"), "--find-address", "ait1" + ADDR[2:]]
    )
    key_audit.main()
    assert seen == [[ADDR]]
