# AITBC Multi-Node Blockchain Setup Scripts

This directory contains modular scripts for setting up and managing a multi-node AITBC blockchain network.

## Scripts Overview

### Core Setup Scripts

1. **01_preflight_setup.sh** - Pre-flight system preparation
   - Stops existing services
   - Updates systemd configurations
   - Sets up environment files
   - Installs CLI tool
   - Creates keystore and directories

2. **02_genesis_authority_setup.sh** - Genesis authority node setup (aitbc1)
   - Pulls latest code
   - Configures genesis authority
   - Creates genesis block
   - Starts blockchain services

3. **03_follower_node_setup.sh** - Follower node setup (aitbc)
   - Configures follower node
   - Sets up cross-node communication
   - Starts follower services

4. **04_create_wallet.sh** - Wallet creation on follower node
   - Creates new wallet using CLI tool
   - Verifies wallet creation
   - Returns wallet address

5. **05_send_transaction.sh** - Transaction sending
   - Sends AIT from genesis to wallet
   - Monitors transaction confirmation
   - Verifies balance update

6. **06_final_verification.sh** - Complete system verification
   - Checks blockchain synchronization
   - Verifies transaction success
   - Tests network health
   - Validates service status

### Master Script

- **setup_multinode_blockchain.sh** - Master orchestrator script
  - Runs all scripts in sequence
  - Provides interactive execution
  - Includes comprehensive summary
  - Handles error checking

## Usage

### Individual Script Execution

```bash
# Run individual scripts
./01_preflight_setup.sh
./02_genesis_authority_setup.sh
./03_follower_node_setup.sh
./04_create_wallet.sh
./05_send_transaction.sh
./06_final_verification.sh
```

### Master Script Execution

```bash
# Run complete setup (interactive)
./setup_multinode_blockchain.sh

# Run complete setup (non-interactive)
echo "y" | ./setup_multinode_blockchain.sh
```

## Script Dependencies

### System Requirements
- aitbc1 node (genesis authority)
- aitbc node (follower)
- SSH access between nodes
- Redis service running
- Python virtual environment

### Environment Variables
- `WALLET_ADDR` - Set by wallet creation script
- `GENESIS_ADDR` - Set by genesis setup script

### File Structure
```
/opt/aitbc/scripts/workflow/
├── 01_preflight_setup.sh
├── 02_genesis_authority_setup.sh
├── 03_follower_node_setup.sh
├── 04_create_wallet.sh
├── 05_send_transaction.sh
├── 06_final_verification.sh
├── setup_multinode_blockchain.sh
└── README.md
```

## Script Features

### Error Handling
- All scripts use `set -e` for error detection
- Comprehensive error messages
- Graceful failure handling

### Logging
- Clear step-by-step output
- Progress indicators
- Success/failure confirmation

### Modularity
- Each script is self-contained
- Can be run independently
- State management between scripts

### Cross-Node Operations
- Automatic SSH handling
- Remote command execution
- File synchronization

## Customization

### Environment Modifications
- Edit `.env` files for different configurations
- Modify service names as needed
- Adjust network settings

### Script Parameters
- Wallet names can be changed
- Transaction amounts are configurable
- Network settings are customizable

## Troubleshooting

### Common Issues
1. **SSH Connection**: Verify SSH keys between nodes
2. **Service Failures**: Check systemd logs
3. **Network Issues**: Verify Redis and RPC connectivity
4. **Permission Errors**: Ensure proper file permissions

### Debug Mode
Add `set -x` to scripts for detailed execution tracing.

### Log Locations
- Systemd logs: `journalctl -u aitbc-blockchain-*`
- Application logs: `/var/log/aitbc/`
- Script logs: Console output

## Security Considerations

### Password Management
- Keystore passwords stored in `/var/lib/aitbc/keystore/.password`
- Change default password in production
- Use proper key management

### Network Security
- SSH key authentication recommended
- Firewall rules for RPC ports
- Redis security configuration

### File Permissions
- Keystore files: `600` (owner only)
- Scripts: `755` (executable)
- Configuration: `644` (readable)

## Maintenance

### Regular Tasks
- Monitor blockchain synchronization
- Check service health
- Update scripts as needed
- Backup configurations

### Updates
- Pull latest code changes
- Update script dependencies
- Test script modifications
- Document changes

## Integration with Workflow

These scripts are referenced in the main workflow documentation:
- `/opt/aitbc/.windsurf/workflows/multi-node-blockchain-setup.md`

The workflow now uses script references instead of inline code, making it:
- More maintainable
- Easier to test
- Reusable components
- Better organized
