"""Provider-side IPFS hosting sweeper for market rentals.

The buyer-side ``aitbc market host`` flow creates the escrow and pins the CID on
the *buyer's* daemon, so the market job alone does not mean the provider is
storing anything. This sweeper closes that loop: it watches the hub market
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

import base64
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import quote

import base58
import requests

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.crypto import sign_transaction_data
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.env_compat import market_getenv
from aitbc.market.job_request_signature import jobs_request_message

logger = get_logger(__name__)

# Job states from the market lifecycle (market_service.main).
# Anything outside this set (RELEASED/REFUNDED/CANCELED/EXPIRED/FAILED, or a
# job that vanished from the listing) triggers unpin of a tracked pin.
ACTIVE_STATES = frozenset({"QUEUED", "RUNNING"})

IPFS_API_URL = os.environ.get("IPFS_API_URL", "http://127.0.0.1:5002")

# IPFS-DEPTH-1 (#1582) residual: the market job payload's ``cid`` is
# buyer-influenced and lands as a Kubo arg on *this* provider's daemon.
# Kubo pin/add accepts IPFS paths, not just CIDs — only bare alphanumeric
# CID spellings are allowed through.
_CID_ARG_RE = re.compile(r"[A-Za-z0-9]{1,256}")

# IPFS-PIN-LEAK-1 (#1687): a crash between pin/add and _save_state orphans a
# pin the state file never recorded. Pins that are on the daemon, untracked
# in state, known to the market job listing, and older than this grace
# window are reclaimed. Default 6h; 0 disables reconciliation.
_UNTRACKED_PIN_GRACE_SECONDS = int(os.environ.get("IPFS_UNTRACKED_PIN_GRACE_SECONDS", "21600"))


def _market_base() -> str:
    """Resolve the hub market base URL.

    Mirrors the CLI's ``_hub_market_client`` resolution: an explicit
    ``MARKET_SERVICE_URL`` wins (unless it is a loopback URL on a non-hub
    node, which is meaningless for a provider), then ``HUB_DISCOVERY_URL``,
    then the public hub default.
    """
    url = market_getenv("MARKET_SERVICE_URL", "").strip()
    if url and not url.startswith(("http://127.0.0.1", "http://localhost")):
        return url.rstrip("/")
    hub = os.environ.get("HUB_DISCOVERY_URL", "hub.aitbc.invalid").strip().rstrip("/")
    if not hub.startswith(("http://", "https://")):
        hub = f"https://{hub}"
    return hub


def _state_path() -> Path:
    data_dir = Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc"))
    return data_dir / "ipfs-pinning.json"


def _wallet_dir() -> Path:
    return Path(os.environ.get("AITBC_WALLET_DIR", "/var/lib/aitbc/wallets"))


def _chain_id() -> str:
    return (os.environ.get("AITBC_CHAIN_ID") or os.environ.get("CHAIN_ID") or "").strip()


def _provider_key(provider_address: str) -> str | None:
    """Return this provider's wallet private key for request signing.

    The market's public job feed no longer carries ``payload.cid``; the
    sweeper proves it is the job's provider by signing with the provider
    wallet — the same key the offer registration flow already uses. The
    wallet JSON is readable by the ``aitbc`` user this process runs as.
    """
    try:
        target = canonical_address(provider_address)
    except (AttributeError, TypeError, ValueError):
        return None
    try:
        for path in sorted(_wallet_dir().glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            try:
                if canonical_address(str(data.get("address") or "")) != target:
                    continue
            except (TypeError, ValueError):
                continue
            key = data.get("private_key")
            if key:
                return str(key)
    except OSError:
        pass
    return None


def _signed_request_params(provider_address: str, route: str, binding: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Build the signed query/body fields a market job route expects, or None.

    The signed message binds the provider address, chain id, a freshness
    timestamp and the exact route (``aitbc.market.job_request_signature``);
    the market returns full job rows only to the recovered signer.
    ``binding`` is an optional attestation payload folded into the signed
    message — pin-confirm requires it so the CID/size claim cannot be
    swapped after signing (#1922).
    """
    key = _provider_key(provider_address)
    chain_id = _chain_id()
    if not key or not chain_id:
        logger.warning("Cannot sign market request for %s: provider wallet key or chain id unavailable", provider_address)
        return None
    issued_at = int(time.time())
    message = jobs_request_message(provider_address, chain_id, issued_at, route, binding=binding)
    return {
        "signer_address": provider_address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "signature": sign_transaction_data(message, key),
    }


def _load_state(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("IPFS pinning state %s unreadable (%s); quarantining and starting fresh", path, e)
    else:
        logger.warning("IPFS pinning state %s is not a JSON object; quarantining and starting fresh", path)
    # A corrupt state file orphans every tracked pin (they are never unpinned).
    # Quarantine it aside rather than passing silently (#1486 class).
    try:
        path.replace(path.with_name(f"{path.name}.corrupt-{int(time.time())}"))
    except OSError as e:
        logger.warning("Could not quarantine corrupt pinning state %s: %s", path, e)
    return {}


def _save_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    """Persist state atomically.

    A crash mid-``write_text`` used to leave a truncated JSON file that
    ``_load_state`` then quarantined — orphaning every tracked pin forever
    (#1486 class / #1687 crash window). Write-then-rename means readers only
    ever see a complete file.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(json.dumps(state, indent=2))
        os.replace(tmp, path)
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


def _valid_cid_arg(cid: str) -> bool:
    return isinstance(cid, str) and bool(_CID_ARG_RE.fullmatch(cid))


def _env_timeout(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _local_fetch_timeout() -> int:
    # #2968: the direct buyer→provider bitswap leg is best-effort. Give it a
    # short fuse, as in the agent-task payload path (#2955), then use the
    # hub-assisted CAR path rather than spending two minutes of every sweep
    # waiting on a session that never transfers a block.
    return _env_timeout("IPFS_HOSTING_LOCAL_TIMEOUT", 20)


def _pin_timeout() -> int:
    return _env_timeout("IPFS_HOSTING_PIN_TIMEOUT", 30)


def _car_transfer_timeout() -> int:
    return _env_timeout("IPFS_HOSTING_CAR_TIMEOUT", 180)


def _failure_report_threshold() -> int:
    return _env_timeout("IPFS_HOSTING_FAILURE_REPORT_THRESHOLD", 3)


def _pin_cid(cid: str) -> bool:
    if not _valid_cid_arg(cid):
        logger.warning("Refusing to pin malformed CID arg %r", cid)
        return False
    try:
        # pin/add blocks until the content is fetched from the swarm.
        _ipfs_post("/api/v0/pin/add", params={"arg": cid}, timeout=_pin_timeout())
        return True
    except requests.RequestException as e:
        logger.warning("IPFS pin of %s failed: %s", cid, e)
        return False


def _unpin_cid(cid: str) -> bool:
    if not _valid_cid_arg(cid):
        logger.warning("Refusing to unpin malformed CID arg %r", cid)
        return False
    try:
        _ipfs_post("/api/v0/pin/rm", params={"arg": cid}, timeout=30)
        return True
    except requests.RequestException as e:
        logger.warning("IPFS unpin of %s failed: %s", cid, e)
        return False


def _dag_stat_total_size(resp: requests.Response) -> int | None:
    """Final TotalSize from a ``dag/stat`` stream (#2907).

    ``object/stat`` was removed from current Kubo, so the old measure call
    always failed and every pin looked unmeasurable. ``dag/stat`` answers
    with progressive JSON objects — take the largest TotalSize seen.
    """
    total: int | None = None
    for line in resp.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            size = json.loads(line).get("TotalSize")
        except (ValueError, AttributeError):
            continue
        if size is not None:
            try:
                size = int(size)
            except (TypeError, ValueError):
                continue
            total = size if total is None else max(total, size)
    return total


def _object_size(cid: str) -> int | None:
    """Cumulative DAG size via ``dag/stat`` (#2802).

    ``object/stat`` was removed from current Kubo, so the old call always
    errored and every measure-then-reclaim check silently saw None. The
    endpoint streams NDJSON stat events; the last ``TotalSize`` is the DAG
    total.
    """
    if not _valid_cid_arg(cid):
        return None
    try:
        resp = _ipfs_post("/api/v0/dag/stat", params={"arg": cid}, timeout=30)
        if resp.status_code != 200:
            return None
        return _dag_stat_total_size(resp)
    except (requests.RequestException, ValueError):
        return None


def _cat_within_cap(cid: str, cap: int, timeout: int | None = None) -> bool | None:
    """Bounded pre-flight fetch probe (#2802).

    ``pin/add`` pulls the whole DAG before anything can measure it — a
    crafted job CID spends the provider's disk first and reclaims after.
    ``cat`` streams the same bytes but the consumer can abort at ``cap``;
    Kubo stops fetching once the client hangs up, bounding the swarm spend
    to ~cap. True = streamed within cap (content now local, pin is cheap);
    False = exceeded cap (refuse before pinning); None = cat cannot serve
    this dag shape (e.g. directory) — caller falls back to pin+measure.
    """
    if not _valid_cid_arg(cid):
        return None
    cat_timeout = timeout or _local_fetch_timeout()
    try:
        resp = requests.post(
            f"{IPFS_API_URL.rstrip('/')}/api/v0/cat",
            params={"arg": cid},
            timeout=cat_timeout,
            stream=True,
        )
        if resp.status_code != 200:
            return None
        received = 0
        for chunk in resp.iter_content(1024 * 1024):
            received += len(chunk)
            if received > cap:
                resp.close()
                return False
        return True
    except requests.RequestException as e:
        logger.debug("IPFS cat probe of %s failed: %s", cid, e)
        return None


def _car_cap_bytes(quota_bytes: int) -> int:
    """Proxy-transfer cap: content quota plus CAR framing overhead."""
    return quota_bytes * 11 // 10 + 1024 * 1024


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    data = stream.read(length)
    if len(data) != length:
        raise ValueError("truncated CAR section")
    return data


def _read_car_varint(stream: BinaryIO, first: bytes | None = None) -> int:
    """Read one unsigned LEB128 varint from a CAR stream."""
    result = 0
    shift = 0
    current = first
    for _ in range(10):
        if current is None:
            current = stream.read(1)
        if not current:
            raise ValueError("truncated CAR varint")
        byte = current[0]
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result
        shift += 7
        current = None
    raise ValueError("oversized CAR varint")


def _bytes_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    result = 0
    shift = 0
    for pos in range(offset, min(len(data), offset + 10)):
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos + 1
        shift += 7
    raise ValueError("invalid multihash varint")


def _cid_binary_multihash(raw: bytes) -> bytes:
    """Extract the multihash from a binary CIDv1, or a bare CIDv0 multihash."""
    # CIDv0 is the bare sha2-256 multihash (0x12 0x20 <digest>) and is the
    # common spelling for UnixFS objects created by older ipfs add flows.
    if len(raw) == 34 and raw[:2] == b"\x12\x20":
        return raw
    version, pos = _bytes_varint(raw, 0)
    if version != 1:
        raise ValueError(f"unsupported CID version {version}")
    _codec, pos = _bytes_varint(raw, pos)
    mh_start = pos
    _hash_code, pos = _bytes_varint(raw, pos)
    digest_len, pos = _bytes_varint(raw, pos)
    end = pos + digest_len
    if end != len(raw):
        raise ValueError("CID multihash length mismatch")
    return raw[mh_start:end]


def _decode_text_cid_multihash(cid: str) -> bytes:
    """Decode the multihash of a CIDv0 or base32/base58 CIDv1 text form.

    Unsupported multibase spellings fail closed: the fallback must never
    import unverified blocks merely because the job used an unusual CID
    encoding.
    """
    try:
        if cid.startswith("Qm"):
            return _cid_binary_multihash(base58.b58decode(cid))
        if cid.startswith("b"):
            encoded = cid[1:]
            padding = "=" * ((-len(encoded)) % 8)
            return _cid_binary_multihash(base64.b32decode((encoded + padding).upper(), casefold=True))
        if cid.startswith("z"):
            return _cid_binary_multihash(base58.b58decode(cid[1:]))
    except ValueError as e:
        raise ValueError(f"malformed CID for CAR verification: {e}") from e
    raise ValueError("unsupported CID multibase for CAR verification")


def _multihash_digest_matches(multihash: bytes, block_data: bytes) -> bool:
    """Validate a block against its multihash, failing closed on weak/unknown hashes."""
    try:
        hash_code, pos = _bytes_varint(multihash, 0)
        digest_len, pos = _bytes_varint(multihash, pos)
    except ValueError:
        return False
    end = pos + digest_len
    if end != len(multihash) or digest_len < 20:
        return False
    expected = multihash[pos:end]
    if hash_code == 0x12 and digest_len <= 32:  # sha2-256, possibly truncated
        actual = hashlib.sha256(block_data).digest()[:digest_len]
    elif hash_code == 0x13 and digest_len <= 64:  # sha2-512, possibly truncated
        actual = hashlib.sha512(block_data).digest()[:digest_len]
    elif hash_code == 0x16 and digest_len <= 32:  # sha3-256, possibly truncated
        actual = hashlib.sha3_256(block_data).digest()[:digest_len]
    elif hash_code == 0x15 and digest_len <= 48:  # sha3-384, possibly truncated
        actual = hashlib.sha3_384(block_data).digest()[:digest_len]
    elif hash_code == 0x14 and digest_len <= 64:  # sha3-512, possibly truncated
        actual = hashlib.sha3_512(block_data).digest()[:digest_len]
    elif hash_code == 0xB220 and digest_len <= 64:  # blake2b-256 family spelling carries length in the multihash
        actual = hashlib.blake2b(block_data, digest_size=digest_len).digest()
    else:
        # sha1 and unknown hash functions fail closed. Kubo's default and the
        # fleet's island daemon use sha2-256; accepting weak or unimplemented
        # hashes would weaken the end-to-end property this path exists for.
        return False
    return actual == expected


def _consume_car_cid(section: bytes) -> tuple[bytes, bytes]:
    """Split one CAR section into binary CID and block payload."""
    # Bare CIDv0 multihash form.
    if len(section) >= 34 and section[:2] == b"\x12\x20":
        return section[:34], section[34:]
    version, pos = _bytes_varint(section, 0)
    if version != 1:
        raise ValueError(f"unsupported CAR CID version {version}")
    _codec, pos = _bytes_varint(section, pos)
    _hash_code, pos = _bytes_varint(section, pos)
    digest_len, pos = _bytes_varint(section, pos)
    end = pos + digest_len
    if end > len(section):
        raise ValueError("truncated CAR CID")
    return section[:end], section[end:]


def _validate_car_integrity(car_file: BinaryIO, expected_cid: str, cap: int) -> None:
    """Verify every block hash in a downloaded CAR before importing it.

    Kubo's production CAR reader does not dependably re-hash every block
    (``go-block-format`` gates that check behind a debug build). The market
    proxy is therefore treated as transport, not authority: this local check
    verifies each block against the multihash in its own CID and requires the
    job CID to be present. Only then may the bytes enter the provider's
    blockstore. Unknown/weak hash functions fail closed.
    """
    expected_multihash = _decode_text_cid_multihash(expected_cid)
    car_file.seek(0)
    header_len = _read_car_varint(car_file)
    if header_len <= 0 or header_len > min(cap, 16 * 1024 * 1024):
        raise ValueError("invalid CAR header length")
    _read_exact(car_file, header_len)
    total = header_len
    found_root = False
    blocks = 0
    while True:
        first = car_file.read(1)
        if not first:
            break
        section_len = _read_car_varint(car_file, first)
        if section_len < 34:
            raise ValueError("invalid CAR block section length")
        total += section_len
        if total > cap:
            raise ValueError(f"content CAR exceeds the {cap}-byte cap")
        section = _read_exact(car_file, section_len)
        cid_bytes, block_data = _consume_car_cid(section)
        multihash = _cid_binary_multihash(cid_bytes)
        if not _multihash_digest_matches(multihash, block_data):
            raise ValueError("CAR block hash does not match its CID")
        if multihash == expected_multihash:
            found_root = True
        blocks += 1
    car_file.seek(0)
    if blocks == 0:
        raise ValueError("CAR contains no blocks")
    if not found_root:
        raise ValueError("CAR does not contain the job CID root")


def _download_market_car(
    market_url: str,
    job_id: str,
    cid: str,
    provider_address: str,
    cap: int,
) -> BinaryIO:
    """Download the job's CAR export through the market's signed hub proxy.

    The returned object is an anonymous temp file positioned at byte zero. It
    is never named in the filesystem and is closed by the caller after the
    local ``dag/import`` upload finishes.
    """
    route = f"/v1/market/jobs/{quote(str(job_id), safe='')}/content-car"
    binding = {"cid": cid}
    signed = _signed_request_params(provider_address, route, binding=binding)
    if signed is None:
        raise RuntimeError("provider wallet signature unavailable for market content-car fetch")
    response = requests.get(
        f"{market_url}{route}",
        params=signed,
        timeout=(5, _car_transfer_timeout()),
        stream=True,
    )
    response.raise_for_status()
    car = tempfile.TemporaryFile(prefix="aitbc-ipfs-car-")
    received = 0
    try:
        for chunk in response.iter_content(1024 * 1024):
            received += len(chunk)
            if received > cap:
                raise ValueError(f"market content CAR exceeds the {cap}-byte cap")
            car.write(chunk)
    except Exception:
        car.close()
        raise
    finally:
        response.close()
    car.seek(0)
    return car


def _import_market_car(car_file: Any) -> None:
    """Import a downloaded CAR into the provider's local daemon."""
    car_file.seek(0)
    car_timeout = _car_transfer_timeout()
    response = requests.post(
        f"{IPFS_API_URL.rstrip('/')}/api/v0/dag/import",
        params={"pin-roots": "false"},
        files={"file": ("content.car", car_file, "application/vnd.ipld.car")},
        timeout=car_timeout,
    )
    response.raise_for_status()


def _safe_exception_detail(exc: BaseException) -> str:
    detail = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    detail = re.sub(r"https?://\S+", "<url>", detail)
    return detail[:240]


def _pin_with_market_fallback(
    cid: str,
    job_id: str,
    market_url: str,
    provider_address: str,
    quota_bytes: int,
) -> tuple[bool, str | None]:
    """Pin locally first, then rescue through the hub CAR proxy (#2968).

    The proxy is not trusted for integrity: it only transports blocks. The
    blocks are verified locally against their CID multihashes before import,
    and the final ``pin/add`` of the job CID fails if the verified DAG does
    not reproduce that CID.
    """
    if _pin_cid(cid):
        return True, None
    direct_error = "direct swarm pin/add failed"
    car_file = None
    try:
        car_cap = _car_cap_bytes(quota_bytes)
        car_file = _download_market_car(market_url, job_id, cid, provider_address, car_cap)
        _validate_car_integrity(car_file, cid, car_cap)
        _import_market_car(car_file)
    except (requests.RequestException, OSError, ValueError, RuntimeError) as fallback_error:
        detail = _safe_exception_detail(fallback_error)
        return False, f"{direct_error}; hub CAR fallback failed: {detail}"
    finally:
        if car_file is not None:
            car_file.close()
    if _pin_cid(cid):
        return True, None
    return False, f"{direct_error}; hub CAR import completed but pin/add still failed"


def _report_pin_error(market_url: str, job_id: str, cid: str, provider_address: str, error_text: str) -> bool:
    """Report a persistent delivery failure to the market job (#2968)."""
    route = f"/v1/market/jobs/{quote(str(job_id), safe='')}/pin-error"
    summary = error_text[:500]
    binding = {"cid": cid, "error": summary}
    signed = _signed_request_params(provider_address, route, binding=binding)
    if signed is None:
        return False
    try:
        response = requests.post(
            f"{market_url}{route}",
            json={"cid": cid, "error": summary, "binding": binding, **signed},
            timeout=20,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        # 409 means delivery was confirmed before this stale failure report
        # landed. That is recovery, not a report failure worth retrying.
        if getattr(getattr(e, "response", None), "status_code", None) == 409:
            return True
        logger.warning("pin-error report for job %s failed: %s", job_id, e)
        return False


def _pin_failures(state: dict[str, dict[str, Any]]) -> dict[str, Any]:
    failures = state.get("_delivery_failures")
    if not isinstance(failures, dict):
        failures = {}
        state["_delivery_failures"] = failures
    return failures


def _record_pin_failure(
    state: dict[str, dict[str, Any]],
    market_url: str,
    job_id: str,
    cid: str,
    provider_address: str,
    error_text: str,
) -> None:
    """Count repeated failures and surface persistent non-delivery once.

    One timeout can be transient; the default third consecutive sweep report
    writes the provider's non-delivery attestation on the market job, which
    fails the unconfirmed rental and flags its escrow for buyer refund.
    """
    failures = _pin_failures(state)
    raw_entry = failures.get(job_id)
    entry: dict[str, Any] = raw_entry if isinstance(raw_entry, dict) else {}
    entry["count"] = int(entry.get("count") or 0) + 1
    entry["cid"] = cid
    entry["error"] = error_text[:500]
    entry["last_error_at"] = datetime.now(UTC).isoformat()
    if entry["count"] >= _failure_report_threshold() and not entry.get("reported"):
        if _report_pin_error(market_url, job_id, cid, provider_address, entry["error"]):
            entry["reported"] = True
    failures[job_id] = entry


def _clear_pin_failure(state: dict[str, dict[str, Any]], job_id: str) -> None:
    failures = state.get("_delivery_failures")
    if isinstance(failures, dict):
        failures.pop(job_id, None)
        if not failures:
            state.pop("_delivery_failures", None)


def _prune_pin_failures(state: dict[str, dict[str, Any]], active_jobs: list[dict[str, Any]]) -> None:
    active_ids = {_job_id(job) for job in active_jobs}
    failures = state.get("_delivery_failures")
    if not isinstance(failures, dict):
        return
    for job_id in list(failures):
        if job_id not in active_ids:
            failures.pop(job_id, None)
    if not failures:
        state.pop("_delivery_failures", None)


# Job listing pagination (#1489): the market caps ``limit`` at
# MARKET_MAX_PAGE_SIZE (default 500). The sweeper pages with ``offset`` until
# an empty page; a market that ignores ``offset`` returns the same first page
# forever and trips the page cap — the sweep is then marked *truncated* and
# stale-pin reclamation is skipped rather than unpinning live rentals.
_JOB_PAGE_SIZE = 500
_JOB_MAX_PAGES = 40  # 20k jobs — beyond this the sweep is marked truncated


def _fetch_jobs_page(
    market_url: str,
    provider_address: str,
    offset: int,
    signed: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """One page of this provider's ipfs market jobs, or None on fetch failure."""
    try:
        response = requests.get(
            f"{market_url}/v1/market/jobs",
            params={
                "service_type": "ipfs",
                "provider_address": provider_address,
                "limit": str(_JOB_PAGE_SIZE),
                "offset": str(offset),
                **signed,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Could not list market ipfs jobs: %s", e)
        return None
    if isinstance(data, dict):
        return list(data.get("jobs", []))
    if isinstance(data, list):
        return data
    return []


def _fetch_jobs(market_url: str, provider_address: str) -> tuple[list[dict[str, Any]], bool] | None:
    """All of this provider's ipfs market jobs, paginated.

    Returns ``(jobs, complete)`` — ``complete`` is False when the page cap was
    hit before the listing was exhausted — or ``None`` on fetch failure
    ("unknown": callers must never unpin based on a failed fetch). The request
    is provider-signed: the public feed is redacted, and full rows
    (``payload.cid`` et al.) go only to the recovered signer. A 401/403,
    missing signing material, or any other failure returns None.
    """
    signed = _signed_request_params(provider_address, "/v1/market/jobs")
    if signed is None:
        return None
    jobs: list[dict[str, Any]] = []
    offset = 0
    for _ in range(_JOB_MAX_PAGES):
        page = _fetch_jobs_page(market_url, provider_address, offset, signed)
        if page is None:
            return None
        jobs.extend(page)
        if not page:
            return jobs, True
        offset += len(page)
    logger.warning(
        "Market ipfs job listing did not end within %d pages; sweep will be marked truncated",
        _JOB_MAX_PAGES,
    )
    return jobs, False


def _fetch_job(market_url: str, job_id: str, provider_address: str) -> tuple[dict[str, Any] | None, bool]:
    """Direct lookup used to verify a pin's job before unpinning (#1489).

    Returns ``(job, True)`` when the market answered — ``job`` None on 404
    means the job is gone — or ``(None, False)`` when the answer is unknown
    (unsigned request, HTTP error, network). Unknown must keep the pin: an
    active job that fell outside the inspected listing page set is still a
    paid rental.
    """
    # #2914: job_id is market/buyer-influenced — encode it so it cannot
    # rewrite the path; the signature covers this exact route string.
    route = f"/v1/market/jobs/{quote(str(job_id), safe='')}"
    signed = _signed_request_params(provider_address, route)
    if signed is None:
        return None, False
    try:
        response = requests.get(f"{market_url}{route}", params=signed, timeout=20)
    except requests.RequestException:
        return None, False
    if response.status_code == 404:
        return None, True
    if response.status_code != 200:
        return None, False
    try:
        data = response.json()
    except ValueError:
        return None, False
    return (data if isinstance(data, dict) else None), True


def _pin_confirmed(job: dict[str, Any]) -> bool:
    payload = job.get("payload") or {}
    return bool(payload.get("provider_confirmed"))


def _confirm_pin(market_url: str, job_id: str, size: int | None, provider_address: str, cid: str | None = None) -> bool:
    route = f"/v1/market/jobs/{quote(str(job_id), safe='')}/pin-confirm"
    # #1922: the market requires the provider attestation to be signed over
    # a {cid, size} binding that matches the job — an unbound signature no
    # longer marks the rental delivered.
    binding = {"cid": cid, "size": size}
    signed = _signed_request_params(provider_address, route, binding=binding)
    if signed is None:
        return False
    try:
        response = requests.post(
            f"{market_url}{route}",
            json={"size": size, "provider_confirmed": True, "binding": binding, **signed},
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
    market_url: str,
    provider_address: str,
) -> bool:
    """Pin a CID for a job not yet tracked in state. True when pinned.

    Provider-side quota enforcement: the market checks usage at purchase
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
    if not _pin_confirmed(job):
        # #2802: bound the swarm fetch BEFORE pin/add — pin/add pulls the
        # whole DAG before anything can measure it, so an under-reported
        # job CID spends the provider's disk first and reclaims after. The
        # cat probe aborts at the buyer's quota; False means oversized.
        probe = _cat_within_cap(cid, quota_bytes)
        if probe is False:
            result["skipped_quota"] += 1
            logger.warning(
                "Skipping pin for job %s: CID %s exceeds the %s MB quota before fetch",
                job_id,
                cid,
                _job_quota_mb(job),
            )
            return False
    pinned, pin_error = _pin_with_market_fallback(cid, job_id, market_url, provider_address, quota_bytes)
    if not pinned:
        result["errors"] += 1
        _record_pin_failure(state, market_url, job_id, cid, provider_address, pin_error or "pin failed")
        return False
    _clear_pin_failure(state, job_id)
    size = _object_size(cid)
    if size is None:
        # #2907
        # rather than letting it persist forever with size=None counted as
        # handled (the old object/stat call always failed on current Kubo,
        # so EVERY pin used to land here unmeasured).
        _unpin_cid(cid)
        result["errors"] += 1
        logger.warning("Unpinned job %s: object size unmeasurable — cannot quota-account", job_id)
        return False
    if not _pin_confirmed(job):
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
    market_url: str,
    usage_by_buyer: dict[str, int],
    state: dict[str, dict[str, Any]],
    result: dict[str, int],
    provider_address: str,
) -> None:
    """Pin one active job's CID (quota-checked) and confirm it if needed."""
    job_id = _job_id(job)
    cid = _job_cid(job)
    if not job_id or not cid:
        return
    if job_id in state and _pin_confirmed(job):
        return
    if job_id not in state and not _pin_new_job(job, job_id, cid, usage_by_buyer, state, result, market_url, provider_address):
        return
    size = state[job_id].get("size")
    if size is None:
        # #2907: pins recorded before measurement worked (or during a stat
        # outage) carry size=None forever — re-stat each sweep so quota
        # accounting converges instead of staying blind.
        size = _object_size(cid)
        if size is not None:
            state[job_id]["size"] = size
            if size > _job_quota_mb(job) * 1024 * 1024:
                # Measured content alone exceeds the job's whole quota —
                # reclaim rather than host it unaccounted.
                _unpin_cid(cid)
                state.pop(job_id, None)
                result["skipped_quota"] += 1
                logger.warning("Unpinned job %s: measured %s bytes exceeds %s MB quota", job_id, size, _job_quota_mb(job))
                return
    if not _pin_confirmed(job):
        if _confirm_pin(market_url, job_id, size, provider_address, cid=cid):
            result["confirmed"] += 1


def _pin_active_jobs(
    active_jobs: list[dict[str, Any]],
    market_url: str,
    state: dict[str, dict[str, Any]],
    result: dict[str, int],
    provider_address: str,
) -> None:
    """Pin every active job's CID, enforcing the per-buyer disk quota."""
    # Per-buyer usage across active jobs, for the provider-side quota check.
    usage_by_buyer: dict[str, int] = {}
    for job in active_jobs:
        buyer = str(job.get("buyer_address") or "")
        usage_by_buyer[buyer] = usage_by_buyer.get(buyer, 0) + _job_size(job)

    _prune_pin_failures(state, active_jobs)
    for job in active_jobs:
        _pin_active_job(job, market_url, usage_by_buyer, state, result, provider_address)


def _unpin_stale_jobs(
    state: dict[str, dict[str, Any]],
    active_jobs: list[dict[str, Any]],
    market_url: str,
    provider_address: str,
    result: dict[str, int],
) -> None:
    """Reclaim disk for jobs confirmed terminal or gone — never on absence alone.

    Each unpin candidate is re-checked with a direct signed job lookup before
    the pin is removed (#1489): a job that was active but fell outside the
    inspected listing page set keeps its pin, and an unverifiable lookup
    defers the unpin to a later sweep.
    """
    active_ids = {_job_id(j) for j in active_jobs}
    # CIDs still referenced by an active job must not be unpinned even if a
    # sibling job that shared the CID reached a terminal state.
    active_cids = {cid for cid in map(_job_cid, active_jobs) if cid}

    for job_id, entry in list(state.items()):
        if job_id.startswith("_"):
            # Reserved bookkeeping keys (e.g. "_untracked" reconcile state)
            # are not job entries.
            continue
        if job_id in active_ids:
            continue
        cid = entry.get("cid")
        if not cid or cid in active_cids:
            del state[job_id]
            continue
        job, known = _fetch_job(market_url, job_id, provider_address)
        if not known:
            result["deferred"] += 1
            continue
        if job is not None and str(job.get("state", "")).upper() in ACTIVE_STATES:
            # Still a live rental — the listing missed it (pagination drift or
            # a state transition mid-sweep). Keep the pin.
            result["deferred"] += 1
            continue
        if _unpin_cid(cid):
            result["unpinned"] += 1
        else:
            result["errors"] += 1
            continue  # keep the state entry so we retry the unpin
        del state[job_id]


def _daemon_pins() -> set[str] | None:
    """CIDs currently pinned on the local daemon, or None when unreachable."""
    try:
        data = _ipfs_post("/api/v0/pin/ls", timeout=30).json()
    except (requests.RequestException, ValueError):
        return None
    keys = data.get("Keys") if isinstance(data, dict) else None
    if not isinstance(keys, dict):
        return set()
    # Keys may be bare CIDs or "/ipfs/<cid>" paths — normalise to the CID.
    return {str(k).rsplit("/", 1)[-1] for k in keys}


def _handle_untracked_candidate(
    cid: str,
    market_cids: set[str],
    untracked: dict[str, Any],
    now: datetime,
    result: dict[str, int],
) -> None:
    """First-seen bookkeeping and grace-gated reclaim for one daemon pin."""
    if cid not in market_cids:
        return
    first_seen_raw = untracked.get(cid)
    if first_seen_raw is None:
        untracked[cid] = now.isoformat()
        return
    try:
        age = (now - datetime.fromisoformat(str(first_seen_raw))).total_seconds()
    except ValueError:
        age = _UNTRACKED_PIN_GRACE_SECONDS + 1
    if age < _UNTRACKED_PIN_GRACE_SECONDS:
        return
    if _unpin_cid(cid):
        result["reclaimed"] += 1
        untracked.pop(cid, None)
        logger.info("Reclaimed untracked IPFS pin %s after grace window", cid)
    # On unpin failure keep the entry so the next sweep retries.


def _reconcile_untracked_pins(
    state: dict[str, dict[str, Any]],
    jobs: list[dict[str, Any]],
    result: dict[str, int],
) -> None:
    """Reclaim pins the state file never recorded (crash window, #1687).

    ``state`` is the only tracker this sweeper has: a crash between
    ``pin/add`` and ``_save_state`` — or a failed save — orphans the pin
    forever because ``--enable-gc`` never collects pinned blocks. Each
    complete sweep diffs ``pin/ls`` against state; a pinned CID that is
    (a) untracked, (b) not referenced by an active job, and (c) known to the
    market listing for this provider is remembered under the reserved
    ``"_untracked"`` key and unpinned once it has stayed untracked for
    ``IPFS_UNTRACKED_PIN_GRACE_SECONDS``. Pins the market has never heard of
    are left alone — they may be legitimate manual pins on this daemon.
    """
    if _UNTRACKED_PIN_GRACE_SECONDS <= 0:
        return
    daemon_pins = _daemon_pins()
    if daemon_pins is None:
        return

    tracked_cids = {
        str(entry.get("cid"))
        for job_id, entry in state.items()
        if not job_id.startswith("_") and isinstance(entry, dict) and entry.get("cid")
    }
    active_cids = {cid for job in jobs if str(job.get("state", "")).upper() in ACTIVE_STATES for cid in [_job_cid(job)] if cid}
    market_cids = {cid for job in jobs for cid in [_job_cid(job)] if cid}

    untracked: dict[str, Any] = state.setdefault("_untracked", {})
    now = datetime.now(UTC)
    for cid in sorted(daemon_pins - tracked_cids - active_cids):
        _handle_untracked_candidate(cid, market_cids, untracked, now, result)

    # Forget bookkeeping for CIDs no longer pinned at all.
    for cid in list(untracked):
        if cid not in daemon_pins:
            untracked.pop(cid, None)
    if not untracked:
        state.pop("_untracked", None)


def sweep_once(provider_address: str, state_path: Path | None = None) -> dict[str, int]:
    """Run one provider-side pin sweep. Returns counters for logging/tests."""
    result = {
        "pinned": 0,
        "confirmed": 0,
        "unpinned": 0,
        "skipped_quota": 0,
        "errors": 0,
        "truncated": 0,
        "deferred": 0,
        "reclaimed": 0,
    }
    if os.environ.get("IPFS_HOSTING_ENABLED", "1").lower() in ("0", "false", "no"):
        return result
    if not provider_address:
        return result
    if not _daemon_available():
        logger.debug("IPFS daemon not reachable at %s; skipping hosting sweep", IPFS_API_URL)
        return result

    market_url = _market_base()
    state_path = state_path or _state_path()
    state = _load_state(state_path)

    fetched = _fetch_jobs(market_url, provider_address)
    if fetched is None:
        result["errors"] += 1
        return result
    jobs, listing_complete = fetched

    active_jobs = [j for j in jobs if str(j.get("state", "")).upper() in ACTIVE_STATES]
    _pin_active_jobs(active_jobs, market_url, state, result, provider_address)
    if listing_complete:
        _unpin_stale_jobs(state, active_jobs, market_url, provider_address, result)
        _reconcile_untracked_pins(state, jobs, result)
    else:
        # The inspected set may be missing active jobs — unpinning now could
        # reclaim paid hosting. Defer reclamation to a complete sweep (#1489).
        result["truncated"] = 1
        logger.warning("IPFS job listing truncated; skipped stale-pin reclamation this sweep")

    _save_state(state_path, state)
    if any(result.values()):
        logger.info("IPFS hosting sweep: %s", result)
    return result
