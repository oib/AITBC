# AITBC CLI Marketplace Tools

## Overview

The enhanced AITBC CLI provides comprehensive marketplace tools for GPU computing, resource management, and global marketplace operations. This guide covers all CLI commands for marketplace participants.

## 🏪 Marketplace Command Group

### Basic Marketplace Operations

```bash
# List all marketplace resources
aitbc marketplace list

# List available GPUs with details
aitbc marketplace gpu list

# List GPUs by region
aitbc marketplace gpu list --region us-west

# List GPUs by model
aitbc marketplace gpu list --model rtx4090

# List GPUs by price range
aitbc marketplace gpu list --max-price 0.05
```

### GPU Offer Management

#### Create GPU Offer
```bash
# Basic GPU offer
aitbc marketplace offer create \
  --miner-id gpu_miner_123 \
  --gpu-model "RTX-4090" \
  --gpu-memory "24GB" \
  --price-per-hour "0.05" \
  --models "gpt2,llama" \
  --endpoint "http://localhost:11434"

# Advanced GPU offer with more options
aitbc marketplace offer create \
  --miner-id gpu_miner_456 \
  --gpu-model "A100" \
  --gpu-memory "40GB" \
  --gpu-count 4 \
  --price-per-hour "0.10" \
  --models "gpt4,claude,llama2" \
  --endpoint "http://localhost:11434" \
  --region us-west \
  --availability "24/7" \
  --min-rental-duration 1h \
  --max-rental-duration 168h \
  --performance-tier "premium"
```

#### List and Manage Offers
```bash
# List your offers
aitbc marketplace offers --miner-id gpu_miner_123

# List all active offers
aitbc marketplace offers --status active

# Update offer pricing
aitbc marketplace offer update \
  --offer-id offer_789 \
  --price-per-hour "0.06"

# Deactivate offer
aitbc marketplace offer deactivate --offer-id offer_789

# Reactivate offer
aitbc marketplace offer activate --offer-id offer_789

# Delete offer permanently
aitbc marketplace offer delete --offer-id offer_789
```

### GPU Rental Operations

#### Rent GPU
```bash
# Basic GPU rental
aitbc marketplace gpu rent \
  --gpu-id gpu_789 \
  --duration 2h

# Advanced GPU rental
aitbc marketplace gpu rent \
  --gpu-id gpu_789 \
  --duration 4h \
  --auto-renew \
  --max-budget 1.0

# Rent by specifications
aitbc marketplace gpu rent \
  --gpu-model "RTX-4090" \
  --gpu-memory "24GB" \
  --duration 2h \
  --region us-west
```

#### Manage Rentals
```bash
# List active rentals
aitbc marketplace rentals --status active

# List rental history
aitbc marketplace rentals --history

# Extend rental
aitbc marketplace rental extend \
  --rental-id rental_456 \
  --additional-duration 2h

# Cancel rental
aitbc marketplace rental cancel --rental-id rental_456

# Monitor rental usage
aitbc marketplace rental monitor --rental-id rental_456
```

### Order Management

```bash
# List all orders
aitbc marketplace orders

# List orders by status
aitbc marketplace orders --status pending
aitbc marketplace orders --status completed
aitbc marketplace orders --status cancelled

# List your orders
aitbc marketplace orders --miner-id gpu_miner_123

# Order details
aitbc marketplace order details --order-id order_789

# Accept order
aitbc marketplace order accept --order-id order_789

# Reject order
aitbc marketplace order reject --order-id order_789 --reason "GPU unavailable"

# Complete order
aitbc marketplace order complete --order-id order_789
```

### Review and Rating System

```bash
# Leave review for miner
aitbc marketplace review create \
  --miner-id gpu_miner_123 \
  --rating 5 \
  --comment "Excellent performance, fast response"

# Leave review for renter
aitbc marketplace review create \
  --renter-id client_456 \
  --rating 4 \
  --comment "Good experience, minor delay"

# List reviews for miner
aitbc marketplace reviews --miner-id gpu_miner_123

# List reviews for renter
aitbc marketplace reviews --renter-id client_456

# List your reviews
aitbc marketplace reviews --my-reviews

# Update review
aitbc marketplace review update \
  --review-id review_789 \
  --rating 5 \
  --comment "Updated: Excellent after support"
```

### Global Marketplace Operations

```bash
# List global marketplace statistics
aitbc marketplace global stats

# List regions
aitbc marketplace global regions

# Region-specific operations
aitbc marketplace global offers --region us-west
aitbc marketplace global rentals --region europe

# Cross-chain operations
aitbc marketplace global cross-chain \
  --source-chain ethereum \
  --target-chain polygon \
  --amount 100

# Global analytics
aitbc marketplace global analytics --period 24h
aitbc marketplace global analytics --period 7d
```

## 🔍 Search and Filtering

### Advanced Search
```bash
# Search GPUs by multiple criteria
aitbc marketplace gpu list \
  --model rtx4090 \
  --memory-min 16GB \
  --price-max 0.05 \
  --region us-west

# Search offers by availability
aitbc marketplace offers search \
  --available-now \
  --min-duration 2h

# Search by performance tier
aitbc marketplace gpu list --performance-tier premium
aitbc marketplace gpu list --performance-tier standard
```

### Filtering and Sorting
```bash
# Sort by price (lowest first)
aitbc marketplace gpu list --sort price

# Sort by performance (highest first)
aitbc marketplace gpu list --sort performance --descending

# Filter by availability
aitbc marketplace gpu list --available-only

# Filter by minimum rental duration
aitbc marketplace gpu list --min-duration 4h
```

## 📊 Analytics and Reporting

### Usage Analytics
```bash
# Personal usage statistics
aitbc marketplace analytics personal

# Spending analytics
aitbc marketplace analytics spending --period 30d

# Earnings analytics (for miners)
aitbc marketplace analytics earnings --period 7d

# Performance analytics
aitbc marketplace analytics performance --gpu-id gpu_789
```

### Marketplace Analytics
```bash
# Overall marketplace statistics
aitbc marketplace analytics market

# Regional analytics
aitbc marketplace analytics regions

# Model popularity analytics
aitbc marketplace analytics models

# Price trend analytics
aitbc marketplace analytics prices --period 7d
```

## ⚙️ Configuration and Preferences

### Marketplace Configuration
```bash
# Set default preferences
aitbc marketplace config set default-region us-west
aitbc marketplace config set max-price 0.10
aitbc marketplace config set preferred-model rtx4090

# Show configuration
aitbc marketplace config show

# Reset configuration
aitbc marketplace config reset
```

### Notification Settings
```bash
# Enable notifications
aitbc marketplace notifications enable --type price-alerts
aitbc marketplace notifications enable --type rental-reminders

# Set price alerts
aitbc marketplace alerts create \
  --type price-drop \
  --gpu-model rtx4090 \
  --target-price 0.04

# Set rental reminders
aitbc marketplace alerts create \
  --type rental-expiry \
  --rental-id rental_456 \
  --reminder-time 30m
```

## 🔧 Advanced Operations

### Batch Operations
```bash
# Batch offer creation from file
aitbc marketplace batch-offers create --file offers.json

# Batch rental management
aitbc marketplace batch-rentals extend --file rentals.json

# Batch price updates
aitbc marketplace batch-prices update --file price_updates.json
```

### Automation Scripts
```bash
# Auto-renew rentals
aitbc marketplace auto-renew enable --max-budget 10.0

# Auto-accept orders (for miners)
aitbc marketplace auto-accept enable --min-rating 4

# Auto-price adjustment
aitbc marketplace auto-price enable --strategy market-based
```

### Integration Tools
```bash
# Export data for analysis
aitbc marketplace export --format csv --file marketplace_data.csv

# Import offers from external source
aitbc marketplace import --file external_offers.json

# Sync with external marketplace
aitbc marketplace sync --source external_marketplace
```

## 🌍 Global Marketplace Features

### Multi-Region Operations
```bash
# List available regions
aitbc marketplace global regions

# Region-specific pricing
aitbc marketplace global pricing --region us-west

# Cross-region arbitrage
aitbc marketplace global arbitrage --source-region us-west --target-region europe
```

### Cross-Chain Operations
```bash
# List supported chains
aitbc marketplace global chains

# Cross-chain pricing
aitbc marketplace global pricing --chain polygon

# Cross-chain transactions
aitbc marketplace global transfer \
  --amount 100 \
  --from-chain ethereum \
  --to-chain polygon
```

## 🛡️ Security and Trust

### Trust Management
```bash
# Check trust score
aitbc marketplace trust score --miner-id gpu_miner_123

# Verify miner credentials
aitbc marketplace verify --miner-id gpu_miner_123

# Report suspicious activity
aitbc marketplace report \
  --type suspicious \
  --target-id gpu_miner_123 \
  --reason "Unusual pricing patterns"
```

### Dispute Resolution
```bash
# Create dispute
aitbc marketplace dispute create \
  --order-id order_789 \
  --reason "Performance not as advertised"

# List disputes
aitbc marketplace disputes --status open

# Respond to dispute
aitbc marketplace dispute respond \
  --dispute-id dispute_456 \
  --response "Offering partial refund"
```

## 📝 Best Practices

### For Miners
1. **Competitive Pricing**: Use `aitbc marketplace analytics prices` to set competitive rates
2. **High Availability**: Keep offers active and update availability regularly
3. **Good Reviews**: Provide excellent service to build reputation
4. **Performance Monitoring**: Use `aitbc marketplace analytics performance` to track GPU performance

### For Renters
1. **Price Comparison**: Use `aitbc marketplace gpu list --sort price` to find best deals
2. **Review Check**: Use `aitbc marketplace reviews --miner-id` before renting
3. **Budget Management**: Set spending limits and track usage with analytics
4. **Rental Planning**: Use auto-renew for longer projects

### For Both
1. **Security**: Enable two-factor authentication and monitor account activity
2. **Notifications**: Set up alerts for important events
3. **Data Backup**: Regularly export transaction history
4. **Market Awareness**: Monitor market trends and adjust strategies

## 🔗 Integration Examples

### Script Integration
```bash
#!/bin/bash
# Find best GPU for specific requirements
BEST_GPU=$(aitbc marketplace gpu list \
  --model rtx4090 \
  --max-price 0.05 \
  --available-only \
  --output json | jq -r '.[0].gpu_id')

echo "Best GPU found: $BEST_GPU"

# Rent the GPU
aitbc marketplace gpu rent \
  --gpu-id $BEST_GPU \
  --duration 4h \
  --auto-renew
```

### API Integration
```bash
# Export marketplace data for external processing
aitbc marketplace gpu list --output json > gpu_data.json

# Process with external tools
python process_gpu_data.py gpu_data.json

# Import results back
aitbc marketplace import --file processed_offers.json
```

## 🆕 Migration from Legacy Commands

If you're transitioning from legacy marketplace commands:

| Legacy Command | Enhanced CLI Command |
|---------------|----------------------|
| `aitbc marketplace list` | `aitbc marketplace list` |
| `aitbc marketplace gpu list` | `aitbc marketplace gpu list` |
| `aitbc marketplace rent` | `aitbc marketplace gpu rent` |
| `aitbc marketplace offers` | `aitbc marketplace offers` |

## 📞 Support and Help

### Command Help
```bash
# General help
aitbc marketplace --help

# Specific command help
aitbc marketplace gpu list --help
aitbc marketplace offer create --help
```

### Troubleshooting
```bash
# Check marketplace status
aitbc marketplace status

# Test connectivity
aitbc marketplace test-connectivity

# Debug mode
aitbc marketplace --debug
```

---

*This guide covers all AITBC CLI marketplace tools for GPU computing, resource management, and global marketplace operations.*
