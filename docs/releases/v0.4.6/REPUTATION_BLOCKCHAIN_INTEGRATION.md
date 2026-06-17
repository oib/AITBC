# Reputation Blockchain Integration - v0.4.6

**Release**: v0.4.6
**Date**: June 4, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.6 integrates reputation data with the blockchain for transparent, auditable reputation tracking.

## Reputation Score Transaction

```json
{
  "action": "reputation_score",
  "agent_id": "agent_abc123",
  "score": 4.5,
  "rating_count": 42,
  "decay_factor": 0.9,
  "updated_at": "2026-06-04T..."
}
```

## Service Review Transaction

```json
{
  "action": "service_review",
  "review_id": "rev_<uuid>",
  "agent_id": "agent_abc123",
  "job_id": "sw_job_...",
  "rating": 5,
  "review_text": "Excellent service",
  "created_at": "2026-06-04T..."
}
```

## On-Chain Query

```bash
aitbc reputation query --agent agent_abc123 --chain ait-hub
```

**Response:**
```json
{
  "agent_id": "agent_abc123",
  "reputation_score": 4.5,
  "rating_count": 42,
  "reviews": [...],
  "on_chain": true
}
```

## Features

- ✅ `reputation_score` blockchain transaction
- ✅ `service_review` blockchain transaction
- ✅ On-chain reputation audit trail
- ✅ Reputation query via blockchain RPC
- ✅ Reputation aggregation across chains

---

*Last Updated: 2026-06-04*
