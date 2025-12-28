---
title: Explorer
description: Using the AITBC blockchain explorer
---

# Explorer

The AITBC explorer allows you to browse and search the blockchain for transactions, jobs, and other activities.

## Features

### Transaction Search
- Search by transaction hash
- Filter by address
- View transaction details

### Job Tracking
- Monitor job status
- View job history
- Analyze performance

### Analytics
- Network statistics
- Volume metrics
- Activity charts

## Using the Explorer

### Web Interface
Visit [https://aitbc.bubuit.net/explorer/](https://aitbc.bubuit.net/explorer/)

### API Access
```bash
# Get transaction
curl https://aitbc.bubuit.net/api/v1/transactions/{tx_hash}

# Get job details
curl https://aitbc.bubuit.net/api/v1/jobs/{job_id}

# Explorer data (blocks)
curl https://aitbc.bubuit.net/api/explorer/blocks
```

## Advanced Features

- Real-time updates
- Custom dashboards
- Data export
- Alert notifications
