"""
Tests for AITBC events module (events.py)
This module has 0% coverage and 275 statements.
"""

import asyncio
import importlib.util
from datetime import UTC, datetime
from pathlib import Path


# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


events = load_module_from_path("aitbc.events", Path("/opt/aitbc/aitbc/events.py"))


# ============================================================================
# Event Priority Tests
# ============================================================================


class TestEventPriority:
    """Test EventPriority enum"""

    def test_priority_values(self):
        assert events.EventPriority.LOW.value == 1
        assert events.EventPriority.MEDIUM.value == 2
        assert events.EventPriority.HIGH.value == 3
        assert events.EventPriority.CRITICAL.value == 4


# ============================================================================
# Event Dataclass Tests
# ============================================================================


class TestEvent:
    """Test Event dataclass"""

    def test_event_initialization(self):
        event = events.Event(event_type="test_event", data={"key": "value"})
        assert event.event_type == "test_event"
        assert event.data == {"key": "value"}
        assert event.timestamp is not None
        assert event.priority == events.EventPriority.MEDIUM
        assert event.source is None

    def test_event_with_priority(self):
        event = events.Event(event_type="test_event", data={"key": "value"}, priority=events.EventPriority.HIGH)
        assert event.priority == events.EventPriority.HIGH

    def test_event_with_source(self):
        event = events.Event(event_type="test_event", data={"key": "value"}, source="test_source")
        assert event.source == "test_source"

    def test_event_with_custom_timestamp(self):
        custom_ts = datetime.now(UTC)
        event = events.Event(event_type="test_event", data={"key": "value"}, timestamp=custom_ts)
        assert event.timestamp == custom_ts


# ============================================================================
# Event Bus Tests
# ============================================================================


class TestEventBus:
    """Test EventBus class"""

    def test_event_bus_initialization(self):
        bus = events.EventBus()
        assert bus.subscribers == {}
        assert bus.event_history == []
        assert bus.max_history == 1000

    def test_subscribe(self):
        bus = events.EventBus()
        handler = lambda e: None  # noqa: E731
        bus.subscribe("test_event", handler)
        assert "test_event" in bus.subscribers
        assert handler in bus.subscribers["test_event"]

    def test_subscribe_multiple_handlers(self):
        bus = events.EventBus()
        handler1 = lambda e: None  # noqa: E731
        handler2 = lambda e: None  # noqa: E731
        bus.subscribe("test_event", handler1)
        bus.subscribe("test_event", handler2)
        assert len(bus.subscribers["test_event"]) == 2

    def test_unsubscribe(self):
        bus = events.EventBus()
        handler = lambda e: None  # noqa: E731
        bus.subscribe("test_event", handler)
        result = bus.unsubscribe("test_event", handler)
        assert result is True
        assert handler not in bus.subscribers["test_event"]

    def test_unsubscribe_nonexistent_handler(self):
        bus = events.EventBus()
        handler = lambda e: None  # noqa: E731
        result = bus.unsubscribe("test_event", handler)
        assert result is False

    def test_unsubscribe_nonexistent_event(self):
        bus = events.EventBus()
        handler = lambda e: None  # noqa: E731
        result = bus.unsubscribe("nonexistent", handler)
        assert result is False

    def test_publish_sync_handler(self):
        bus = events.EventBus()
        called = []

        def handler(event):
            called.append(event)

        bus.subscribe("test_event", handler)
        event = events.Event(event_type="test_event", data={"key": "value"})
        bus.publish_sync(event)

        assert len(called) == 1
        assert called[0] == event

    def test_publish_async_handler(self):
        bus = events.EventBus()
        called = []

        async def handler(event):
            called.append(event)

        bus.subscribe("test_event", handler)
        event = events.Event(event_type="test_event", data={"key": "value"})
        asyncio.run(bus.publish(event))

        assert len(called) == 1
        assert called[0] == event

    def test_publish_multiple_handlers(self):
        bus = events.EventBus()
        called = []

        def handler1(event):
            called.append("handler1")

        def handler2(event):
            called.append("handler2")

        bus.subscribe("test_event", handler1)
        bus.subscribe("test_event", handler2)
        event = events.Event(event_type="test_event", data={"key": "value"})
        bus.publish_sync(event)

        assert len(called) == 2
        assert "handler1" in called
        assert "handler2" in called

    def test_publish_handler_error(self):
        bus = events.EventBus()

        def handler(event):
            raise ValueError("Handler error")

        bus.subscribe("test_event", handler)
        event = events.Event(event_type="test_event", data={"key": "value"})
        # Should not raise, error is logged
        bus.publish_sync(event)

    def test_publish_no_subscribers(self):
        bus = events.EventBus()
        event = events.Event(event_type="test_event", data={"key": "value"})
        # Should not raise
        bus.publish_sync(event)

    def test_get_event_history(self):
        bus = events.EventBus()
        event1 = events.Event(event_type="test_event", data={"key": "value1"})
        event2 = events.Event(event_type="test_event", data={"key": "value2"})
        bus.publish_sync(event1)
        bus.publish_sync(event2)

        history = bus.get_event_history()
        assert len(history) == 2

    def test_get_event_history_with_type_filter(self):
        bus = events.EventBus()
        event1 = events.Event(event_type="event1", data={"key": "value1"})
        event2 = events.Event(event_type="event2", data={"key": "value2"})
        bus.publish_sync(event1)
        bus.publish_sync(event2)

        history = bus.get_event_history(event_type="event1")
        assert len(history) == 1
        assert history[0].event_type == "event1"

    def test_get_event_history_with_limit(self):
        bus = events.EventBus()
        for i in range(10):
            event = events.Event(event_type="test_event", data={"index": i})
            bus.publish_sync(event)

        history = bus.get_event_history(limit=5)
        assert len(history) == 5

    def test_clear_history(self):
        bus = events.EventBus()
        event = events.Event(event_type="test_event", data={"key": "value"})
        bus.publish_sync(event)
        bus.clear_history()
        assert len(bus.event_history) == 0

    def test_history_max_limit(self):
        bus = events.EventBus()
        # max_history is set to 1000 by default, not configurable via constructor
        # Test that history is limited to max_history
        for i in range(1005):
            event = events.Event(event_type="test_event", data={"index": i})
            bus.publish_sync(event)

        assert len(bus.event_history) == 1000


# ============================================================================
# Async Event Bus Tests
# ============================================================================


class TestAsyncEventBus:
    """Test AsyncEventBus class"""

    def test_async_event_bus_initialization(self):
        bus = events.AsyncEventBus()
        assert bus.max_history == 1000
        assert bus.semaphore is not None

    def test_async_event_bus_custom_concurrency(self):
        bus = events.AsyncEventBus(max_concurrent_handlers=5)
        assert bus.semaphore is not None

    def test_async_event_bus_publish(self):
        bus = events.AsyncEventBus()
        called = []

        def handler(event):
            called.append(event)

        bus.subscribe("test_event", handler)
        event = events.Event(event_type="test_event", data={"key": "value"})
        asyncio.run(bus.publish(event))

        assert len(called) == 1

    def test_async_event_bus_publish_async_handler(self):
        bus = events.AsyncEventBus()
        called = []

        async def handler(event):
            called.append(event)

        bus.subscribe("test_event", handler)
        event = events.Event(event_type="test_event", data={"key": "value"})
        asyncio.run(bus.publish(event))

        assert len(called) == 1


# ============================================================================
# Event Handler Decorator Tests
# ============================================================================


class TestEventHandlerDecorator:
    """Test event_handler decorator"""

    def test_event_handler_decorator(self):
        events._global_event_bus = None

        @events.event_handler("test_event")
        def handler(event):
            pass

        bus = events.get_global_event_bus()
        assert "test_event" in bus.subscribers
        assert handler in bus.subscribers["test_event"]

    def test_event_handler_with_custom_bus(self):
        custom_bus = events.EventBus()

        @events.event_handler("test_event", event_bus=custom_bus)
        def handler(event):
            pass

        assert "test_event" in custom_bus.subscribers
        assert handler in custom_bus.subscribers["test_event"]


# ============================================================================
# Publish Event Helper Tests
# ============================================================================


class TestPublishEventHelper:
    """Test publish_event helper function"""

    def test_publish_event(self):
        events._global_event_bus = None
        events.publish_event("test_event", {"key": "value"})

        bus = events.get_global_event_bus()
        assert len(bus.event_history) == 1
        assert bus.event_history[0].event_type == "test_event"

    def test_publish_event_with_custom_bus(self):
        custom_bus = events.EventBus()
        events.publish_event("test_event", {"key": "value"}, event_bus=custom_bus)

        assert len(custom_bus.event_history) == 1


# ============================================================================
# Global Event Bus Tests
# ============================================================================


class TestGlobalEventBus:
    """Test global event bus functions"""

    def test_get_global_event_bus_singleton(self):
        events._global_event_bus = None
        bus1 = events.get_global_event_bus()
        bus2 = events.get_global_event_bus()
        assert bus1 is bus2

    def test_set_global_event_bus(self):
        events._global_event_bus = None
        custom_bus = events.EventBus()
        events.set_global_event_bus(custom_bus)
        assert events.get_global_event_bus() is custom_bus


# ============================================================================
# Event Filter Tests
# ============================================================================


class TestEventFilter:
    """Test EventFilter class"""

    def test_event_filter_initialization(self):
        filter_obj = events.EventFilter()
        assert filter_obj.event_bus is not None
        assert filter_obj.filters == []

    def test_event_filter_with_custom_bus(self):
        custom_bus = events.EventBus()
        filter_obj = events.EventFilter(event_bus=custom_bus)
        assert filter_obj.event_bus is custom_bus

    def test_add_filter(self):
        filter_obj = events.EventFilter()

        def filter_func(event):
            return event.event_type == "test"

        filter_obj.add_filter(filter_func)
        assert len(filter_obj.filters) == 1

    def test_matches_no_filters(self):
        filter_obj = events.EventFilter()
        event = events.Event(event_type="test", data={})
        assert filter_obj.matches(event) is True

    def test_matches_with_filter(self):
        filter_obj = events.EventFilter()

        def filter_func(event):
            return event.event_type == "test"

        filter_obj.add_filter(filter_func)
        event = events.Event(event_type="test", data={})
        assert filter_obj.matches(event) is True

    def test_matches_filter_fails(self):
        filter_obj = events.EventFilter()

        def filter_func(event):
            return event.event_type == "test"

        filter_obj.add_filter(filter_func)
        event = events.Event(event_type="other", data={})
        assert filter_obj.matches(event) is False

    def test_get_filtered_events(self):
        bus = events.EventBus()
        filter_obj = events.EventFilter(event_bus=bus)

        event1 = events.Event(event_type="test", data={})
        event2 = events.Event(event_type="other", data={})
        bus.publish_sync(event1)
        bus.publish_sync(event2)

        def filter_func(event):
            return event.event_type == "test"

        filter_obj.add_filter(filter_func)
        filtered = filter_obj.get_filtered_events()
        assert len(filtered) == 1
        assert filtered[0].event_type == "test"


# ============================================================================
# Event Aggregator Tests
# ============================================================================


class TestEventAggregator:
    """Test EventAggregator class"""

    def test_event_aggregator_initialization(self):
        agg = events.EventAggregator()
        assert agg.window_seconds == 60
        assert agg.aggregated_events == {}

    def test_event_aggregator_custom_window(self):
        agg = events.EventAggregator(window_seconds=120)
        assert agg.window_seconds == 120

    def test_add_event(self):
        agg = events.EventAggregator()
        event = events.Event(event_type="test", data={"count": 1})
        agg.add_event(event)

        assert "test" in agg.aggregated_events
        assert agg.aggregated_events["test"]["count"] == 1

    def test_add_event_multiple(self):
        agg = events.EventAggregator()
        event1 = events.Event(event_type="test", data={"count": 1})
        event2 = events.Event(event_type="test", data={"count": 2})
        agg.add_event(event1)
        agg.add_event(event2)

        assert agg.aggregated_events["test"]["count"] == 2

    def test_add_event_data_merge(self):
        agg = events.EventAggregator()
        event1 = events.Event(event_type="test", data={"value": 10})
        event2 = events.Event(event_type="test", data={"value": 5})
        agg.add_event(event1)
        agg.add_event(event2)

        assert agg.aggregated_events["test"]["data"]["value"] == 15

    def test_get_aggregated_events(self):
        agg = events.EventAggregator()
        event = events.Event(event_type="test", data={})
        agg.add_event(event)

        result = agg.get_aggregated_events()
        assert "test" in result

    def test_get_aggregated_events_expires_old(self):
        agg = events.EventAggregator(window_seconds=0.01)
        event = events.Event(event_type="test", data={})
        agg.add_event(event)

        import time

        time.sleep(0.02)

        result = agg.get_aggregated_events()
        assert "test" not in result

    def test_clear(self):
        agg = events.EventAggregator()
        event = events.Event(event_type="test", data={})
        agg.add_event(event)
        agg.clear()

        assert agg.aggregated_events == {}


# ============================================================================
# Event Router Tests
# ============================================================================


class TestEventRouter:
    """Test EventRouter class"""

    def test_event_router_initialization(self):
        router = events.EventRouter()
        assert router.routes == []

    def test_add_route(self):
        router = events.EventRouter()

        def condition(event):
            return event.event_type == "test"

        def handler(event):
            pass

        router.add_route(condition, handler)
        assert len(router.routes) == 1

    def test_route_matching(self):
        router = events.EventRouter()
        called = []

        def condition(event):
            return event.event_type == "test"

        def handler(event):
            called.append(event)

        router.add_route(condition, handler)
        event = events.Event(event_type="test", data={})
        result = asyncio.run(router.route(event))

        assert result is True
        assert len(called) == 1

    def test_route_no_match(self):
        router = events.EventRouter()

        def condition(event):
            return event.event_type == "other"

        def handler(event):
            pass

        router.add_route(condition, handler)
        event = events.Event(event_type="test", data={})
        result = asyncio.run(router.route(event))

        assert result is False

    def test_route_async_handler(self):
        router = events.EventRouter()
        called = []

        def condition(event):
            return event.event_type == "test"

        async def handler(event):
            called.append(event)

        router.add_route(condition, handler)
        event = events.Event(event_type="test", data={})
        asyncio.run(router.route(event))

        assert len(called) == 1

    def test_route_handler_error(self):
        router = events.EventRouter()

        def condition(event):
            return event.event_type == "test"

        def handler(event):
            raise ValueError("Handler error")

        router.add_route(condition, handler)
        event = events.Event(event_type="test", data={})
        # Should not raise, error is logged
        result = asyncio.run(router.route(event))
        assert result is False
