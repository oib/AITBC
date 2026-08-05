"""API Gateway test configuration.

`api_gateway.main` reads REQUIRE_AUTH, API_KEY and RATE_LIMIT into module constants at
import time, so these must be set before the app module is first imported.
"""

import os

os.environ.setdefault("API_GATEWAY_REQUIRE_AUTH", "false")
# High enough that routing tests never trip the limiter; throttling has its own module
# which reloads the app with a deliberately low limit.
os.environ.setdefault("API_GATEWAY_RATE_LIMIT", "10000/minute")
