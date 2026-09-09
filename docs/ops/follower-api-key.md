# Follower API key

The `FOLLOWER_API_KEY` is safe to publish. It opens only the agent coin-request
registration and execution endpoints, and neither of those can pay outside the
hub's coin-request policy.

The `COORDINATOR_API_KEY` must not be published. It also authenticates the
agent WebSocket and other coordinator surfaces.
