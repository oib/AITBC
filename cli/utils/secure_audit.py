"""
Tamper-Evident Audit Logger
Provides cryptographic integrity for audit logs
"""

import json
import hashlib
import secrets
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, List, Optional, Tuple
from eth_utils import keccak


class SecureAuditLogger:
    """
    Tamper-evident audit logger with cryptographic integrity
    Each entry includes hash of previous entry for chain integrity
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or Path.home() / ".aitbc" / "audit"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "audit_secure.jsonl"
        self.integrity_file = self.log_dir / "integrity.json"
        
        # Initialize integrity tracking
        self._init_integrity()
    
    def _init_integrity(self):
        """Initialize integrity tracking"""
        if not self.integrity_file.exists():
            integrity_data = {
                "genesis_hash": None,
                "last_hash": None,
                "entry_count": 0,
                "created_at": datetime.now(datetime.UTC).isoformat(),
                "version": "1.0"
            }
            with open(self.integrity_file, "w") as f:
                json.dump(integrity_data, f, indent=2)
    
    def _get_integrity_data(self) -> Dict:
        """Get current integrity data"""
        with open(self.integrity_file, "r") as f:
            return json.load(f)
    
    def _update_integrity(self, entry_hash: str):
        """Update integrity tracking"""
        integrity_data = self._get_integrity_data()
        
        if integrity_data["genesis_hash"] is None:
            integrity_data["genesis_hash"] = entry_hash
        
        integrity_data["last_hash"] = entry_hash
        integrity_data["entry_count"] += 1
        integrity_data["last_updated"] = datetime.now(datetime.UTC).isoformat()
        
        with open(self.integrity_file, "w") as f:
            json.dump(integrity_data, f, indent=2)
    
    def _create_entry_hash(self, entry: Dict, previous_hash: Optional[str] = None) -> str:
        """
        Create cryptographic hash for audit entry
        
        Args:
            entry: Audit entry data
            previous_hash: Hash of previous entry for chain integrity
            
        Returns:
            Entry hash
        """
        # Create canonical representation
        entry_data = {
            "timestamp": entry["timestamp"],
            "action": entry["action"],
            "user": entry["user"],
            "details": entry["details"],
            "previous_hash": previous_hash,
            "nonce": entry.get("nonce", "")
        }
        
        # Sort keys for deterministic ordering
        entry_str = json.dumps(entry_data, sort_keys=True, separators=(',', ':'))
        return keccak(entry_str.encode()).hex()
    
    def log(self, action: str, details: dict = None, user: str = None):
        """
        Log an audit event with cryptographic integrity
        
        Args:
            action: Action being logged
            details: Additional details
            user: User performing action
        """
        # Get previous hash for chain integrity
        integrity_data = self._get_integrity_data()
        previous_hash = integrity_data["last_hash"]
        
        # Create audit entry
        entry = {
            "timestamp": datetime.now(datetime.UTC).isoformat(),
            "action": action,
            "user": user or "unknown",
            "details": details or {},
            "nonce": secrets.token_hex(16)
        }
        
        # Create entry hash
        entry_hash = self._create_entry_hash(entry, previous_hash)
        entry["entry_hash"] = entry_hash
        
        # Write to log file
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        
        # Update integrity tracking
        self._update_integrity(entry_hash)
    
    def verify_integrity(self) -> Tuple[bool, List[str]]:
        """
        Verify the integrity of the entire audit log
        
        Returns:
            Tuple of (is_valid, issues)
        """
        if not self.log_file.exists():
            return True, ["No audit log exists"]
        
        issues = []
        previous_hash = None
        entry_count = 0
        
        try:
            with open(self.log_file, "r") as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    
                    entry = json.loads(line)
                    entry_count += 1
                    
                    # Verify entry hash
                    expected_hash = self._create_entry_hash(entry, previous_hash)
                    actual_hash = entry.get("entry_hash")
                    
                    if actual_hash != expected_hash:
                        issues.append(f"Line {line_num}: Hash mismatch - entry may be tampered")
                    
                    # Verify chain integrity
                    if previous_hash and entry.get("previous_hash") != previous_hash:
                        issues.append(f"Line {line_num}: Chain integrity broken")
                    
                    previous_hash = actual_hash
            
            # Verify against integrity file
            integrity_data = self._get_integrity_data()
            
            if integrity_data["entry_count"] != entry_count:
                issues.append(f"Entry count mismatch: log has {entry_count}, integrity says {integrity_data['entry_count']}")
            
            if integrity_data["last_hash"] != previous_hash:
                issues.append("Final hash mismatch with integrity file")
            
            return len(issues) == 0, issues
            
        except Exception as e:
            return False, [f"Verification failed: {str(e)}"]
    
    def get_logs(self, limit: int = 50, action_filter: str = None, verify: bool = True) -> List[Dict]:
        """
        Read audit log entries with optional integrity verification
        
        Args:
            limit: Maximum number of entries
            action_filter: Filter by action type
            verify: Whether to verify integrity
            
        Returns:
            List of audit entries
        """
        if verify:
            is_valid, issues = self.verify_integrity()
            if not is_valid:
                raise ValueError(f"Audit log integrity compromised: {issues}")
        
        if not self.log_file.exists():
            return []
        
        entries = []
        with open(self.log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    if action_filter and entry.get("action") != action_filter:
                        continue
                    entries.append(entry)
        
        return entries[-limit:]
    
    def export_audit_report(self, output_file: Optional[Path] = None) -> Dict:
        """
        Export comprehensive audit report with integrity verification
        
        Args:
            output_file: Optional file to write report
            
        Returns:
            Audit report data
        """
        # Verify integrity
        is_valid, issues = self.verify_integrity()
        
        # Get statistics
        all_entries = self.get_logs(limit=10000, verify=False)  # Don't double-verify
        
        # Action statistics
        action_counts = {}
        user_counts = {}
        hourly_counts = {}
        
        for entry in all_entries:
            # Action counts
            action = entry.get("action", "unknown")
            action_counts[action] = action_counts.get(action, 0) + 1
            
            # User counts
            user = entry.get("user", "unknown")
            user_counts[user] = user_counts.get(user, 0) + 1
            
            # Hourly counts
            try:
                hour = entry["timestamp"][:13]  # YYYY-MM-DDTHH
                hourly_counts[hour] = hourly_counts.get(hour, 0) + 1
            except:
                pass
        
        # Create report
        report = {
            "audit_report": {
                "generated_at": datetime.now(datetime.UTC).isoformat(),
                "integrity": {
                    "is_valid": is_valid,
                    "issues": issues
                },
                "statistics": {
                    "total_entries": len(all_entries),
                    "unique_actions": len(action_counts),
                    "unique_users": len(user_counts),
                    "date_range": {
                        "first_entry": all_entries[0]["timestamp"] if all_entries else None,
                        "last_entry": all_entries[-1]["timestamp"] if all_entries else None
                    }
                },
                "action_breakdown": action_counts,
                "user_breakdown": user_counts,
                "recent_activity": hourly_counts
            },
            "sample_entries": all_entries[-10:]  # Last 10 entries
        }
        
        # Write to file if specified
        if output_file:
            with open(output_file, "w") as f:
                json.dump(report, f, indent=2)
        
        return report
    
    def search_logs(self, query: str, limit: int = 50) -> List[Dict]:
        """
        Search audit logs for specific content
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            Matching entries
        """
        entries = self.get_logs(limit=1000, verify=False)  # Get more for search
        
        matches = []
        query_lower = query.lower()
        
        for entry in entries:
            # Search in action, user, and details
            searchable_text = f"{entry.get('action', '')} {entry.get('user', '')} {json.dumps(entry.get('details', {}))}"
            
            if query_lower in searchable_text.lower():
                matches.append(entry)
                if len(matches) >= limit:
                    break
        
        return matches
    
    def get_chain_info(self) -> Dict:
        """
        Get information about the audit chain
        
        Returns:
            Chain information
        """
        integrity_data = self._get_integrity_data()
        
        return {
            "genesis_hash": integrity_data["genesis_hash"],
            "last_hash": integrity_data["last_hash"],
            "entry_count": integrity_data["entry_count"],
            "created_at": integrity_data["created_at"],
            "last_updated": integrity_data.get("last_updated"),
            "version": integrity_data["version"],
            "log_file": str(self.log_file),
            "integrity_file": str(self.integrity_file)
        }


# Global secure audit logger instance
secure_audit_logger = SecureAuditLogger()


# Convenience functions for backward compatibility
def log_action(action: str, details: dict = None, user: str = None):
    """Log an action with secure audit logger"""
    secure_audit_logger.log(action, details, user)


def verify_audit_integrity() -> Tuple[bool, List[str]]:
    """Verify audit log integrity"""
    return secure_audit_logger.verify_integrity()


def get_audit_logs(limit: int = 50, action_filter: str = None) -> List[Dict]:
    """Get audit logs with integrity verification"""
    return secure_audit_logger.get_logs(limit, action_filter)
