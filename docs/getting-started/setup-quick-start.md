# AITBC Setup - Quick Start

**Last Updated**: 2026-06-30
**Version**: 1.0

## 5-Minute Quick Start

```bash
# One-command installation (includes service user setup)
bash <(curl -sSL https://raw.githubusercontent.com/oib/AITBC/main/scripts/deployment/setup.sh)

# Or manual installation
git clone https://github.com/oib/aitbc.git /opt/aitbc
cd /opt/aitbc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The setup script automatically creates service users for security isolation based on network exposure.

> **🟢 Service Status**: All core services are operational as of June 7, 2026. See [Service Status](../infrastructure/SYSTEMD_SERVICES.md#current-service-status) for details.

> **⚠️ v0.4.26 Update**: JWT authentication is now required. `setup.sh` automatically generates `JWT_SECRET` and `SECRET_KEY`. If upgrading from an earlier version, run `/opt/aitbc/scripts/utils/load-keystore-secrets.sh` after updating the credential files.

## Install Profiles

AITBC provides pre-configured dependency profiles for different deployment scenarios. The setup script automatically detects the appropriate profile based on your node configuration, or you can manually install a specific profile.

### Available Profiles

Profiles are mapped from the three role axes (`BLOCKCHAIN_MODE` + `MARKET_ROLE` + `HARDWARE_PROFILE`) to one of four install profiles:

| Profile | Role Mapping | Description | Use Case |
|---------|-------------|-------------|----------|
| **customer-no-gpu** | follower + customer + nogpu | Lightweight client | Standard follower node consuming resources |
| **server-no-gpu** | follower + shop + nogpu | Core blockchain services | Follower that provides marketplace services, no GPU |
| **hub** | hub + any + nogpu | Full blockchain hub | Central hub node with all services + dev deps |
| **provider-gpu** | any + any + gpu | GPU service provider | Any node with GPU (gets AI/ML deps including pycuda) |

### Manual Profile Installation

```bash
# Activate virtual environment first
source /opt/aitbc/venv/bin/activate

# Install specific profile
./scripts/deployment/install-profiles.sh customer-no-gpu
./scripts/deployment/install-profiles.sh provider-gpu

# List all available profiles
./scripts/deployment/install-profiles.sh
```

### Automatic Profile Detection

The setup.sh script automatically selects the appropriate profile based on your `/etc/aitbc/blockchain.env` configuration:

- `HARDWARE_PROFILE=gpu` → **provider-gpu** (regardless of other axes)
- `BLOCKCHAIN_MODE=hub` + `HARDWARE_PROFILE=nogpu` → **hub**
- `MARKET_ROLE=customer` + `HARDWARE_PROFILE=nogpu` → **customer-no-gpu**
- `MARKET_ROLE=shop` + `HARDWARE_PROFILE=nogpu` → **server-no-gpu**
- Default → **customer-no-gpu**

### Profile Dependencies

Each profile installs different dependency sets:

- **customer-no-gpu**: requirements-minimal.txt + CLI requirements
- **server-no-gpu**: requirements.txt + security.txt
- **hub**: requirements.txt + security.txt + dev.txt
- **provider-gpu**: requirements.txt + ai-ml.txt + security.txt

## Node Profiles

During setup, you will be prompted to configure two independent axes that determine which services run:

### Axis 1: Blockchain Mode (`BLOCKCHAIN_MODE`)
- **follower** (default) - Receives blocks from hub, runs periodic sync
- **hub** - Produces and broadcasts blocks, runs lease tracker for subscription system

### Axis 2: Market Role (`MARKET_ROLE`)
- **customer** (default) - Consumes GPU resources
- **shop** - Provides GPU resources to the marketplace

### Hardware Profile (`HARDWARE_PROFILE`)
- **nogpu** (default) - No GPU available
- **gpu** - GPU available for compute

These two axes are **independent** — a hub can also be a shop, and a follower can be a customer or a shop. The service selection combines both axes (see [Role-Based Service Selection](./setup-service-selection.md) below).

These profiles are set in `/etc/aitbc/blockchain.env` (read by blockchain node):

```bash
# Node Profiles (set during setup.sh) — two independent axes
BLOCKCHAIN_MODE=follower  # follower or hub
MARKET_ROLE=customer       # customer or shop
HARDWARE_PROFILE=nogpu    # gpu or nogpu
```

> **For detailed environment configuration:** See [Environment Configuration Guide](../blockchain/ENVIRONMENT_CONFIGURATION.md) for complete reference on `blockchain.env`, `node.env`, and `blockchain-secrets.env`.

## Related Topics

- [Service Selection](./setup-service-selection.md) - Role-based service configuration
- [Subscription System](./setup-subscription.md) - Lease-based block synchronization
- [Configuration](./setup-configuration.md) - Runtime directories, secrets, and environment files
- [Security](./setup-security.md) - Service user security
- [Reference](./setup-reference.md) - Common commands, troubleshooting, and links
