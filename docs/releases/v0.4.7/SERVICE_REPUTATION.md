# Service Reputation System - v0.4.7

**Release**: v0.4.7
**Date**: June 5, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.7 introduces a comprehensive service reputation system with cross-node rating synchronization, allowing customers to rate and review services with automatic synchronization across nodes.

## Features

### ServiceRating Model
- service_id, rating (1-5), reviewer_id, comment, created_at
- Automatic rating aggregation and average calculation
- Rating submission via API and CLI
- Rating retrieval with pagination support
- Rating display in marketplace listings

### Database Schema
```sql
CREATE TABLE service_ratings (
    rating_id UUID PRIMARY KEY,
    service_id VARCHAR(255) NOT NULL,
    rating FLOAT NOT NULL CHECK (rating >= 1.0 AND rating <= 5.0),
    reviewer_id VARCHAR(255),
    comment TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    synced_at TIMESTAMP WITH TIME ZONE,
    source_node VARCHAR(255)
);
```

### SoftwareService Model Extension
- avg_rating field (FLOAT)
- rating_count field (INTEGER)
- Automatic aggregation on rating submission

### CLI Commands

#### Rate Service
```bash
aitbc market rate --service-id <plugin_id or offer_id> --rating 4.5 --comment "Great service"
```

#### View Ratings
```bash
aitbc market ratings --service-id <plugin_id or offer_id> --limit 50 --offset 0
```

#### Sync Ratings
```bash
aitbc market sync-ratings --remote-url https://aitbc3.aitbc.bubuit.net/api --limit 100
```

## Results

- ✅ ServiceRating model with service_id, rating (1-5), reviewer_id, comment, created_at
- ✅ SoftwareService model extended with avg_rating and rating_count fields
- ✅ Automatic rating aggregation and average calculation
- ✅ Rating submission via API and CLI
- ✅ Rating retrieval with pagination support
- ✅ Rating display in marketplace listings
- ✅ Database schema with sync metadata (synced_at, source_node)

---

*Last Updated: 2026-06-05*
