# Development Logs Policy

## 📁 Log Location
All development logs should be stored in: `/opt/aitbc/dev/logs/`

## 🗂️ Directory Structure
```
dev/logs/
├── archive/          # Old logs by date
├── current/          # Current session logs
├── tools/            # Download logs, wget logs, etc.
├── cli/              # CLI operation logs
├── services/         # Service-related logs
└── temp/             # Temporary logs
```

## 🛡️ Prevention Measures
1. **Use log aliases**: `wgetlog`, `curllog`, `devlog`
2. **Environment variables**: `$AITBC_DEV_LOGS_DIR`
3. **Git ignore**: Prevents log files in project root
4. **Cleanup scripts**: `cleanlogs`, `archivelogs`

## 🚀 Quick Commands
```bash
# Load log environment
source /opt/aitbc/.env.dev

# Navigate to logs
devlogs              # Go to main logs directory
currentlogs          # Go to current session logs
toolslogs            # Go to tools logs
clilogs              # Go to CLI logs
serviceslogs         # Go to service logs

# Log operations
wgetlog <url>        # Download with proper logging
curllog <url>        # Curl with proper logging
devlog "message"     # Add dev log entry
cleanlogs            # Clean old logs
archivelogs          # Archive current logs

# View logs
./dev/logs/view-logs.sh tools    # View tools logs
./dev/logs/view-logs.sh recent   # View recent activity
```

## 📋 Best Practices
1. **Never** create log files in project root
2. **Always** use proper log directories
3. **Use** log aliases for common operations
4. **Clean** up old logs regularly
5. **Archive** important logs before cleanup

