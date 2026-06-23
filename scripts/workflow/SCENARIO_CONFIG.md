# Scenario Configuration Guide

## Overview

Scenario scripts use a centralized configuration file to make them flexible for different deployment setups. This allows you to easily configure the hub, shop, and customer identities without modifying individual scripts.

## Configuration File

The configuration file is located at:
```
/etc/aitbc/.env.scenario
```

An example configuration is available at:
```
/opt/aitbc/examples/.env.scenario.example
```

## Configuration Variables

### Hub Configuration
- `HUB_URL`: The blockchain hub URL (default: `https://hub.aitbc.bubuit.net`)
- `HUB_BLOCKCHAIN_RPC`: The hub's blockchain RPC endpoint (default: `http://hub.aitbc.bubuit.net:8202`)

### Shop/Service Provider Configuration
- `SHOP_URL`: The shop/service provider URL (default: `https://aitbc3.aitbc.bubuit.net`)
- `SHOP_BLOCKCHAIN_RPC`: The shop's blockchain RPC endpoint (default: `http://localhost:8202`)

### Customer Configuration
- `CUSTOMER_ID`: Customer identity for scenarios (default: `customer_001`)
- `CUSTOMER_WALLET`: Customer wallet address (default: empty)

### Service Ports (v0.4.4, v0.4.5, v0.4.6)
- `BLOCKCHAIN_RPC_PORT`: 8202
- `BLOCKCHAIN_P2P_PORT`: 8200
- `AGENT_COORDINATOR_PORT`: 8107
- `AGENT_PORT`: 8103
- `TRADING_PORT`: 8104
- `GOVERNANCE_PORT`: 8105
- `EXCHANGE_PORT`: 8106
- `WALLET_PORT`: 8108
- `PLUGIN_REGISTRY_PORT`: 8109
- `WHISPER_PORT`: 8110
- `PEERTUBE_PORT`: 8220

### Service Endpoints
- `PLUGIN_REGISTRY_ENDPOINT`: Shop's plugin registry endpoint
- `WHISPER_ENDPOINT`: Shop's Whisper service endpoint
- `PEERTUBE_ENDPOINT`: Shop's PeerTube transcoder endpoint

## Usage

### 1. Using Default Configuration

Scenario scripts will automatically use the configuration file if it exists. If it doesn't exist, they fall back to sensible defaults:

```bash
Copy the example an/ edscripts/workflow/24_marketplace_scenario.sh
```

# Copy example to productio# loc#tio#
cp / pt/aitbc/examples/.env.scenario.example2.etc/aitbc/.env.scenario

# Edit configuration
nan  /eucstomizing Configuration

Edit the configuration file to match your environment:

```bash
nano /opt/aitbc/.env.scenario
```

Example for a different island:
```bash
# Hub Configuration
export HUB_URL="https://hub.example.com"
export HUB_BLOCKCHAIN_RPC="http://hub.example.com:8202"

# Shop Configuration
export SHOP_URL="https://node1.example.com"
export SHOP_BLOCKCHAIN_RPC="http://localhost:8202"

# Customer Configuration
export CUSTOMER_ID="customer_abc123"
export CUSTOMER_WALLET="0x1234..."
```

### 3. Runtime Override

You can override configuration at runtime by setting environment variables before running a scenario:

```bash
export HUB_URL="https://custom-hub.example.com"
export SHOP_URL="https://custom-shop.example.com"
./scripts/workflow/24_marketplace_scenario.sh
```

## Architecture

### Hub vs Shop

- **Hub**: The blockchain hub for the island (e.g., `hub.aitbc.bubuit.net`). Handles blockchain operations, hardware+software bundle offer discovery, and transaction coordination.
- **Shop**: A follower node that provides services (e.g., `aitbc3.aitbc.bubuit.net`). Runs services like Whisper transcription, plugin registry, and PeerTube transcoding.

### Customer

The customer is the identity that initiates scenarios, submits jobs, and makes payments. This can be configured to test different customer roles.

### Marketplace Model (v0.4.7+)

**Important**: The GPU-only marketplace has been deprecated. All marketplace operations now use hardware+software bundles only.

- **Hardware+Software Bundles**: Offers combine GPU hardware with software services (Ollama, Whisper, etc.)
- **No GPU-Only Listings**: Direct GPU rentals without software are no longer supported
- **Plugin Registry Integration**: All bundles are automatically registered in the plugin registry
- **Escrow Payments**: All transactions use escrow with on-chain job verification

## Scenario Scripts Using Configuration

All scenario scripts in the following directories use this configuration:
- `/opt/aitbc/scripts/workflow/`
- `/opt/aitbc/dev/testing/tests/`

### Updated Scenario Scripts (v0.4.7)

The following scenario scripts have been updated to reflect the hardware+software bundle marketplace:

- `24_marketplace_scenario.sh` - Main marketplace workflow with bundles
- `24_marketplace_scenario_real.sh` - Real hardware+software bundle testing
- `24_marketplace_scenario_simple.sh` - Simplified bundle workflow
- `28_marketplace_scenario_with_ai.sh` - AI response tracking with bundles

### Deprecated Commands

The following GPU-only marketplace commands are no longer available:
- `aitbc market offer gpu_id price duration` (removed)
- `aitbc market bid` (removed)
- `aitbc market accept` (removed)

### Current Commands

Use these commands for hardware+software bundles:
- `aitbc market offer ollama|whisper <model> <price> --gpu-device <id>`
- `aitbc market run <offer_id> <prompt>`
- `aitbc market transcribe <offer_id> <audio_file>`
- `aitbc market list` (shows hardware+software bundles only)
- `aitbc market cancel <offer_id>`

## Troubleshooting

### Configuration Not Loading

If you see "⚠️ Using default configuration (env file not found)", ensure:
1. The file exists at `/etc/aitbc/.env.scenario`
2. The file has proper permissions (`chmod 644 /etc/aitbc/.env.scenario`)

### Service Unavailable

If a service endpoint is unavailable:
1. Check that the `SHOP_URL` is correct for your environment
2. Verify the service is running on the specified port
3. Check firewall rules allow access to the service

### Blockchain Connection Issues

If blockchain operations fail:
1. Verify `HUB_BLOCKCHAIN_RPC` is accessible
2. Check that the blockchain node is running
3. Ensure the RPC port (8202) is open

## See Also

- [SERVICE_PORTS.md](../../deployment/SERVICE_PORTS.md) - Complete port reference
- [RELEASE_v0.4.4.md](../../docs/releases/RELEASE_v0.4.4.md) - Port architecture changes
- [RELEASE_v0.4.5.md](../../docs/releases/RELEASE_v0.4.5.md) - Software marketplace ports
- [RELEASE_v0.4.6.md](../../docs/releases/RELEASE_v0.4.6.md) - Agent communication ports
