"""Island members detection via journalctl parsing."""

import logging
import re
import subprocess


def get_island_members() -> set[str]:
    """
    Get list of island members by parsing journalctl for blockchain sync events.
    
    Returns:
        Set of member IDs/names that are syncing with the blockchain.
    """
    logger = logging.getLogger(__name__)
    members: set[str] = set()

    try:
        # Query journalctl for blockchain sync events
        # Look for sync events from blockchain-node or similar services
        cmd = [
            "journalctl",
            "-u", "aitbc-blockchain-node",
            "--since", "24 hours ago",
            "-o", "cat",
            "--no-pager"
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.warning(f"Failed to query journalctl: {result.stderr}")
            return members

        # Parse logs for sync events
        # Look for patterns like "synced with peer", "connected to", "peer added"
        sync_patterns = [
            r"synced with (peer|node) [^\s]*:([a-zA-Z0-9_-]+)",
            r"connected to (peer|node) [^\s]*:([a-zA-Z0-9_-]+)",
            r"peer (added|connected):([a-zA-Z0-9_-]+)",
            r"new peer:([a-zA-Z0-9_-]+)",
            r"peer_id[=:]\s*([a-zA-Z0-9_-]+)"
        ]

        for line in result.stdout.split('\n'):
            for pattern in sync_patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, tuple):
                        member_id = match[-1]  # Get the last capture group
                    else:
                        member_id = match

                    if member_id and len(member_id) > 3:  # Filter out short matches
                        members.add(member_id)

        logger.info(f"Found {len(members)} island members from journalctl")

    except subprocess.TimeoutExpired:
        logger.error("journalctl query timed out")
    except Exception as e:
        logger.error(f"Error parsing journalctl: {e}")

    return members
