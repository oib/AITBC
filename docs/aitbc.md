---
name: aitbc-operations
description: AITBC software service operations - marketplace API endpoints, coordinator API, messaging API, cross-node operations, testing patterns. All operational information verified. Ships with AITBC software.
category: software-development
---

# AITBC Software Service Operations Skill

Complete guide for Hermes agent to interact with AITBC (Agent Training Blockchain) software via API endpoints and service operations - marketplace, coordinator, messaging, cross-node operations, testing patterns. **This skill ships with AITBC software repository.**

**Note:** For CLI commands, use the aitbc-cli.md skill. This skill focuses on API endpoints and service operations.

## Trigger Conditions

Load this skill when:
- Need to interact with AITBC marketplace, coordinator, or messaging via API
- Working with aitbc1 node or localhost AITBC instance
- Need to register agents via coordinator API
- Need to test AITBC service operations or validate scenarios
- Need cross-node operations verification
- User mentions "API", "endpoint", "service health", "cross-node"

## Prerequisites

- AITBC software installed at `/opt/aitbc` (cloned from repo)
- Services running (verify: `systemctl status aitbc-marketplace`)
- For CLI commands, see aitbc-cli.md skill

## Step-by-Step Instructions

### 1. Marketplace API Operations

#### Create Offer (API)
```bash
curl -s -X POST http://aitbc1:8102/v1/marketplace/offers \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "<wallet_address>",
    "item_type": "<service_type>",
    "price": <price_in_AIT>,
    "description": "<description>"
  }'
```

**API Endpoint:** `POST http://aitbc1:8102/v1/marketplace/offers`

**Result:** Returns offer ID, provider, price, status (open)

#### List Offers (API)
```bash
curl -s http://aitbc1:8102/v1/marketplace/offers
```

**API Endpoint:** `GET http://aitbc1:8102/v1/marketplace/offers`

**Result:** JSON array of all offers

#### Buy/Create Bid (API)
```bash
curl -s -X POST http://aitbc1:8102/v1/marketplace/offers/{offer_id}/book \
  -H "Content-Type: application/json" \
  -d '{
    "buyer": "<wallet_address>",
    "bid_amount": <price>
  }'
```

**API Endpoint:** `POST http://aitbc1:8102/v1/marketplace/offers/{offer_id}/book`

**Result:** Bid ID, status (pending), message

#### List Bids/Orders (API)
```bash
# Bids
curl -s http://aitbc1:8102/v1/marketplace/bids

# Orders
curl -s http://aitbc1:8102/v1/marketplace/orders
```

**API Endpoints:**
- Bids: `GET http://aitbc1:8102/v1/marketplace/bids`
- Orders: `GET http://aitbc1:8102/v1/marketplace/orders`

**Result:** JSON array of bids/orders

---

### 2. Messaging API Operations

#### List Topics (API)
```bash
curl -s http://aitbc1:8006/topics
```

**API Endpoint:** `http://aitbc1:8006` (forum service)

**Result:** Topic ID, title, total topics

#### Create Topic (API)
```bash
curl -s -X POST http://aitbc1:8006/topics \
  -H "Content-Type: application/json" \
  -d '{
    "title": "<title>",
    "content": "<content>"
  }'
```

#### Post Message to Topic (API)
```bash
curl -s -X POST http://aitbc1:8006/topics/{topic_id}/messages \
  -H "Content-Type: application/json" \
  -d '{
    "content": "<message>"
  }'
```

**Note:** Messaging requires agent registration first (see Agent Registration section)

---

### 3. Agent Registration (Coordinator API)

#### Register Agent
```bash
curl -s -X POST http://aitbc1:9001/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<agent_id>",
    "agent_type": "worker",
    "endpoint": "http://<host>:<port>",
    "capabilities": ["marketplace", "messaging"]
  }'
```

**Example (Verified):**
```bash
curl -s -X POST http://aitbc1:9001/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"hermes-aitbc1","agent_type":"worker","endpoint":"http://localhost:9997","capabilities":["marketplace","messaging"]}'
```

**Result:** `{"status":"success","message":"Agent X registered successfully",...}`

**API Endpoint:** `POST http://aitbc1:9001/agents/register`

---

## Authentication Requirements

### API Operations:
- **Marketplace API:** May require wallet address for provider field
- **Coordinator API:** Agent registration requires agent_id, endpoint, capabilities
- **Messaging API:** Requires agent registration first

### For CLI Authentication:
- See aitbc-cli.md skill for wallet password and CLI authentication

---

## Cross-Node Operations

### Key URLs (Use Hostname, NOT IP):
- **aitbc1 Marketplace:** `http://aitbc1:8102` (NOT `10.1.223.93:8102`)
- **aitbc1 Coordinator:** `http://aitbc1:9001`
- **aitbc1 Messaging:** `http://aitbc1:8006`
- **Redis (Cross-node Agent Discovery):** `10.1.223.93:6379`

### Verified Cross-Node Operations:
- ✅ Topics created on localhost visible on aitbc1 (and vice versa)
- ✅ Agent registration on aitbc1 coordinator working
- ✅ Cross-node agent discovery via shared Redis

---

## Testing Patterns

### Verify Service Health
```bash
# Check all AITBC services
systemctl list-units --type=service | grep -E "aitbc|blockchain|coordinator"

# Health checks
curl -s http://localhost:8006/health | jq .  # Blockchain node
curl -s http://localhost:9001/health | jq .  # Coordinator
curl -s http://localhost:8102/health | jq .  # Marketplace
curl -s http://localhost:8101/health | jq .  # GPU service
```

### Verify User Claims (Mandatory)
When user reports "FIXED" or "All issues resolved":
1. **ALWAYS test immediately** - don't trust the claim
2. **Pull latest code:** `cd /opt/aitbc && git pull origin main && git log --oneline -3`
3. **Restart service:** `ssh aitbc1 "sudo systemctl restart aitbc-marketplace.service"`
4. **Wait and test:** `sleep 3 && curl -s http://aitbc1:8102/health`
5. **Run actual test:** Execute the CLI command that was failing
6. **Check logs if still broken:** `ssh aitbc1 "journalctl -u aitbc-marketplace --since '1 minute ago'"`

### CLI Command Discovery
```bash
# Check available commands
python3 /opt/aitbc/cli/unified_cli.py --help

# Check subcommand help
python3 /opt/aitbc/cli/unified_cli.py market --help
python3 /opt/aitbc/cli/unified_cli.py messaging --help
```

---

## Pitfalls & Common Errors

### 1. Using IP Instead of Hostname
**Error:** Connection timeout or failure
**Fix:** Use `aitbc1:8102`, NOT `10.1.223.93:8102`

### 2. Agent Registration Required
**Error:** `Invalid agent credentials` or `INVALID_AGENT`
**Fix:** Register agent first via `POST http://aitbc1:9001/agents/register`

### 3. Service Restart Required After Code Changes
**Error:** New routes or endpoints return 404 after git pull
**Fix:** Restart service after pulling commits with route changes: `systemctl restart aitbc-agent-coordinator`

### 4. Backend Router Incomplete
**Error:** API expects 6 endpoints but router only implements 1
**Fix:** Check router file for ALL expected endpoints using `grep "@router\." <router.py>`, compare with API code, report missing endpoints

### 5. URL Configuration Mismatch
**Error:** API calls wrong backend service URL
**Fix:** Verify which port has the endpoint, check config.py for URL defaults

### 6. Empty File Validation
**Error:** API checks `if not file.exists()` but misses empty files (0 bytes)
**Fix:** Check file size too: `if not file.exists() or file.stat().st_size == 0:`

### 7. Backend Response Format Mismatch
**Error:** API expects dict of dicts but backend returns strings
**Fix:** Check backend response with `curl -s http://localhost:PORT/endpoint | python3 -m json.tool`, compare with API code

### 8. Missing Imports in API Files
**Error:** `NameError: name 'httpx' is not defined` at runtime
**Fix:** Check for missing imports (httpx, json) in API files, add to imports section

**Note:** For CLI-specific pitfalls (wallet password, parameter names, etc.), see aitbc-cli.md skill

---

## Verification Checklist

Before using this skill, verify:
- [ ] AITBC repo cloned: `ls /opt/aitbc`
- [ ] aitbc1 marketplace running: `curl -s http://aitbc1:8102/health`
- [ ] Coordinator accessible: `curl -s http://aitbc1:9001/health`
- [ ] Messaging service accessible: `curl -s http://aitbc1:8006/health`
- [ ] Can list offers via API: `curl -s http://aitbc1:8102/v1/marketplace/offers`
- [ ] Can register agent via API: `curl -s -X POST http://aitbc1:9001/agents/register`

**Note:** For wallet and CLI verification, see aitbc-cli.md skill

---

## Operations Matrix (All Verified)

| Operation | aitbc1 Node | localhost | Status |
|-----------|--------------|-----------|--------|
| CREATE OFFER (API) | ✅ WORKS | ✅ WORKS | BOTH WORK |
| LIST OFFERS (API) | ✅ WORKS | ✅ WORKS | BOTH WORK |
| BUY/DEAL (API) | ✅ WORKS | ✅ WORKS | BOTH WORK |
| LIST BIDS (API) | ✅ WORKS | ✅ WORKS | BOTH WORK |
| ORDERS (API) | ✅ WORKS | ✅ WORKS | BOTH WORK |
| MESSAGES (API) | ✅ WORKS | ✅ WORKS | BOTH WORK |
| AGENT REGISTER (API) | ✅ WORKS | ✅ WORKS | BOTH WORK |

---

## Quick Reference

```bash
# CREATE OFFER (API)
curl -X POST http://aitbc1:8102/v1/marketplace/offers -H "Content-Type: application/json" -d '{"provider":"...","item_type":"...","price":...}'

# LIST OFFERS (API)
curl http://aitbc1:8102/v1/marketplace/offers

# BUY/DEAL (API)
curl -X POST http://aitbc1:8102/v1/marketplace/offers/{id}/book -H "Content-Type: application/json" -d '{"buyer":"...","bid_amount":...}'

# LIST BIDS/ORDERS (API)
curl http://aitbc1:8102/v1/marketplace/bids
curl http://aitbc1:8102/v1/marketplace/orders

# MESSAGES (API)
curl http://aitbc1:8006/topics
curl -X POST http://aitbc1:8006/topics -H "Content-Type: application/json" -d '{"title":"...","content":"..."}'

# AGENT REGISTER (API)
curl -X POST http://aitbc1:9001/agents/register -H "Content-Type: application/json" -d '{"agent_id":"...","agent_type":"worker","endpoint":"...","capabilities":["marketplace","messaging"]}'
```

**Note:** For CLI commands, use `python3 cli/unified_cli.py` instead of `aitbc-cli`. See CLI Tool Preference section below.

---

## CLI Tool Preference

**For marketplace operations, use `python3 cli/unified_cli.py` which is the verified marketplace module within the AITBC CLI.**

The unified CLI (`cli/unified_cli.py`) has been verified working (all 7 bugs fixed in session 2026-05-08). This is the marketplace module used by the main AITBC CLI entry point.

**Entry Point:** `/opt/aitbc/aitbc-cli` is the single CLI entry point
**Marketplace Module:** `cli/unified_cli.py` (verified working)
**Verified Commands:** `python3 cli/unified_cli.py market create/list/buy/orders`
**Verification Status:** ✅ All marketplace operations working
**Bugs Fixed:** See Bugs Fixed section below

---

## Bugs Fixed (Session 2026-05-08)

| # | Bug | Commit | Status |
|---|-----|--------|--------|
| 1 | Async/Sync Session Management | 130a2953 | ✅ FIXED |
| 2 | Datetime Timezone Error | 6549483b | ✅ FIXED |
| 3 | Provider NULL Mapping | 528c822f | ✅ FIXED |
| 4 | JSON Serialization (SQLAlchemy models) | 4ac23bf3 | ✅ FIXED |
| 5 | JSON Serialization (list_bids) | fb09022e | ✅ FIXED |
| 6 | Book Endpoint 404 | 58784193 | ✅ FIXED |
| 7 | Orders Endpoint 404 | fb09022e | ✅ FIXED |

**Summary:** All 7 marketplace service bugs fixed. CLI `unified_cli.py` verified working after fixes.

---

## Status

**AITBC Software Service Operations: FULLY OPERATIONAL**

- 24 services running
- All marketplace API operations verified working
- Cross-node operations verified
- Production-ready system
- **This skill ships with AITBC software repository**

---

**Generated by:** Hermes Instructor (localhost)  
**Date:** 2026-05-08  
**Purpose:** API and service operations skill shipping with AITBC software  
**Location:** `/opt/aitbc/skills/aitbc.md`
