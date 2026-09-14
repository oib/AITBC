"""Provider-side IPFS hosting sweeper for marketplace rentals.

The buyer-side ``aitbc market host`` flow creates the escrow and pins the CID on
the *buyer's* daemon, so the marketplace job alone does not mean the provider is
storing anything. This sweeper closes that loop: it watches the hub marketplace
for active ``service_type=ipfs`` jobs assigned to this provider wallet, pins each
job CID on the local island daemon (Kubo fetches the blocks from the buyer's peer
over the private swarm), and reports ``provider_confirmed`` via pin-confirm so
the rental is verifiably hosted.

On terminal job states the sweeper removes the pin again so rented disk is
reclaimed. Only pins this sweeper created are managed -- they are tracked in a
small state file so unrelated daemon pins are never touched.

The miner main loop calls :func:`sweep_once` on its own cadence. Everything is
synchronous and failure-tolerant: a single bad job or a down daemon must never
take the miner loop down.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# Job states from the marketplace lifecycle (marketplace_service.main).
# Anything outside this set (RELEASED/REFUNDED/CANCELED/EXPIRED/FAILED, or a
# job that vanished from the listing) triggers unpin of a tracked pin.
ACTIVE_STATES = frozenset({"QUEUED", "RUNNING"})

IPFS_API_URL = os.environ.get("IPFS_API_URL", "http://127.0.0.1:5002")


def _marketplace_base() -> str:
    """Resolve the hub marketplace base URL.

    Mirrors the CLI's ``_hub_marketplace_client`` resolution: an explicit
    ``MARKETPLACE_SERVICE_URL`` wins (unless it is a loopback URL on a non-hub
    node, which is meaningless for a provider), then ``HUB_DISCOVERY_URL``,
    then the public hub default.
    """
    url = os.environ.get("MARKETPLACE_SERVICE_URL", "").strip()
    if url and not url.startswith(("http://127.0.0.1", "http://localhost")):
        return url.rstrip("/")
    hub = os.environ.get("HUB_DISCOVERY_URL", "hub.aitbc.bubuit.net").strip().rstrip("/")
    if not hub.startswith(("http://", "https://")):
        hub = f"https://{hub}"
    return hub


def _state_path() -> Path:
    data_dir = Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc"))
    return data_dir / "ipfs-pinning.json"


def _load_state(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data: dict[str, dict[str, Any]] = json.loads(path.read_text())
        return data
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2))
    except OSError as e:
        logger.warning("Could not persist ipfs-pinning state to %s: %s", path, e)


def _ipfs_post(path: str, timeout: int = 30, **kwargs: Any) -> requests.Response:
    response = requests.post(f"{IPFS_API_URL.rstrip('/')}{path}", timeout=timeout, **kwargs)
    response.raise_for_status()
    return response


def _daemon_available() -> bool:
    try:
        _ipfs_post("/api/v0/id", timeout=3)
        return True
    except requests.RequestException:
        return False


def _pin_cid(cid: str) -> bool:
    try:
        # pin/add blocks until the content is fetched from the swarm.
        _ipfs_post("/api/v0/pin/add", params={"arg": cid}, timeout=120)
        return True
    except requests.RequestException as e:
        logger.warning("IPFS pin of %s failed: %s", cid, e)
        return False


def _unpin_cid(cid: str) -> bool:
    try:
        _ipfs_post("/api/v0/pin/rm", params={"arg": cid}, timeout=30)
        return True
    except requests.RequestException as e:
        logger.warning("IPFS unpin of %s failed: %s", cid, e)
        return False


def _object_size(cid: str) -> int | None:
    try:
        data = _ipfs_post("/api/v0/object/stat", params={"arg": cid}, timeout=30).json()
        cumulative = data.get("CumulativeSize")
        return int(cumulative) if cumulative is not None else None
    except (requests.RequestException, ValueError):
        return None


def _fetch_jobs(marketplace_url: str, provider_address: str) -> list[dict[str, Any]] | None:
    """Return this provider's ipfs marketplace jobs, or None on fetch failure.

    None (rather than an empty list) signals "unknown" so callers do not unpin
    based on a failed fetch.
    """
    try:
        response = requests.get(
            f"{marketplace_url}/v1/marketplace/jobs",
            params={
                "service_type": "ipfs",
                "provider_address": provider_address,
                "limit": "500",
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Could not list marketplace ipfs jobs: %s", e)
        return None
    if isinstance(data, dict):
        return list(data.get("jobs", []))
    if isinstance(data, list):
        return data
    return []


def _pin_confirmed(job: dict[str, Any]) -> bool:
    payload = job.get("payload") or {}
    return bool(payload.get("provider_confirmed"))


def _confirm_pin(marketplace_url: str, job_id: str, size: int | None) -> bool:
    try:
        response = requests.post(
            f"{marketplace_url}/v1/marketplace/jobs/{job_id}/pin-confirm",
            json={"size": size, "provider_confirmed": True},
            timeout=20,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.warning("pin-confirm for job %s failed: %s", job_id, e)
        return False


def _job_id(job: dict[str, Any]) -> str:
    return str(job.get("job_id") or job.get("id") or "")


def _job_cid(job: dict[str, Any]) -> str | None:
    cid = (job.get("payload") or {}).get("cid")
    return str(cid) if cid else None


def _job_size(job: dict[str, Any]) -> int:
    size = (job.get("payload") or {}).get("size")
    try:
        return int(size) if size is not None else 0
    except (TypeError, ValueError):
        return 0


def _job_quota_mb(job: dict[str, Any]) -> int:
    quota = (job.get("constraints") or {}).get("disk_quota_mb")
    try:
        return int(quota) if quota is not None else 100
    except (TypeError, ValueError):
        return 100


def _pin_new_job(
    job: dict[str, Any],
    job_id: str,
    cid: str,
    usage_by_buyer: dict[str, int],
    state: dict[str, dict[str, Any]],
    result: dict[str, int],
) -> bool:
    """Pin a CID for a job not yet tracked in state. True when pinned.

    Provider-side quota enforcement: the marketplace checks usage at purchase
    time, but a crafted request could bypass the CLI, so the provider re-checks
    before spending its own disk. Jobs that are already provider-confirmed skip
    the gate -- the pin is recovery after state loss, not new spend.
    """
    buyer = str(job.get("buyer_address") or "")
    quota_bytes = _job_quota_mb(job) * 1024 * 1024
    if not _pin_confirmed(job) and _job_size(job) and usage_by_buyer.get(buyer, 0) > quota_bytes:
        result["skipped_quota"] += 1
        logger.warning(
            "Skipping pin for job %s: buyer %s active usage %s exceeds %s MB quota",
            job_id,
            buyer,
            usage_by_buyer.get(buyer, 0),
            _job_quota_mb(job),
        )
        return False
    if not _pin_cid(cid):
        result["errors"] += 1
        return False
    size = _object_size(cid)
    if size is not None and not _pin_confirmed(job):
        declared = _job_size(job)
        actual_total = usage_by_buyer.get(buyer, 0) - declared + size
        if actual_total > quota_bytes:
            # The declared size under-reported the content; reclaim the
            # disk and leave the job unconfirmed rather than hosting
            # beyond the offer's per-customer quota.
            _unpin_cid(cid)
            result["skipped_quota"] += 1
            logger.warning(
                "Unpinned job %s: measured usage %s exceeds %s MB quota for buyer %s",
                job_id,
                actual_total,
                _job_quota_mb(job),
                buyer,
            )
            return False
    state[job_id] = {
        "cid": cid,
        "size": size,
        "pinned_at": datetime.now(UTC).isoformat(),
    }
    result["pinned"] += 1
    return True


def _pin_active_job(
    job: dict[str, Any],
    marketplace_url: str,
    usage_by_buyer: dict[str, int],
    state: dict[str, dict[str, Any]],
    result: dict[str, int],
) -> None:
    """Pin one active job's CID (quota-checked) and confirm it if needed."""
    job_id = _job_id(job)
    cid = _job_cid(job)
    if not job_id or not cid:
        return
    if job_id in state and _pin_confirmed(job):
        return
    if job_id not in state and not _pin_new_job(job, job_id, cid, usage_by_buyer, state, result):
        return
    size = state[job_id].get("size")
    if not _pin_confirmed(job):
        if _confirm_pin(marketplace_url, job_id, size):
            result["confirmed"] += 1


def _pin_active_jobs(
    active_jobs: list[dict[str, Any]],
    marketplace_url: str,
    state: dict[str, dict[str, Any]],
    result: dict[str, int],
) -> None:
    """Pin every active job's CID, enforcing the per-buyer disk quota."""
    # Per-buyer usage across active jobs, for the provider-side quota check.
    usage_by_buyer: dict[str, int] = {}
    for job in active_jobs:
        buyer = str(job.get("buyer_address") or "")
        usage_by_buyer[buyer] = usage_by_buyer.get(buyer, 0) + _job_size(job)

    for job in active_jobs:
        _pin_active_job(job, marketplace_url, usage_by_buyer, state, result)


def _unpin_stale_jobs(
    state: dict[str, dict[str, Any]],
    active_jobs: list[dict[str, Any]],
    result: dict[str, int],
) -> None:
    """Reclaim disk for jobs that left the active set (terminal or gone)."""
    active_ids = {_job_id(j) for j in active_jobs}
    # CIDs still referenced by an active job must not be unpinned even if a
    # sibling job that shared the CID reached a terminal state.
    active_cids = {cid for cid in map(_job_cid, active_jobs) if cid}

    for job_id, entry in list(state.items()):
        if job_id in active_ids:
            continue
        cid = entry.get("cid")
        if cid and cid not in active_cids:
            if _unpin_cid(cid):
                result["unpinned"] += 1
            else:
                result["errors"] += 1
                continue  # keep the state entry so we retry the unpin
        del state[job_id]


def sweep_once(provider_address: str, state_path: Path | None = None) -> dict[str, int]:
    """Run one provider-side pin sweep. Returns counters for logging/tests."""
    result = {"pinned": 0, "confirmed": 0, "unpinned": 0, "skipped_quota": 0, "errors": 0}
    if os.environ.get("IPFS_HOSTING_ENABLED", "1").lower() in ("0", "false", "no"):
        return result
    if not provider_address:
        return result
    if not _daemon_available():
        logger.debug("IPFS daemon not reachable at %s; skipping hosting sweep", IPFS_API_URL)
        return result

    marketplace_url = _marketplace_base()
    state_path = state_path or _state_path()
    state = _load_state(state_path)

    jobs = _fetch_jobs(marketplace_url, provider_address)
    if jobs is None:
        result["errors"] += 1
        return result

    active_jobs = [j for j in jobs if str(j.get("state", "")).upper() in ACTIVE_STATES]
    _pin_active_jobs(active_jobs, marketplace_url, state, result)
    _unpin_stale_jobs(state, active_jobs, result)

    _save_state(state_path, state)
    if any(result.values()):
        logger.info("IPFS hosting sweep: %s", result)
    return result
