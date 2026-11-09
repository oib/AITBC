"""Service-layer tests for agent_coordination/services/performance.py
(#1289 round 8) — MetaLearningEngine, ResourceManager,
PerformanceOptimizer and the DB-backed AgentPerformanceService, against
the real in-memory session.

Documented stubs (not defects): every "algorithm" — MAML/Reptile/
Meta-SGD/prototypical, the four adaptation strategies, the four
resource-optimization algorithms and the four optimization techniques —
returns a canned parameter dict with no computation. simulate_* methods
return formulaic scores derived from list lengths. The DB rows and
service contracts around them are real and covered here.

The three defects originally pinned strict-xfail here were fixed in
#1321 (this branch): the LATENCY zero-division guard, real
base_performance injection so optimize_agent_performance produces an
actual result, and change-tracked (rebound) JSON metrics/history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.agent_coordination.domain.agent_performance import (
    AgentPerformanceProfile,
    LearningStrategy,
    MetaLearningModel,
    OptimizationTarget,
    PerformanceMetric,
    PerformanceOptimization,
    ResourceAllocation,
    ResourceType,
)
from coordinator_api.contexts.agent_coordination.services.performance import (
    AgentPerformanceService,
    MetaLearningEngine,
    PerformanceOptimizer,
    ResourceManager,
)


@pytest.fixture
def perf_svc(db_session: Session) -> AgentPerformanceService:
    return AgentPerformanceService(db_session)


class TestPerformanceProfile:
    async def test_create_profile_persists(self, perf_svc: AgentPerformanceService, db_session: Session) -> None:
        profile = await perf_svc.create_performance_profile("ag1", "trainer", {"accuracy": 0.9})
        assert profile.profile_id.startswith("perf_")
        assert profile.agent_id == "ag1"
        assert profile.performance_metrics == {"accuracy": 0.9}
        assert profile.overall_score == 0.0  # not computed at create
        row = db_session.exec(
            select(AgentPerformanceProfile).where(AgentPerformanceProfile.profile_id == profile.profile_id)
        ).one()
        assert row.agent_type == "trainer"

    async def test_update_metrics_auto_creates_profile(self, perf_svc: AgentPerformanceService, db_session: Session) -> None:
        profile = await perf_svc.update_performance_metrics("ghost", {"accuracy": 0.8})
        assert profile.agent_id == "ghost"
        assert profile.performance_metrics == {"accuracy": 0.8}
        # auto-created via create_performance_profile -> score stays 0.0
        assert profile.overall_score == 0.0

    async def test_update_metrics_appends_history_and_scores(
        self, perf_svc: AgentPerformanceService, db_session: Session
    ) -> None:
        await perf_svc.update_performance_metrics("ag1", {"accuracy": 0.5})
        await perf_svc.update_performance_metrics("ag1", {"accuracy": 0.7})
        profile = await perf_svc.update_performance_metrics("ag1", {"accuracy": 0.9}, task_context={"task": "t1"})
        assert profile.performance_metrics["accuracy"] == 0.9
        assert len(profile.performance_history) == 2
        assert profile.performance_history[-1]["context"] == {"task": "t1"}
        assert profile.overall_score == pytest.approx(0.9)
        # trend compares last two history entries: (0.9-0.7)/0.7
        assert profile.improvement_trends["accuracy"] == pytest.approx(0.2 / 0.7)
        assert profile.last_assessed is not None
        # the JSON mutations must actually persist across expire/refresh
        db_session.expire_all()
        row = db_session.exec(select(AgentPerformanceProfile).where(AgentPerformanceProfile.agent_id == "ag1")).one()
        assert row.performance_metrics["accuracy"] == 0.9
        assert len(row.performance_history) == 2
        assert row.overall_score == pytest.approx(profile.overall_score)

    async def test_comprehensive_profile_found_and_missing(self, perf_svc: AgentPerformanceService) -> None:
        await perf_svc.create_performance_profile("ag1", initial_metrics={"accuracy": 0.9})
        data = await perf_svc.get_comprehensive_profile("ag1")
        assert data["agent_id"] == "ag1"
        assert data["performance_metrics"] == {"accuracy": 0.9}
        assert data["last_assessed"] is None  # never assessed
        assert await perf_svc.get_comprehensive_profile("nobody") == {"error": "Profile not found"}

    async def test_score_and_trend_math(self, perf_svc: AgentPerformanceService) -> None:
        # accuracy alone: weight .3 / total .3 -> 1.0
        assert perf_svc.calculate_overall_score({"accuracy": 1.0}) == pytest.approx(1.0)
        assert perf_svc.calculate_overall_score({}) == 0.0
        # unknown metric gets default weight 0.1
        s = perf_svc.calculate_overall_score({"custom": 2.0})
        assert s == pytest.approx(2.0)
        assert perf_svc.calculate_improvement_trends([]) == {}
        assert perf_svc.calculate_improvement_trends([{"metrics": {"a": 1.0}}]) == {}
        trends = perf_svc.calculate_improvement_trends([{"metrics": {"a": 2.0, "b": 0.0}}, {"metrics": {"a": 3.0, "b": 5.0}}])
        assert trends["a"] == pytest.approx(0.5)
        assert "b" not in trends  # previous value 0 -> skipped


class TestCapabilities:
    async def test_capability_lifecycle_and_proficiency(self, perf_svc: AgentPerformanceService, db_session: Session) -> None:
        cap = await perf_svc.create_capability(
            session=db_session,
            agent_id="ag1",
            capability_name="summarize",
            capability_type="nlp",
            domain_area="text",
            skill_level=8.0,
            specialization_areas=["news"],
        )
        assert cap.capability_id.startswith("cap_")
        assert cap.proficiency_score == pytest.approx(0.8)
        caps = await perf_svc.list_capabilities("ag1")
        assert [c.capability_name for c in caps] == ["summarize"]
        # skill_level=10 boundary -> proficiency clamps at 1.0
        # (skill_level itself is le=10.0 on the model, so >10 never reaches here)
        cap2 = await perf_svc.create_capability(
            session=db_session,
            agent_id="ag1",
            capability_name="over",
            capability_type="x",
            domain_area="y",
            skill_level=10.0,
            specialization_areas=[],
        )
        assert cap2.proficiency_score == 1.0
        assert await perf_svc.list_capabilities("other") == []

    async def test_analytics_aggregation(self, perf_svc: AgentPerformanceService, db_session: Session) -> None:
        await perf_svc.create_performance_profile("ag1", initial_metrics={"accuracy": 0.9})
        for name, skill in (("low", 2.0), ("high", 9.0), ("mid", 5.0)):
            await perf_svc.create_capability(
                session=db_session,
                agent_id="ag1",
                capability_name=name,
                capability_type="t",
                domain_area="d",
                skill_level=skill,
                specialization_areas=[],
            )
        analytics = await perf_svc.get_performance_analytics("ag1", period_days=7)
        assert analytics["capability_count"] == 3
        assert analytics["overall_score"] == 0.0
        assert analytics["period_days"] == 7
        # top_capabilities sorted by skill_level desc, capped at 5
        assert analytics["top_capabilities"][0]["name"] == "high"
        assert analytics["top_capabilities"][0]["proficiency"] == pytest.approx(0.9)
        # unknown agent -> zeroed defaults
        empty = await perf_svc.get_performance_analytics("ghost")
        assert empty["overall_score"] == 0.0
        assert empty["capability_count"] == 0
        assert empty["top_capabilities"] == []


class TestResourceManager:
    @pytest.fixture
    def rm(self) -> ResourceManager:
        return ResourceManager()

    def test_initial_allocation_task_types(self, rm: ResourceManager) -> None:
        general = rm.calculate_initial_allocation({})
        assert general[ResourceType.CPU] == 2.0
        inference = rm.calculate_initial_allocation({"task_type": "inference", "model_size": "large"})
        assert inference[ResourceType.GPU] == 1.0
        assert inference[ResourceType.NETWORK] == 200.0
        small = rm.calculate_initial_allocation({"task_type": "inference", "model_size": "small"})
        assert small[ResourceType.GPU] == 0.0
        training = rm.calculate_initial_allocation({"task_type": "training"})
        assert training[ResourceType.GPU] == 2.0
        assert training[ResourceType.STORAGE] == 200.0
        text = rm.calculate_initial_allocation({"task_type": "text_generation"})
        assert text[ResourceType.MEMORY] == 6.0
        # workload_factor scales every resource
        scaled = rm.calculate_initial_allocation({"workload_factor": 2.0})
        assert scaled[ResourceType.CPU] == 4.0
        assert scaled[ResourceType.NETWORK] == 200.0

    async def test_optimize_dispatch_and_targets(self, rm: ResourceManager) -> None:
        base = rm.calculate_initial_allocation({"task_type": "inference", "model_size": "large"})
        speed = await rm.optimize_allocation(base, {"task_type": "inference"}, OptimizationTarget.SPEED)
        assert speed[ResourceType.CPU] == min(16.0, 4.0 * 1.5)
        assert speed[ResourceType.GPU] >= 1.0
        cost = await rm.optimize_allocation(base, {}, OptimizationTarget.COST)
        assert cost[ResourceType.GPU] == 0.0
        assert cost[ResourceType.CPU] == 2.0  # 4.0 * 0.5
        acc = await rm.optimize_allocation(base, {"task_type": "training"}, OptimizationTarget.ACCURACY)
        assert acc[ResourceType.GPU_MEMORY_GB] == acc[ResourceType.GPU] * 8.0
        # unknown target (SCALABILITY/RELIABILITY) -> initial allocation unchanged
        same = await rm.optimize_allocation(base, {}, OptimizationTarget.SCALABILITY)
        assert same == base

    async def test_allocate_resources_persists(self, rm: ResourceManager, db_session: Session) -> None:
        alloc = await rm.allocate_resources(db_session, "ag1", {"task_type": "training"}, OptimizationTarget.EFFICIENCY)
        assert alloc.allocation_id.startswith("alloc_")
        assert alloc.status == "allocated"
        row = db_session.exec(select(ResourceAllocation).where(ResourceAllocation.allocation_id == alloc.allocation_id)).one()
        assert row.agent_id == "ag1"
        assert row.gpu_count > 0

    def test_stub_algorithms_return_canned_params(self, rm: ResourceManager) -> None:
        """Documented stubs: all four 'algorithms' return fixed dicts."""
        alloc = {ResourceType.CPU: 2.0}
        for name in ("genetic_optimization", "simulated_annealing", "gradient_optimization", "bayesian_optimization"):
            result = getattr(rm, name)(alloc)
            assert "algorithm" in result


class TestPerformanceOptimizer:
    @pytest.fixture
    def opt(self) -> PerformanceOptimizer:
        return PerformanceOptimizer()

    def test_analyze_accuracy_gap_and_bottlenecks(self, opt: PerformanceOptimizer) -> None:
        analysis = opt.analyze_current_performance(
            {"accuracy": 0.5, "cpu_utilization": 0.95, "gpu_utilization": 0.99}, PerformanceMetric.ACCURACY
        )
        assert analysis["current_value"] == 0.5
        assert analysis["target_value"] == 0.95
        assert analysis["gap"] == pytest.approx(0.45)
        assert analysis["improvement_potential"] == pytest.approx(0.45 / 0.95)
        assert analysis["bottlenecks"] == ["cpu", "gpu"]

    def test_analyze_latency_above_target_negative_potential(self, opt: PerformanceOptimizer) -> None:
        """Documents: beating the latency target yields a NEGATIVE
        improvement_potential (only upper-clamped by min(1.0, x))."""
        analysis = opt.analyze_current_performance({"latency": 50.0}, PerformanceMetric.LATENCY)
        assert analysis["gap"] == pytest.approx(-50.0)
        assert analysis["improvement_potential"] < 0

    def test_analyze_latency_zero_metric(self, opt: PerformanceOptimizer) -> None:
        """#1321: a missing/zero latency metric no longer divides by zero —
        improvement_potential is 0.0."""
        analysis = opt.analyze_current_performance({}, PerformanceMetric.LATENCY)
        assert analysis["improvement_potential"] == 0.0

    async def test_evaluate_candidates_picks_best_score(self, opt: PerformanceOptimizer) -> None:
        candidates = [
            {"expected_improvement": 0.1, "resource_cost": 0.5, "complexity": 0.9},
            {"expected_improvement": 0.9, "resource_cost": 0.1, "complexity": 0.1},
        ]
        best = await opt.evaluate_candidates(candidates, PerformanceMetric.ACCURACY)
        assert best["expected_improvement"] == 0.9
        assert await opt.evaluate_candidates([], PerformanceMetric.ACCURACY) == {}
        # all-negative scores -> no candidate selected -> {}
        neg = [{"expected_improvement": 0.0, "resource_cost": 1.0, "complexity": 1.0}]
        assert await opt.evaluate_candidates(neg, PerformanceMetric.ACCURACY) == {}

    async def test_apply_optimization_boosts_target_metric(self, opt: PerformanceOptimizer) -> None:
        candidate = {
            "base_performance": {"accuracy": 0.8, "latency": 100.0},
            "expected_improvement": 0.2,
            "target_metric": "accuracy",
        }
        result = await opt.apply_optimization(candidate)
        assert result["accuracy"] == pytest.approx(0.96)
        assert result["latency"] == pytest.approx(102.0)  # 10% of improvement factor
        assert await opt.apply_optimization({}) == {}

    def test_calculate_improvements_and_cost(self, opt: PerformanceOptimizer) -> None:
        baseline = {"a": 1.0, "b": 1.0}
        optimized = {"a": 2.0, "b": 1.0}
        imp = opt.calculate_improvements(baseline, optimized)
        assert imp["overall"] == pytest.approx(0.5)
        # resource keys absent -> defaults cpu=1, mem=2 -> equal -> 0.0
        assert imp["resource"] == pytest.approx(0.0)
        # cost: cpu 1*10 + mem 2*2 + gpu 0 + storage 50*0.1 = 19 both sides -> 0.0
        assert imp["cost"] == pytest.approx(0.0)
        assert opt.calculate_improvements({}, {})["overall"] == 0.0
        # cost formula spot-check
        assert opt.calculate_cost({"cpu_cores": 2, "memory_gb": 4, "gpu_count": 1, "storage_gb": 100}) == pytest.approx(
            20 + 8 + 100 + 10
        )

    async def test_stub_techniques_return_canned_candidates(self, opt: PerformanceOptimizer) -> None:
        analysis = {"current_value": 0.5}
        for name in ("tune_hyperparameters", "optimize_architecture", "select_algorithm", "optimize_data_pipeline"):
            candidate = await getattr(opt, name)(PerformanceMetric.ACCURACY, analysis)
            assert candidate["technique"]
            assert 0.0 <= candidate["expected_improvement"] <= 1.0

    async def test_optimize_agent_performance_produces_result(self, opt: PerformanceOptimizer, db_session: Session) -> None:
        result = await opt.optimize_agent_performance(db_session, "ag1", PerformanceMetric.ACCURACY, {"accuracy": 0.8})
        assert result.status == "completed"
        assert result.optimized_performance != {}
        assert result.performance_improvement > 0
        row = db_session.exec(
            select(PerformanceOptimization).where(PerformanceOptimization.optimization_id == result.optimization_id)
        ).one()
        assert row.status == "completed"


class TestMetaLearningEngine:
    @pytest.fixture
    def mle(self) -> MetaLearningEngine:
        return MetaLearningEngine()

    def _model_row(self, session: Session, **overrides: Any) -> MetaLearningModel:
        """Direct row construction — create_meta_learning_model fire-and-
        forgets train_meta_model on the same session, which races tests."""
        fields: dict[str, Any] = {
            "model_id": "meta_t1",
            "model_name": "t",
            "base_algorithms": ["cnn"],
            "meta_strategy": LearningStrategy.META_LEARNING,
            "adaptation_targets": ["text_generation", "reasoning"],
            "meta_features": ["a", "b"],
            "task_distributions": {"text_generation": 0.5, "reasoning": 0.5},
            "status": "ready",
            "meta_accuracy": 0.85,
            "adaptation_speed": 0.9,
            "trained_at": datetime.now(UTC),
        }
        fields.update(overrides)
        model = MetaLearningModel(**fields)
        session.add(model)
        session.commit()
        session.refresh(model)
        return model

    async def test_create_model_and_features(self, mle: MetaLearningEngine, db_session: Session) -> None:
        model = await mle.create_meta_learning_model(
            db_session, "m1", ["cnn", "lstm"], LearningStrategy.TRANSFER_LEARNING, ["text_generation"]
        )
        assert model.model_id.startswith("meta_")
        assert "text_length" in model.meta_features
        # single target: base 1.0 + variation (0 - 0.5) * 0.1 = 0.95
        assert model.task_distributions["text_generation"] == pytest.approx(0.95)
        # status is "training" until the background task lands; both legal
        assert model.status in {"training", "ready"}

    async def test_train_meta_model_math(self, mle: MetaLearningEngine, db_session: Session) -> None:
        model = self._model_row(db_session, model_id="meta_tr1", status="training")
        await mle.train_meta_model(db_session, model.model_id)
        db_session.refresh(model)
        assert model.status == "ready"
        # simulate is formulaic: accuracy = min(1, .75 + 2 targets * .05)
        assert model.meta_accuracy == pytest.approx(0.85)
        assert model.trained_at is not None
        sim = await mle.simulate_meta_training(model)
        assert sim["accuracy"] == pytest.approx(0.85)
        with pytest.raises(ValueError, match="not found"):
            await mle.train_meta_model(db_session, "meta_missing")

    async def test_adapt_to_new_task(self, mle: MetaLearningEngine, db_session: Session) -> None:
        model = self._model_row(db_session)
        result = await mle.adapt_to_new_task(db_session, model.model_id, {"task": "new"}, adaptation_steps=10)
        assert result["steps_used"] == 10
        assert result["convergence_achieved"] == (result["success"] > 0.7)
        db_session.expire_all()
        session_model = db_session.exec(select(MetaLearningModel).where(MetaLearningModel.model_id == model.model_id)).one()
        assert session_model.deployment_count == 1
        # success_rate = (0 * 0 + success) / 1 = success
        assert session_model.success_rate == pytest.approx(result["success"])
        # a model still in "training" status cannot adapt
        m2 = self._model_row(db_session, model_id="meta_x", status="training")
        with pytest.raises(ValueError, match="not ready"):
            await mle.adapt_to_new_task(db_session, m2.model_id, {})

    def test_feature_and_distribution_generation(self, mle: MetaLearningEngine) -> None:
        feats = mle.generate_meta_features(["image_generation", "unknown_target"])
        assert "resolution" in feats and "complexity" in feats
        assert len(feats) == len(set(feats))
        dists = mle.setup_task_distributions(["a", "b"])
        assert set(dists) == {"a", "b"}
        assert all(v >= 0.1 for v in dists.values())
        assert mle.setup_task_distributions([]) == {}

    async def test_stub_algorithms_and_strategies(self, mle: MetaLearningEngine, db_session: Session) -> None:
        """Documented stubs: algorithms/strategies return fixed dicts."""
        model = self._model_row(db_session)
        for name in ("maml_algorithm", "reptile_algorithm", "meta_sgd_algorithm", "prototypical_algorithm"):
            assert getattr(mle, name)({})["algorithm"]
        for name in ("fast_adaptation", "gradual_adaptation", "transfer_adaptation", "multi_task_adaptation"):
            assert getattr(mle, name)(model, {})["strategy"]
        # adapt strategies are sync stubs but simulate_adaptation is real math
        sim = await mle.simulate_adaptation(model, {}, steps=10)
        assert 0 < sim["success"] <= 1.0
        assert sim["adaptation_time"] == pytest.approx(1.0)
