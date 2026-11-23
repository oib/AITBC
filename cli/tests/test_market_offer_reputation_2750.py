"""#2750: `market list` reputation enrichment must not probe the coordinator
for placeholder provider/node ids.

Stress-harness leftovers publish offers whose ``node_id``/``provider_address``
is a sentinel ("default", "none", "n/a") — #2435 catalog rule. Those ids can
never have a reputation profile, so ``_reputation_for_offer`` used to fire a
guaranteed-404 ``GET /reputation/profile/{id}`` per offer per listing,
spamming the coordinator (observed live: ~270 hits on
``/v1/reputation/profile/default``).
"""

from typing import Any

from aitbc_cli.commands.market import offers as offers_mod


class _RecordingClient:
    """Duck-typed AITBCHTTPClient that records GET paths and answers profiles."""

    def __init__(self, profiles=None):
        self.paths: list[str] = []
        self._profiles = profiles or {}

    def get(self, path, params=None):
        self.paths.append(path)
        agent = path.rsplit("/", 1)[-1]
        profile = self._profiles.get(agent)
        if profile is None:
            raise RuntimeError(f"404 profile not found: {agent}")
        return profile


def _client(profiles=None):
    return _RecordingClient(profiles)


def test_sentinel_node_id_makes_no_request():
    client = _client()
    offer = {"node_id": "default", "provider_address": ""}
    offers_mod._reputation_for_offer(client, "http://coord/v1", offer)
    assert client.paths == []
    assert "trust_score" not in offer


def test_sentinel_provider_and_node_make_no_request():
    for sentinel in ("default", "none", "n/a", " Default "):
        client = _client()
        offer = {"provider_address": sentinel, "node_id": sentinel}
        offers_mod._reputation_for_offer(client, "http://coord/v1", offer)
        assert client.paths == [], sentinel


def test_sentinel_provider_falls_through_to_real_node_id():
    client = _client({"miner-7": {"trust_score": 800, "reputation_level": "gold", "jobs_completed": 12}})
    offer: dict[str, Any] = {"provider_address": "default", "node_id": "miner-7"}
    offers_mod._reputation_for_offer(client, "http://coord/v1", offer)
    assert client.paths == ["http://coord/v1/reputation/profile/miner-7"]
    assert offer["trust_score"] == 800.0
    assert offer["reputation_level"] == "gold"
    assert offer["jobs_completed"] == 12


def test_real_agent_id_still_enriched():
    client = _client({"agent-x": {"trust_score": 500, "reputation_level": "silver", "jobs_completed": 3}})
    offer: dict[str, Any] = {"provider_address": "agent-x", "node_id": "ignored-node"}
    offers_mod._reputation_for_offer(client, "http://coord/v1", offer)
    assert client.paths == ["http://coord/v1/reputation/profile/agent-x"]
    assert offer["trust_score"] == 500.0


def test_wallet_provider_makes_no_request():
    client = _client()
    offer = {"provider_address": "0x" + "ab" * 20, "node_id": "default"}
    offers_mod._reputation_for_offer(client, "http://coord/v1", offer)
    assert client.paths == []
