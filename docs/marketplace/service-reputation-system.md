# Service Reputation System

## Overview

The AITBC Service Reputation System enables customers to rate and review software services offered through the marketplace. Ratings are automatically aggregated to calculate average scores and counts, and can be synchronized across multiple nodes to ensure consistency across the distributed network.

## Features

- **Rating Submission**: Customers can rate services on a 1-5 scale with optional comments
- **Automatic Aggregation**: Average ratings and counts are calculated automatically
- **Cross-Node Sync**: Ratings propagate between hub and aitbc3 nodes
- **Conflict Resolution**: Most recent rating wins when conflicts occur
- **Audit Trail**: Sync metadata tracks rating origin and sync status
- **CLI Integration**: Rating commands available via `aitbc market rate` and `aitbc market ratings`
- **API Integration**: RESTful endpoints for rating management

## Architecture

### Database Schema

#### ServiceRating Model
```python
class ServiceRating(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    service_id: str  # References SoftwareService.plugin_id
    rating: float  # 1.0 to 5.0
    reviewer_id: str  # Wallet address or user ID
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    synced_at: Optional[datetime] = None  # Timestamp when synced to remote
    source_node: str = "local"  # Origin node identifier
```

#### SoftwareService Model (Extended)
```python
class SoftwareService(SQLModel, table=True):
    # ... existing fields ...
    avg_rating: float = Field(default=0.0)
    rating_count: int = Field(default=0)
```

### API Endpoints

#### POST `/v1/marketplace/offer/{service_id}/rate`
Submit a rating for a service.

**Request:**
```json
{
  "rating": 4.5,
  "reviewer_id": "ait1abc123...",
  "comment": "Great service!"
}
```

**Response:**
```json
{
  "status": "success",
  "rating": {
    "id": "rating-uuid",
    "service_id": "ollama-llama3.2:3b",
    "rating": 4.5,
    "reviewer_id": "ait1abc123...",
    "comment": "Great service!",
    "created_at": "2026-06-05T10:40:43.469518",
    "source_node": "local"
  }
}
```

#### GET `/v1/marketplace/offer/{service_id}/ratings`
Retrieve ratings for a service.

**Query Parameters:**
- `limit`: Number of ratings to return (default: 50)
- `offset`: Pagination offset (default: 0)

**Response:**
```json
{
  "service_id": "ollama-llama3.2:3b",
  "service_info": {
    "avg_rating": 4.2,
    "rating_count": 5
  },
  "ratings": [
    {
      "id": "rating-uuid",
      "service_id": "ollama-llama3.2:3b",
      "rating": 4.5,
      "reviewer_id": "ait1abc123...",
      "comment": "Great service!",
      "created_at": "2026-06-05T10:40:43.469518",
      "source_node": "local"
    }
  ],
  "count": 5,
  "limit": 50,
  "offset": 0
}
```

#### GET `/v1/marketplace/ratings/unsynced`
Fetch ratings that haven't been synced to remote nodes.

**Query Parameters:**
- `limit`: Number of ratings to return (default: 100)

**Response:**
```json
{
  "ratings": [
    {
      "id": "rating-uuid",
      "service_id": "ollama-llama3.2:3b",
      "rating": 4.5,
      "reviewer_id": "ait1abc123...",
      "comment": "Great service!",
      "created_at": "2026-06-05T10:40:43.469518",
      "source_node": "local"
    }
  ],
  "count": 3
}
```

#### POST `/v1/marketplace/ratings/sync`
Sync ratings from a remote node with conflict resolution.

**Request:**
```json
[
  {
    "id": "rating-uuid",
    "service_id": "ollama-llama3.2:3b",
    "rating": 4.5,
    "reviewer_id": "ait1abc123...",
    "comment": "Great service!",
    "created_at": "2026-06-05T10:40:43.469518",
    "source_node": "hub"
  }
]
```

**Response:**
```json
{
  "status": "success",
  "synced": 1,
  "updated": 0,
  "skipped": 0
}
```

#### POST `/v1/marketplace/ratings/mark-synced`
Mark ratings as synced after successful propagation.

**Request:**
```json
["rating-uuid-1", "rating-uuid-2"]
```

**Response:**
```json
{
  "status": "success",
  "marked_synced": 2
}
```

## CLI Commands

### Submit a Rating
```bash
aitbc market rate <service_id> <rating> [--comment <text>] [--reviewer-id <id>]
```

**Example:**
```bash
aitbc market rate ollama-llama3.2:3b 4.5 --comment "Great service!"
```

### View Ratings
```bash
aitbc market ratings <service_id> [--limit <n>] [--offset <n>]
```

**Example:**
```bash
aitbc market ratings ollama-llama3.2:3b --limit 10
```

### Sync Ratings
```bash
aitbc market sync-ratings [--remote-url <url>] [--limit <n>]
```

**Example:**
```bash
aitbc market sync-ratings --remote-url https://aitbc3.aitbc.bubuit.net/api --limit 100
```

## Cross-Node Synchronization

### Architecture

The reputation system supports cross-node rating synchronization between the hub's local marketplace and the aitbc3 software service registry.

**Sync Flow:**
1. Rating created on hub with `source_node="local"` and `synced_at=NULL`
2. CLI command fetches unsynced ratings via `/v1/marketplace/ratings/unsynced`
3. Ratings pushed to remote via `/v1/marketplace/ratings/sync`
4. Remote applies conflict resolution (most recent `created_at` wins)
5. Hub marks ratings as synced via `/v1/marketplace/ratings/mark-synced`
6. Service averages recalculated on both nodes

### Conflict Resolution

When the same rating (same service_id + reviewer_id) exists on both nodes:
- Compare `created_at` timestamps
- Keep the most recent rating
- Update `synced_at` to current timestamp
- Update `source_node` to reflect origin

### Sync Tracking

- `synced_at`: Timestamp when rating was last synced to remote
- `source_node`: Origin node identifier ("local", "hub", "aitbc3", etc.)
- Ratings with `synced_at=NULL` are considered unsynced

## Rating Aggregation

Average ratings are calculated automatically when ratings are submitted or updated:

```python
def _update_service_rating(session: Session, service_id: str):
    ratings = session.exec(
        select(ServiceRating).where(ServiceRating.service_id == service_id)
    ).all()

    if ratings:
        avg = sum(r.rating for r in ratings) / len(ratings)
        count = len(ratings)
    else:
        avg = 0.0
        count = 0

    service = session.exec(
        select(SoftwareService).where(SoftwareService.plugin_id == service_id)
    ).first()

    if service:
        service.avg_rating = avg
        service.rating_count = count
        session.add(service)
        session.commit()
```

## Marketplace Integration

Ratings are displayed in the marketplace listings:

```bash
aitbc market list
```

**Output:**
```
Offer ID    Type    Model              GPU                 Price         Rating       Status
sw_offer_   OLLAMA  llama3.2:3b        RTX 4090 [GPU 0]    0.05 AIT/h     ⭐ 4.2 (5)   active
```

## Security Considerations

- **Reviewer Validation**: Reviewer ID defaults to wallet address for accountability
- **Rating Scale**: Ratings are validated to be between 1.0 and 5.0
- **Comment Sanitization**: Comments should be sanitized to prevent XSS
- **Rate Limiting**: Consider adding rate limiting to prevent spam ratings
- **Sync Authentication**: Sync endpoints should require authentication in production

## Troubleshooting

### Ratings Not Syncing
1. Check remote URL is accessible: `curl https://aitbc3.aitbc.bubuit.net/api/health`
2. Verify ratings are unsynced: `curl http://localhost:8102/v1/marketplace/ratings/unsynced`
3. Check sync logs: `journalctl -u aitbc-marketplace -f`

### Average Rating Not Updating
1. Verify rating was submitted successfully
2. Check database for rating record
3. Restart marketplace service: `systemctl restart aitbc-marketplace`

### Conflict Resolution Issues
1. Check `created_at` timestamps on conflicting ratings
2. Ensure timezone consistency across nodes
3. Manually resolve conflicts via direct database access if needed

## Future Enhancements

- **Automatic Periodic Sync**: Systemd timer for automatic sync every N minutes
- **Pull Sync**: CLI command to pull ratings from remote (currently only push)
- **Rating History**: Track rating changes over time
- **Reviewer Reputation**: Weight ratings based on reviewer history
- **Flagging System**: Allow users to flag inappropriate reviews
- **Response System**: Allow service providers to respond to reviews
- **Analytics Dashboard**: Rating trends and insights
