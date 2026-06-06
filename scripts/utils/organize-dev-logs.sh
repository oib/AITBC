#!/bin/bash
#
# AITBC Development Logs Organization Script
# Organizes scattered logs and sets up prevention measures
#

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Configuration
PROJECT_ROOT="/opt/aitbc"
DEV_LOGS_DIR="$PROJECT_ROOT/dev/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Main execution
main() {
    print_header "AITBC Development Logs Organization"
    echo ""
    
    # Step 1: Create proper log structure
    print_header "Step 1: Creating Log Directory Structure"
    create_log_structure
    
    # Step 2: Move existing scattered logs
    print_header "Step 2: Moving Existing Logs"
    move_existing_logs
    
    # Step 3: Set up log prevention measures
    print_header "Step 3: Setting Up Prevention Measures"
    setup_prevention
    
    # Step 4: Create log management tools
    print_header "Step 4: Creating Log Management Tools"
    create_log_tools
    
    # Step 5: Configure environment
    print_header "Step 5: Configuring Environment"
    configure_environment
    
    print_header "Log Organization Complete! 🎉"
    echo ""
    echo "✅ Log structure created"
    echo "✅ Existing logs moved"
    echo "✅ Prevention measures in place"
    echo "✅ Management tools created"
    echo "✅ Environment configured"
    echo ""
    echo "📁 New Log Structure:"
    echo "  $DEV_LOGS_DIR/"
    echo "  ├── archive/          # Old logs by date"
    echo "  ├── current/          # Current session logs"
    echo "  ├── tools/            # Download logs, wget logs, etc."
    echo "  ├── cli/              # CLI operation logs"
    echo "  ├── services/         # Service-related logs"
    echo "  └── temp/             # Temporary logs"
    echo ""
    echo "🛡️ Prevention Measures:"
    echo "  • Log aliases configured"
    echo "  • Environment variables set"
    echo "  • Cleanup scripts created"
    echo "  • Git ignore rules updated"
}

# Create proper log directory structure
create_log_structure() {
    print_status "Creating log directory structure..."
    
    mkdir -p "$DEV_LOGS_DIR"/{archive,current,tools,cli,services,temp}
    
    # Create subdirectories with timestamps
    mkdir -p "$DEV_LOGS_DIR/archive/$(date +%Y)/$(date +%m)"
    mkdir -p "$DEV_LOGS_DIR/current/$(date +%Y-%m-%d)"
    
    print_status "Log structure created"
}

# Move existing scattered logs
move_existing_logs() {
    print_status "Moving existing scattered logs..."
    
    # Move wget-log if it exists and has content
    if [[ -f "$PROJECT_ROOT/wget-log" && -s "$PROJECT_ROOT/wget-log" ]]; then
        mv "$PROJECT_ROOT/wget-log" "$DEV_LOGS_DIR/tools/wget-log-$TIMESTAMP"
        print_status "Moved wget-log to tools directory"
    elif [[ -f "$PROJECT_ROOT/wget-log" ]]; then
        rm "$PROJECT_ROOT/wget-log"  # Remove empty file
        print_status "Removed empty wget-log"
    fi
    
    # Find and move other common log files
    local common_logs=("*.log" "*.out" "*.err" "download.log" "install.log" "build.log")
    
    for log_pattern in "${common_logs[@]}"; do
        find "$PROJECT_ROOT" -maxdepth 1 -name "$log_pattern" -type f 2>/dev/null | while read log_file; do
            if [[ -s "$log_file" ]]; then
                local filename=$(basename "$log_file")
                mv "$log_file" "$DEV_LOGS_DIR/tools/${filename%.*}-$TIMESTAMP.${filename##*.}"
                print_status "Moved $filename to tools directory"
            else
                rm "$log_file"
                print_status "Removed empty $filename"
            fi
        done
    done
    
    print_status "Existing logs organized"
}

# Set up prevention measures
setup_prevention() {
    print_status "Setting up log prevention measures..."
    
    # Create log aliases
    cat > "$PROJECT_ROOT/.env.dev.logs" << 'EOF'
# AITBC Development Log Environment
export AITBC_DEV_LOGS_DIR="/opt/aitbc/dev/logs"
export AITBC_CURRENT_LOG_DIR="$AITBC_DEV_LOGS_DIR/current/$(date +%Y-%m-%d)"
export AITBC_TOOLS_LOG_DIR="$AITBC_DEV_LOGS_DIR/tools"
export AITBC_CLI_LOG_DIR="$AITBC_DEV_LOGS_DIR/cli"
export AITBC_SERVICES_LOG_DIR="$AITBC_DEV_LOGS_DIR/services"

# Log aliases
alias devlogs="cd $AITBC_DEV_LOGS_DIR"
alias currentlogs="cd $AITBC_CURRENT_LOG_DIR"
alias toolslogs="cd $AITBC_TOOLS_LOG_DIR"
alias clilogs="cd $AITBC_CLI_LOG_DIR"
alias serviceslogs="cd $AITBC_SERVICES_LOG_DIR"

# Common log commands
alias wgetlog="wget -o $AITBC_TOOLS_LOG_DIR/wget-log-$(date +%Y%m%d_%H%M%S).log"
alias curllog="curl -o $AITBC_TOOLS_LOG_DIR/curl-log-$(date +%Y%m%d_%H%M%S).log"
alias devlog="echo '[$(date +%Y-%m-%d %H:%M:%S)]' >> $AITBC_CURRENT_LOG_DIR/dev-session-$(date +%Y%m%d).log"

# Log cleanup
alias cleanlogs="find $AITBC_DEV_LOGS_DIR -name '*.log' -mtime +7 -delete"
alias archivelogs="find $AITBC_DEV_LOGS_DIR/current -name '*.log' -mtime +1 -exec mv {} $AITBC_DEV_LOGS_DIR/archive/$(date +%Y)/$(date +%m)/ \;"
EOF
    
    # Update main .env.dev to include log environment
    if [[ -f "$PROJECT_ROOT/.env.dev" ]]; then
        if ! grep -q "AITBC_DEV_LOGS_DIR" "$PROJECT_ROOT/.env.dev"; then
            echo "" >> "$PROJECT_ROOT/.env.dev"
            echo "# Development Logs Environment" >> "$PROJECT_ROOT/.env.dev"
            echo "source /opt/aitbc/.env.dev.logs" >> "$PROJECT_ROOT/.env.dev"
        fi
    fi
    
    print_status "Log aliases and environment configured"
}

# Create log management tools
create_log_tools() {
    print_status "Creating log management tools..."
    
    # Log organizer script
    cat > "$DEV_LOGS_DIR/organize-logs.sh" << 'EOF'
#!/bin/bash
# AITBC Log Organizer Script

DEV_LOGS_DIR="/opt/aitbc/dev/logs"

echo "🔧 Organizing AITBC Development Logs..."

# Move logs from project root to proper locations
find /opt/aitbc -maxdepth 1 -name "*.log" -type f | while read log_file; do
    if [[ -s "$log_file" ]]; then
        filename=$(basename "$log_file")
        timestamp=$(date +%Y%m%d_%H%M%S)
        mv "$log_file" "$DEV_LOGS_DIR/tools/${filename%.*}-$timestamp.${filename##*.}"
        echo "✅ Moved $filename"
    else
        rm "$log_file"
        echo "🗑️  Removed empty $filename"
    fi
done

echo "🎉 Log organization complete!"
EOF
    
    # Log cleanup script
    cat > "$DEV_LOGS_DIR/cleanup-logs.sh" << 'EOF'
#!/bin/bash
# AITBC Log Cleanup Script

DEV_LOGS_DIR="/opt/aitbc/dev/logs"

echo "🧹 Cleaning up AITBC Development Logs..."

# Remove logs older than 7 days
find "$DEV_LOGS_DIR" -name "*.log" -mtime +7 -delete

# Archive current logs older than 1 day
find "$DEV_LOGS_DIR/current" -name "*.log" -mtime +1 -exec mv {} "$DEV_LOGS_DIR/archive/$(date +%Y)/$(date +%m)/" \;

# Remove empty directories
find "$DEV_LOGS_DIR" -type d -empty -delete

echo "✅ Log cleanup complete!"
EOF
    
    # Log viewer script
    cat > "$DEV_LOGS_DIR/view-logs.sh" << 'EOF'
#!/bin/bash
# AITBC Log Viewer Script

DEV_LOGS_DIR="/opt/aitbc/dev/logs"

case "${1:-help}" in
    "tools")
        echo "🔧 Tools Logs:"
        ls -la "$DEV_LOGS_DIR/tools/" | tail -10
        ;;
    "current")
        echo "📋 Current Logs:"
        ls -la "$DEV_LOGS_DIR/current/" | tail -10
        ;;
    "cli")
        echo "💻 CLI Logs:"
        ls -la "$DEV_LOGS_DIR/cli/" | tail -10
        ;;
    "services")
        echo "🔧 Service Logs:"
        ls -la "$DEV_LOGS_DIR/services/" | tail -10
        ;;
    "recent")
        echo "📊 Recent Activity:"
        find "$DEV_LOGS_DIR" -name "*.log" -mtime -1 -exec ls -la {} \;
        ;;
    "help"|*)
        echo "🔍 AITBC Log Viewer"
        echo ""
        echo "Usage: $0 {tools|current|cli|services|recent|help}"
        echo ""
        echo "Commands:"
        echo "  tools    - Show tools directory logs"
        echo "  current  - Show current session logs"
        echo "  cli      - Show CLI operation logs"
        echo "  services - Show service-related logs"
        echo "  recent   - Show recent log activity"
        echo "  help     - Show this help message"
        ;;
esac
EOF
    
    # Make scripts executable
    chmod +x "$DEV_LOGS_DIR"/*.sh
    
    print_status "Log management tools created"
}

# Configure environment
configure_environment() {
    print_status "Configuring environment for log management..."
    
    # Update .gitignore to prevent log files in root
    if [[ -f "$PROJECT_ROOT/.gitignore" ]]; then
        if ! grep -q "# Development logs" "$PROJECT_ROOT/.gitignore"; then
            echo "" >> "$PROJECT_ROOT/.gitignore"
            echo "# Development logs - keep in dev/logs/" >> "$PROJECT_ROOT/.gitignore"
            echo "*.log" >> "$PROJECT_ROOT/.gitignore"
            echo "*.out" >> "$PROJECT_ROOT/.gitignore"
            echo "*.err" >> "$PROJECT_ROOT/.gitignore"
            echo "wget-log" >> "$PROJECT_ROOT/.gitignore"
            echo "download.log" >> "$PROJECT_ROOT/.gitignore"
        fi
    fi
    
    # Create a log prevention reminder
    cat > "$PROJECT_ROOT/DEV_LOGS.md" << 'EOF'
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

EOF
    
    print_status "Environment configured"
}

# Run main function
main "$@"
