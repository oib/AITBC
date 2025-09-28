from __future__ import annotations

from typing import Final


class RedisKeys:
    namespace: Final[str] = "poolhub"

    @classmethod
    def miner_hash(cls, miner_id: str) -> str:
        return f"{cls.namespace}:miner:{miner_id}"

    @classmethod
    def miner_rankings(cls, region: str | None = None) -> str:
        suffix = region or "global"
        return f"{cls.namespace}:rankings:{suffix}"

    @classmethod
    def miner_session(cls, session_token: str) -> str:
        return f"{cls.namespace}:session:{session_token}"

    @classmethod
    def heartbeat_stream(cls) -> str:
        return f"{cls.namespace}:heartbeat-stream"

    @classmethod
    def match_requests(cls) -> str:
        return f"{cls.namespace}:match-requests"

    @classmethod
    def match_results(cls, job_id: str) -> str:
        return f"{cls.namespace}:match-results:{job_id}"

    @classmethod
    def feedback_channel(cls) -> str:
        return f"{cls.namespace}:events:feedback"

    @classmethod
    def match_results_channel(cls, job_id: str) -> str:
        return f"{cls.namespace}:events:match-results:{job_id}"
