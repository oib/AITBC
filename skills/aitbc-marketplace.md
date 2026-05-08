# AITBC Marketplace Skill

## Trigger Conditions
Activate when user requests marketplace operations: listing creation, price optimization, market analysis, trading operations, GPU provider registration, or marketplace status checks.

## Purpose
Create, manage, and optimize AITBC marketplace listings with pricing strategies and competitive analysis.

## Prerequisites
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- Wallet with sufficient balance for listing fees
- Marketplace service operational
- GPU provider marketplace operational for resource allocation (if using GPU features)

## Operations

### List Marketplace Items
```bash
# Via aitbc-cli
./aitbc-cli marketplace --action list --rpc-url http://localhost:8006

# Alternative command
./aitbc-cli market-list --rpc-url http://localhost:8006
```

### Create Marketplace Listing
```bash
# Via aitbc-cli
./aitbc-cli marketplace \
  --action create \
  --name <item_name> \
  --price <price> \
  --description <description> \
  --wallet <wallet_name> \
  --rpc-url http://localhost:8006

# Alternative command
./aitbc-cli market-create \
  --wallet <wallet_name> \
  --type <service_type> \
  --price <price> \
  --description <description> \
  --password <password> \
  --rpc-url http://localhost:8006
```

### Search Marketplace
```bash
./aitbc-cli marketplace --action search --name <search_term> --rpc-url http://localhost:8006
```

### List My Listings
```bash
./aitbc-cli marketplace --action my-listings --wallet <wallet_name> --rpc-url http://localhost:8006
```

### GPU Provider Registration
```bash
# Register as GPU provider
python3 cli/unified_cli.py market gpu-provider-register \
  --wallet <wallet_name> \
  --gpu-model <model_name> \
  --gpu-count <number> \
  --models <comma_separated_models> \
  --marketplace-url http://aitbc1:8102
```

### Buy/Create Bid
```bash
python3 cli/unified_cli.py market buy \
  --item <offer_id> \
  --wallet <wallet_name> \
  --password "$(cat /var/lib/aitbc/keystore/.genesis_password)" \
  --marketplace-url http://aitbc1:8102
```

### List Bids/Orders
```bash
python3 cli/unified_cli.py market orders \
  --wallet <wallet_name> \
  --marketplace-url http://aitbc1:8102
```

## Common Pitfalls

1. **Insufficient Balance:** Check wallet balance before creating listings
2. **Invalid Service Type:** Ensure service type is valid (ai-inference, ai-training, resource-compute, resource-storage, data-processing, gpu-provider)
3. **Marketplace URL:** Use correct marketplace URL (http://aitbc1:8102 for unified_cli.py)
4. **Password Required:** Use password from `/var/lib/aitbc/keystore/.genesis_password` for genesis wallet
5. **Listing Not Found:** Verify listing ID is correct when searching or bidding

## Verification Checklist
- [ ] Marketplace list returns available items
- [ ] Listing creation returns valid listing ID
- [ ] My listings shows created listings
- [ ] Search returns matching items
- [ ] GPU provider registration returns provider ID
- [ ] Bid creation returns bid ID and status

## CLI Tool Preference
- **Primary CLI:** `/opt/aitbc/aitbc-cli` is the single CLI entry point
- **Module:** `cli/unified_cli.py` is a module within the CLI tool for marketplace and messaging operations
- **Note:** For marketplace operations, prefer `python3 cli/unified_cli.py` (verified working with 7 bugs fixed)
- **Marketplace URL:** `http://aitbc1:8102` for unified_cli.py marketplace operations
