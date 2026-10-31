#!/usr/bin/env python3
"""build-genesis.py — build a loader-valid genesis document (RESET-GENESIS-BUILDER-1).

Thin CLI over ``aitbc_chain.genesis_builder.build_genesis_doc``: reads
operator-supplied inputs, builds the document with all claims computed, and
writes it under a data dir as ``data/<chain_id>/genesis.json``.

Modes
-----
--scratch (default): the only write path implemented. The output must live
    under an explicit ``--data-dir``/``AITBC_DATA_DIR`` that resolves outside
    the forbidden prefixes (``/var/lib/aitbc``, ``/etc/aitbc``, ``/root``), and
    the target file must not exist unless ``--force`` is given.

--live:   the reset-day write. Evaluates the preconditions (manifest chain
    id matches, target has no existing blocks or genesis for that id, an
    operator line is supplied for the output record) and proceeds only when
    all pass — the gate is the guard, the scratch-mode forbidden-prefix
    check does not apply.

Run from the repo venv so ``aitbc_chain`` is importable:

    .venv/bin/python scripts/ops/build-genesis.py \
        --manifest manifest.json --allocations allocs.json \
        --parameters params.json --bridge-validators validators.json \
        --data-dir /tmp/bc2-rehearsal/node-0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from aitbc_chain.genesis_builder import (
    FORBIDDEN_WRITE_PREFIXES,
    GenesisBuildError,
    build_genesis_doc,
    check_live_conditions,
)


def _load_json(path: str | None, *, what: str) -> Any:
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text())
    except OSError as exc:
        raise GenesisBuildError(f"cannot read {what} at {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GenesisBuildError(f"{what} at {path} is not valid JSON: {exc}") from exc


def _forbidden(path: Path) -> str | None:
    resolved = str(path)
    for prefix in FORBIDDEN_WRITE_PREFIXES:
        if resolved == prefix or resolved.startswith(prefix + os.sep):
            return prefix
    return None


def _read_inputs(args: argparse.Namespace) -> tuple[dict, list, dict, list | None]:
    manifest = _load_json(args.manifest, what="manifest") or {}
    if not isinstance(manifest, dict):
        raise GenesisBuildError("manifest must be a JSON object")
    allocations = _load_json(args.allocations, what="allocations")
    if not isinstance(allocations, list):
        raise GenesisBuildError("allocations file must be a JSON list")
    parameters = _load_json(args.parameters, what="parameters") or {}
    if not isinstance(parameters, dict):
        raise GenesisBuildError("parameters file must be a JSON object")
    validators = _load_json(args.bridge_validators, what="bridge-validators")
    if validators is not None and not isinstance(validators, list):
        raise GenesisBuildError("bridge-validators file must be a JSON list")
    return manifest, allocations, parameters, validators


def _target_paths(args: argparse.Namespace, chain_id: str) -> tuple[Path, Path, Path]:
    data_dir = args.data_dir or os.environ.get("AITBC_DATA_DIR")
    if not data_dir:
        raise GenesisBuildError("no output dir: pass --data-dir or set AITBC_DATA_DIR")
    data_root = Path(data_dir).resolve()
    target_dir = data_root / "data" / chain_id
    return data_root, target_dir, target_dir / "genesis.json"


def _run_live(chain_id: str, manifest: dict, target_dir: Path, operator_line: str | None) -> None:
    """The reset-day gate: all preconditions must pass or the build refuses.

    Met preconditions let the write proceed to the live data dir — the gate
    is the guard, and the operator's named line is recorded in the output.
    """
    unmet = check_live_conditions(
        doc={"chain_id": chain_id},
        manifest=manifest,
        target_dir_exists=target_dir.exists(),
        operator_line=operator_line,
    )
    if unmet:
        raise GenesisBuildError("live-mode preconditions unmet: " + "; ".join(unmet))


def _check_scratch(data_root: Path, target_dir: Path, target: Path, *, force: bool) -> None:
    bad = _forbidden(data_root)
    if bad:
        raise GenesisBuildError(f"scratch output dir {data_root} is under the forbidden prefix {bad}")
    if target.exists() and not force:
        raise GenesisBuildError(f"target {target} already exists (pass --force to overwrite)")
    chain_db = target_dir / "chain.db"
    if chain_db.exists() and not force:
        raise GenesisBuildError(
            f"{chain_db} already exists — the chain dir is not empty; refusing to seed a genesis over existing state"
        )


def _write_outputs(target_dir: Path, target: Path, doc: dict, chain_id: str, operator_line: str | None) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    provenance = {
        "mode": "scratch",
        "chain_id": chain_id,
        "operator_line": operator_line,
        "genesis_file": str(target),
    }
    (target_dir / "genesis.manifest.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    print(f"wrote {target}")
    print(f"genesis_hash={doc['genesis_hash']} state_root={doc['state_root']}")
    if operator_line:
        print(f"operator_line={operator_line}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--scratch", action="store_true", help="scratch mode (default): write under --data-dir")
    mode.add_argument(
        "--live",
        action="store_true",
        help="live mode: reset-day write — proceeds only when every precondition passes (operator line required)",
    )
    p.add_argument("--manifest", help="JSON: {chain_id, expected_total_units?, timestamp?}")
    p.add_argument("--allocations", required=True, help="JSON: [{address, balance, nonce?}]")
    p.add_argument("--parameters", help="JSON: {name: value}")
    p.add_argument("--bridge-validators", dest="bridge_validators", help="JSON: [{address, public_key, epoch?}]")
    p.add_argument("--data-dir", help="output data dir (default: AITBC_DATA_DIR)")
    p.add_argument("--operator-line", help="operator's named line, recorded in the output manifest")
    p.add_argument("--force", action="store_true", help="overwrite an existing target file (scratch only)")
    args = p.parse_args(argv)

    try:
        manifest, allocations, parameters, validators = _read_inputs(args)
        chain_id = str(manifest.get("chain_id") or "").strip()
        if not chain_id:
            raise GenesisBuildError("manifest does not name a chain_id")
        data_root, target_dir, target = _target_paths(args, chain_id)

        if args.live:
            _run_live(chain_id, manifest, target_dir, args.operator_line)
        else:
            _check_scratch(data_root, target_dir, target, force=args.force)

        doc = build_genesis_doc(
            chain_id=chain_id,
            allocations=allocations,
            parameters=parameters,
            bridge_validators=validators,
            timestamp=manifest.get("timestamp"),
            expected_total=manifest.get("expected_total_units"),
        )
        _write_outputs(target_dir, target, doc, chain_id, args.operator_line)
        return 0
    except GenesisBuildError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
