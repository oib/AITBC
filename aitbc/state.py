"""
State management utilities for AITBC
Provides state machine base classes, state persistence, and state transition helpers
"""

import json
import os
from typing import Any, Callable, Dict, Optional, TypeVar, Generic, List
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from abc import ABC, abstractmethod
import asyncio


T = TypeVar('T')


class StateTransitionError(Exception):
    """Raised when invalid state transition is attempted"""
    pass


class StatePersistenceError(Exception):
    """Raised when state persistence fails"""
    pass


@dataclass
class StateTransition:
    """Record of a state transition"""
    from_state: str
    to_state: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = field(default_factory=dict)


class StateMachine(ABC):
    """Base class for state machines"""
    
    def __init__(self, initial_state: str):
        """Initialize state machine"""
        self.current_state = initial_state
        self.transitions: List[StateTransition] = []
        self.state_data: Dict[str, Dict[str, Any]] = {initial_state: {}}
    
    @abstractmethod
    def get_valid_transitions(self, state: str) -> List[str]:
        """Get valid transitions from a state"""
        pass
    
    def can_transition(self, to_state: str) -> bool:
        """Check if transition is valid"""
        return to_state in self.get_valid_transitions(self.current_state)
    
    def transition(self, to_state: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Transition to a new state"""
        if not self.can_transition(to_state):
            raise StateTransitionError(
                f"Invalid transition from {self.current_state} to {to_state}"
            )
        
        from_state = self.current_state
        self.current_state = to_state
        
        # Record transition
        transition = StateTransition(
            from_state=from_state,
            to_state=to_state,
            data=data or {}
        )
        self.transitions.append(transition)
        
        # Initialize state data if needed
        if to_state not in self.state_data:
            self.state_data[to_state] = {}
    
    def get_state_data(self, state: Optional[str] = None) -> Dict[str, Any]:
        """Get data for a state"""
        state = state or self.current_state
        return self.state_data.get(state, {}).copy()
    
    def set_state_data(self, data: Dict[str, Any], state: Optional[str] = None) -> None:
        """Set data for a state"""
        state = state or self.current_state
        if state not in self.state_data:
            self.state_data[state] = {}
        self.state_data[state].update(data)
    
    def get_transition_history(self, limit: Optional[int] = None) -> List[StateTransition]:
        """Get transition history"""
        if limit:
            return self.transitions[-limit:]
        return self.transitions.copy()
    
    def reset(self, initial_state: str) -> None:
        """Reset state machine to initial state"""
        self.current_state = initial_state
        self.transitions.clear()
        self.state_data = {initial_state: {}}


class ConfigurableStateMachine(StateMachine):
    """State machine with configurable transitions"""
    
    def __init__(self, initial_state: str, transitions: Dict[str, List[str]]):
        """Initialize configurable state machine"""
        super().__init__(initial_state)
        self.transitions_config = transitions
    
    def get_valid_transitions(self, state: str) -> List[str]:
        """Get valid transitions from configuration"""
        return self.transitions_config.get(state, [])
    
    def add_transition(self, from_state: str, to_state: str) -> None:
        """Add a transition to configuration"""
        if from_state not in self.transitions_config:
            self.transitions_config[from_state] = []
        if to_state not in self.transitions_config[from_state]:
            self.transitions_config[from_state].append(to_state)


class StatePersistence:
    """State persistence to file"""
    
    def __init__(self, storage_path: str):
        """Initialize state persistence"""
        self.storage_path = storage_path
        self._ensure_storage_dir()
    
    def _ensure_storage_dir(self) -> None:
        """Ensure storage directory exists"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
    
    def save_state(self, state_machine: StateMachine) -> None:
        """Save state machine to file"""
        try:
            state_data = {
                "current_state": state_machine.current_state,
                "state_data": state_machine.state_data,
                "transitions": [
                    {
                        "from_state": t.from_state,
                        "to_state": t.to_state,
                        "timestamp": t.timestamp.isoformat(),
                        "data": t.data
                    }
                    for t in state_machine.transitions
                ]
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(state_data, f, indent=2)
        except Exception as e:
            raise StatePersistenceError(f"Failed to save state: {e}")
    
    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load state from file"""
        try:
            if not os.path.exists(self.storage_path):
                return None
            
            with open(self.storage_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            raise StatePersistenceError(f"Failed to load state: {e}")
    
    def delete_state(self) -> None:
        """Delete persisted state"""
        try:
            if os.path.exists(self.storage_path):
                os.remove(self.storage_path)
        except Exception as e:
            raise StatePersistenceError(f"Failed to delete state: {e}")


class AsyncStateMachine(StateMachine):
    """Async state machine with async transition handlers"""
    
    def __init__(self, initial_state: str):
        """Initialize async state machine"""
        super().__init__(initial_state)
        self.transition_handlers: Dict[str, Callable] = {}
    
    def on_transition(self, to_state: str, handler: Callable) -> None:
        """Register a handler for transition to a state"""
        self.transition_handlers[to_state] = handler
    
    async def transition_async(self, to_state: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Async transition to a new state"""
        if not self.can_transition(to_state):
            raise StateTransitionError(
                f"Invalid transition from {self.current_state} to {to_state}"
            )
        
        from_state = self.current_state
        self.current_state = to_state
        
        # Record transition
        transition = StateTransition(
            from_state=from_state,
            to_state=to_state,
            data=data or {}
        )
        self.transitions.append(transition)
        
        # Initialize state data if needed
        if to_state not in self.state_data:
            self.state_data[to_state] = {}
        
        # Call transition handler if exists
        if to_state in self.transition_handlers:
            handler = self.transition_handlers[to_state]
            if asyncio.iscoroutinefunction(handler):
                await handler(transition)
            else:
                handler(transition)


class StateMonitor:
    """Monitor state machine state and transitions"""
    
    def __init__(self, state_machine: StateMachine):
        """Initialize state monitor"""
        self.state_machine = state_machine
        self.observers: List[Callable] = []
    
    def add_observer(self, observer: Callable) -> None:
        """Add an observer for state changes"""
        self.observers.append(observer)
    
    def remove_observer(self, observer: Callable) -> bool:
        """Remove an observer"""
        try:
            self.observers.remove(observer)
            return True
        except ValueError:
            return False
    
    def notify_observers(self, transition: StateTransition) -> None:
        """Notify all observers of state change"""
        for observer in self.observers:
            try:
                observer(transition)
            except Exception as e:
                print(f"Error in state observer: {e}")
    
    def wrap_transition(self, original_transition: Callable) -> Callable:
        """Wrap transition method to notify observers"""
        def wrapper(*args, **kwargs):
            result = original_transition(*args, **kwargs)
            # Get last transition
            if self.state_machine.transitions:
                self.notify_observers(self.state_machine.transitions[-1])
            return result
        return wrapper


class StateValidator:
    """Validate state machine configurations"""
    
    @staticmethod
    def validate_transitions(transitions: Dict[str, List[str]]) -> bool:
        """Validate that all target states exist"""
        all_states = set(transitions.keys())
        all_states.update(*transitions.values())
        
        for from_state, to_states in transitions.items():
            for to_state in to_states:
                if to_state not in all_states:
                    return False
        
        return True
    
    @staticmethod
    def check_for_deadlocks(transitions: Dict[str, List[str]]) -> List[str]:
        """Check for states with no outgoing transitions"""
        deadlocks = []
        for state, to_states in transitions.items():
            if not to_states:
                deadlocks.append(state)
        return deadlocks
    
    @staticmethod
    def check_for_orphans(transitions: Dict[str, List[str]]) -> List[str]:
        """Check for states with no incoming transitions"""
        incoming = set()
        for to_states in transitions.values():
            incoming.update(to_states)
        
        orphans = []
        for state in transitions.keys():
            if state not in incoming:
                orphans.append(state)
        
        return orphans


class StateSnapshot:
    """Snapshot of state machine state"""
    
    def __init__(self, state_machine: StateMachine):
        """Create snapshot"""
        self.current_state = state_machine.current_state
        self.state_data = state_machine.state_data.copy()
        self.transitions = state_machine.transitions.copy()
        self.timestamp = datetime.now(datetime.UTC)
    
    def restore(self, state_machine: StateMachine) -> None:
        """Restore state machine from snapshot"""
        state_machine.current_state = self.current_state
        state_machine.state_data = self.state_data.copy()
        state_machine.transitions = self.transitions.copy()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dict"""
        return {
            "current_state": self.current_state,
            "state_data": self.state_data,
            "transitions": [
                {
                    "from_state": t.from_state,
                    "to_state": t.to_state,
                    "timestamp": t.timestamp.isoformat(),
                    "data": t.data
                }
                for t in self.transitions
            ],
            "timestamp": self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StateSnapshot':
        """Create snapshot from dict"""
        snapshot = cls.__new__(cls)
        snapshot.current_state = data["current_state"]
        snapshot.state_data = data["state_data"]
        snapshot.transitions = [
            StateTransition(
                from_state=t["from_state"],
                to_state=t["to_state"],
                timestamp=datetime.fromisoformat(t["timestamp"]),
                data=t["data"]
            )
            for t in data["transitions"]
        ]
        snapshot.timestamp = datetime.fromisoformat(data["timestamp"])
        return snapshot
