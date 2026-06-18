"""Tests for AITBC state module.

Tests cover:
- Exceptions: StateTransitionError, StatePersistenceError
- StateTransition dataclass
- StateMachine base class
- ConfigurableStateMachine
- StatePersistence
- AsyncStateMachine
- StateMonitor
- StateValidator
- StateSnapshot
"""

import json
import os
import tempfile
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from aitbc.state import (
    AsyncStateMachine,
    ConfigurableStateMachine,
    StateMachine,
    StateMonitor,
    StatePersistence,
    StatePersistenceError,
    StateSnapshot,
    StateTransition,
    StateTransitionError,
    StateValidator,
)


class TestStateExceptions:
    """Test state exceptions."""

    def test_state_transition_error(self):
        """Test StateTransitionError."""
        with pytest.raises(StateTransitionError):
            raise StateTransitionError("Invalid transition")

    def test_state_persistence_error(self):
        """Test StatePersistenceError."""
        with pytest.raises(StatePersistenceError):
            raise StatePersistenceError("Persistence failed")


class TestStateTransition:
    """Test StateTransition dataclass."""

    def test_state_transition_creation(self):
        """Test StateTransition creation."""
        transition = StateTransition(
            from_state="idle",
            to_state="running",
            timestamp=datetime.now(UTC),
            data={"user": "test"},
        )
        assert transition.from_state == "idle"
        assert transition.to_state == "running"
        assert transition.data == {"user": "test"}

    def test_state_transition_defaults(self):
        """Test StateTransition with defaults."""
        transition = StateTransition(from_state="a", to_state="b")
        assert transition.from_state == "a"
        assert transition.to_state == "b"
        assert transition.data == {}
        assert transition.timestamp is not None


class TestStateMachine:
    """Test StateMachine base class."""

    class ConcreteStateMachine(StateMachine):
        def __init__(self, initial_state: str):
            super().__init__(initial_state)
            self._transitions = {
                "idle": ["running", "stopped"],
                "running": ["idle", "paused"],
                "paused": ["running", "stopped"],
                "stopped": ["idle"],
            }

        def get_valid_transitions(self, state: str) -> list[str]:
            return self._transitions.get(state, [])

    def test_init(self):
        """Test StateMachine initialization."""
        sm = self.ConcreteStateMachine("idle")
        assert sm.current_state == "idle"
        assert sm.transitions == []
        assert "idle" in sm.state_data

    def test_can_transition_true(self):
        """Test can_transition returns True for valid."""
        sm = self.ConcreteStateMachine("idle")
        assert sm.can_transition("running") is True

    def test_can_transition_false(self):
        """Test can_transition returns False for invalid."""
        sm = self.ConcreteStateMachine("idle")
        # "paused" is not a valid transition from "idle"
        assert sm.can_transition("paused") is False

    def test_transition_valid(self):
        """Test valid transition."""
        sm = self.ConcreteStateMachine("idle")
        sm.transition("running")
        assert sm.current_state == "running"
        assert len(sm.transitions) == 1
        assert sm.transitions[0].from_state == "idle"
        assert sm.transitions[0].to_state == "running"
        assert "running" in sm.state_data

    def test_transition_with_data(self):
        """Test transition with data."""
        sm = self.ConcreteStateMachine("idle")
        sm.transition("running", {"speed": 100})
        assert sm.transitions[0].data == {"speed": 100}

    def test_transition_invalid_raises(self):
        """Test invalid transition raises StateTransitionError."""
        sm = self.ConcreteStateMachine("idle")
        # "paused" is not a valid transition from "idle"
        with pytest.raises(StateTransitionError):
            sm.transition("paused")

    def test_get_state_data(self):
        """Test get_state_data."""
        sm = self.ConcreteStateMachine("idle")
        sm.set_state_data({"key": "value"})
        data = sm.get_state_data()
        assert data == {"key": "value"}

    def test_get_state_data_specific(self):
        """Test get_state_data for specific state."""
        sm = self.ConcreteStateMachine("idle")
        sm.set_state_data({"idle_data": True})
        sm.transition("running")
        idle_data = sm.get_state_data("idle")
        running_data = sm.get_state_data("running")
        assert idle_data == {"idle_data": True}
        assert running_data == {}

    def test_set_state_data(self):
        """Test set_state_data."""
        sm = self.ConcreteStateMachine("idle")
        sm.set_state_data({"count": 5})
        sm.set_state_data({"name": "test"})
        assert sm.get_state_data() == {"count": 5, "name": "test"}

    def test_get_transition_history(self):
        """Test get_transition_history."""
        sm = self.ConcreteStateMachine("idle")
        sm.transition("running")
        sm.transition("paused")
        history = sm.get_transition_history()
        assert len(history) == 2
        assert history[0].from_state == "idle"
        assert history[1].from_state == "running"

    def test_get_transition_history_limit(self):
        """Test get_transition_history with limit."""
        sm = self.ConcreteStateMachine("idle")
        sm.transition("running")
        sm.transition("paused")
        history = sm.get_transition_history(limit=1)
        assert len(history) == 1
        assert history[0].from_state == "running"

    def test_reset(self):
        """Test reset."""
        sm = self.ConcreteStateMachine("idle")
        sm.transition("running")
        sm.transition("paused")
        sm.set_state_data({"key": "value"})
        sm.reset("idle")
        assert sm.current_state == "idle"
        assert sm.transitions == []
        assert sm.state_data == {"idle": {}}


class TestConfigurableStateMachine:
    """Test ConfigurableStateMachine."""

    def test_init(self):
        """Test ConfigurableStateMachine initialization."""
        transitions = {"idle": ["running"], "running": ["stopped"]}
        sm = ConfigurableStateMachine("idle", transitions)
        assert sm.current_state == "idle"
        assert sm.transitions_config == transitions

    def test_get_valid_transitions(self):
        """Test get_valid_transitions from config."""
        transitions = {"idle": ["running"], "running": ["stopped"]}
        sm = ConfigurableStateMachine("idle", transitions)
        assert sm.get_valid_transitions("idle") == ["running"]
        assert sm.get_valid_transitions("running") == ["stopped"]
        assert sm.get_valid_transitions("unknown") == []

    def test_add_transition(self):
        """Test add_transition."""
        transitions = {"idle": ["running"]}
        sm = ConfigurableStateMachine("idle", transitions)
        sm.add_transition("idle", "paused")
        assert "paused" in sm.transitions_config["idle"]

    def test_add_transition_new_from_state(self):
        """Test add_transition with new from_state."""
        transitions = {"idle": ["running"]}
        sm = ConfigurableStateMachine("idle", transitions)
        sm.add_transition("running", "completed")
        assert "running" in sm.transitions_config
        assert "completed" in sm.transitions_config["running"]


class TestStatePersistence:
    """Test StatePersistence."""

    def test_init_creates_dir(self):
        """Test init creates storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state", "test.json")
            StatePersistence(path)
            assert os.path.exists(os.path.dirname(path))

    def test_save_state(self):
        """Test save_state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.json")
            persistence = StatePersistence(path)

            class TestMachine(StateMachine):
                def get_valid_transitions(self, state):
                    # Return the target state as valid from any state
                    return ["running", "idle", "paused", "stopped"]

            sm = TestMachine("idle")
            sm.transition("running", {"task": "task1"})

            persistence.save_state(sm)

            with open(path) as f:
                data = json.load(f)

            assert data["current_state"] == "running"
            assert "idle" in data["state_data"]
            assert "running" in data["state_data"]
            assert len(data["transitions"]) == 1

    def test_load_state_exists(self):
        """Test load_state when file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.json")
            persistence = StatePersistence(path)

            # Also save state with valid transitions
            class TestMachine(StateMachine):
                def get_valid_transitions(self, state):
                    return ["running", "idle", "paused", "stopped"]

            sm = TestMachine("idle")
            sm.transition("running", {"task": "task1"})
            persistence.save_state(sm)

            loaded = persistence.load_state()
            assert loaded["current_state"] == "running"

    def test_load_state_not_exists(self):
        """Test load_state when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "nonexistent.json")
            persistence = StatePersistence(path)

            result = persistence.load_state()
            assert result is None

    def test_delete_state(self):
        """Test delete_state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.json")
            persistence = StatePersistence(path)

            # Create file
            with open(path, "w") as f:
                json.dump({}, f)
            assert os.path.exists(path)

            persistence.delete_state()
            assert not os.path.exists(path)

    def test_save_persistence_error(self):
        """Test save_state raises StatePersistenceError on failure."""
        # Mock open to simulate permission error
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.json")
            persistence = StatePersistence(path)

            class TestMachine(StateMachine):
                def get_valid_transitions(self, state):
                    return ["running", "idle", "paused", "stopped"]

            sm = TestMachine("idle")
            sm.transition("running")

            # Mock open to raise PermissionError
            with patch("builtins.open", side_effect=PermissionError("Permission denied")):
                with pytest.raises(StatePersistenceError):
                    persistence.save_state(sm)


class TestAsyncStateMachine:
    """Test AsyncStateMachine."""

    class ConcreteAsyncSM(AsyncStateMachine):
        def get_valid_transitions(self, state):
            return ["running", "idle", "paused"]

    @pytest.fixture
    def async_sm(self):
        return self.ConcreteAsyncSM("idle")

    def test_async_init(self, async_sm):
        """Test AsyncStateMachine initialization."""
        assert async_sm.current_state == "idle"
        assert async_sm.transition_handlers == {}

    def test_on_transition(self, async_sm):
        """Test on_transition registers handler."""

        def handler(transition):
            pass

        async_sm.on_transition("running", handler)
        assert async_sm.transition_handlers["running"] == handler

    @pytest.mark.asyncio
    async def test_transition_async_valid(self, async_sm):
        """Test async transition valid."""
        await async_sm.transition_async("running")
        assert async_sm.current_state == "running"
        assert len(async_sm.transitions) == 1

    @pytest.mark.asyncio
    async def test_transition_async_invalid(self, async_sm):
        """Test async transition invalid raises."""
        with pytest.raises(StateTransitionError):
            await async_sm.transition_async("invalid")

    @pytest.mark.asyncio
    async def test_transition_async_with_handler(self, async_sm):
        """Test transition_async calls handler."""
        handler_called = []

        async def async_handler(transition):
            handler_called.append(transition)

        async_sm.on_transition("running", async_handler)
        await async_sm.transition_async("running")

        assert len(handler_called) == 1
        assert handler_called[0].to_state == "running"

    @pytest.mark.asyncio
    async def test_transition_async_with_sync_handler(self, async_sm):
        """Test transition_async with sync handler."""
        handler_called = []

        def sync_handler(transition):
            handler_called.append(transition)

        async_sm.on_transition("running", sync_handler)
        await async_sm.transition_async("running")

        assert len(handler_called) == 1


class TestStateMonitor:
    """Test StateMonitor."""

    @pytest.fixture
    def sm(self):
        class TestSM(StateMachine):
            def get_valid_transitions(self, state):
                return ["running"]

        return TestSM("idle")

    def test_init(self, sm):
        """Test StateMonitor initialization."""
        monitor = StateMonitor(sm)
        assert monitor.state_machine == sm
        assert monitor.observers == []

    def test_add_observer(self, sm):
        """Test add_observer."""
        monitor = StateMonitor(sm)
        observer = Mock()
        monitor.add_observer(observer)
        assert observer in monitor.observers

    def test_remove_observer(self, sm):
        """Test remove_observer."""
        monitor = StateMonitor(sm)
        observer = Mock()
        monitor.add_observer(observer)

        result = monitor.remove_observer(observer)
        assert result is True
        assert observer not in monitor.observers

    def test_remove_nonexistent_observer(self, sm):
        """Test remove_observer with non-existent observer."""
        monitor = StateMonitor(sm)
        observer = Mock()

        result = monitor.remove_observer(observer)
        assert result is False

    def test_notify_observers(self, sm):
        """Test notify_observers."""
        monitor = StateMonitor(sm)
        observer1 = Mock()
        observer2 = Mock()
        monitor.add_observer(observer1)
        monitor.add_observer(observer2)

        transition = StateTransition(from_state="idle", to_state="running")
        monitor.notify_observers(transition)

        observer1.assert_called_once_with(transition)
        observer2.assert_called_once_with(transition)

    def test_notify_observer_error(self, sm):
        """Test notify_observers handles observer errors."""
        monitor = StateMonitor(sm)
        bad_observer = Mock(side_effect=Exception("Observer failed"))
        good_observer = Mock()
        monitor.add_observer(bad_observer)
        monitor.add_observer(good_observer)

        transition = StateTransition(from_state="idle", to_state="running")
        monitor.notify_observers(transition)

        bad_observer.assert_called_once()
        good_observer.assert_called_once()

    def test_wrap_transition(self, sm):
        """Test wrap_transition."""
        monitor = StateMonitor(sm)
        observer = Mock()
        monitor.add_observer(observer)

        original = sm.transition
        wrapped = monitor.wrap_transition(original)

        wrapped("running")

        assert sm.current_state == "running"
        observer.assert_called_once()


class TestStateValidator:
    """Test StateValidator."""

    def test_validate_transitions_valid(self):
        """Test validate_transitions with valid config."""
        # All target states must exist as source states
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": []}
        assert StateValidator.validate_transitions(transitions) is True

    def test_validate_transitions_invalid(self):
        """Test validate_transitions with invalid target."""
        transitions = {"idle": ["running"], "running": ["nonexistent"]}
        assert StateValidator.validate_transitions(transitions) is False

    def test_check_for_deadlocks(self):
        """Test check_for_deadlocks."""
        transitions = {"idle": ["running"], "running": [], "stopped": ["idle"]}
        deadlocks = StateValidator.check_for_deadlocks(transitions)
        assert "running" in deadlocks

    def test_check_for_deadlocks_none(self):
        """Test check_for_deadlocks with no deadlocks."""
        transitions = {"idle": ["running"], "running": ["stopped"]}
        deadlocks = StateValidator.check_for_deadlocks(transitions)
        assert deadlocks == []

    def test_check_for_orphans(self):
        """Test check_for_orphans."""
        transitions = {"idle": ["running"], "running": ["stopped"], "orphan": []}
        orphans = StateValidator.check_for_orphans(transitions)
        assert "orphan" in orphans

    def test_check_for_orphans_none(self):
        """Test check_for_orphans with no orphans."""
        transitions = {"idle": ["running"], "running": ["stopped"], "stopped": ["idle"]}
        orphans = StateValidator.check_for_orphans(transitions)
        assert orphans == []


class TestStateSnapshot:
    """Test StateSnapshot."""

    @pytest.fixture
    def sm(self):
        class TestSM(StateMachine):
            def get_valid_transitions(self, state):
                return ["running", "paused", "idle", "stopped"]

        return TestSM("idle")

    def test_snapshot_creation(self, sm):
        """Test StateSnapshot creation."""
        sm.transition("running", {"task": "test"})
        snapshot = StateSnapshot(sm)

        assert snapshot.current_state == "running"
        assert "idle" in snapshot.state_data
        assert "running" in snapshot.state_data
        assert len(snapshot.transitions) == 1

    def test_restore(self, sm):
        """Test restore from snapshot."""
        sm.transition("running")
        sm.set_state_data({"key": "value"})
        snapshot = StateSnapshot(sm)

        # Modify original
        sm.transition("paused")
        sm.set_state_data({"new": "data"})

        # Restore
        snapshot.restore(sm)

        assert sm.current_state == "running"
        assert sm.get_state_data() == {"key": "value"}

    def test_to_dict(self, sm):
        """Test to_dict."""
        sm.transition("running")
        snapshot = StateSnapshot(sm)

        data = snapshot.to_dict()

        assert data["current_state"] == "running"
        assert "idle" in data["state_data"]
        assert len(data["transitions"]) == 1
        assert data["transitions"][0]["from_state"] == "idle"
        assert "timestamp" in data

    def test_from_dict(self, sm):
        """Test from_dict."""
        data = {
            "current_state": "running",
            "state_data": {"idle": {}, "running": {"task": "test"}},
            "transitions": [
                {"from_state": "idle", "to_state": "running", "timestamp": datetime.now(UTC).isoformat(), "data": {}}
            ],
            "timestamp": datetime.now(UTC).isoformat(),
        }

        snapshot = StateSnapshot.from_dict(data)

        assert snapshot.current_state == "running"
        assert snapshot.state_data["running"]["task"] == "test"
        assert len(snapshot.transitions) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
