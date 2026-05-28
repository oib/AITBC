---
name: aitbc-marketplace
description: Marketplace operations including listing creation, price optimization, market analysis, trading operations, GPU provider registration, and marketplace status checks
category: marketplace
---

# AITBC Marketplace Skill

**Status:** 🟡 **Procedure Validated** - Procedures accurate if dependencies and services are present

## Trigger Conditions
Activate when user requests marketplace operations: listing creation, price optimization, market analysis, trading operations, GPU provider registration, or marketplace status checks.

## Purpose
Create, manage, and optimize AITBC marketplace listings with pricing strategies and competitive analysis.

## Prerequisites
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- Wallet with sufficient balance for listing fees
- Marketplace service operational on port 8102
- GPU provider marketplace operational for resource allocation (if using GPU features)

## Prerequisites Check
Before proceeding, verify:
```bash
# Check service status
systemctl list-units --state=running | grep aitbc

# Check Python dependencies
source /opt/aitbc/venv/bin/activate && pip list | grep -E "fastapi|click|uvicorn"

# Verify CLI accessible
/opt/aitbc/aitbc-cli --version

# Check marketplace health
curl -s http://localhost:8102/health

# Check wallet balance
/opt/aitbc/aitbc-cli balance --name genesis
```

**If services are not running or dependencies are missing**, see [Blockchain Troubleshooting](aitbc-blockchain-troubleshooting.md) for resolution steps.

## Port Reference

For authoritative port configuration, see [Service Ports Reference](../../docs/reference/SERVICE_PORTS.md).

**Quick Reference:**
| Service | Port | Notes |
|---------|------|-------|
| Marketplace | 8102 | Offers, bids, orders |
| Blockchain RPC | 8006 | Default RPC for CLI |
| Coordinator API | 8011 | Agent registration |

## Operations

### List Marketplace Items
```bash
# Via API
curl -s http://localhost:8102/v1/marketplace/offers

# Via aitbc-cli
cd /opt/aitbc && ./aitbc-cli marketplace --action list

# Alternative command
cd /opt/aitbc && ./aitbc-cli market-list
```

### Create Marketplace Listing
```bash
# Via API
curl -s -X POST http://localhost:8102/v1/marketplace/offers \
  -H "Content-Type: application/json" \
  -d '{"provider":"<address>","item_type":"<type>","price":<price>,"description":"<desc>"}'

# Via aitbc-cli
cd /opt/aitbc && ./aitbc-cli market-create \
  --wallet <wallet_name> \
  --type <service_type> \
  --price <price> \
  --description <description> \
  --password <password>
```

### Search Marketplace
```bash
cd /opt/aitbc && ./aitbc-cli marketplace --action search --name <search_term>
```

### List My Listings
```bash
cd /opt/aitbc && ./aitbc-cli marketplace --action my-listings --wallet <wallet_name>
```

### GPU Provider Registration
```bash
cd /opt/aitbc && python3 cli/unified_cli.py market gpu-provider-register \
  --wallet <wallet_name> \
  --gpu-model <model_name> \
  --gpu-count <number> \
  --models <comma_separated_models> \
  --marketplace-url http://localhost:8102
```

### Buy/Create Bid
```bash
# Via API
curl -s -X POST http://localhost:8102/v1/marketplace/offers/{offer_id}/book \
  -H "Content-Type: application/json" \
  -d '{"buyer":"<address>","bid_amount":<amount>}'

# Via CLI
cd /opt/aitbc && python3 cli/unified_cli.py market buy \
  --item <offer_id> \
  --wallet <wallet_name> \
  --password "$(cat /var/lib/aitbc/keystore/.genesis_password)" \
  --marketplace-url http://localhost:8102
```

### List Bids/Orders
```bash
# Via API
curl -s http://localhost:8102/v1/marketplace/bids
curl -s http://localhost:8102/v1/marketplace/orders

# Via CLI
cd /opt/aitbc && python3 cli/unified_cli.py market orders \
  --wallet <wallet_name> \
  --marketplace-url http://localhost:8102
```

## Common Pitfalls

1. **Insufficient Balance:** Check wallet balance before creating listings
2. **Invalid Service Type:** Ensure service type is valid (ai-inference, ai-training, resource-compute, resource-storage, data-processing, gpu-provider)
3. **Marketplace URL:** Use correct marketplace URL (http://localhost:8102 on main node)
4. **Password Required:** Use password from `/var/lib/aitbc/keystore/.genesis_password` for genesis wallet
5. **Listing Not Found:** Verify listing ID is correct when searching or bidding

## Verification Checklist
- [ ] Marketplace list returns available items
- [ ] Listing creation returns valid listing ID
- [ ] My listings shows created listings
- [ ] Search returns matching items
- [ ] GPU provider registration returns provider ID
- [ ] Bid creation returns bid ID and status

## CLI Entry Point

**Canonical CLI:** `/opt/aitbc/aitbc-cli` (wrapper script)

This is the single CLI entry point for all AITBC operations. The wrapper script loads `cli/unified_cli.py` automatically.

**Direct Python Invocation:** `python3 cli/unified_cli.py`

Use direct Python invocation for:
- Marketplace operations (GPU provider registration, trading)
- GPU testing and Ollama operations
- Specific module features requiring direct access

**Usage Examples:**
```bash
# Standard operations (use wrapper)
/opt/aitbc/aitbc-cli marketplace --action list
/opt/aitbc/aitbc-cli market-create --wallet genesis --type ai-inference --price 100

# Marketplace/GPU operations (use direct Python)
python3 cli/unified_cli.py market gpu-provider-register --wallet genesis --gpu-model llama2
python3 cli/unified_cli.py market buy --item <offer_id> --wallet genesis
```

---

**Generated by:** OWL (aitbc main node)
**Date:** 2026-05-20
**Location:** `/opt/aitbc/skills/aitbc-marketplace.md`
