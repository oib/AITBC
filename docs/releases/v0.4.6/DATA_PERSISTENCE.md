# Data Persistence - v0.4.6

**Release**: v0.4.6
**Date**: June 4, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.6 uses Redis for message and workflow persistence, and SQLModel for reputation data.

## Redis-Based Storage

- ✅ Redis-based message storage (no SQL migration needed)
- ✅ Redis-based workflow persistence
- ✅ Redis-based agent registry

## SQLModel Tables

### AgentReputation Table
- agent_id, trust_score, reputation_level, performance_rating

### CommunityFeedback Table
- agent_id, reviewer_id, ratings, feedback_text

### ReputationEvent Table
- agent_id, event_type, impact_score, trust_score_before/after

### TrustScoreCalculation Table
- agent_id, category, base_score, adjusted_score

## Features

- ✅ Redis-based message storage (no SQL migration needed)
- ✅ Redis-based workflow persistence
- ✅ Redis-based agent registry
- ✅ AgentReputation table (agent_id, trust_score, reputation_level, performance_rating)
- ✅ CommunityFeedback table (agent_id, reviewer_id, ratings, feedback_text)
- ✅ ReputationEvent table (agent_id, event_type, impact_score, trust_score_before/after)
- ✅ TrustScoreCalculation table (agent_id, category, base_score, adjusted_score)

---

*Last Updated: 2026-06-04*
