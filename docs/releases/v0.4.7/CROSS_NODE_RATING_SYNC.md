# Cross-Node Rating Synchronization - v0.4.7

**Release**: v0.4.7
**Date**: June 5, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.7 adds cross-node rating synchronization, enabling automatic propagation of service ratings across AITBC nodes with conflict resolution.

## Features

### Sync Metadata Fields
- synced_at - Timestamp when rating was last synchronized
- source_node - Node where rating originated

### API Endpoints

#### Fetch Unsynced Ratings
```bash
GET /v1/marketplace/ratings/unsynced
```
Returns ratings that haven't been synced to other nodes.

#### Sync Ratings from Remote
```bash
POST /v1/marketplace/ratings/sync
```
Sync ratings from remote node with conflict resolution.

#### Mark Ratings as Synced
```bash
POST /v1/marketplace/ratings/mark-synced
```
Mark ratings as successfully synced.

### CLI Command
```bash
aitbc market sync-ratings --remote-url https://aitbc3.aitbc.bubuit.net/api --limit 100
```

### Conflict Resolution
- Keep most recent rating based on timestamp
- Sync tracking and audit trail
- Automatic conflict detection and resolution

## Results

- ✅ Sync metadata fields: synced_at, source_node
- ✅ GET `/v1/marketplace/ratings/unsynced` - Fetch unsynced ratings
- ✅ POST `/v1/marketplace/ratings/sync` - Sync ratings from remote with conflict resolution
- ✅ POST `/v1/marketplace/ratings/mark-synced` - Mark ratings as synced
- ✅ CLI command: `aitbc market sync-ratings [--remote-url] [--limit]`
- ✅ Conflict resolution: keep most recent rating based on timestamp
- ✅ Sync tracking and audit trail
- ✅ End-to-end tested: hub → aitbc3 rating propagation

---

*Last Updated: 2026-06-05*
