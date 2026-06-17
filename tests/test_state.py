"""
Tests for state management utilities
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from aitbc.state.state import (
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


class TestExceptions:
    """Tests for state exceptions"""

    def test_state_transition_error(self):
        """Test StateTransitionError"""
        with pytest.raises(StateTransitionError):
            raise StateTransitionError("Invalid transition")

    def test_state_persistence_error(self):
        """Test StatePersistenceError"""
        with pytest.raises(StatePersistenceError):
            raise StatePersistenceError("Persistence failed")


class TestStateTransition:
    """Tests for StateTransition dataclass"""

    def test_state_transition_creation(self):
        """Test StateTransition creation"""
        transition = StateTransition(from_state="state1", to_state="state2", data={"key": "value"})
        assert transition.from_state == "state1"
        assert transition.to_state == "state2"
        assert transition.data == {"key": "value"}
        assert transition.timestamp is not None

    def test_state_transition_defaults(self):
        """Test StateTransition with defaults"""
        transition = StateTransition(from_state="state1", to_state="state2")
        assert transition.data == {}
        assert transition.timestamp is not None


class TestStateMachine:
    """Tests for StateMachine"""

    def test_initialization(self):
        """Test StateMachine initialization"""
        machine = TestableStateMachine("initial")
        assert machine.current_state == "initial"
        assert machine.transitions == []
        assert machine.state_data == {"initial": {}}

    def test_can_transition_valid(self):
        """Test can_transition with valid transition"""
        machine = TestableStateMachine("state1")
        assert machine.can_transition("state2") is True

    def test_can_transition_invalid(self):
        """Test can_transition with invalid transition"""
        machine = TestableStateMachine("state1")
        assert machine.can_transition("invalid") is False

    def test_transition_success(self):
        """Test successful transition"""
        machine = TestableStateMachine("state1")
        machine.transition("state2")

        assert machine.current_state == "state2"
        assert len(machine.transitions) == 1
        assert machine.transitions[0].from_state == "state1"
        assert machine.transitions[0].to_state == "state2"

    def test_transition_with_data(self):
        """Test transition with data"""
        machine = TestableStateMachine("state1")
        machine.transition("state2", data={"key": "value"})

        assert machine.transitions[0].data == {"key": "value"}

    def test_transition_invalid(self):
        """Test invalid transition raises error"""
        machine = TestableStateMachine("state1")

        with pytest.raises(StateTransitionError):
            machine.transition("invalid")

    def test_get_state_data_current(self):
        """Test get_state_data for current state"""
        machine = TestableStateMachine("state1")
        machine.set_state_data({"key": "value"})

        data = machine.get_state_data()
        assert data == {"key": "value"}

    def test_get_state_data_specific(self):
        """Test get_state_data for specific state"""
        machine = TestableStateMachine("state1")
        machine.set_state_data({"key": "value1"}, state="state1")
        machine.transition("state2")
        machine.set_state_data({"key": "value2"}, state="state2")

        data = machine.get_state_data("state1")
        assert data == {"key": "value1"}

    def test_set_state_data(self):
        """Test set_state_data"""
        machine = TestableStateMachine("state1")
        machine.set_state_data({"key": "value"})

        assert machine.state_data["state1"] == {"key": "value"}

    def test_set_state_data_merge(self):
        """Test set_state_data merges existing data"""
        machine = TestableStateMachine("state1")
        machine.set_state_data({"key1": "value1"})
        machine.set_state_data({"key2": "value2"})

        assert machine.state_data["state1"] == {"key1": "value1", "key2": "value2"}

    def test_get_transition_history(self):
        """Test get_transition_history"""
        machine = TestableStateMachine("state1")
        machine.transition("state2")
        machine.transition("state3")

        history = machine.get_transition_history()
        assert len(history) == 2

    def test_get_transition_history_with_limit(self):
        """Test get_transition_history with limit"""
        machine = TestableStateMachine("state1")
        machine.transition("state2")
        machine.transition("state3")
        machine.transition("state4")

        history = machine.get_transition_history(limit=2)
        assert len(history) == 2
        assert history[0].from_state == "state2"
        assert history[1].from_state == "state3"

    def test_reset(self):
        """Test reset state machine"""
        machine = TestableStateMachine("state1")
        machine.transition("state2")
        machine.set_state_data({"key": "value"})

        machine.reset("initial")

        assert machine.current_state == "initial"
        assert machine.transitions == []
        assert machine.state_data == {"initial": {}}


class TestConfigurableStateMachine:
    """Tests for ConfigurableStateMachine"""

    def test_initialization(self):
        """Test ConfigurableStateMachine initialization"""
        transitions = {"state1": ["state2", "state3"], "state2": ["state3"]}
        machine = ConfigurableStateMachine("state1", transitions)

        assert machine.current_state == "state1"
        assert machine.transitions_config == transitions

    def test_get_valid_transitions(self):
        """Test get_valid_transitions from config"""
        transitions = {"state1": ["state2", "state3"]}
        machine = ConfigurableStateMachine("state1", transitions)

        valid = machine.get_valid_transitions("state1")
        assert valid == ["state2", "state3"]

    def test_get_valid_transitions_empty(self):
        """Test get_valid_transitions for state with no transitions"""
        transitions = {"state1": []}
        machine = ConfigurableStateMachine("state1", transitions)

        valid = machine.get_valid_transitions("state1")
        assert valid == []

    def test_add_transition(self):
        """Test add_transition"""
        transitions = {"state1": ["state2"]}
        machine = ConfigurableStateMachine("state1", transitions)

        machine.add_transition("state1", "state3")

        assert "state3" in machine.transitions_config["state1"]

    def test_add_transition_new_from_state(self):
        """Test add_transition creates new from_state"""
        transitions = {}
        machine = ConfigurableStateMachine("state1", transitions)

        machine.add_transition("state1", "state2")

        assert "state1" in machine.transitions_config
        assert "state2" in machine.transitions_config["state1"]


class TestStatePersistence:
    """Tests for StatePersistence"""

    def test_initialization(self):
        """Test StatePersistence initialization"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "state.json")
            persistence = StatePersistence(storage_path)

            assert persistence.storage_path == storage_path

    def test_save_state(self):
        """Test save_state"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "state.json")
            persistence = StatePersistence(storage_path)

            machine = TestableStateMachine("state1")
            machine.transition("state2")

            persistence.save_state(machine)

            assert os.path.exists(storage_path)

    def test_load_state(self):
        """Test load_state"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "state.json")
            persistence = StatePersistence(storage_path)

            machine = TestableStateMachine("state1")
            machine.transition("state2")
            persistence.save_state(machine)

            loaded = persistence.load_state()

            assert loaded is not None
            assert loaded["current_state"] == "state2"

    def test_load_state_not_exists(self):
        """Test load_state when file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "nonexistent.json")
            persistence = StatePersistence(storage_path)

            loaded = persistence.load_state()

            assert loaded is None

    def test_delete_state(self):
        """Test delete_state"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "state.json")
            persistence = StatePersistence(storage_path)

            machine = TestableStateMachine("state1")
            persistence.save_state(machine)

            persistence.delete_state()

            assert not os.path.exists(storage_path)

    def test_delete_state_not_exists(self):
        """Test delete_state when file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "nonexistent.json")
            persistence = StatePersistence(storage_path)

            # Should not raise
            persistence.delete_state()

    def test_save_state_error(self):
        """Test save_state raises error on failure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a path that will fail (e.g., invalid directory)
            storage_path = os.path.join(tmpdir, "subdir", "state.json")
            persistence = StatePersistence(storage_path)

            machine = TestableStateMachine("state1")
            # Don't create the parent directory - this will cause an error
            # Manually clear the directory that was auto-created
            import shutil

            if os.path.exists(os.path.dirname(storage_path)):
                shutil.rmtree(os.path.dirname(storage_path))

            with pytest.raises(StatePersistenceError):
                persistence.save_state(machine)


class TestAsyncStateMachine:
    """Tests for AsyncStateMachine"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test AsyncStateMachine initialization"""
        machine = AsyncTestableStateMachine("initial")
        assert machine.current_state == "initial"
        assert machine.transition_handlers == {}

    @pytest.mark.asyncio
    async def test_on_transition(self):
        """Test on_transition handler registration"""
        machine = AsyncTestableStateMachine("state1")
        handler = Mock()

        machine.on_transition("state2", handler)

        assert "state2" in machine.transition_handlers

    @pytest.mark.asyncio
    async def test_transition_async(self):
        """Test async transition"""
        machine = AsyncTestableStateMachine("state1")
        await machine.transition_async("state2")

        assert machine.current_state == "state2"
        assert len(machine.transitions) == 1

    @pytest.mark.asyncio
    async def test_transition_async_invalid(self):
        """Test async transition with invalid state"""
        machine = AsyncTestableStateMachine("state1")

        with pytest.raises(StateTransitionError):
            await machine.transition_async("invalid")

    @pytest.mark.asyncio
    async def test_transition_async_with_sync_handler(self):
        """Test async transition calls sync handler"""
        machine = AsyncTestableStateMachine("state1")
        handler = Mock()
        machine.on_transition("state2", handler)

        await machine.transition_async("state2")

        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_transition_async_with_async_handler(self):
        """Test async transition calls async handler"""
        machine = AsyncTestableStateMachine("state1")

        async_handler_called = [False]

        async def async_handler(transition):
            async_handler_called[0] = True

        machine.on_transition("state2", async_handler)

        await machine.transition_async("state2")

        assert async_handler_called[0] is True


class TestStateMonitor:
    """Tests for StateMonitor"""

    def test_initialization(self):
        """Test StateMonitor initialization"""
        machine = TestableStateMachine("state1")
        monitor = StateMonitor(machine)

        assert monitor.state_machine == machine
        assert monitor.observers == []

    def test_add_observer(self):
        """Test add_observer"""
        machine = TestableStateMachine("state1")
        monitor = StateMonitor(machine)
        observer = Mock()

        monitor.add_observer(observer)

        assert observer in monitor.observers

    def test_remove_observer(self):
        """Test remove_observer"""
        machine = TestableStateMachine("state1")
        monitor = StateMonitor(machine)
        observer = Mock()
        monitor.add_observer(observer)

        result = monitor.remove_observer(observer)

        assert result is True
        assert observer not in monitor.observers

    def test_remove_observer_not_found(self):
        """Test remove_observer when observer not found"""
        machine = TestableStateMachine("state1")
        monitor = StateMonitor(machine)
        observer = Mock()

        result = monitor.remove_observer(observer)

        assert result is False

    def test_notify_observers(self):
        """Test notify_observers"""
        machine = TestableStateMachine("state1")
        monitor = StateMonitor(machine)
        observer1 = Mock()
        observer2 = Mock()
        monitor.add_observer(observer1)
        monitor.add_observer(observer2)

        transition = StateTransition("state1", "state2")
        monitor.notify_observers(transition)

        observer1.assert_called_once_with(transition)
        observer2.assert_called_once_with(transition)

    @patch("aitbc.state.state.logger")
    def test_notify_observers_error(self, mock_logger):
        """Test notify_observers handles observer errors"""
        machine = TestableStateMachine("state1")
        monitor = StateMonitor(machine)

        def failing_observer(transition):
            raise Exception("Observer error")

        monitor.add_observer(failing_observer)

        transition = StateTransition("state1", "state2")
        monitor.notify_observers(transition)

        mock_logger.error.assert_called_once()

    def test_wrap_transition(self):
        """Test wrap_transition"""
        machine = TestableStateMachine("state1")
        monitor = StateMonitor(machine)
        observer = Mock()
        monitor.add_observer(observer)

        wrapped = monitor.wrap_transition(machine.transition)
        wrapped("state2")

        observer.assert_called_once()


class TestStateValidator:
    """Tests for StateValidator"""

    def test_validate_transitions_valid(self):
        """Test validate_transitions with valid config"""
        transitions = {"state1": ["state2", "state3"], "state2": ["state3"], "state3": []}

        result = StateValidator.validate_transitions(transitions)
        assert result is True

    def test_validate_transitions_invalid(self):
        """Test validate_transitions with invalid target state"""
        transitions = {"state1": ["state2", "nonexistent"]}

        result = StateValidator.validate_transitions(transitions)
        # "nonexistent" is not a valid state since it's not in transitions.keys()
        assert result is False

    def test_check_for_deadlocks(self):
        """Test check_for_deadlocks"""
        transitions = {
            "state1": ["state2"],
            "state2": [],  # No outgoing transitions
        }

        deadlocks = StateValidator.check_for_deadlocks(transitions)
        assert "state2" in deadlocks

    def test_check_for_deadlocks_none(self):
        """Test check_for_deadlocks with no deadlocks"""
        transitions = {"state1": ["state2"], "state2": ["state1"]}

        deadlocks = StateValidator.check_for_deadlocks(transitions)
        assert deadlocks == []

    def test_check_for_orphans(self):
        """Test check_for_orphans"""
        transitions = {
            "state1": ["state2"],
            "state2": ["state3"],
            "state3": [],  # state3 is an orphan (no incoming transitions from defined states)
        }

        # Actually state3 has incoming from state2, so let's create a real orphan
        transitions = {
            "state1": ["state2"],
            "state2": [],
            "orphan": [],  # No incoming transitions
        }

        orphans = StateValidator.check_for_orphans(transitions)
        assert "orphan" in orphans

    def test_check_for_orphans_none(self):
        """Test check_for_orphans with no orphans"""
        transitions = {"state1": ["state2"], "state2": ["state1"]}

        orphans = StateValidator.check_for_orphans(transitions)
        assert orphans == []


class TestStateSnapshot:
    """Tests for StateSnapshot"""

    def test_initialization(self):
        """Test StateSnapshot creation"""
        machine = TestableStateMachine("state1")
        machine.transition("state2")

        snapshot = StateSnapshot(machine)

        assert snapshot.current_state == "state2"
        assert snapshot.state_data == machine.state_data
        assert snapshot.transitions == machine.transitions
        assert snapshot.timestamp is not None

    def test_restore(self):
        """Test restore from snapshot"""
        machine1 = TestableStateMachine("state1")
        machine1.transition("state2")
        machine1.set_state_data({"key": "value"})

        snapshot = StateSnapshot(machine1)

        machine2 = TestableStateMachine("initial")
        snapshot.restore(machine2)

        assert machine2.current_state == "state2"
        assert machine2.state_data == machine1.state_data

    def test_to_dict(self):
        """Test to_dict conversion"""
        machine = TestableStateMachine("state1")
        snapshot = StateSnapshot(machine)

        data = snapshot.to_dict()

        assert "current_state" in data
        assert "state_data" in data
        assert "transitions" in data
        assert "timestamp" in data

    def test_from_dict(self):
        """Test from_dict creation"""
        machine = TestableStateMachine("state1")
        machine.transition("state2")
        snapshot = StateSnapshot(machine)

        data = snapshot.to_dict()
        restored = StateSnapshot.from_dict(data)

        assert restored.current_state == snapshot.current_state
        assert restored.state_data == snapshot.state_data


# Helper classes for testing
class TestableStateMachine(StateMachine):
    """Concrete implementation for testing"""

    def get_valid_transitions(self, state: str):
        if state == "state1":
            return ["state2", "state3"]
        elif state == "state2":
            return ["state3"]
        elif state == "state3":
            return ["state4"]
        elif state == "state4":
            return ["state1"]
        return []


class AsyncTestableStateMachine(AsyncStateMachine):
    """Concrete async implementation for testing"""

    def get_valid_transitions(self, state: str):
        if state == "state1":
            return ["state2"]
        return []
