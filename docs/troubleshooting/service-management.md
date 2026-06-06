# Service Management Troubleshooting

This guide covers service management issues including service startup, configuration, permissions, and resource monitoring.

## Service Won't Start

**Symptoms:**
- Service fails to start
- Systemd service shows "failed" status
- No logs available

**Diagnosis:**
```bash
# Check service status
systemctl status aitbc-coordinator-api

# Check recent logs
journalctl -u aitbc-coordinator-api -n 50

# Check for errors in logs
journalctl -u aitbc-coordinator-api -f | grep -i error
```

**Solutions:**
1. Check configuration files
```bash
# Validate configuration
python -m apps.coordinator_api.main --validate-config
```

2. Check port conflicts
```bash
# Check if port is in use
netstat -tulpn | grep 8203

# Kill process using the port
kill -9 $(lsof -t -i:8203)
```

3. Check permissions
```bash
# Check file permissions
ls -la /opt/aitbc

# Fix permissions
chown -R aitbc:aitbc /opt/aitbc
```

4. Check dependencies
```bash
# Verify Python dependencies
source venv/bin/activate
pip list

# Install missing dependencies
pip install -r requirements.txt
```

## High CPU Usage

**Symptoms:**
- Service consuming excessive CPU
- System sluggish
- High load averages

**Diagnosis:**
```bash
# Check CPU usage
top -p $(pgrep -f coordinator-api)

# Check process details
ps aux | grep coordinator-api

# Check system load
uptime
```

**Solutions:**
1. Profile the application
```bash
# Profile with cProfile
python -m cProfile -o profile.stats apps/coordinator_api/main.py

# Analyze profile
python -m pstats profile.stats
```

2. Check for infinite loops
```bash
# Monitor process strace
strace -p $(pgrep -f coordinator-api)
```

3. Optimize database queries
```bash
# Enable query logging
export SQLALCHEMY_ECHO=true

# Analyze slow queries
psql -d aitbc -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

## Memory Leaks

**Symptoms:**
- Memory usage increases over time
- Service crashes with OOM killer
- Swap usage high

**Diagnosis:**
```bash
# Check memory usage
free -h

# Check process memory
ps aux | grep coordinator-api

# Monitor memory over time
watch -n 1 'free -h'
```

**Solutions:**
1. Check for memory leaks
```bash
# Use memory profiler
pip install memory-profiler
python -m memory_profiler apps/coordinator_api/main.py
```

2. Check connection pooling
```python
# Reduce pool size
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10
)
```

3. Restart service periodically
```bash
# Add to crontab
0 2 * * * systemctl restart aitbc-coordinator-api
```

## See Also

- [Database Issues](database-issues.md) - Database connection and performance issues
- [Performance Issues](performance-issues.md) - High CPU, memory, disk I/O issues
- [Network Issues](network-issues.md) - Network connectivity problems
