"""Island members detection via journalctl parsing.

Moved from hermes_service.handlers.island_members in v0.5.9 §3.
"""

import re
import subprocess

from aitbc.aitbc_logging import get_logger


def get_island_members() -> set[str]:
    """
    Get list of island members by parsing journalctl for blockchain sync events.

    Returns:
        Set of member IDs/names that are syncing with the blockchain.
    """
    logger = get_logger(__name__)
    members: set[str] = set()
    try:
        cmd = ["journalctl", "-u", "aitbc-blockchain-node", "--since", "24 hours ago", "-o", "cat", "--no-pager"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning("Failed to query journalctl: %s", result.stderr)
            return members
        sync_patterns = [
            "synced with (peer|node) [^\\s]*:([a-zA-Z0-9_-]+)",
            "connected to (peer|node) [^\\s]*:([a-zA-Z0-9_-]+)",
            "peer (added|connected):([a-zA-Z0-9_-]+)",
            "new peer:([a-zA-Z0-9_-]+)",
            "peer_id[=:]\\s*([a-zA-Z0-9_-]+)",
        ]
        for line in result.stdout.split("\n"):
            for pattern in sync_patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, tuple):
                        member_id = match[-1]
                    else:
                        member_id = match
                    if member_id and len(member_id) > 3:
                        members.add(member_id)
        logger.info("Found %s island members from journalctl", len(members))
    except subprocess.TimeoutExpired:
        logger.error("journalctl query timed out")
    except Exception as e:
        logger.error("Error parsing journalctl: %s", e)
    return members
