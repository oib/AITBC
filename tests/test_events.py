"""
Tests for event utilities
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from aitbc.events import (
    AsyncEventBus,
    Event,
    EventAggregator,
    EventBus,
    EventFilter,
    EventPriority,
    EventRouter,
    event_handler,
    get_global_event_bus,
    publish_event,
    set_global_event_bus,
)


class TestEventPriority:
    """Tests for EventPriority enum"""

    def test_priority_values(self):
        """Test EventPriority enum values"""
        assert EventPriority.LOW.value == 1
        assert EventPriority.MEDIUM.value == 2
        assert EventPriority.HIGH.value == 3
        assert EventPriority.CRITICAL.value == 4


class TestEvent:
    """Tests for Event dataclass"""

    def test_event_creation(self):
        """Test Event creation"""
        event = Event(
            event_type="test_event",
            data={"key": "value"}
        )
        assert event.event_type == "test_event"
        assert event.data == {"key": "value"}
        assert event.timestamp is not None
        assert event.priority == EventPriority.MEDIUM

    def test_event_with_timestamp(self):
        """Test Event with custom timestamp"""
        timestamp = datetime.now(UTC)
        event = Event(
            event_type="test_event",
            data={},
            timestamp=timestamp
        )
        assert event.timestamp == timestamp

    def test_event_with_priority(self):
        """Test Event with custom priority"""
        event = Event(
            event_type="test_event",
            data={},
            priority=EventPriority.HIGH
        )
        assert event.priority == EventPriority.HIGH

    def test_event_with_source(self):
        """Test Event with source"""
        event = Event(
            event_type="test_event",
            data={},
            source="test_source"
        )
        assert event.source == "test_source"


class TestEventBus:
    """Tests for EventBus"""

    def test_initialization(self):
        """Test EventBus initialization"""
        bus = EventBus()
        assert bus.subscribers == {}
        assert bus.event_history == []
        assert bus.max_history == 1000

    def test_subscribe(self):
        """Test subscribe to event"""
        bus = EventBus()
        handler = Mock()

        bus.subscribe("test_event", handler)

        assert "test_event" in bus.subscribers
        assert handler in bus.subscribers["test_event"]

    def test_subscribe_multiple(self):
        """Test subscribe multiple handlers"""
        bus = EventBus()
        handler1 = Mock()
        handler2 = Mock()

        bus.subscribe("test_event", handler1)
        bus.subscribe("test_event", handler2)

        assert len(bus.subscribers["test_event"]) == 2

    def test_unsubscribe(self):
        """Test unsubscribe from event"""
        bus = EventBus()
        handler = Mock()
        bus.subscribe("test_event", handler)

        result = bus.unsubscribe("test_event", handler)

        assert result is True
        assert handler not in bus.subscribers["test_event"]

    def test_unsubscribe_not_found(self):
        """Test unsubscribe when handler not found"""
        bus = EventBus()
        handler = Mock()

        result = bus.unsubscribe("test_event", handler)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish(self):
        """Test publish event"""
        bus = EventBus()
        handler = Mock()
        bus.subscribe("test_event", handler)

        event = Event(event_type="test_event", data={"key": "value"})
        await bus.publish(event)

        handler.assert_called_once_with(event)
        assert event in bus.event_history

    @pytest.mark.asyncio
    async def test_publish_sync_handler(self):
        """Test publish with sync handler"""
        bus = EventBus()
        handler = Mock()
        bus.subscribe("test_event", handler)

        event = Event(event_type="test_event", data={})
        await bus.publish(event)

        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_async_handler(self):
        """Test publish with async handler"""
        bus = EventBus()

        async_handler_called = [False]

        async def async_handler(event):
            async_handler_called[0] = True

        bus.subscribe("test_event", async_handler)

        event = Event(event_type="test_event", data={})
        await bus.publish(event)

        assert async_handler_called[0] is True

    @pytest.mark.asyncio
    async def test_publish_handler_error(self):
        """Test publish handles handler errors"""
        bus = EventBus()

        def failing_handler(event):
            raise Exception("Handler error")

        bus.subscribe("test_event", failing_handler)

        event = Event(event_type="test_event", data={})
        # Should not raise
        await bus.publish(event)

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self):
        """Test publish with no subscribers"""
        bus = EventBus()

        event = Event(event_type="test_event", data={})
        # Should not raise
        await bus.publish(event)

        assert event in bus.event_history

    def test_publish_sync(self):
        """Test publish_sync"""
        bus = EventBus()
        handler = Mock()
        bus.subscribe("test_event", handler)

        event = Event(event_type="test_event", data={})
        bus.publish_sync(event)

        handler.assert_called_once()

    def test_get_event_history(self):
        """Test get_event_history"""
        bus = EventBus()
        event1 = Event(event_type="event1", data={})
        event2 = Event(event_type="event2", data={})
        bus.event_history.extend([event1, event2])

        history = bus.get_event_history()

        assert len(history) == 2

    def test_get_event_history_with_type(self):
        """Test get_event_history filtered by type"""
        bus = EventBus()
        event1 = Event(event_type="event1", data={})
        event2 = Event(event_type="event2", data={})
        event3 = Event(event_type="event1", data={})
        bus.event_history.extend([event1, event2, event3])

        history = bus.get_event_history(event_type="event1")

        assert len(history) == 2
        assert all(e.event_type == "event1" for e in history)

    def test_get_event_history_with_limit(self):
        """Test get_event_history with limit"""
        bus = EventBus()
        for i in range(10):
            bus.event_history.append(Event(event_type="test", data={"i": i}))

        history = bus.get_event_history(limit=5)

        assert len(history) == 5

    def test_clear_history(self):
        """Test clear_history"""
        bus = EventBus()
        bus.event_history.append(Event(event_type="test", data={}))

        bus.clear_history()

        assert bus.event_history == []


class TestAsyncEventBus:
    """Tests for AsyncEventBus"""

    def test_initialization(self):
        """Test AsyncEventBus initialization"""
        bus = AsyncEventBus()
        assert bus.max_history == 1000
        assert bus.semaphore is not None

    def test_initialization_custom_concurrency(self):
        """Test AsyncEventBus with custom concurrency"""
        bus = AsyncEventBus(max_concurrent_handlers=5)
        assert bus.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_publish_concurrent(self):
        """Test publish with concurrency control"""
        bus = AsyncEventBus(max_concurrent_handlers=2)

        call_count = [0]

        async def slow_handler(event):
            call_count[0] += 1
            await asyncio.sleep(0.1)

        for _ in range(5):
            bus.subscribe("test_event", slow_handler)

        event = Event(event_type="test_event", data={})
        await bus.publish(event)

        assert call_count[0] == 5


class TestEventHandlerDecorator:
    """Tests for event_handler decorator"""

    def test_event_handler_decorator(self):
        """Test event_handler decorator"""
        bus = EventBus()

        @event_handler("test_event", event_bus=bus)
        def handler(event):
            pass

        assert "test_event" in bus.subscribers
        assert handler in bus.subscribers["test_event"]

    def test_event_handler_global_bus(self):
        """Test event_handler with global bus"""
        @event_handler("test_event")
        def handler(event):
            pass

        global_bus = get_global_event_bus()
        assert "test_event" in global_bus.subscribers


class TestPublishEvent:
    """Tests for publish_event helper"""

    def test_publish_event(self):
        """Test publish_event helper"""
        bus = EventBus()
        handler = Mock()
        bus.subscribe("test_event", handler)

        publish_event("test_event", {"key": "value"}, event_bus=bus)

        handler.assert_called_once()
        assert handler.call_args[0][0].event_type == "test_event"


class TestGlobalEventBus:
    """Tests for global event bus"""

    def test_get_global_event_bus_singleton(self):
        """Test get_global_event_bus returns singleton"""
        bus1 = get_global_event_bus()
        bus2 = get_global_event_bus()

        assert bus1 is bus2

    def test_set_global_event_bus(self):
        """Test set_global_event_bus"""
        custom_bus = EventBus()
        set_global_event_bus(custom_bus)

        result = get_global_event_bus()

        assert result is custom_bus


class TestEventFilter:
    """Tests for EventFilter"""

    def test_initialization(self):
        """Test EventFilter initialization"""
        bus = EventBus()
        filter = EventFilter(bus)

        assert filter.event_bus == bus
        assert filter.filters == []

    def test_add_filter(self):
        """Test add_filter"""
        bus = EventBus()
        filter = EventFilter(bus)

        def filter_func(event):
            return True

        filter.add_filter(filter_func)

        assert filter_func in filter.filters

    def test_matches_no_filters(self):
        """Test matches with no filters"""
        bus = EventBus()
        filter = EventFilter(bus)
        event = Event(event_type="test", data={})

        assert filter.matches(event) is True

    def test_matches_with_filters(self):
        """Test matches with filters"""
        bus = EventBus()
        filter = EventFilter(bus)

        filter.add_filter(lambda e: e.event_type == "test")
        filter.add_filter(lambda e: "key" in e.data)

        event1 = Event(event_type="test", data={"key": "value"})
        event2 = Event(event_type="test", data={})
        event3 = Event(event_type="other", data={"key": "value"})

        assert filter.matches(event1) is True
        assert filter.matches(event2) is False
        assert filter.matches(event3) is False

    def test_get_filtered_events(self):
        """Test get_filtered_events"""
        bus = EventBus()
        filter = EventFilter(bus)

        filter.add_filter(lambda e: e.event_type == "test")

        event1 = Event(event_type="test", data={})
        event2 = Event(event_type="other", data={})
        event3 = Event(event_type="test", data={})
        bus.event_history.extend([event1, event2, event3])

        filtered = filter.get_filtered_events()

        assert len(filtered) == 2
        assert all(e.event_type == "test" for e in filtered)


class TestEventAggregator:
    """Tests for EventAggregator"""

    def test_initialization(self):
        """Test EventAggregator initialization"""
        agg = EventAggregator()

        assert agg.window_seconds == 60
        assert agg.aggregated_events == {}

    def test_add_event(self):
        """Test add_event"""
        agg = EventAggregator()
        event = Event(event_type="test", data={"value": 10})

        agg.add_event(event)

        assert "test" in agg.aggregated_events
        assert agg.aggregated_events["test"]["count"] == 1

    def test_add_event_merge_data(self):
        """Test add_event merges numeric data"""
        agg = EventAggregator()
        event1 = Event(event_type="test", data={"value": 10})
        event2 = Event(event_type="test", data={"value": 20})

        agg.add_event(event1)
        agg.add_event(event2)

        assert agg.aggregated_events["test"]["data"]["value"] == 30

    def test_get_aggregated_events(self):
        """Test get_aggregated_events"""
        agg = EventAggregator(window_seconds=1)
        event = Event(event_type="test", data={})

        agg.add_event(event)

        result = agg.get_aggregated_events()

        assert "test" in result

    def test_get_aggregated_events_expired(self):
        """Test get_aggregated_events removes expired events"""
        agg = EventAggregator(window_seconds=0)
        event = Event(event_type="test", data={})

        agg.add_event(event)

        # Wait for expiration
        import time
        time.sleep(0.1)

        result = agg.get_aggregated_events()

        assert "test" not in result

    def test_clear(self):
        """Test clear"""
        agg = EventAggregator()
        event = Event(event_type="test", data={})
        agg.add_event(event)

        agg.clear()

        assert agg.aggregated_events == {}


class TestEventRouter:
    """Tests for EventRouter"""

    def test_initialization(self):
        """Test EventRouter initialization"""
        router = EventRouter()

        assert router.routes == []

    def test_add_route(self):
        """Test add_route"""
        router = EventRouter()
        handler = Mock()

        router.add_route(lambda e: True, handler)

        assert len(router.routes) == 1

    @pytest.mark.asyncio
    async def test_route_matching(self):
        """Test route to matching handler"""
        router = EventRouter()
        handler = Mock()

        router.add_route(lambda e: e.event_type == "test", handler)

        event = Event(event_type="test", data={})
        result = await router.route(event)

        assert result is True
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_no_match(self):
        """Test route with no matching handler"""
        router = EventRouter()
        handler = Mock()

        router.add_route(lambda e: e.event_type == "other", handler)

        event = Event(event_type="test", data={})
        result = await router.route(event)

        assert result is False
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_async_handler(self):
        """Test route with async handler"""
        router = EventRouter()

        async_handler_called = [False]

        async def async_handler(event):
            async_handler_called[0] = True

        router.add_route(lambda e: True, async_handler)

        event = Event(event_type="test", data={})
        await router.route(event)

        assert async_handler_called[0] is True
