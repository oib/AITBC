"""
Event utilities for AITBC
Provides event bus implementation, pub/sub patterns, and event decorators
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum
import inspect
import functools


T = TypeVar('T')


class EventPriority(Enum):
    """Event priority levels"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Event:
    """Base event class"""
    event_type: str
    data: Dict[str, Any]
    timestamp: datetime = None
    priority: EventPriority = EventPriority.MEDIUM
    source: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(datetime.UTC)


class EventBus:
    """Simple in-memory event bus for pub/sub patterns"""
    
    def __init__(self):
        """Initialize event bus"""
        self.subscribers: Dict[str, List[Callable]] = {}
        self.event_history: List[Event] = []
        self.max_history = 1000
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe to an event type"""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(handler)
    
    def unsubscribe(self, event_type: str, handler: Callable) -> bool:
        """Unsubscribe from an event type"""
        if event_type in self.subscribers:
            try:
                self.subscribers[event_type].remove(handler)
                return True
            except ValueError:
                pass
        return False
    
    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers"""
        # Add to history
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)
        
        # Notify subscribers
        handlers = self.subscribers.get(event.event_type, [])
        
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                print(f"Error in event handler: {e}")
    
    def publish_sync(self, event: Event) -> None:
        """Publish an event synchronously"""
        asyncio.run(self.publish(event))
    
    def get_event_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        """Get event history"""
        events = self.event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]
    
    def clear_history(self) -> None:
        """Clear event history"""
        self.event_history.clear()


class AsyncEventBus(EventBus):
    """Async event bus with additional features"""
    
    def __init__(self, max_concurrent_handlers: int = 10):
        """Initialize async event bus"""
        super().__init__()
        self.semaphore = asyncio.Semaphore(max_concurrent_handlers)
    
    async def publish(self, event: Event) -> None:
        """Publish event with concurrency control"""
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)
        
        handlers = self.subscribers.get(event.event_type, [])
        
        tasks = []
        for handler in handlers:
            async def safe_handler():
                async with self.semaphore:
                    try:
                        if inspect.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                    except Exception as e:
                        print(f"Error in event handler: {e}")
            
            tasks.append(safe_handler())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def event_handler(event_type: str, event_bus: Optional[EventBus] = None):
    """Decorator to register event handler"""
    def decorator(func: Callable) -> Callable:
        # Use global event bus if none provided
        bus = event_bus or get_global_event_bus()
        bus.subscribe(event_type, func)
        return func
    return decorator


def publish_event(event_type: str, data: Dict[str, Any], event_bus: Optional[EventBus] = None) -> None:
    """Helper to publish an event"""
    bus = event_bus or get_global_event_bus()
    event = Event(event_type=event_type, data=data)
    bus.publish_sync(event)


# Global event bus instance
_global_event_bus: Optional[EventBus] = None


def get_global_event_bus() -> EventBus:
    """Get or create global event bus"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def set_global_event_bus(bus: EventBus) -> None:
    """Set global event bus"""
    global _global_event_bus
    _global_event_bus = bus


class EventFilter:
    """Filter events based on criteria"""
    
    def __init__(self, event_bus: Optional[EventBus] = None):
        """Initialize event filter"""
        self.event_bus = event_bus or get_global_event_bus()
        self.filters: List[Callable[[Event], bool]] = []
    
    def add_filter(self, filter_func: Callable[[Event], bool]) -> None:
        """Add a filter function"""
        self.filters.append(filter_func)
    
    def matches(self, event: Event) -> bool:
        """Check if event matches all filters"""
        return all(f(event) for f in self.filters)
    
    def get_filtered_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        """Get filtered events"""
        events = self.event_bus.get_event_history(event_type, limit)
        return [e for e in events if self.matches(e)]


class EventAggregator:
    """Aggregate events over time windows"""
    
    def __init__(self, window_seconds: int = 60):
        """Initialize event aggregator"""
        self.window_seconds = window_seconds
        self.aggregated_events: Dict[str, Dict[str, Any]] = {}
    
    def add_event(self, event: Event) -> None:
        """Add event to aggregation"""
        key = event.event_type
        now = datetime.now(datetime.UTC)
        
        if key not in self.aggregated_events:
            self.aggregated_events[key] = {
                "count": 0,
                "first_seen": now,
                "last_seen": now,
                "data": {}
            }
        
        agg = self.aggregated_events[key]
        agg["count"] += 1
        agg["last_seen"] = now
        
        # Merge data
        for k, v in event.data.items():
            if k not in agg["data"]:
                agg["data"][k] = v
            elif isinstance(v, (int, float)):
                agg["data"][k] = agg["data"].get(k, 0) + v
    
    def get_aggregated_events(self) -> Dict[str, Dict[str, Any]]:
        """Get aggregated events"""
        # Remove old events
        now = datetime.now(datetime.UTC)
        cutoff = now.timestamp() - self.window_seconds
        
        to_remove = []
        for key, agg in self.aggregated_events.items():
            if agg["last_seen"].timestamp() < cutoff:
                to_remove.append(key)
        
        for key in to_remove:
            del self.aggregated_events[key]
        
        return self.aggregated_events
    
    def clear(self) -> None:
        """Clear all aggregated events"""
        self.aggregated_events.clear()


class EventRouter:
    """Route events to different handlers based on criteria"""
    
    def __init__(self):
        """Initialize event router"""
        self.routes: List[Callable[[Event], Optional[Callable]]] = []
    
    def add_route(self, condition: Callable[[Event], bool], handler: Callable) -> None:
        """Add a route"""
        self.routes.append((condition, handler))
    
    async def route(self, event: Event) -> bool:
        """Route event to matching handler"""
        for condition, handler in self.routes:
            if condition(event):
                try:
                    if inspect.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                    return True
                except Exception as e:
                    print(f"Error in routed handler: {e}")
        return False
