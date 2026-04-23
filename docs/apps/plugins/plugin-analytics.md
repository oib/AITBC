# Plugin Analytics

## Status
✅ Operational

## Overview
Analytics plugin for collecting, processing, and analyzing data from various AITBC components and services.

## Architecture

### Core Components
- **Data Collector**: Collects data from services and plugins
- **Data Processor**: Processes and normalizes collected data
- **Analytics Engine**: Performs analytics and generates insights
- **Report Generator**: Generates reports and visualizations
- **Storage Manager**: Manages data storage and retention

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- PostgreSQL database
- Access to service metrics endpoints

### Installation
```bash
cd /opt/aitbc/apps/plugin-analytics
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
DATABASE_URL=postgresql://user:pass@localhost/analytics
COLLECTION_INTERVAL=300
RETENTION_DAYS=90
```

### Running the Service
```bash
.venv/bin/python main.py
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Set up database
5. Configure data sources
6. Run tests: `pytest tests/`

### Project Structure
```
plugin-analytics/
├── src/
│   ├── data_collector/      # Data collection
│   ├── data_processor/      # Data processing
│   ├── analytics_engine/    # Analytics engine
│   ├── report_generator/    # Report generation
│   └── storage_manager/     # Storage management
├── tests/                   # Test suite
└── pyproject.toml           # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run data collector tests
pytest tests/test_collector.py

# Run analytics engine tests
pytest tests/test_analytics.py
```

## API Reference

### Data Collection

#### Start Collection
```http
POST /api/v1/analytics/collection/start
Content-Type: application/json

{
  "data_source": "string",
  "interval": 300
}
```

#### Stop Collection
```http
POST /api/v1/analytics/collection/stop
Content-Type: application/json

{
  "collection_id": "string"
}
```

#### Get Collection Status
```http
GET /api/v1/analytics/collection/status
```

### Analytics

#### Run Analysis
```http
POST /api/v1/analytics/analyze
Content-Type: application/json

{
  "analysis_type": "trend|anomaly|correlation",
  "data_source": "string",
  "time_range": "1h|1d|1w"
}
```

#### Get Analysis Results
```http
GET /api/v1/analytics/results/{analysis_id}
```

### Reports

#### Generate Report
```http
POST /api/v1/analytics/reports/generate
Content-Type: application/json

{
  "report_type": "summary|detailed|custom",
  "data_source": "string",
  "time_range": "1d|1w|1m"
}
```

#### Get Report
```http
GET /api/v1/analytics/reports/{report_id}
```

#### List Reports
```http
GET /api/v1/analytics/reports?limit=10
```

### Data Management

#### Query Data
```http
POST /api/v1/analytics/data/query
Content-Type: application/json

{
  "data_source": "string",
  "filters": {},
  "time_range": "1h"
}
```

#### Export Data
```http
POST /api/v1/analytics/data/export
Content-Type: application/json

{
  "data_source": "string",
  "format": "csv|json",
  "time_range": "1d"
}
```

## Configuration

### Environment Variables
- `DATABASE_URL`: PostgreSQL connection string
- `COLLECTION_INTERVAL`: Data collection interval (default: 300s)
- `RETENTION_DAYS`: Data retention period (default: 90 days)
- `MAX_BATCH_SIZE`: Maximum batch size for processing

### Data Sources
- **Blockchain Metrics**: Blockchain node metrics
- **Exchange Data**: Exchange trading data
- **Agent Activity**: Agent coordination data
- **System Metrics**: System performance metrics

### Analysis Types
- **Trend Analysis**: Identify trends over time
- **Anomaly Detection**: Detect unusual patterns
- **Correlation Analysis**: Find correlations between metrics

## Troubleshooting

**Data not collecting**: Check data source connectivity and configuration.

**Analysis not running**: Verify data availability and analysis parameters.

**Report generation failed**: Check data completeness and report configuration.

**Storage full**: Review retention policy and data growth rate.

## Security Notes

- Secure database access credentials
- Implement data encryption at rest
- Validate all data inputs
- Implement access controls for sensitive data
- Regularly audit data access logs
- Comply with data retention policies
