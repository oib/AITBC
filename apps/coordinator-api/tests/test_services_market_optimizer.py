"""Coverage for MarketStrategyOptimizer deploy/evaluate paths (#1289 residual).

Uses the shared db_session fixture (in-memory sqlite). The RL training
engine itself is exercised only through optimize_agent_strategy with a
single episode; deploy/evaluate/simulate paths are pinned directly on
ReinforcementLearningConfig rows. One strict xfail pins #1368:
deployed_at is stored via datetime.now(UTC) but sqlite returns it naive
on reload — evaluate_strategy_performance then raises TypeError on the
aware-minus-naive subtraction (same class as #1353).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.advanced_rl.domain import ReinforcementLearningConfig
from coordinator_api.contexts.advanced_rl.services.advanced_rl.market_optimizer import (
    MarketStrategyOptimizer,
)


@pytest.fixture
def optimizer() -> MarketStrategyOptimizer:
    return MarketStrategyOptimizer()


def _make_config(session: Session, status: str = "ready", **over) -> ReinforcementLearningConfig:
    kwargs = {
        "config_id": "rl_test1",
        "agent_id": "agent1",
        "environment_type": "market_trading",
        "algorithm": "ppo",
        "status": status,
        "reward_history": [0.5, 0.6, 0.55],
        "success_rate_history": [0.7, 0.8, 0.75],
    }
    kwargs.update(over)
    cfg = ReinforcementLearningConfig(**kwargs)
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg


# ---------------------------------------------------------------------------
# deploy_strategy
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_deploy_not_found(optimizer, db_session):
    with pytest.raises(ValueError, match="not found"):
        await optimizer.deploy_strategy(db_session, "rl_missing", {})


@pytest.mark.unit
async def test_deploy_requires_ready_status(optimizer, db_session):
    _make_config(db_session, status="training")
    with pytest.raises(ValueError, match="not ready"):
        await optimizer.deploy_strategy(db_session, "rl_test1", {})


@pytest.mark.xfail(
    strict=True,
    reason="#1369: deploy_strategy increments rl_config.deployment_count — field does not exist on ReinforcementLearningConfig -> AttributeError on every deploy attempt; deployment is dead code",
)
@pytest.mark.unit
async def test_deploy_success(optimizer, db_session):
    _make_config(db_session, status="ready")
    res = await optimizer.deploy_strategy(db_session, "rl_test1", {"market_conditions": "bull"})
    assert res["success"] is True
    assert res["config_id"] == "rl_test1"
    assert "expected_return" in res["deployment_performance"]
    cfg = db_session.exec(select(ReinforcementLearningConfig).where(ReinforcementLearningConfig.config_id == "rl_test1")).one()
    assert cfg.status == "deployed"
    assert cfg.deployment_count == 1
    assert cfg.deployed_at is not None


# ---------------------------------------------------------------------------
# evaluate_strategy_performance
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_evaluate_not_found(optimizer, db_session):
    with pytest.raises(ValueError, match="not found"):
        await optimizer.evaluate_strategy_performance(db_session, "rl_missing")


@pytest.mark.unit
async def test_evaluate_requires_deployed(optimizer, db_session):
    _make_config(db_session, status="ready")
    with pytest.raises(ValueError, match="not deployed"):
        await optimizer.evaluate_strategy_performance(db_session, "rl_test1")


@pytest.mark.xfail(
    strict=True,
    reason="#1368: deployed_at reloads naive from sqlite — (now(UTC) - deployed_at) raises TypeError even without expire_all, since evaluate re-queries the row",
)
@pytest.mark.unit
async def test_evaluate_deployed_metrics(optimizer, db_session):
    _make_config(db_session, status="deployed", deployed_at=datetime.now(UTC))
    res = await optimizer.evaluate_strategy_performance(db_session, "rl_test1", evaluation_period=14)
    assert res["config_id"] == "rl_test1"
    assert res["evaluation_period_days"] == 14
    assert 0.7 <= res["success_rate"] <= 1.0
    assert res["deployment_age_days"] == 0


# ---------------------------------------------------------------------------
# simulate_deployment_performance
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_simulate_performance_market_multipliers(optimizer, db_session):
    cfg = _make_config(db_session, reward_history=[0.5] * 10)
    normal = optimizer.simulate_deployment_performance(cfg, {})
    bull = optimizer.simulate_deployment_performance(cfg, {"market_conditions": "bull"})
    bear = optimizer.simulate_deployment_performance(cfg, {"market_conditions": "bear"})
    assert bull["expected_return"] == pytest.approx(normal["expected_return"] * 1.2)
    assert bear["expected_return"] == pytest.approx(normal["expected_return"] * 0.8)
    for scores in (normal, bull, bear):
        assert 0.0 <= scores["risk_score"] <= 0.3
        assert 0.3 <= scores["stability_score"] <= 1.0
        assert 0.5 <= scores["adaptability_score"] <= 1.0


@pytest.mark.unit
def test_simulate_performance_empty_history_defaults(optimizer, db_session):
    cfg = _make_config(db_session, reward_history=[])
    res = optimizer.simulate_deployment_performance(cfg, {})
    assert res["expected_return"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# optimize_agent_strategy (single-episode smoke)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_optimize_agent_strategy_single_episode(optimizer, db_session):
    res = await optimizer.optimize_agent_strategy(db_session, "agent1", "pricing_strategy", training_episodes=1)
    assert "success" in res
    # a config row was created regardless of training outcome
    rows = db_session.exec(select(ReinforcementLearningConfig)).all()
    assert len(rows) == 1
    assert rows[0].agent_id == "agent1"
    # unknown strategy_type falls back to market_trading env
    res2 = await optimizer.optimize_agent_strategy(db_session, "agent2", "nonexistent_strategy", training_episodes=1)
    assert "success" in res2


# ---------------------------------------------------------------------------
# strict xfail — naive deployed_at crashes evaluate after reload (#1368)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="#1368: deployed_at stored aware but sqlite reloads it naive — (now(UTC) - deployed_at) raises TypeError in evaluate_strategy_performance",
)
@pytest.mark.unit
async def test_evaluate_after_reload_no_tz_crash(optimizer, db_session):
    _make_config(db_session, status="ready")
    await optimizer.deploy_strategy(db_session, "rl_test1", {})
    db_session.expire_all()  # simulate post-restart reload from sqlite
    res = await optimizer.evaluate_strategy_performance(db_session, "rl_test1")
    assert res["config_id"] == "rl_test1"
