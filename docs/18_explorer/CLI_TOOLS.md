# AITBC CLI Blockchain Explorer Tools

## Overview

The enhanced AITBC CLI provides comprehensive blockchain exploration tools that allow you to explore the AITBC blockchain directly from the command line. These tools provide the same functionality as the web-based blockchain explorer with additional CLI-specific features.

## 🔍 Blockchain Explorer Command Group

### Basic Blockchain Exploration

```bash
# Get blockchain status and overview
aitbc blockchain status

# Get detailed blockchain information
aitbc blockchain info

# List recent blocks
aitbc blockchain blocks --limit 10

# Get specific block details
aitbc blockchain block <BLOCK_HEIGHT>

# Get transaction details
aitbc blockchain transaction <TX_ID>
```

### Advanced Block Exploration

#### Block Listing and Filtering
```bash
# List latest blocks
aitbc blockchain blocks --limit 20

# List blocks with detailed information
aitbc blockchain blocks --limit 10 --detailed

# List blocks by time range
aitbc blockchain blocks --since "1 hour ago"
aitbc blockchain blocks --since "2024-01-01" --until "2024-01-31"

# List blocks by validator
aitbc blockchain blocks --validator <VALIDATOR_ADDRESS>

# List blocks with transaction count
aitbc blockchain blocks --show-transactions
```

#### Block Details
```bash
# Get block by height
aitbc blockchain block 12345

# Get block by hash
aitbc blockchain block --hash <BLOCK_HASH>

# Get block with full transaction details
aitbc blockchain block 12345 --full

# Get block with validator information
aitbc blockchain block 12345 --validator-info
```

### Transaction Exploration

#### Transaction Search and Details
```bash
# Get transaction by hash
aitbc blockchain transaction 0x1234567890abcdef...

# Get transaction with full details
aitbc blockchain transaction <TX_ID> --full

# Get transaction with receipt information
aitbc blockchain transaction <TX_ID> --receipt

# Get transaction with block context
aitbc blockchain transaction <TX_ID> --block-info
```

#### Transaction Filtering and Search
```bash
# Search transactions by address
aitbc blockchain transactions --address <ADDRESS>

# Search transactions by type
aitbc blockchain transactions --type transfer
aitbc blockchain transactions --type stake
aitbc blockchain transactions --type smart_contract

# Search transactions by time range
aitbc blockchain transactions --since "1 hour ago"
aitbc blockchain transactions --since "2024-01-01" --until "2024-01-31"

# Search transactions by amount range
aitbc blockchain transactions --min-amount 1.0 --max-amount 100.0

# Search transactions with pagination
aitbc blockchain transactions --limit 50 --offset 100
```

### Address Exploration

#### Address Information and Balance
```bash
# Get address balance
aitbc blockchain balance <ADDRESS>

# Get address transaction history
aitbc blockchain address <ADDRESS>

# Get address with detailed information
aitbc blockchain address <ADDRESS> --detailed

# Get address transaction count
aitbc blockchain address <ADDRESS> --tx-count
```

#### Address Analytics
```bash
# Get address transaction history
aitbc blockchain transactions --address <ADDRESS>

# Get address sent/received statistics
aitbc blockchain address <ADDRESS> --stats

# Get address first/last transaction
aitbc blockchain address <ADDRESS> --first-last

# Get address token holdings
aitbc blockchain address <ADDRESS> --tokens
```

### Validator Exploration

#### Validator Information
```bash
# List all validators
aitbc blockchain validators

# Get validator details
aitbc blockchain validator <VALIDATOR_ADDRESS>

# Get validator performance
aitbc blockchain validator <VALIDATOR_ADDRESS> --performance

# Get validator rewards
aitbc blockchain validator <VALIDATOR_ADDRESS> --rewards
```

#### Validator Analytics
```bash
# List active validators
aitbc blockchain validators --status active

# List validators by stake amount
aitbc blockchain validators --sort stake --descending

# Get validator statistics
aitbc blockchain validators --stats

# Get validator uptime
aitbc blockchain validator <VALIDATOR_ADDRESS> --uptime
```

### Network Exploration

#### Network Status and Health
```bash
# Get network overview
aitbc blockchain network

# Get peer information
aitbc blockchain peers

# Get network statistics
aitbc blockchain network --stats

# Get network health
aitbc blockchain network --health
```

#### Peer Management
```bash
# List connected peers
aitbc blockchain peers

# Get peer details
aitbc blockchain peers --detailed

# Get peer statistics
aitbc blockchain peers --stats

# Test peer connectivity
aitbc blockchain peers --test
```

### Advanced Search and Analytics

#### Custom Queries
```bash
# Search blocks with custom criteria
aitbc blockchain search --type block --validator <ADDRESS> --limit 10

# Search transactions with custom criteria
aitbc blockchain search --type transaction --address <ADDRESS> --amount-min 1.0

# Search by smart contract
aitbc blockchain search --type contract --address <CONTRACT_ADDRESS>

# Search by event logs
aitbc blockchain search --type event --event <EVENT_NAME>
```

#### Analytics and Reporting
```bash
# Generate blockchain analytics report
aitbc blockchain analytics --period 24h

# Generate transaction volume report
aitbc blockchain analytics --type volume --period 7d

# Generate validator performance report
aitbc blockchain analytics --type validators --period 30d

# Generate network activity report
aitbc blockchain analytics --type network --period 1h
```

## 📊 Real-time Monitoring

### Live Blockchain Monitoring
```bash
# Monitor new blocks in real-time
aitbc blockchain monitor blocks

# Monitor transactions in real-time
aitbc blockchain monitor transactions

# Monitor specific address
aitbc blockchain monitor address <ADDRESS>

# Monitor validator activity
aitbc blockchain monitor validator <VALIDATOR_ADDRESS>
```

### Real-time Filtering
```bash
# Monitor blocks with filtering
aitbc blockchain monitor blocks --validator <ADDRESS>

# Monitor transactions with filtering
aitbc blockchain monitor transactions --address <ADDRESS> --min-amount 1.0

# Monitor with alerts
aitbc blockchain monitor transactions --alert --threshold 100.0
```

## 🔧 Configuration and Customization

### Explorer Configuration
```bash
# Set default explorer settings
aitbc blockchain config set default-limit 20
aitbc blockchain config set show-transactions true
aitbc blockchain config set currency USD

# Show current configuration
aitbc blockchain config show

# Reset configuration
aitbc blockchain config reset
```

### Output Formatting
```bash
# Format output as JSON
aitbc blockchain blocks --output json

# Format output as table
aitbc blockchain blocks --output table

# Format output as CSV
aitbc blockchain transactions --output csv --file transactions.csv

# Custom formatting
aitbc blockchain transaction <TX_ID> --format custom --template "Hash: {hash}, Amount: {amount}"
```

## 🌐 Integration with Web Explorer

### Synchronization with Web Explorer
```bash
# Sync CLI data with web explorer
aitbc blockchain sync --explorer https://explorer.aitbc.dev

# Export data for web explorer
aitbc blockchain export --format json --file explorer_data.json

# Import data from web explorer
aitbc blockchain import --source https://explorer.aitbc.dev/api
```

### API Integration
```bash
# Use CLI as API proxy
aitbc blockchain api --port 8080

# Generate API documentation
aitbc blockchain api --docs

# Test API endpoints
aitbc blockchain api --test
```

## 📝 Advanced Usage Examples

### Research and Analysis
```bash
# Analyze transaction patterns
aitbc blockchain analytics --type patterns --period 7d

# Track large transactions
aitbc blockchain transactions --min-amount 1000.0 --output json

# Monitor whale activity
aitbc blockchain monitor transactions --min-amount 10000.0 --alert

# Analyze validator performance
aitbc blockchain validators --sort performance --descending --limit 10
```

### Auditing and Compliance
```bash
# Audit trail for address
aitbc blockchain address <ADDRESS> --full --audit

# Generate compliance report
aitbc blockchain compliance --address <ADDRESS> --period 30d

# Track suspicious transactions
aitbc blockchain search --type suspicious --amount-min 10000.0

# Generate AML report
aitbc blockchain aml --address <ADDRESS> --report
```

### Development and Testing
```bash
# Test blockchain connectivity
aitbc blockchain test --full

# Benchmark performance
aitbc blockchain benchmark --operations 1000

# Validate blockchain data
aitbc blockchain validate --full

# Debug transaction issues
aitbc blockchain debug --transaction <TX_ID>
```

## 🔍 Search Patterns and Examples

### Common Search Patterns
```bash
# Find all transactions from an address
aitbc blockchain transactions --address <ADDRESS> --type sent

# Find all transactions to an address
aitbc blockchain transactions --address <ADDRESS> --type received

# Find transactions between two addresses
aitbc blockchain transactions --from <ADDRESS_1> --to <ADDRESS_2>

# Find high-value transactions
aitbc blockchain transactions --min-amount 100.0 --sort amount --descending

# Find recent smart contract interactions
aitbc blockchain transactions --type smart_contract --since "1 hour ago"
```

### Complex Queries
```bash
# Find blocks with specific validator and high transaction count
aitbc blockchain search --blocks --validator <ADDRESS> --min-tx 100

# Find transactions during specific time period with specific amount range
aitbc blockchain transactions --since "2024-01-01" --until "2024-01-31" --min-amount 10.0 --max-amount 100.0

# Monitor address for large transactions
aitbc blockchain monitor address <ADDRESS> --min-amount 1000.0 --alert

# Generate daily transaction volume report
aitbc blockchain analytics --type volume --period 1d --output csv --file daily_volume.csv
```

## 🚀 Performance and Optimization

### Caching and Performance
```bash
# Enable caching for faster queries
aitbc blockchain cache enable

# Clear cache
aitbc blockchain cache clear

# Set cache size
aitbc blockchain config set cache-size 1GB

# Benchmark query performance
aitbc blockchain benchmark --query "transactions --address <ADDRESS>"
```

### Batch Operations
```bash
# Batch transaction lookup
aitbc blockchain batch-transactions --file tx_hashes.txt

# Batch address lookup
aitbc blockchain batch-addresses --file addresses.txt

# Batch block lookup
aitbc blockchain batch-blocks --file block_heights.txt
```

## 📱 Mobile and Remote Access

### Remote Blockchain Access
```bash
# Connect to remote blockchain node
aitbc blockchain remote --node https://node.aitbc.dev

# Use remote explorer API
aitbc blockchain remote --explorer https://explorer.aitbc.dev

# SSH tunnel for secure access
aitbc blockchain tunnel --ssh user@server --port 8545
```

### Mobile Optimization
```bash
# Mobile-friendly output
aitbc blockchain blocks --mobile --limit 5

# Compact output for mobile
aitbc blockchain transaction <TX_ID> --compact

# Quick status check
aitbc blockchain status --quick
```

## 🔗 Integration with Other Tools

### Data Export and Integration
```bash
# Export to CSV for Excel
aitbc blockchain transactions --output csv --file transactions.csv

# Export to JSON for analysis
aitbc blockchain blocks --output json --file blocks.json

# Export to database
aitbc blockchain export --database postgresql --connection-string "postgres://user:pass@localhost/aitbc"

# Integrate with Elasticsearch
aitbc blockchain export --elasticsearch --url http://localhost:9200
```

### Scripting and Automation
```bash
#!/bin/bash
# Script to monitor large transactions
for tx in $(aitbc blockchain transactions --min-amount 1000.0 --output json | jq -r '.[].hash'); do
    echo "Large transaction detected: $tx"
    aitbc blockchain transaction $tx --full
done

# Script to track address activity
aitbc blockchain monitor address <ADDRESS> --format json | while read line; do
    echo "New activity: $line"
    # Send notification or trigger alert
done
```

## 🛠️ Troubleshooting and Debugging

### Common Issues and Solutions
```bash
# Check blockchain connectivity
aitbc blockchain test --connectivity

# Debug transaction lookup
aitbc blockchain debug --transaction <TX_ID> --verbose

# Check data integrity
aitbc blockchain validate --integrity

# Reset corrupted cache
aitbc blockchain cache clear --force

# Check API endpoints
aitbc blockchain api --status
```

### Performance Issues
```bash
# Check query performance
aitbc blockchain benchmark --query "blocks --limit 100"

# Optimize cache settings
aitbc blockchain config set cache-size 2GB
aitbc blockchain config set cache-ttl 3600

# Monitor resource usage
aitbc blockchain monitor --resources
```

## 📚 Best Practices

### For Researchers
1. **Use filters effectively** to narrow down search results
2. **Export data** for offline analysis
3. **Use caching** for repeated queries
4. **Monitor real-time** for time-sensitive analysis
5. **Document queries** for reproducibility

### For Developers
1. **Use JSON output** for programmatic access
2. **Test connectivity** before running complex queries
3. **Use batch operations** for multiple lookups
4. **Monitor performance** for optimization
5. **Handle errors gracefully** in scripts

### For Analysts
1. **Use analytics commands** for insights
2. **Export to CSV/Excel** for reporting
3. **Set up monitoring** for ongoing analysis
4. **Use alerts** for important events
5. **Validate data** before making decisions

## 🆕 Migration from Web Explorer

If you're transitioning from the web-based explorer:

| Web Explorer Feature | CLI Equivalent |
|---------------------|----------------|
| Block listing | `aitbc blockchain blocks --limit 20` |
| Transaction search | `aitbc blockchain transaction <TX_ID>` |
| Address lookup | `aitbc blockchain address <ADDRESS>` |
| Validator info | `aitbc blockchain validator <ADDRESS>` |
| Real-time updates | `aitbc blockchain monitor blocks` |
| Advanced search | `aitbc blockchain search --type <TYPE>` |

## 📞 Support and Help

### Command Help
```bash
# General help
aitbc blockchain --help

# Specific command help
aitbc blockchain blocks --help
aitbc blockchain transaction --help
aitbc blockchain search --help
```

### Troubleshooting
```bash
# Check system status
aitbc blockchain status --full

# Test all functionality
aitbc blockchain test --comprehensive

# Generate diagnostic report
aitbc blockchain diagnose --export diagnostic.json
```

---

*This guide covers all AITBC CLI blockchain explorer tools for comprehensive blockchain exploration and analysis.*
