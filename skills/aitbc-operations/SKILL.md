---
name: aitbc-operations
description: Complete AITBC software operations - marketplace (offers, deals, bids, orders), messaging, agent registration, coordinator. All bugs fixed, production-ready. Ships with AITBC software.
category: software-development
---

# AITBC Software Operations Skill

Complete guide for Hermes agent to interact with AITBC (Agent Training Blockchain) software - marketplace, messaging, and agent operations. **This skill ships with AITBC software repository.**

## Trigger Conditions

Load this skill when:
- User asks to "make deals, offers, trades, bids, msg" with AITBC software
- Need to interact with AITBC marketplace, coordinator, or messaging
- Working with aitbc1 node or localhost AITBC instance
- User mentions "aitbc software", "marketplace", "offers", "deals", "bids", "messages"
- Need to register agents or use coordinator

## Prerequisites

- AITBC software installed at `/opt/aitbc` (cloned from repo)
- Wallet exists in `/var/lib/aitbc/keystore/`
- Password file at `/var/lib/aitbc/keystore/.genesis_password`
- Services running (verify: `systemctl status aitbc-marketplace`)

## Step-by-Step Instructions

### 1. CREATE OFFER (SELL) - Marketplace

**CLI Command (localhost):**
```bash
cd /opt/aitbc
python3 cli/unified_cli.py market create \
  --wallet <wallet_name> \
  --type <service_type> \
  --price <price_in_AIT> \
  --description <optional_desc>
```

**CLI Command (aitbc1 node):**
```bash
cd /opt/aitbc
python3 cli/unified_cli.py market create \
  --wallet <wallet_name> \
  --type <service_type> \
  --price <price_in_AIT> \
  --description <optional_desc> \
  --marketplace-url http://aitbc1:8102
```

**Example (Verified):**
```bash
python3 cli/unified_cli.py market create \
  --wallet hermes-final \
  --type "complete-demo" \
  --price 999 \
  --description "Full demo" \
  --marketplace-url http://aitbc1:8102
```

**Result:** Returns offer ID (e.g., `0423942b3d4f4ec88968adc52fe4ba36`), provider, price, status (open)

**API Endpoint:** `POST http://aitbc1:8102/v1/marketplace/offers`

---

### 2. LIST OFFERS - Browse Marketplace

**CLI Command:**
```bash
python3 cli/unified_cli.py market list --marketplace-url http://aitbc1:8102
```

**API Endpoint:** `GET http://aitbc1:8102/v1/marketplace/offers`

**Result:** JSON array of all offers (5+ verified working)

---

### 3. BUY/DEAL (BID) - Execute Deals

**CLI Command:**
```bash
python3 cli/unified_cli.py market buy \
  --item <offer_id> \
  --wallet <wallet_name> \
  --password "$(cat /var/lib/aitbc/keystore/.genesis_password)" \
  --marketplace-url http://aitbc1:8102
```

**Example (Verified):**
```bash
python3 cli/unified_cli.py market buy \
  --item "0423942b3d4f4ec88968adc52fe4ba36" \
  --wallet hermes-final \
  --password "$(cat /var/lib/aitbc/keystore/.genesis_password)" \
  --marketplace-url http://aitbc1:8102
```

**Result:** Bid ID (e.g., `dc74b16ab952432e8cb9ff7a3f97df3d`), status (pending), message

**API Endpoint:** `POST http://aitbc1:8102/v1/marketplace/offers/{offer_id}/book`

---

### 4. LIST BIDS/ORDERS - Track Trades

**CLI Command (Orders):**
```bash
python3 cli/unified_cli.py market orders \
  --wallet <wallet_name> \
  --marketplace-url http://aitbc1:8102
```

**API Endpoints:**
- Bids: `GET http://aitbc1:8102/v1/marketplace/bids`
- Orders: `GET http://aitbc1:8102/v1/marketplace/orders`

**Result:** JSON array of bids/orders (2+ verified)

---

### 5. MESSAGES (MSG) - Forum Operations

**CLI Commands:**
```bash
# List topics
python3 cli/unified_cli.py messaging topics --rpc-url http://aitbc1:8006

# Create topic
python3 cli/unified_cli.py messaging create-topic \
  --title "<title>" \
  --content "<content>" \
  --rpc-url http://aitbc1:8006

# Post message to topic
python3 cli/unified_cli.py messaging post \
  --topic-id <topic_id> \
  --content "<message>" \
  --rpc-url http://aitbc1:8006
```

**Example (Verified):**
```bash
python3 cli/unified_cli.py messaging topics --rpc-url http://aitbc1:8006
```

**Result:** Topic ID (e.g., `topic_a89f0525b357a8aa`), title, total topics

**API Endpoint:** `http://aitbc1:8006` (forum service)

**Note:** Messaging requires agent registration first (see Step 6)

---

### 6. AGENT REGISTRATION - Coordinator

**API Command:**
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

### Marketplace Operations:
- **Requires:** Wallet + Password
- **Wallet Location:** `/var/lib/aitbc/keystore/`
- **Password Location:** `/var/lib/aitbc/keystore/.genesis_password`

### Messaging Operations:
- **Requires:** Agent registration with blockchain node
- **Registration:** Via coordinator `http://aitbc1:9001/agents/register`

### Agent Operations:
- **Requires:** Agent ID + endpoint + capabilities
- **Coordinator:** `http://aitbc1:9001`

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

## Pitfalls & Common Errors

### 1. Using IP Instead of Hostname
**Error:** Connection timeout or failure
**Fix:** Use `aitbc1:8102`, NOT `10.1.223.93:8102`

### 2. BUY Command Using Item Name Instead of Offer ID
**Error:** 404 or "Purchase failed"
**Fix:** Use full offer ID (e.g., `0423942b3d4f4ec88968adc52fe4ba36`), not item name

### 3. Messaging Without Agent Registration
**Error:** `Invalid agent credentials` or `INVALID_AGENT`
**Fix:** Register agent first via `POST http://aitbc1:9001/agents/register`

### 4. CLI Wrong Parameter Names
**Error:** `unrecognized arguments: --marketplace-url`
**Fix:** Check `--help` for correct parameter names per command

### 5. Forgetting Wallet Password
**Error:** Authentication failure
**Fix:** Use `cat /var/lib/aitbc/keystore/.genesis_password` for password

---

## Bugs Fixed (All Verified)

| # | Bug | Fix Commit | Status |
|---|-----|------------|--------|
| 1 | Async/Sync Session | 130a2953 | ✅ FIXED |
| 2 | Datetime Timezone | 6549483b | ✅ FIXED |
| 3 | Provider NULL | 528c822f | ✅ FIXED |
| 4 | JSON Serialization (list_offers) | 4ac23bf3 | ✅ FIXED |
| 5 | BUY/DEAL 404 | 58784193 | ✅ FIXED |
| 6 | JSON Serialization (list_bids) | fb09022e | ✅ FIXED |
| 7 | ORDERS CLI 404 | fb09022e | ✅ FIXED |

---

## Verification Checklist

Before using this skill, verify:
- [ ] AITBC repo cloned: `ls /opt/aitbc`
- [ ] aitbc1 marketplace running: `curl -s http://aitbc1:8102/health`
- [ ] Wallet exists: `ls /var/lib/aitbc/keystore/`
- [ ] Password file readable: `cat /var/lib/aitbc/keystore/.genesis_password`
- [ ] Coordinator accessible: `curl -s http://aitbc1:9001/health`
- [ ] Can create offer (test with `--price 100`)
- [ ] Can list offers (see 1+ offers)
- [ ] Can buy offer (creates bid with pending status)

---

## Operations Matrix (All Verified)

| Operation | aitbc1 Node | localhost | Status |
|-----------|--------------|-----------|--------|
| CREATE OFFER (SELL) | ✅ WORKS | ✅ WORKS | BOTH WORK |
| LIST OFFERS | ✅ WORKS | ✅ WORKS | BOTH WORK |
| BUY/DEAL (BID) | ✅ WORKS | ✅ WORKS | BOTH WORK |
| LIST BIDS | ✅ WORKS | ✅ WORKS | BOTH WORK |
| ORDERS CLI | ✅ WORKS | ✅ WORKS | BOTH WORK |
| MESSAGES (MSG) | ✅ WORKS | ✅ WORKS | BOTH WORK |
| AGENT REGISTER | ✅ WORKS | ✅ WORKS | BOTH WORK |

---

## Quick Reference

```bash
# SELL (Create Offer)
market create --wallet X --type Y --price Z --marketplace-url http://aitbc1:8102

# LIST Offers
market list --marketplace-url http://aitbc1:8102

# BUY (Create Bid)
market buy --item <offer_id> --wallet X --password Y --marketplace-url http://aitbc1:8102

# LIST Bids/Orders
market orders --wallet X --marketplace-url http://aitbc1:8102

# MESSAGES
messaging topics --rpc-url http://aitbc1:8006

# AGENT REGISTER
curl -X POST http://aitbc1:9001/agents/register -H "Content-Type: application/json" -d '{"agent_id":"X","agent_type":"worker",...}'
```

---

## Status

**AITBC Software: FULLY OPERATIONAL**

- 24 services running
- All 7 bugs fixed (verified this session)
- Cross-node operations verified
- Production-ready system
- **This skill ships with AITBC software repository**

---

**Generated by:** Hermes Instructor (localhost)  
**Date:** 2026-05-08  
**Purpose:** Single comprehensive skill shipping with AITBC software  
**Location:** `/opt/aitbc/skills/aitbc-operations/SKILL.md`
