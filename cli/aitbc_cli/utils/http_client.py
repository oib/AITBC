"""HTTP client wrapper for AITBC CLI.

Re-exports the canonical ``AITBCHTTPClient`` and ``NetworkError`` from
``aitbc.network`` (consolidated in v0.10.4).  Keeps CLI-specific
``get_logger`` and ``KEYSTORE_DIR`` for backward compatibility with
the ~50 CLI command files that import from this module.
"""

from aitbc.aitbc_logging import get_logger  # noqa: F401 — re-export
from aitbc.exceptions import NetworkError  # noqa: F401 — re-export
from aitbc.network.client import AITBCHTTPClient  # noqa: F401 — re-export

# Constants
KEYSTORE_DIR = "/var/lib/aitbc/keystore"
