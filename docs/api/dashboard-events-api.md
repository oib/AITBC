# API Reference: Dashboard Events Query (ABS-429)

Paginated, server-side-filtered read over the run-event log. Replaces client-side
tail filtering in the Mission Control dashboard (epic ABS-410, story ABS-429).

## Endpoint

```
GET /api/v1/projects/:project/events
```

**Authentication**: HttpOnly session cookie (same bearer guard as all `/api/v1`
routes). Requests without a valid session receive `401`.

---

## Query Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `ticket` | string | — | Exact match on `run_event.ticket` (e.g. `ABS-429`). |
| `seat` | string | — | Exact match on `run_event.role` (e.g. `be-developer`). |
| `kind` | string | — | Comma-separated list; matches `run_event.kind IN (...)`. |
| `run_id` | string | — | Exact match on `run_event.run_id`. |
| `before` | number | — | Keyset cursor: return events with `id < before`, newest-first. Omit to start from the live head. |
| `limit` | number | `50` | Page size. Clamped to `[1, 200]`. |

All filter params are optional and combinable. When multiple are present the
WHERE clause is their intersection (AND).

---

## Response

**200 OK**

```json
{
  "events": [
    {
      "seq":         "512",
      "run_id":      "run-abc123",
      "ticket":      "ABS-429",
      "seat":        "be-developer",
      "kind":        "handoff",
      "to_status":   "In Review",
      "note":        null,
      "source":      "orchestrator",
      "occurred_at": "2026-07-18T12:28:06Z"
    }
  ],
  "next_cursor": "450",
  "head":        "512"
}
```

| Field | Type | Description |
| --- | --- | --- |
| `events` | array | Page of events, newest-first (`id DESC`). |
| `events[].seq` | string (int) | Global sequence id (`run_event.id`). |
| `events[].run_id` | string | The orchestrator run that emitted this event. |
| `events[].ticket` | string or null | Ticket the event belongs to, if set. |
| `events[].seat` | string or null | Agent role/seat that emitted the event. |
| `events[].kind` | string | Event kind (e.g. `handoff`, `transition`, `gate-results`). |
| `events[].to_status` | string or null | Target status for `transition` events; `null` otherwise. |
| `events[].note` | string or null | Short human-readable note, if recorded. |
| `events[].source` | string | Actor or system that wrote the event. |
| `events[].occurred_at` | string (ISO 8601 UTC) | Wall-clock time the event was recorded. |
| `next_cursor` | string or null | `seq` of the oldest event on a full page — pass as `before` to fetch the next page. `null` when the page is partial (no more pages). |
| `head` | string or null | Project-level `MAX(id)` at query time — the live head for follow-mode resumption. `null` when the project has no events. |

---

## Pagination

The endpoint uses **keyset (cursor) pagination** on `id DESC`. This is
mathematically gap- and duplicate-free across page boundaries.

**Browse mode** — walk backwards through history:

```
GET /api/v1/projects/my-project/events?limit=50
  → { events: [...], next_cursor: "450", head: "512" }

GET /api/v1/projects/my-project/events?before=450&limit=50
  → { events: [...], next_cursor: "380", head: "512" }

GET /api/v1/projects/my-project/events?before=380&limit=50
  → { events: [...], next_cursor: null, head: "512" }   ← last page
```

**Follow mode** — detect new events via the `head` field:

```
# First request — store the returned head.
GET /api/v1/projects/my-project/events?limit=1
  → head = "512"

# Next poll — a higher head means new events arrived.
GET /api/v1/projects/my-project/events?limit=1
  → head = "520"   ← new events since seq 512
```

The `head` is the project-level `MAX(id)` returned on every request. A
follow-mode client stores the last seen `head`; when the next poll returns a
higher value, new events are available starting from `before=<last-head>`.

---

## Errors

| Status | Body | Meaning |
| --- | --- | --- |
| `400` | `{ "error": "bad_before", "before": "<value>" }` | `before` is not a non-negative finite integer. |
| `404` | `{ "error": "not_found" }` | Project slug not found or not accessible to the session. |
| `401` | — | No valid session cookie. |

---

## Examples

**Filter by ticket and kind:**

```bash
curl -b "session=<token>" \
  "https://example.com/api/v1/projects/boilerplate/events?ticket=ABS-429&kind=handoff,gate-results"
```

**Browse the last 10 events for a specific run:**

```bash
curl -b "session=<token>" \
  "https://example.com/api/v1/projects/boilerplate/events?run_id=run-abc123&limit=10"
```

**Fetch from TypeScript (dashboard client):**

```typescript
const resp = await fetch(
  `/api/v1/projects/${project}/events?ticket=${ticket}&limit=50`,
  { credentials: "include" },   // sends the HttpOnly session cookie
);
const { events, next_cursor, head } = await resp.json();
```

---

## Implementation Notes

- All filter conditions are typed-column equalities or `IN` lists
  (ADR-A-0026 — no comment-body or JSONB parsing).
- No new database tables or migrations; all referenced `run_event` columns
  exist from migration 005.
- No new auth surface; the route is session-gated via the same
  `projectId(request, reply)` guard used by all sibling dashboard routes.
- Advisory (non-blocking): no dedicated `(project_id, id DESC)` index or
  filter-column indexes beyond those from migration 005. Acceptable for
  current telemetry volume; flagged for the S9b successor (ABS-430).

**Successor:** ABS-430 (S9b) adds the EventFeed filter UI and Run Timeline on
top of this endpoint.
