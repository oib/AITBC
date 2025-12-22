# AITBC Chaos Testing Framework

This framework implements chaos engineering tests to validate the resilience and recovery capabilities of the AITBC platform.

## Overview

The chaos testing framework simulates real-world failure scenarios to:
- Test system resilience under adverse conditions
- Measure Mean-Time-To-Recovery (MTTR) metrics
- Identify single points of failure
- Validate recovery procedures
- Ensure SLO compliance

## Components

### Test Scripts

1. **`chaos_test_coordinator.py`** - Coordinator API outage simulation
   - Deletes coordinator pods to simulate complete service outage
   - Measures recovery time and service availability
   - Tests load handling during and after recovery

2. **`chaos_test_network.py`** - Network partition simulation
   - Creates network partitions between blockchain nodes
   - Tests consensus resilience during partition
   - Measures network recovery time

3. **`chaos_test_database.py`** - Database failure simulation
   - Simulates PostgreSQL connection failures
   - Tests high latency scenarios
   - Validates application error handling

4. **`chaos_orchestrator.py`** - Test orchestration and reporting
   - Runs multiple chaos test scenarios
   - Aggregates MTTR metrics across tests
   - Generates comprehensive reports
   - Supports continuous chaos testing

## Prerequisites

- Python 3.8+
- kubectl configured with cluster access
- Helm charts deployed in target namespace
- Administrative privileges for network manipulation

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd aitbc/infra/scripts

# Install dependencies
pip install aiohttp

# Make scripts executable
chmod +x chaos_*.py
```

## Usage

### Running Individual Tests

#### Coordinator Outage Test
```bash
# Basic test
python3 chaos_test_coordinator.py --namespace default

# Custom outage duration
python3 chaos_test_coordinator.py --namespace default --outage-duration 120

# Dry run (no actual chaos)
python3 chaos_test_coordinator.py --dry-run
```

#### Network Partition Test
```bash
# Partition 50% of nodes for 60 seconds
python3 chaos_test_network.py --namespace default

# Partition 30% of nodes for 90 seconds
python3 chaos_test_network.py --namespace default --partition-duration 90 --partition-ratio 0.3
```

#### Database Failure Test
```bash
# Simulate connection failure
python3 chaos_test_database.py --namespace default --failure-type connection

# Simulate high latency (5000ms)
python3 chaos_test_database.py --namespace default --failure-type latency
```

### Running All Tests

```bash
# Run all scenarios with default parameters
python3 chaos_orchestrator.py --namespace default

# Run specific scenarios
python3 chaos_orchestrator.py --namespace default --scenarios coordinator network

# Continuous chaos testing (24 hours, every 60 minutes)
python3 chaos_orchestrator.py --namespace default --continuous --duration 24 --interval 60
```

## Test Scenarios

### 1. Coordinator API Outage

**Objective**: Test system resilience when the coordinator service becomes unavailable.

**Steps**:
1. Generate baseline load on coordinator API
2. Delete all coordinator pods
3. Wait for specified outage duration
4. Monitor service recovery
5. Generate post-recovery load

**Metrics Collected**:
- MTTR (Mean-Time-To-Recovery)
- Success/error request counts
- Recovery time distribution

### 2. Network Partition

**Objective**: Test blockchain consensus during network partitions.

**Steps**:
1. Identify blockchain node pods
2. Apply iptables rules to partition nodes
3. Monitor consensus during partition
4. Remove network partition
5. Verify network recovery

**Metrics Collected**:
- Network recovery time
- Consensus health during partition
- Node connectivity status

### 3. Database Failure

**Objective**: Test application behavior when database is unavailable.

**Steps**:
1. Simulate database connection failure or high latency
2. Monitor API behavior during failure
3. Restore database connectivity
4. Verify application recovery

**Metrics Collected**:
- Database recovery time
- API error rates during failure
- Application resilience metrics

## Results and Reporting

### Test Results Format

Each test generates a JSON results file with the following structure:

```json
{
  "test_start": "2024-12-22T10:00:00.000Z",
  "test_end": "2024-12-22T10:05:00.000Z",
  "scenario": "coordinator_outage",
  "mttr": 45.2,
  "error_count": 156,
  "success_count": 844,
  "recovery_time": 45.2
}
```

### Orchestrator Report

The orchestrator generates a comprehensive report including:

- Summary metrics across all scenarios
- SLO compliance analysis
- Recommendations for improvements
- MTTR trends and statistics

Example report snippet:
```json
{
  "summary": {
    "total_scenarios": 3,
    "successful_scenarios": 3,
    "average_mttr": 67.8,
    "max_mttr": 120.5,
    "min_mttr": 45.2
  },
  "recommendations": [
    "Average MTTR exceeds 2 minutes. Consider improving recovery automation.",
    "Coordinator recovery is slow. Consider reducing pod startup time."
  ]
}
```

## SLO Targets

| Metric | Target | Current |
|--------|--------|---------|
| MTTR (Average) | ≤ 120 seconds | TBD |
| MTTR (Maximum) | ≤ 300 seconds | TBD |
| Success Rate | ≥ 99.9% | TBD |

## Best Practices

### Before Running Tests

1. **Backup Critical Data**: Ensure recent backups are available
2. **Notify Team**: Inform stakeholders about chaos testing
3. **Check Cluster Health**: Verify all components are healthy
4. **Schedule Appropriately**: Run during low-traffic periods

### During Tests

1. **Monitor Logs**: Watch for unexpected errors
2. **Have Rollback Plan**: Be ready to manually intervene
3. **Document Observations**: Note any unusual behavior
4. **Stop if Critical**: Abort tests if production is impacted

### After Tests

1. **Review Results**: Analyze MTTR and error rates
2. **Update Documentation**: Record findings and improvements
3. **Address Issues**: Fix any discovered problems
4. **Schedule Follow-up**: Plan regular chaos testing

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Chaos Testing
on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly at 2 AM Sunday
  workflow_dispatch:

jobs:
  chaos-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install aiohttp
      - name: Run chaos tests
        run: |
          cd infra/scripts
          python3 chaos_orchestrator.py --namespace staging
      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: chaos-results
          path: "*.json"
```

## Troubleshooting

### Common Issues

1. **kubectl not found**
   ```bash
   # Ensure kubectl is installed and configured
   which kubectl
   kubectl version
   ```

2. **Permission denied errors**
   ```bash
   # Check RBAC permissions
   kubectl auth can-i create pods --namespace default
   kubectl auth can-i exec pods --namespace default
   ```

3. **Network rules not applying**
   ```bash
   # Check if iptables is available in pods
   kubectl exec -it <pod> -- iptables -L
   ```

4. **Tests hanging**
   ```bash
   # Check pod status
   kubectl get pods --namespace default
   kubectl describe pod <pod-name> --namespace default
   ```

### Debug Mode

Enable debug logging:
```bash
export PYTHONPATH=.
python3 -u chaos_test_coordinator.py --namespace default 2>&1 | tee debug.log
```

## Contributing

To add new chaos test scenarios:

1. Create a new script following the naming pattern `chaos_test_<scenario>.py`
2. Implement the required methods: `run_test()`, `save_results()`
3. Add the scenario to `chaos_orchestrator.py`
4. Update documentation

## Security Considerations

- Chaos tests require elevated privileges
- Only run in authorized environments
- Ensure test isolation from production data
- Review network rules before deployment
- Monitor for security violations during tests

## Support

For issues or questions:
- Check the troubleshooting section
- Review test logs for error details
- Contact the DevOps team at devops@aitbc.io

## License

This chaos testing framework is part of the AITBC project and follows the same license terms.
