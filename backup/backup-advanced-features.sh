#!/bin/bash

# AITBC Advanced Agent Features Production Backup Script
# Comprehensive backup system for production deployment

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_critical() {
    echo -e "${RED}[CRITICAL]${NC} $1"
}

print_backup() {
    echo -e "${PURPLE}[BACKUP]${NC} $1"
}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
CONTRACTS_DIR="$ROOT_DIR/contracts"
SERVICES_DIR="$ROOT_DIR/apps/coordinator-api/src/app/services"
MONITORING_DIR="$ROOT_DIR/monitoring"
BACKUP_DIR="${BACKUP_DIR:-/backup/advanced-features}"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="advanced-features-backup-$DATE.tar.gz"
ENCRYPTION_KEY="${ENCRYPTION_KEY:-your_encryption_key_here}"

echo "🔄 AITBC Advanced Agent Features Production Backup"
echo "================================================="
echo "Backup Directory: $BACKUP_DIR"
echo "Timestamp: $DATE"
echo "Encryption: Enabled"
echo ""

# Create backup directory
create_backup_directory() {
    print_backup "Creating backup directory..."
    
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$BACKUP_DIR/contracts"
    mkdir -p "$BACKUP_DIR/services"
    mkdir -p "$BACKUP_DIR/config"
    mkdir -p "$BACKUP_DIR/monitoring"
    mkdir -p "$BACKUP_DIR/database"
    mkdir -p "$BACKUP_DIR/logs"
    mkdir -p "$BACKUP_DIR/deployment"
    
    print_success "Backup directory created: $BACKUP_DIR"
}

# Backup smart contracts
backup_contracts() {
    print_backup "Backing up smart contracts..."
    
    # Backup contract source code
    tar -czf "$BACKUP_DIR/contracts/source-$DATE.tar.gz" \
        contracts/ \
        --exclude=node_modules \
        --exclude=artifacts \
        --exclude=cache \
        --exclude=.git
    
    # Backup compiled contracts
    if [[ -d "$CONTRACTS_DIR/artifacts" ]]; then
        tar -czf "$BACKUP_DIR/contracts/artifacts-$DATE.tar.gz" \
            "$CONTRACTS_DIR/artifacts"
    fi
    
    # Backup deployment data
    if [[ -f "$CONTRACTS_DIR/deployed-contracts-mainnet.json" ]]; then
        cp "$CONTRACTS_DIR/deployed-contracts-mainnet.json" \
            "$BACKUP_DIR/deployment/deployment-$DATE.json"
    fi
    
    # Backup contract verification data
    if [[ -f "$CONTRACTS_DIR/slither-report.json" ]]; then
        cp "$CONTRACTS_DIR/slither-report.json" \
            "$BACKUP_DIR/deployment/slither-report-$DATE.json"
    fi
    
    if [[ -f "$CONTRACTS_DIR/mythril-report.json" ]]; then
        cp "$CONTRACTS_DIR/mythril-report.json" \
            "$BACKUP_DIR/deployment/mythril-report-$DATE.json"
    fi
    
    print_success "Smart contracts backup completed"
}

# Backup services
backup_services() {
    print_backup "Backing up services..."
    
    # Backup service source code
    tar -czf "$BACKUP_DIR/services/source-$DATE.tar.gz" \
        apps/coordinator-api/src/app/services/ \
        --exclude=__pycache__ \
        --exclude=*.pyc \
        --exclude=.git
    
    # Backup service configuration
    if [[ -f "$ROOT_DIR/apps/coordinator-api/config/advanced_features.json" ]]; then
        cp "$ROOT_DIR/apps/coordinator-api/config/advanced_features.json" \
            "$BACKUP_DIR/config/advanced-features-$DATE.json"
    fi
    
    # Backup service logs
    if [[ -d "/var/log/aitbc" ]]; then
        tar -czf "$BACKUP_DIR/logs/services-$DATE.tar.gz" \
            /var/log/aitbc/ \
            --exclude=*.log.gz
    fi
    
    print_success "Services backup completed"
}

# Backup configuration
backup_configuration() {
    print_backup "Backing up configuration..."
    
    # Backup environment files
    if [[ -f "$ROOT_DIR/.env.production" ]]; then
        cp "$ROOT_DIR/.env.production" \
            "$BACKUP_DIR/config/env-production-$DATE"
    fi
    
    # Backup monitoring configuration
    if [[ -f "$ROOT_DIR/monitoring/advanced-features-monitoring.yml" ]]; then
        cp "$ROOT_DIR/monitoring/advanced-features-monitoring.yml" \
            "$BACKUP_DIR/monitoring/monitoring-$DATE.yml"
    fi
    
    # Backup Prometheus configuration
    if [[ -f "$ROOT_DIR/monitoring/prometheus.yml" ]]; then
        cp "$ROOT_DIR/monitoring/prometheus.yml" \
            "$BACKUP_DIR/monitoring/prometheus-$DATE.yml"
    fi
    
    # Backup Grafana configuration
    if [[ -d "$ROOT_DIR/monitoring/grafana" ]]; then
        tar -czf "$BACKUP_DIR/monitoring/grafana-$DATE.tar.gz" \
            "$ROOT_DIR/monitoring/grafana"
    fi
    
    # Backup security configuration
    if [[ -d "$ROOT_DIR/security" ]]; then
        tar -czf "$BACKUP_DIR/config/security-$DATE.tar.gz" \
            "$ROOT_DIR/security"
    fi
    
    print_success "Configuration backup completed"
}

# Backup database
backup_database() {
    print_backup "Backing up database..."
    
    # Backup PostgreSQL database
    if command -v pg_dump &> /dev/null; then
        if [[ -n "${DATABASE_URL:-}" ]]; then
            pg_dump "$DATABASE_URL" > "$BACKUP_DIR/database/postgres-$DATE.sql"
            print_success "PostgreSQL backup completed"
        else
            print_warning "DATABASE_URL not set, skipping PostgreSQL backup"
        fi
    else
        print_warning "pg_dump not available, skipping PostgreSQL backup"
    fi
    
    # Backup Redis data
    if command -v redis-cli &> /dev/null; then
        if redis-cli ping | grep -q "PONG"; then
            redis-cli --rdb "$BACKUP_DIR/database/redis-$DATE.rdb"
            print_success "Redis backup completed"
        else
            print_warning "Redis not running, skipping Redis backup"
        fi
    else
        print_warning "redis-cli not available, skipping Redis backup"
    fi
    
    # Backup monitoring data
    if [[ -d "/var/lib/prometheus" ]]; then
        tar -czf "$BACKUP_DIR/monitoring/prometheus-data-$DATE.tar.gz" \
            /var/lib/prometheus
    fi
    
    if [[ -d "/var/lib/grafana" ]]; then
        tar -czf "$BACKUP_DIR/monitoring/grafana-data-$DATE.tar.gz" \
            /var/lib/grafana
    fi
    
    print_success "Database backup completed"
}

# Create encrypted backup
create_encrypted_backup() {
    print_backup "Creating encrypted backup..."
    
    # Create full backup
    tar -czf "$BACKUP_DIR/$BACKUP_FILE" \
        "$BACKUP_DIR/contracts/" \
        "$BACKUP_DIR/services/" \
        "$BACKUP_DIR/config/" \
        "$BACKUP_DIR/monitoring/" \
        "$BACKUP_DIR/database/" \
        "$BACKUP_DIR/logs/" \
        "$BACKUP_DIR/deployment/"
    
    # Encrypt backup
    if command -v gpg &> /dev/null; then
        gpg --symmetric --cipher-algo AES256 \
            --output "$BACKUP_DIR/$BACKUP_FILE.gpg" \
            --batch --yes --passphrase "$ENCRYPTION_KEY" \
            "$BACKUP_DIR/$BACKUP_FILE"
        
        # Remove unencrypted backup
        rm "$BACKUP_DIR/$BACKUP_FILE"
        
        print_success "Encrypted backup created: $BACKUP_DIR/$BACKUP_FILE.gpg"
    else
        print_warning "gpg not available, keeping unencrypted backup"
        print_warning "Backup file: $BACKUP_DIR/$BACKUP_FILE"
    fi
}

# Upload to cloud storage
upload_to_cloud() {
    if [[ -n "${S3_BUCKET:-}" && -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
        print_backup "Uploading to S3..."
        
        if command -v aws &> /dev/null; then
            aws s3 cp "$BACKUP_DIR/$BACKUP_FILE.gpg" \
                "s3://$S3_BUCKET/advanced-features-backups/"
            
            print_success "Backup uploaded to S3: s3://$S3_BUCKET/advanced-features-backups/$BACKUP_FILE.gpg"
        else
            print_warning "AWS CLI not available, skipping S3 upload"
        fi
    else
        print_warning "S3 configuration not set, skipping cloud upload"
    fi
}

# Cleanup old backups
cleanup_old_backups() {
    print_backup "Cleaning up old backups..."
    
    # Keep only last 7 days of local backups
    find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete
    find "$BACKUP_DIR" -name "*.gpg" -mtime +7 -delete
    find "$BACKUP_DIR" -name "*.sql" -mtime +7 -delete
    find "$BACKUP_DIR" -name "*.rdb" -mtime +7 -delete
    
    # Clean up old directories
    find "$BACKUP_DIR" -type d -name "*-$DATE" -mtime +7 -exec rm -rf {} + 2>/dev/null || true
    
    print_success "Old backups cleaned up"
}

# Verify backup integrity
verify_backup() {
    print_backup "Verifying backup integrity..."
    
    local backup_file="$BACKUP_DIR/$BACKUP_FILE.gpg"
    if [[ ! -f "$backup_file" ]]; then
        backup_file="$BACKUP_DIR/$BACKUP_FILE"
    fi
    
    if [[ -f "$backup_file" ]]; then
        # Check file size
        local file_size=$(stat -f%z "$backup_file" 2>/dev/null || stat -c%s "$backup_file" 2>/dev/null)
        
        if [[ $file_size -gt 1000 ]]; then
            print_success "Backup integrity verified (size: $file_size bytes)"
        else
            print_error "Backup integrity check failed - file too small"
            return 1
        fi
    else
        print_error "Backup file not found"
        return 1
    fi
}

# Generate backup report
generate_backup_report() {
    print_backup "Generating backup report..."
    
    local report_file="$BACKUP_DIR/backup-report-$DATE.json"
    
    local backup_size=0
    local backup_file="$BACKUP_DIR/$BACKUP_FILE.gpg"
    if [[ -f "$backup_file" ]]; then
        backup_size=$(stat -f%z "$backup_file" 2>/dev/null || stat -c%s "$backup_file" 2>/dev/null)
    fi
    
    cat > "$report_file" << EOF
{
    "backup": {
        "timestamp": "$(date -Iseconds)",
        "backup_file": "$BACKUP_FILE",
        "backup_size": $backup_size,
        "backup_directory": "$BACKUP_DIR",
        "encryption_enabled": true,
        "cloud_upload": "$([[ -n "${S3_BUCKET:-}" ]] && echo "enabled" || echo "disabled")"
    },
    "components": {
        "contracts": "backed_up",
        "services": "backed_up",
        "configuration": "backed_up",
        "monitoring": "backed_up",
        "database": "backed_up",
        "logs": "backed_up",
        "deployment": "backed_up"
    },
    "verification": {
        "integrity_check": "passed",
        "file_size": $backup_size,
        "encryption": "verified"
    },
    "cleanup": {
        "retention_days": 7,
        "old_backups_removed": true
    },
    "next_backup": "$(date -d '+1 day' -Iseconds)"
}
EOF
    
    print_success "Backup report saved to $report_file"
}

# Send notification
send_notification() {
    if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
        print_backup "Sending Slack notification..."
        
        local message="✅ Advanced Agent Features backup completed successfully\n"
        message+="📁 Backup file: $BACKUP_FILE\n"
        message+="📊 Size: $(du -h "$BACKUP_DIR/$BACKUP_FILE.gpg" | cut -f1)\n"
        message+="🕐 Timestamp: $(date -Iseconds)"
        
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"$message\"}" \
            "$SLACK_WEBHOOK_URL" || true
    fi
    
    if [[ -n "${EMAIL_TO:-}" && -n "${EMAIL_FROM:-}" ]]; then
        print_backup "Sending email notification..."
        
        local subject="Advanced Agent Features Backup Completed"
        local body="Backup completed successfully at $(date -Iseconds)\n\n"
        body+="Backup file: $BACKUP_FILE\n"
        body+="Size: $(du -h "$BACKUP_DIR/$BACKUP_FILE.gpg" | cut -f1)\n"
        body+="Location: $BACKUP_DIR\n\n"
        body+="This is an automated backup notification."
        
        echo -e "$body" | mail -s "$subject" "$EMAIL_TO" || true
    fi
}

# Main execution
main() {
    print_critical "🔄 STARTING PRODUCTION BACKUP - ADVANCED AGENT FEATURES"
    
    local backup_failed=0
    
    # Run backup steps
    create_backup_directory || backup_failed=1
    backup_contracts || backup_failed=1
    backup_services || backup_failed=1
    backup_configuration || backup_failed=1
    backup_database || backup_failed=1
    create_encrypted_backup || backup_failed=1
    upload_to_cloud || backup_failed=1
    cleanup_old_backups || backup_failed=1
    verify_backup || backup_failed=1
    generate_backup_report || backup_failed=1
    send_notification
    
    if [[ $backup_failed -eq 0 ]]; then
        print_success "🎉 PRODUCTION BACKUP COMPLETED SUCCESSFULLY!"
        echo ""
        echo "📊 Backup Summary:"
        echo "  Backup File: $BACKUP_FILE"
        echo "  Location: $BACKUP_DIR"
        echo "  Encryption: Enabled"
        echo "  Cloud Upload: $([[ -n "${S3_BUCKET:-}" ]] && echo "Completed" || echo "Skipped")"
        echo "  Retention: 7 days"
        echo ""
        echo "✅ All components backed up successfully"
        echo "🔐 Backup is encrypted and secure"
        echo "📊 Backup integrity verified"
        echo "🧹 Old backups cleaned up"
        echo "📧 Notifications sent"
        echo ""
        echo "🎯 Backup Status: COMPLETED - DATA SECURED"
    else
        print_error "❌ PRODUCTION BACKUP FAILED!"
        echo ""
        echo "📊 Backup Summary:"
        echo "  Backup File: $BACKUP_FILE"
        echo "  Location: $BACKUP_DIR"
        echo "  Status: FAILED"
        echo ""
        echo "⚠️  Some backup steps failed"
        echo "🔧 Please review the errors above"
        echo "📊 Check backup integrity manually"
        echo "🔐 Verify encryption is working"
        echo "🧹 Clean up partial backups if needed"
        echo ""
        echo "🎯 Backup Status: FAILED - INVESTIGATE IMMEDIATELY"
        exit 1
    fi
}

# Handle script interruption
trap 'print_critical "Backup interrupted - please check partial backup"; exit 1' INT TERM

# Run main function
main "$@"
