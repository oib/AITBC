"""conftest for agent tests - adds agent-coordinator src to path"""

import os
import sys
from pathlib import Path

# SECRET_KEY is required by agent-coordinator Settings (v0.10.3 A4)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-agent-tests-at-least-32-chars")

AGENT_COORDINATOR_SRC = Path(__file__).parent.parent.parent / "apps" / "agent-coordinator" / "src"
if str(AGENT_COORDINATOR_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_COORDINATOR_SRC))
