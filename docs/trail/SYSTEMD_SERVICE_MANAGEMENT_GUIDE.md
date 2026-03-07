# 🔧 SystemD Service Management Guide

## ✅ **Proper Service Management Commands**

### **Service Status & Control**
```bash
# Check service status
systemctl status aitbc-coordinator --no-pager

# Start service
sudo systemctl start aitbc-coordinator

# Stop service
sudo systemctl stop aitbc-coordinator

# Restart service
sudo systemctl restart aitbc-coordinator

# Enable service (start on boot)
sudo systemctl enable aitbc-coordinator

# Disable service
sudo systemctl disable aitbc-coordinator
```

### **Log Management with journalctl**
```bash
# View recent logs
sudo journalctl -u aitbc-coordinator --since "10 minutes ago" --no-pager

# View all logs for service
sudo journalctl -u aitbc-coordinator --no-pager

# Follow live logs
sudo journalctl -u aitbc-coordinator -f

# View logs with lines limit
sudo journalctl -u aitbc-coordinator --since "1 hour ago" --no-pager | tail -20

# View logs for specific time range
sudo journalctl -u aitbc-coordinator --since "09:00" --until "10:00" --no-pager

# View logs with priority filtering
sudo journalctl -u aitbc-coordinator -p err --no-pager
sudo journalctl -u aitbc-coordinator -p warning --no-pager
```

### **Service Troubleshooting**
```bash
# Check service configuration
systemctl cat aitbc-coordinator

# Check service dependencies
systemctl list-dependencies aitbc-coordinator

# Check failed services
systemctl --failed

# Analyze service startup
systemd-analyze critical-chain aitbc-coordinator
```

---

## 🚀 **Current AITBC Service Setup**

### **Service Configuration**
```ini
[Unit]
Description=AITBC Coordinator API Service
Documentation=https://docs.aitbc.dev
After=network.target
Wants=network.target

[Service]
Type=simple
User=aitbc
Group=aitbc
WorkingDirectory=/home/oib/windsurf/aitbc/apps/coordinator-api
Environment=PYTHONPATH=/home/oib/windsurf/aitbc/apps/coordinator-api/src
EnvironmentFile=/home/oib/windsurf/aitbc/apps/coordinator-api/.env
ExecStart=/bin/bash -c 'cd /home/oib/windsurf/aitbc/apps/coordinator-api && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000'
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aitbc-coordinator

[Install]
WantedBy=multi-user.target
```

### **Service Features**
- ✅ **Automatic Restart**: Restarts on failure
- ✅ **Journal Logging**: All logs go to systemd journal
- ✅ **Environment Variables**: Proper PYTHONPATH set
- ✅ **User Isolation**: Runs as 'aitbc' user
- ✅ **Boot Startup**: Enabled for automatic start

---

## 📊 **Service Monitoring**

### **Health Check Commands**
```bash
# Service health
curl -s http://localhost:8000/health

# Service status summary
systemctl is-active aitbc-coordinator
systemctl is-enabled aitbc-coordinator
systemctl is-failed aitbc-coordinator

# Resource usage
systemctl status aitbc-coordinator --no-pager | grep -E "(Memory|CPU|Tasks)"
```

### **Log Analysis**
```bash
# Error logs only
sudo journalctl -u aitbc-coordinator -p err --since "1 hour ago"

# Warning and error logs
sudo journalctl -u aitbc-coordinator -p warning..err --since "1 hour ago"

# Performance logs
sudo journalctl -u aitbc-coordinator --since "1 hour ago" | grep -E "(memory|cpu|response)"

# API request logs
sudo journalctl -u aitbc-coordinator --since "1 hour ago" | grep "HTTP Request"
```

---

## 🔄 **Service Management Workflow**

### **Daily Operations**
```bash
# Morning check
systemctl status aitbc-coordinator --no-pager
sudo journalctl -u aitbc-coordinator --since "1 hour ago" --no-pager | tail -10

# Service restart (if needed)
sudo systemctl restart aitbc-coordinator
sleep 5
systemctl status aitbc-coordinator --no-pager

# Health verification
curl -s http://localhost:8000/health
```

### **Troubleshooting Steps**
```bash
# 1. Check service status
systemctl status aitbc-coordinator --no-pager

# 2. Check recent logs
sudo journalctl -u aitbc-coordinator --since "10 minutes ago" --no-pager

# 3. Check for errors
sudo journalctl -u aitbc-coordinator -p err --since "1 hour ago" --no-pager

# 4. Restart service if needed
sudo systemctl restart aitbc-coordinator

# 5. Verify functionality
curl -s http://localhost:8000/health
aitbc --test-mode marketplace gpu list
```

---

## 🎯 **Best Practices**

### **✅ DO:**
- Always use `systemctl` for service management
- Use `journalctl` for log viewing
- Check service status before making changes
- Use `--no-pager` for script-friendly output
- Enable services for automatic startup

### **❌ DON'T:**
- Don't kill processes manually (use systemctl stop)
- Don't start services directly (use systemctl start)
- Don't ignore journal logs
- Don't run services as root (unless required)
- Don't disable logging

---

## 📝 **Quick Reference**

| Command | Purpose |
|---------|---------|
| `systemctl status service` | Check status |
| `systemctl start service` | Start service |
| `systemctl stop service` | Stop service |
| `systemctl restart service` | Restart service |
| `journalctl -u service` | View logs |
| `journalctl -u service -f` | Follow logs |
| `systemctl enable service` | Enable on boot |
| `systemctl disable service` | Disable on boot |

---

**🎉 Always use systemctl and journalctl for proper AITBC service management!**
