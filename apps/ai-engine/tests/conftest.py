"""AI engine test configuration.

ai_service reads AI_ENGINE_REQUIRE_AUTH, AI_ENGINE_API_KEY and AI_ENGINE_ALLOW_SIMULATION
into module constants at import time, so the test values must be set before the module is
first imported.
"""

import os

os.environ.setdefault("AI_ENGINE_REQUIRE_AUTH", "false")
os.environ.setdefault("AI_ENGINE_ALLOW_SIMULATION", "true")
