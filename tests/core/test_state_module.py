"""
Tests for AITBC state management module (state.py)
This module has 0% coverage and 182 statements.
"""

import asyncio
import importlib.util
import tempfile
from datetime import datetime
from pathlib import Path

import pytest


# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


state = load_module_from_path("aitbc.state", Path("/opt/aitbc/aitbc/state/state.py"))


# ============================================================================
# State Transition Tests
# ============================================================================


class TestStateTransition:
    """Test StateTransition dataclass"""

    def test_state_transition_creation(self):
        transition = state.StateTransition(from_state="idle", to_state="running")
        assert transition.from_state == "idle"
        assert transition.to_state == "running"
        assert transition.timestamp is not None
        assert transition.data == {}

    def test_state_transition_with_data(self):
        transition = state.StateTransition(from_state="idle", to_state="running", data={"reason": "start"})
        assert transition.data == {"reason": "start"}


# ============================================================================
# State Machine Tests
# ============================================================================


class TestConfigurableStateMachine:
    """Test ConfigurableStateMachine (concrete implementation of StateMachine)"""

    def test_configurable_initialization(self):
        transitions = {"idle": ["running", "stopped"], "running": ["stopped"], "stopped": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        assert machine.current_state == "idle"
        assert len(machine.transitions) == 0

    def test_get_valid_transitions(self):
        transitions = {"idle": ["running", "stopped"], "running": ["stopped"], "stopped": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        valid = machine.get_valid_transitions("idle")
        assert "running" in valid
        assert "stopped" in valid

    def test_can_transition(self):
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        assert machine.can_transition("running") is True
        assert machine.can_transition("stopped") is False

    def test_transition_valid(self):
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        machine.transition("running")
        assert machine.current_state == "running"
        assert len(machine.transitions) == 1

    def test_transition_invalid(self):
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        with pytest.raises(state.StateTransitionError):
            machine.transition("stopped")

    def test_transition_with_data(self):
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        machine.transition("running", data={"reason": "manual"})
        assert machine.transitions[0].data == {"reason": "manual"}

    def test_add_transition(self):
        transitions = {"idle": [], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        machine.add_transition("idle", "running")
        assert "running" in machine.transitions_config["idle"]

    def test_get_state_data(self):
        transitions = {"idle": [], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        data = machine.get_state_data()
        assert data == {}

    def test_set_state_data(self):
        transitions = {"idle": [], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        machine.set_state_data({"value": "test"})
        data = machine.get_state_data()
        assert data == {"value": "test"}

    def test_get_transition_history(self):
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        machine.transition("running")
        history = machine.get_transition_history()
        assert len(history) == 1
        assert history[0].from_state == "idle"
        assert history[0].to_state == "running"

    def test_get_transition_history_with_limit(self):
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        machine.transition("running")
        machine.transition("stopped")
        history = machine.get_transition_history(limit=1)
        assert len(history) == 1
        assert history[0].to_state == "stopped"

    def test_reset(self):
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        machine.transition("running")
        machine.reset("idle")
        assert machine.current_state == "idle"
        assert len(machine.transitions) == 0


# ============================================================================
# State Persistence Tests
# ============================================================================


class TestStatePersistence:
    """Test StatePersistence"""

    def test_state_persistence_initialization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "state.json"
            persistence = state.StatePersistence(str(storage_path))
            assert persistence.storage_path == str(storage_path)

    def test_save_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "state.json"
            persistence = state.StatePersistence(str(storage_path))

            transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
            machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
            machine.transition("running")

            persistence.save_state(machine)
            assert storage_path.exists()

    def test_load_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "state.json"
            persistence = state.StatePersistence(str(storage_path))

            transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
            machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
            machine.transition("running")
            machine.set_state_data({"value": "test"})

            persistence.save_state(machine)
            loaded = persistence.load_state()
            assert loaded is not None
            assert loaded["current_state"] == "running"
            assert loaded["state_data"]["running"]["value"] == "test"

    def test_load_state_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "nonexistent.json"
            persistence = state.StatePersistence(str(storage_path))
            loaded = persistence.load_state()
            assert loaded is None

    def test_delete_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "state.json"
            persistence = state.StatePersistence(str(storage_path))

            transitions = {"idle": [], "running": []}
            machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
            persistence.save_state(machine)

            persistence.delete_state()
            assert not storage_path.exists()

    def test_delete_state_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "nonexistent.json"
            persistence = state.StatePersistence(str(storage_path))
            # Should not raise
            persistence.delete_state()


# ============================================================================
# Async State Machine Tests
# ============================================================================


class TestAsyncStateMachine:
    """Test AsyncStateMachine"""

    def test_async_state_machine_initialization(self):
        # Create a concrete implementation by implementing get_valid_transitions
        class ConcreteAsyncMachine(state.AsyncStateMachine):
            def get_valid_transitions(self, state: str) -> list[str]:
                return {"idle": ["running"], "running": ["stopped"], "stopped": []}.get(state, [])

        machine = ConcreteAsyncMachine(initial_state="idle")
        assert machine.current_state == "idle"
        assert len(machine.transition_handlers) == 0

    def test_on_transition(self):
        class ConcreteAsyncMachine(state.AsyncStateMachine):
            def get_valid_transitions(self, state: str) -> list[str]:
                return {"idle": ["running"], "running": []}.get(state, [])

        machine = ConcreteAsyncMachine(initial_state="idle")
        handler = lambda t: None  # noqa: E731
        machine.on_transition("running", handler)
        assert "running" in machine.transition_handlers

    def test_transition_async(self):
        async def _test():
            class ConcreteAsyncMachine(state.AsyncStateMachine):
                def get_valid_transitions(self, state: str) -> list[str]:
                    return {"idle": ["running"], "running": []}.get(state, [])

            machine = ConcreteAsyncMachine(initial_state="idle")
            await machine.transition_async("running")
            assert machine.current_state == "running"
            assert len(machine.transitions) == 1

        asyncio.run(_test())

    def test_transition_async_invalid(self):
        async def _test():
            class ConcreteAsyncMachine(state.AsyncStateMachine):
                def get_valid_transitions(self, state: str) -> list[str]:
                    return {"idle": ["running"], "running": []}.get(state, [])

            machine = ConcreteAsyncMachine(initial_state="idle")
            with pytest.raises(state.StateTransitionError):
                await machine.transition_async("stopped")

        asyncio.run(_test())

    def test_transition_async_with_handler(self):
        async def _test():
            call_count = 0

            def handler(transition):
                nonlocal call_count
                call_count += 1

            class ConcreteAsyncMachine(state.AsyncStateMachine):
                def get_valid_transitions(self, state: str) -> list[str]:
                    return {"idle": ["running"], "running": []}.get(state, [])

            machine = ConcreteAsyncMachine(initial_state="idle")
            machine.on_transition("running", handler)
            await machine.transition_async("running")
            assert call_count == 1

        asyncio.run(_test())

    def test_transition_async_with_async_handler(self):
        async def _test():
            call_count = 0

            async def handler(transition):
                nonlocal call_count
                call_count += 1

            class ConcreteAsyncMachine(state.AsyncStateMachine):
                def get_valid_transitions(self, state: str) -> list[str]:
                    return {"idle": ["running"], "running": []}.get(state, [])

            machine = ConcreteAsyncMachine(initial_state="idle")
            machine.on_transition("running", handler)
            await machine.transition_async("running")
            assert call_count == 1

        asyncio.run(_test())


# ============================================================================
# State Monitor Tests
# ============================================================================


class TestStateMonitor:
    """Test StateMonitor"""

    def test_state_monitor_initialization(self):
        transitions = {"idle": [], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        monitor = state.StateMonitor(machine)
        assert monitor.state_machine == machine
        assert len(monitor.observers) == 0

    def test_add_observer(self):
        transitions = {"idle": [], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        monitor = state.StateMonitor(machine)

        observer = lambda t: None  # noqa: E731
        monitor.add_observer(observer)
        assert observer in monitor.observers

    def test_remove_observer(self):
        transitions = {"idle": [], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        monitor = state.StateMonitor(machine)

        observer = lambda t: None  # noqa: E731
        monitor.add_observer(observer)
        result = monitor.remove_observer(observer)
        assert result is True
        assert observer not in monitor.observers

    def test_remove_observer_not_found(self):
        transitions = {"idle": [], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        monitor = state.StateMonitor(machine)

        observer = lambda t: None  # noqa: E731
        result = monitor.remove_observer(observer)
        assert result is False

    def test_notify_observers(self):
        transitions = {"idle": ["running"], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        monitor = state.StateMonitor(machine)

        call_count = 0

        def observer(transition):
            nonlocal call_count
            call_count += 1

        monitor.add_observer(observer)
        transition = state.StateTransition(from_state="idle", to_state="running")
        monitor.notify_observers(transition)
        assert call_count == 1

    def test_wrap_transition(self):
        transitions = {"idle": ["running"], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        monitor = state.StateMonitor(machine)

        wrapped = monitor.wrap_transition(machine.transition)
        wrapped("running")
        assert machine.current_state == "running"


# ============================================================================
# State Validator Tests
# ============================================================================


class TestStateValidator:
    """Test StateValidator"""

    def test_validate_transitions_valid(self):
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
        result = state.StateValidator.validate_transitions(transitions)
        assert result is True

    def test_validate_transitions_invalid(self):
        transitions = {
            "idle": ["running"],
            "running": ["stopped"],
            "stopped": ["nonexistent"],  # nonexistent not a source state
        }
        result = state.StateValidator.validate_transitions(transitions)
        assert result is False

    def test_check_for_deadlocks(self):
        transitions = {
            "idle": ["running"],
            "running": ["stopped"],
            "stopped": [],  # Deadlock - no outgoing transitions
        }
        deadlocks = state.StateValidator.check_for_deadlocks(transitions)
        assert "stopped" in deadlocks

    def test_check_for_deadlocks_none(self):
        transitions = {"idle": ["running"], "running": ["idle"]}
        deadlocks = state.StateValidator.check_for_deadlocks(transitions)
        assert len(deadlocks) == 0

    def test_check_for_orphans(self):
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
        orphans = state.StateValidator.check_for_orphans(transitions)
        assert "idle" in orphans  # No incoming transitions to idle

    def test_check_for_orphans_none(self):
        transitions = {"idle": ["running"], "running": ["idle"]}
        orphans = state.StateValidator.check_for_orphans(transitions)
        assert len(orphans) == 0


# ============================================================================
# State Snapshot Tests
# ============================================================================


class TestStateSnapshot:
    """Test StateSnapshot"""

    def test_state_snapshot_creation(self):
        transitions = {"idle": [], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        snapshot = state.StateSnapshot(machine)
        assert snapshot.current_state == "idle"
        assert snapshot.timestamp is not None
        assert len(snapshot.transitions) == 0

    def test_state_snapshot_with_transitions(self):
        transitions = {"idle": ["running"], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        machine.transition("running")
        snapshot = state.StateSnapshot(machine)
        assert snapshot.current_state == "running"
        assert len(snapshot.transitions) == 1

    def test_state_snapshot_with_data(self):
        transitions = {"idle": [], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        machine.set_state_data({"value": "test"})
        snapshot = state.StateSnapshot(machine)
        assert snapshot.state_data["idle"]["value"] == "test"

    def test_state_snapshot_restore(self):
        transitions = {"idle": ["running"], "running": []}
        machine1 = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        machine1.transition("running")
        machine1.set_state_data({"value": "test"})

        snapshot = state.StateSnapshot(machine1)

        machine2 = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        snapshot.restore(machine2)

        assert machine2.current_state == "running"
        assert machine2.state_data["running"]["value"] == "test"
        assert len(machine2.transitions) == 1

    def test_state_snapshot_to_dict(self):
        transitions = {"idle": [], "running": []}
        machine = state.ConfigurableStateMachine(initial_state="idle", transitions=transitions)
        snapshot = state.StateSnapshot(machine)
        data = snapshot.to_dict()
        assert data["current_state"] == "idle"
        assert "transitions" in data
        assert "timestamp" in data

    def test_state_snapshot_from_dict(self):
        data = {
            "current_state": "running",
            "state_data": {"running": {"value": "test"}},
            "transitions": [
                {"from_state": "idle", "to_state": "running", "timestamp": datetime.now().isoformat(), "data": {}}
            ],
            "timestamp": datetime.now().isoformat(),
        }
        snapshot = state.StateSnapshot.from_dict(data)
        assert snapshot.current_state == "running"
        assert snapshot.state_data["running"]["value"] == "test"
        assert len(snapshot.transitions) == 1
