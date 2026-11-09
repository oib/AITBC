"""Coverage for CrossChainReputationService export/import roundtrip.

#1371 regression pins: import_reputation_data previously passed raw JSON
dicts to the dataclass constructors — datetime fields arrived as strings
(export uses ``json.dumps(default=str)``), so ``sync_reputation_cross_chain``
and ``get_reputation_analytics`` crashed with TypeError on imported data.
The import also dropped reputation_stakes/reputation_delegations entirely
and choked on the init=False ``tier`` field that ``asdict`` exports.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coordinator_api.contexts.cross_chain.services.cross_chain.reputation import (
    CrossChainReputationService,
    ReputationDelegation,
    ReputationScore,
    ReputationStake,
)


@pytest.fixture
def svc() -> CrossChainReputationService:
    return CrossChainReputationService({})


def _score(agent_id: str = "agent1", chain_id: int = 1) -> ReputationScore:
    now = datetime.now(UTC)
    return ReputationScore(
        agent_id=agent_id,
        chain_id=chain_id,
        score=8000,
        task_count=10,
        success_count=9,
        failure_count=1,
        last_updated=now,
        sync_timestamp=now,
        is_active=True,
    )


async def _seed(svc: CrossChainReputationService) -> None:
    svc.reputation_data["agent1"] = _score()
    svc.chain_reputations["agent1"] = {2: _score(chain_id=2)}
    svc.reputation_stakes["agent1"] = [
        ReputationStake(
            agent_id="agent1",
            amount=100,
            lock_period=30,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(days=30),
            is_active=True,
            reward_rate=0.05,
            multiplier=1.0,
        )
    ]
    svc.reputation_delegations["agent1"] = [
        ReputationDelegation(
            delegator="agent1",
            delegate="agent2",
            amount=50,
            start_time=datetime.now(UTC),
            is_active=True,
            fee_rate=0.01,
        )
    ]


@pytest.mark.unit
async def test_export_import_roundtrip_restores_all_sections(svc):
    await _seed(svc)
    exported = await svc.export_reputation_data()

    svc2 = CrossChainReputationService({})
    await svc2.import_reputation_data(exported)

    rep = svc2.reputation_data["agent1"]
    assert isinstance(rep.last_updated, datetime)
    assert rep.last_updated.tzinfo is not None
    assert isinstance(rep.sync_timestamp, datetime)
    assert rep.score == 8000

    chain_rep = svc2.chain_reputations["agent1"][2]
    assert isinstance(chain_rep.last_updated, datetime)

    stake = svc2.reputation_stakes["agent1"][0]
    assert isinstance(stake.start_time, datetime)
    assert isinstance(stake.end_time, datetime)

    delegation = svc2.reputation_delegations["agent1"][0]
    assert isinstance(delegation.start_time, datetime)
    assert delegation.delegate == "agent2"


@pytest.mark.unit
async def test_imported_score_survives_analytics_path(svc):
    """get_reputation_analytics does datetime arithmetic on imported rows."""
    await _seed(svc)
    exported = await svc.export_reputation_data()

    svc2 = CrossChainReputationService({})
    await svc2.import_reputation_data(exported)
    analytics = await svc2.get_reputation_analytics("agent1")
    assert analytics.agent_id == "agent1"
