# aitbc.events

Event system for AITBC applications.

## Exports

- `Event`, `EventPriority` - Event dataclass and priority enum
- `EventBus`, `AsyncEventBus` - Event buses (sync and async)
- `EventFilter`, `EventAggregator`, `EventRouter`
- `event_handler`, `publish_event`
- `get_global_event_bus`, `set_global_event_bus`

## Usage

```python
from aitbc.events import EventBus, Event, publish_event
```
