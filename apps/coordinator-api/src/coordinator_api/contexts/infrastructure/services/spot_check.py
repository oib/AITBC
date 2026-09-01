from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from aitbc.constants import LOG_DIR

from ....config import settings
from ..domain import Job
from .jobs import JobService

logger = get_logger(__name__)


def _spot_check_log_path() -> Path:
    """Return the log path for spot-check comparisons."""
    # Use the audit log directory if configured, otherwise LOG_DIR.
    base = Path(getattr(settings, "audit_log_dir", None) or LOG_DIR)
    return base / "spot_checks.jsonl"


def _output_text(result: dict[str, Any] | None) -> str:
    """Extract the canonical output string from a job result payload."""
    if not result:
        return ""
    inner = result.get("result") or {}
    return str(inner.get("output", "")).strip()


def _hash_output(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_log(record: dict[str, Any]) -> None:
    """Append a structured JSON line to the spot-check log."""
    path = _spot_check_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except Exception as e:
        logger.warning("Failed to write spot-check log to %s: %s", path, e)


class SpotCheckService:
    """G3 shadow-mode spot-check re-runs for deterministic-decoding jobs.

    A deterministic job can be re-executed by another (or the same) miner with
    identical decoding parameters. The coordinator compares the two outputs and
    logs whether they match exactly. This is intentionally log-only; no automatic
    slashing happens at this stage.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.job_service = JobService(session)

    def schedule_if_eligible(self, job: Job) -> Job | None:
        """Create a shadow re-run of a completed deterministic-decoding job."""
        constraints = job.constraints or {}
        if not constraints.get("deterministic_decoding"):
            return None
        if constraints.get("spot_check_for") or constraints.get("shadow_mode"):
            return None

        now = datetime.now(UTC)
        shadow_constraints = dict(constraints)
        shadow_constraints["deterministic_decoding"] = True
        shadow_constraints["shadow_mode"] = True
        shadow_constraints["spot_check_for"] = job.id
        # Ensure the same decode seed is reused.
        if "decode_seed" not in shadow_constraints:
            shadow_constraints["decode_seed"] = 0

        shadow = Job(
            client_id=job.client_id,
            client_ref=job.client_ref,
            state="QUEUED",
            payload=job.payload,
            constraints=shadow_constraints,
            ttl_seconds=job.ttl_seconds,
            requested_at=now,
            expires_at=now + timedelta(seconds=job.ttl_seconds),
        )
        self.session.add(shadow)
        self.session.commit()
        self.session.refresh(shadow)

        _write_log(
            {
                "event": "scheduled",
                "timestamp": now.isoformat(),
                "original_job_id": job.id,
                "spot_check_job_id": shadow.id,
            }
        )
        logger.info("Scheduled shadow spot-check job %s for deterministic job %s", shadow.id, job.id)
        return shadow

    def complete_spot_check(self, job: Job) -> dict[str, Any]:
        """Compare a completed spot-check re-run to the original job and log it."""
        constraints = job.constraints or {}
        original_id = constraints.get("spot_check_for")
        if not original_id:
            return {}

        original = self.session.execute(select(Job).where(Job.id == original_id)).scalars().first()
        if not original:
            logger.warning("Spot-check job %s references missing original %s", job.id, original_id)
            return {}

        spot_output = _output_text(job.result)
        original_output = _output_text(original.result)
        match = spot_output == original_output

        spot_hash = _hash_output(spot_output)
        original_hash = _hash_output(original_output)

        record = {
            "event": "completed",
            "timestamp": datetime.now(UTC).isoformat(),
            "original_job_id": original_id,
            "spot_check_job_id": job.id,
            "assigned_miner_id": job.assigned_miner_id,
            "match": match,
            "original_output_hash": original_hash,
            "spot_output_hash": spot_hash,
            "original_output_length": len(original_output),
            "spot_output_length": len(spot_output),
        }
        _write_log(record)

        # Record the outcome on the original job so it is queryable without
        # adding a new table. Constraints are stored as JSON, so extra keys are
        # safe as long as the code reading them checks the dict directly.
        original_result = dict(original.constraints or {})
        original_result["spot_check_result"] = {
            "spot_check_job_id": job.id,
            "match": match,
            "completed_at": record["timestamp"],
            "original_output_hash": original_hash,
            "spot_output_hash": spot_hash,
        }
        original.constraints = original_result
        self.session.add(original)

        # Also store on the shadow job for symmetry.
        shadow_constraints = dict(constraints)
        shadow_constraints["spot_check_result"] = record
        job.constraints = shadow_constraints
        self.session.add(job)
        self.session.commit()

        if match:
            logger.info("Spot-check match for job %s (shadow %s)", original_id, job.id)
        else:
            logger.warning(
                "Spot-check MISMATCH for job %s (shadow %s): original_hash=%s spot_hash=%s",
                original_id,
                job.id,
                original_hash,
                spot_hash,
            )
        return record
