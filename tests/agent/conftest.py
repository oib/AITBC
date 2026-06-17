"""conftest for agent tests - adds agent-coordinator src to path"""

import sys
from pathlib import Path

AGENT_COORDINATOR_SRC = Path(__file__).parent.parent.parent / "apps" / "agent-coordinator" / "src"
if str(AGENT_COORDINATOR_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_COORDINATOR_SRC))
