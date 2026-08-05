"""Island members configuration.

Previously this parsed ``journalctl`` log lines with regexes, which let any line
matching a pattern claim island membership. It now reads the operator-configured
list of trusted island members from the application settings.
"""

from aitbc.aitbc_logging import get_logger

from ..config import settings

logger = get_logger(__name__)


def get_island_members() -> set[str]:
    """Return the configured set of trusted island member IDs.

    Returns:
        Set of trusted member IDs/names.
    """
    members = {m.strip() for m in settings.island_members if m.strip()}
    logger.info("Loaded %s trusted island members from configuration", len(members))
    return members
