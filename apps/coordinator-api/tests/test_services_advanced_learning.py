"""Coverage for AdvancedLearningService in-memory learning paths (#1289 residual).

The service keeps models/sessions/analytics in dicts — no DB, no torch.
Background session executors are exercised with tiny hyperparameters
(epochs=1) or left to be cancelled at loop teardown. Regression pin for #1370: import_learning_data must restore
learning_analytics and coerce enum fields — fixed on this branch.
"""

from __future__ import annotations

import pytest

from coordinator_api.contexts.analytics.services.ai_analytics.advanced_learning import (
    AdvancedLearningService,
    FederatedNode,
    LearningStatus,
    LearningType,
    MetaLearningTask,
    ModelType,
)


@pytest.fixture
def svc() -> AdvancedLearningService:
    return AdvancedLearningService({})


async def _make_active_model(svc, model_type=ModelType.TASK_PLANNING, learning_type=LearningType.SUPERVISED):
    model = await svc.create_model("agent1", model_type, learning_type)
    model.status = LearningStatus.ACTIVE
    model.accuracy = 0.9
    return model


# ---------------------------------------------------------------------------
# create_model / templates
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_create_model_registers_model_and_analytics(svc):
    model = await svc.create_model("agent1", ModelType.BIDDING_STRATEGY, LearningType.SUPERVISED)
    assert model.id in svc.models
    assert model.status == LearningStatus.INITIALIZING
    # template params merged with hyperparameter overrides
    assert model.parameters["architecture"] == "lstm"
    assert model.parameters["layers"] == 3
    assert model_id_analytics(svc, model.id).agent_id == "agent1"


@pytest.mark.unit
async def test_create_model_unknown_type_empty_template(svc):
    # all ModelType members have templates; a non-member can't be constructed,
    # but hyperparameters fully override template keys
    model = await svc.create_model("a", ModelType.PREDICTION, LearningType.SUPERVISED, {"layers": 99})
    assert model.parameters["layers"] == 99
    assert model.parameters["hidden_size"] == 768


def model_id_analytics(svc, model_id):
    return svc.learning_analytics[model_id]


# ---------------------------------------------------------------------------
# start_learning_session
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_start_session_unknown_model(svc):
    with pytest.raises(ValueError, match="not found"):
        await svc.start_learning_session("nope", [], [])


@pytest.mark.unit
async def test_start_session_creates_and_marks_training(svc):
    model = await svc.create_model("agent1", ModelType.CLASSIFICATION, LearningType.SUPERVISED)
    session = await svc.start_learning_session(model.id, [{"x": 1}], [{"x": 2}], {"epochs": 1, "learning_rate": 0.01})
    assert session.id in svc.learning_sessions
    assert session.hyperparameters["epochs"] == 1
    assert session.hyperparameters["learning_rate"] == 0.01
    assert model.status == LearningStatus.TRAINING


# ---------------------------------------------------------------------------
# predict / adapt / performance / optimize
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_predict_requires_active_model(svc):
    model = await svc.create_model("agent1", ModelType.TASK_PLANNING, LearningType.SUPERVISED)
    with pytest.raises(ValueError, match="not active"):
        await svc.predict_with_model(model.id, {})
    model.status = LearningStatus.ACTIVE
    pred = await svc.predict_with_model(model.id, {"q": 1})
    assert pred["prediction"] == "task_plan"
    assert "confidence" in pred


@pytest.mark.unit
async def test_adapt_model_guards(svc):
    model = await svc.create_model("agent1", ModelType.TASK_PLANNING, LearningType.SUPERVISED)
    with pytest.raises(ValueError, match="does not support adaptation"):
        await svc.adapt_model(model.id, [{"x": 1}])
    meta = await svc.create_model("agent1", ModelType.TASK_PLANNING, LearningType.META_LEARNING)
    meta.accuracy = 0.8
    res = await svc.adapt_model(meta.id, [{"x": 1}], adaptation_steps=2)
    assert res["accuracy"] > 0.8
    assert res["improvement"] == pytest.approx(res["accuracy"] - 0.8)


@pytest.mark.unit
async def test_get_model_performance_shape(svc):
    model = await _make_active_model(svc)
    perf = await svc.get_model_performance(model.id)
    assert perf["model_id"] == model.id
    assert perf["model_type"] == "task_planning"
    assert perf["status"] == "active"
    assert perf["accuracy"] == 0.9


@pytest.mark.unit
async def test_get_top_models_sorts_by_accuracy(svc):
    m1 = await _make_active_model(svc)
    m1.accuracy = 0.5
    m2 = await svc.create_model("agent2", ModelType.PREDICTION, LearningType.SUPERVISED)
    m2.accuracy = 0.99
    top = await svc.get_top_models()
    assert top[0].id == m2.id
    typed = await svc.get_top_models(model_type=ModelType.TASK_PLANNING)
    assert all(m.model_type == ModelType.TASK_PLANNING for m in typed)


@pytest.mark.unit
async def test_optimize_model_updates_metrics(svc):
    model = await _make_active_model(svc)
    model.inference_time = 0.1
    assert await svc.optimize_model(model.id) is True
    assert model.accuracy >= 0.9
    assert await svc.optimize_model("missing") is False


# ---------------------------------------------------------------------------
# meta-learning / federated setup
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_execute_meta_learning_creates_session(svc):
    tasks = [
        MetaLearningTask(
            id="t1",
            task_type="plan",
            input_features=["a"],
            output_features=["b"],
            support_set_size=2,
            query_set_size=1,
            adaptation_steps=1,
            inner_lr=0.01,
            outer_lr=0.001,
            meta_iterations=10,
        )
    ]
    session_id = await svc.execute_meta_learning("agent1", tasks, algorithm="Reptile")
    session = svc.learning_sessions[session_id]
    assert session.learning_type == LearningType.META_LEARNING
    assert session.hyperparameters["algorithm"] == "Reptile"
    # support+query data prepared: 2 support + 1 query
    assert len(session.training_data) == 2
    assert len(session.validation_data) == 1
    # a TASK_PLANNING meta model was registered
    assert any(m.learning_type == LearningType.META_LEARNING for m in svc.models.values())


@pytest.mark.unit
async def test_setup_federated_learning(svc):
    model = await svc.create_model("agent1", ModelType.COLLABORATION, LearningType.FEDERATED)
    nodes = [
        FederatedNode(
            id=f"n{i}",
            agent_id=f"a{i}",
            endpoint="http://x",
            data_size=10,
            model_version="1",
            last_sync=None,
            contribution_weight=0.5,
            bandwidth_limit=100,
            computation_limit=100,
            is_active=True,
        )
        for i in range(3)
    ]
    with pytest.raises(ValueError, match="not found"):
        await svc.setup_federated_learning("missing", nodes)
    session_id = await svc.setup_federated_learning(model.id, nodes, algorithm="FedProx")
    session = svc.learning_sessions[session_id]
    assert session.hyperparameters["algorithm"] == "FedProx"
    assert session.hyperparameters["max_participants"] == 3
    assert len(svc.federated_nodes) == 3


# ---------------------------------------------------------------------------
# analytics / export-import
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_learning_analytics_filtered_by_agent(svc):
    await svc.create_model("agent1", ModelType.TASK_PLANNING, LearningType.SUPERVISED)
    await svc.create_model("agent2", ModelType.PREDICTION, LearningType.SUPERVISED)
    a1 = await svc.get_learning_analytics("agent1")
    assert len(a1) == 1 and a1[0].agent_id == "agent1"


@pytest.mark.unit
async def test_export_import_roundtrip(svc):
    model = await _make_active_model(svc)
    exported = await svc.export_learning_data()
    svc2 = AdvancedLearningService({})
    await svc2.import_learning_data(exported)
    assert model.id in svc2.models
    assert svc2.models[model.id].accuracy == 0.9


@pytest.mark.unit
async def test_import_rejects_unknown_format(svc):
    with pytest.raises(ValueError, match="Unsupported format"):
        await svc.import_learning_data("{}", format="xml")


# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_imported_model_performance_works(svc):
    model = await _make_active_model(svc)
    exported = await svc.export_learning_data()
    svc2 = AdvancedLearningService({})
    await svc2.import_learning_data(exported)
    perf = await svc2.get_model_performance(model.id)
    assert perf["model_id"] == model.id
