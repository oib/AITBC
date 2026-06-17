"""conftest for unit tests - adds coordinator-api src to path"""

import sys
from pathlib import Path

COORDINATOR_API_SRC = Path(__file__).parent.parent.parent / "apps" / "coordinator-api" / "src"
if str(COORDINATOR_API_SRC) not in sys.path:
    sys.path.insert(0, str(COORDINATOR_API_SRC))
