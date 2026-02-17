"""
Audit logging service for privacy compliance
"""

import os
import json
import hashlib
import gzip
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict

from ..schemas import ConfidentialAccessLog
from ..config import settings
from ..logging import get_logger

logger = get_logger(__name__)


@dataclass
class AuditEvent:
    """Structured audit event"""

    event_id: str
    timestamp: datetime
    event_type: str
    participant_id: str
    transaction_id: Optional[str]
    action: str
    resource: str
    outcome: str
    details: Dict[str, Any]
    ip_address: Optional[str]
    user_agent: Optional[str]
    authorization: Optional[str]
    signature: Optional[str]


class AuditLogger:
    """Tamper-evident audit logging for privacy compliance"""

    def __init__(self, log_dir: str = None):
        # Use test-specific directory if in test environment
        if os.getenv("PYTEST_CURRENT_TEST"):
            # Use project logs directory for tests
            # Navigate from coordinator-api/src/app/services/audit_logging.py to project root
            # Path: coordinator-api/src/app/services/audit_logging.py -> apps/coordinator-api/src -> apps/coordinator-api -> apps -> project_root
            project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
            test_log_dir = project_root / "logs" / "audit"
            log_path = log_dir or str(test_log_dir)
        else:
            log_path = log_dir or settings.audit_log_dir
        
        self.log_dir = Path(log_path)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Current log file
        self.current_file = None
        self.current_hash = None

        # Async writer task
        self.write_queue = asyncio.Queue(maxsize=10000)
        self.writer_task = None

        # Chain of hashes for integrity
        self.chain_hash = self._load_chain_hash()

    async def start(self):
        """Start the background writer task"""
        if self.writer_task is None:
            self.writer_task = asyncio.create_task(self._background_writer())

    async def stop(self):
        """Stop the background writer task"""
        if self.writer_task:
            self.writer_task.cancel()
            try:
                await self.writer_task
            except asyncio.CancelledError:
                pass
            self.writer_task = None

    async def log_access(
        self,
        participant_id: str,
        transaction_id: Optional[str],
        action: str,
        outcome: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        authorization: Optional[str] = None,
    ):
        """Log access to confidential data"""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            timestamp=datetime.utcnow(),
            event_type="access",
            participant_id=participant_id,
            transaction_id=transaction_id,
            action=action,
            resource="confidential_transaction",
            outcome=outcome,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            authorization=authorization,
            signature=None,
        )

        # Add signature for tamper-evidence
        event.signature = self._sign_event(event)

        # Queue for writing
        await self.write_queue.put(event)

    async def log_key_operation(
        self,
        participant_id: str,
        operation: str,
        key_version: int,
        outcome: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Log key management operations"""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            timestamp=datetime.utcnow(),
            event_type="key_operation",
            participant_id=participant_id,
            transaction_id=None,
            action=operation,
            resource="encryption_key",
            outcome=outcome,
            details={**(details or {}), "key_version": key_version},
            ip_address=None,
            user_agent=None,
            authorization=None,
            signature=None,
        )

        event.signature = self._sign_event(event)
        await self.write_queue.put(event)

    async def log_policy_change(
        self,
        participant_id: str,
        policy_id: str,
        change_type: str,
        outcome: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Log access policy changes"""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            timestamp=datetime.utcnow(),
            event_type="policy_change",
            participant_id=participant_id,
            transaction_id=None,
            action=change_type,
            resource="access_policy",
            outcome=outcome,
            details={**(details or {}), "policy_id": policy_id},
            ip_address=None,
            user_agent=None,
            authorization=None,
            signature=None,
        )

        event.signature = self._sign_event(event)
        await self.write_queue.put(event)

    def query_logs(
        self,
        participant_id: Optional[str] = None,
        transaction_id: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Query audit logs"""
        results = []

        # Get list of log files to search
        log_files = self._get_log_files(start_time, end_time)

        for log_file in log_files:
            try:
                # Read and decompress if needed
                if log_file.suffix == ".gz":
                    with gzip.open(log_file, "rt") as f:
                        for line in f:
                            event = self._parse_log_line(line.strip())
                            if self._matches_query(
                                event,
                                participant_id,
                                transaction_id,
                                event_type,
                                start_time,
                                end_time,
                            ):
                                results.append(event)
                                if len(results) >= limit:
                                    return results
                else:
                    with open(log_file, "r") as f:
                        for line in f:
                            event = self._parse_log_line(line.strip())
                            if self._matches_query(
                                event,
                                participant_id,
                                transaction_id,
                                event_type,
                                start_time,
                                end_time,
                            ):
                                results.append(event)
                                if len(results) >= limit:
                                    return results
            except Exception as e:
                logger.error(f"Failed to read log file {log_file}: {e}")
                continue

        # Sort by timestamp (newest first)
        results.sort(key=lambda x: x.timestamp, reverse=True)

        return results[:limit]

    def verify_integrity(self, start_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Verify integrity of audit logs"""
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=30)

        results = {
            "verified_files": 0,
            "total_files": 0,
            "integrity_violations": [],
            "chain_valid": True,
        }

        log_files = self._get_log_files(start_date)

        for log_file in log_files:
            results["total_files"] += 1

            try:
                # Verify file hash
                file_hash = self._calculate_file_hash(log_file)
                stored_hash = self._get_stored_hash(log_file)

                if file_hash != stored_hash:
                    results["integrity_violations"].append(
                        {
                            "file": str(log_file),
                            "expected": stored_hash,
                            "actual": file_hash,
                        }
                    )
                    results["chain_valid"] = False
                else:
                    results["verified_files"] += 1

            except Exception as e:
                logger.error(f"Failed to verify {log_file}: {e}")
                results["integrity_violations"].append(
                    {"file": str(log_file), "error": str(e)}
                )
                results["chain_valid"] = False

        return results

    def export_logs(
        self,
        start_time: datetime,
        end_time: datetime,
        format: str = "json",
        include_signatures: bool = True,
    ) -> str:
        """Export audit logs for compliance reporting"""
        events = self.query_logs(start_time=start_time, end_time=end_time, limit=10000)

        if format == "json":
            export_data = {
                "export_metadata": {
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "event_count": len(events),
                    "exported_at": datetime.utcnow().isoformat(),
                    "include_signatures": include_signatures,
                },
                "events": [],
            }

            for event in events:
                event_dict = asdict(event)
                event_dict["timestamp"] = event.timestamp.isoformat()

                if not include_signatures:
                    event_dict.pop("signature", None)

                export_data["events"].append(event_dict)

            return json.dumps(export_data, indent=2)

        elif format == "csv":
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Header
            header = [
                "event_id",
                "timestamp",
                "event_type",
                "participant_id",
                "transaction_id",
                "action",
                "resource",
                "outcome",
                "ip_address",
                "user_agent",
            ]
            if include_signatures:
                header.append("signature")
            writer.writerow(header)

            # Events
            for event in events:
                row = [
                    event.event_id,
                    event.timestamp.isoformat(),
                    event.event_type,
                    event.participant_id,
                    event.transaction_id,
                    event.action,
                    event.resource,
                    event.outcome,
                    event.ip_address,
                    event.user_agent,
                ]
                if include_signatures:
                    row.append(event.signature)
                writer.writerow(row)

            return output.getvalue()

        else:
            raise ValueError(f"Unsupported export format: {format}")

    async def _background_writer(self):
        """Background task for writing audit events"""
        while True:
            try:
                # Get batch of events
                events = []
                while len(events) < 100:
                    try:
                        # Use asyncio.wait_for for timeout
                        event = await asyncio.wait_for(
                            self.write_queue.get(), timeout=1.0
                        )
                        events.append(event)
                    except asyncio.TimeoutError:
                        if events:
                            break
                        continue

                # Write events
                if events:
                    self._write_events(events)

            except Exception as e:
                logger.error(f"Background writer error: {e}")
                # Brief pause to avoid error loops
                await asyncio.sleep(1)

    def _write_events(self, events: List[AuditEvent]):
        """Write events to current log file"""
        try:
            self._rotate_if_needed()

            with open(self.current_file, "a") as f:
                for event in events:
                    # Convert to JSON line
                    event_dict = asdict(event)
                    event_dict["timestamp"] = event.timestamp.isoformat()

                    # Write with signature
                    line = json.dumps(event_dict, separators=(",", ":")) + "\n"
                    f.write(line)
                    f.flush()

            # Update chain hash
            self._update_chain_hash(events[-1])

        except Exception as e:
            logger.error(f"Failed to write audit events: {e}")

    def _rotate_if_needed(self):
        """Rotate log file if needed"""
        now = datetime.utcnow()
        today = now.date()

        # Check if we need a new file
        if self.current_file is None:
            self._new_log_file(today)
        else:
            file_date = datetime.fromisoformat(
                self.current_file.stem.split("_")[1]
            ).date()

            if file_date != today:
                self._new_log_file(today)

    def _new_log_file(self, date):
        """Create new log file for date"""
        filename = f"audit_{date.isoformat()}.log"
        self.current_file = self.log_dir / filename

        # Write header with metadata
        if not self.current_file.exists():
            header = {
                "created_at": datetime.utcnow().isoformat(),
                "version": "1.0",
                "format": "jsonl",
                "previous_hash": self.chain_hash,
            }

            with open(self.current_file, "w") as f:
                f.write(f"# {json.dumps(header)}\n")

    def _generate_event_id(self) -> str:
        """Generate unique event ID"""
        return f"evt_{datetime.utcnow().timestamp()}_{os.urandom(4).hex()}"

    def _sign_event(self, event: AuditEvent) -> str:
        """Sign event for tamper-evidence"""
        # Create canonical representation
        event_data = {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "participant_id": event.participant_id,
            "action": event.action,
            "outcome": event.outcome,
        }

        # Hash with previous chain hash
        data = json.dumps(event_data, separators=(",", ":"), sort_keys=True)
        combined = f"{self.chain_hash}:{data}".encode()

        return hashlib.sha256(combined).hexdigest()

    def _update_chain_hash(self, last_event: AuditEvent):
        """Update chain hash with new event"""
        self.chain_hash = last_event.signature or self.chain_hash

        # Store chain hash for integrity checking
        chain_file = self.log_dir / "chain.hash"
        with open(chain_file, "w") as f:
            f.write(self.chain_hash)

    def _load_chain_hash(self) -> str:
        """Load previous chain hash"""
        chain_file = self.log_dir / "chain.hash"
        if chain_file.exists():
            with open(chain_file, "r") as f:
                return f.read().strip()
        return "0" * 64  # Initial hash

    def _get_log_files(
        self, start_time: Optional[datetime], end_time: Optional[datetime]
    ) -> List[Path]:
        """Get list of log files to search"""
        files = []

        for file in self.log_dir.glob("audit_*.log*"):
            try:
                # Extract date from filename
                date_str = file.stem.split("_")[1]
                file_date = datetime.fromisoformat(date_str).date()

                # Check if file is in range
                file_start = datetime.combine(file_date, datetime.min.time())
                file_end = file_start + timedelta(days=1)

                if (not start_time or file_end >= start_time) and (
                    not end_time or file_start <= end_time
                ):
                    files.append(file)

            except Exception:
                continue

        return sorted(files)

    def _parse_log_line(self, line: str) -> Optional[AuditEvent]:
        """Parse log line into event"""
        if line.startswith("#"):
            return None  # Skip header

        try:
            data = json.loads(line)
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
            return AuditEvent(**data)
        except Exception as e:
            logger.error(f"Failed to parse log line: {e}")
            return None

    def _matches_query(
        self,
        event: Optional[AuditEvent],
        participant_id: Optional[str],
        transaction_id: Optional[str],
        event_type: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
    ) -> bool:
        """Check if event matches query criteria"""
        if not event:
            return False

        if participant_id and event.participant_id != participant_id:
            return False

        if transaction_id and event.transaction_id != transaction_id:
            return False

        if event_type and event.event_type != event_type:
            return False

        if start_time and event.timestamp < start_time:
            return False

        if end_time and event.timestamp > end_time:
            return False

        return True

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file"""
        hash_sha256 = hashlib.sha256()

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)

        return hash_sha256.hexdigest()

    def _get_stored_hash(self, file_path: Path) -> str:
        """Get stored hash for file"""
        hash_file = file_path.with_suffix(".hash")
        if hash_file.exists():
            with open(hash_file, "r") as f:
                return f.read().strip()
        return ""


# Global audit logger instance
audit_logger = AuditLogger()
