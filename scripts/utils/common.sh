#!/bin/bash
# ============================================================================
# AITBC Mesh Network Implementation - Shared Utilities
# ============================================================================
# This file contains common functions used by all phase scripts
# Source this file in other scripts: source /opt/aitbc/scripts/utils/common.sh
# ============================================================================

# Configuration
AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
CONFIG_DIR="${AITBC_ROOT}/config"
LOG_DIR="${AITBC_ROOT}/logs"
BACKUP_DIR="${AITBC_ROOT}/backups"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# Logging Functions
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
    log_to_file "INFO" "$1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    log_to_file "WARN" "$1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} "$1""
    log_to_file "ERROR" "$1"
}

log_debug() {
    if [[ "${DEBUG_MODE}" == "true" ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
        log_to_file "DEBUG" "$1"
    fi
}

log_to_file() {
    local level="$1"
    local message="$2"
    local script_name=$(basename "$0")
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local log_file="${LOG_DIR}/${script_name%.sh}.log"
    
    # Create log directory if it doesn't exist
    mkdir -p "${LOG_DIR}"
    
    # Append to log file
    echo "${timestamp} [${level}] ${message}" >> "${log_file}"
}

# ============================================================================
# Backup Functions
# ============================================================================

backup_directory() {
    local source_dir="$1"
    local backup_name="${2:-$(basename $source_dir)}"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="${BACKUP_DIR}/${backup_name}_backup_${timestamp}"
    
    log_info "Creating backup of ${source_dir}..."
    
    if [[ -d "$source_dir" ]]; then
        mkdir -p "${BACKUP_DIR}"
        cp -r "$source_dir" "$backup_path"
        log_info "Backup created: ${backup_path}"
        echo "$backup_path"  # Return backup path
        return 0
    else
        log_warn "Source directory does not exist: ${source_dir}"
        return 1
    fi
}

restore_backup() {
    local backup_path="$1"
    local target_dir="$2"
    
    log_info "Restoring backup from ${backup_path}..."
    
    if [[ -d "$backup_path" ]]; then
        rm -rf "$target_dir"
        cp -r "$backup_path" "$target_dir"
        log_info "Restored backup to ${target_dir}"
        return 0
    else
        log_error "Backup path does not exist: ${backup_path}"
        return 1
    fi
}

# ============================================================================
# Validation Functions
# ============================================================================

validate_directory() {
    local dir="$1"
    local create_if_missing="${2:-false}"
    
    if [[ ! -d "$dir" ]]; then
        if [[ "$create_if_missing" == "true" ]]; then
            mkdir -p "$dir"
            log_info "Created directory: ${dir}"
            return 0
        else
            log_error "Directory does not exist: ${dir}"
            return 1
        fi
    fi
    return 0
}

validate_file() {
    local file="$1"
    
    if [[ ! -f "$file" ]]; then
        log_error "File does not exist: ${file}"
        return 1
    fi
    return 0
}

validate_command() {
    local cmd="$1"
    
    if ! command -v "$cmd" &> /dev/null; then
        log_error "Required command not found: ${cmd}"
        return 1
    fi
    return 0
}

# ============================================================================
# Configuration Functions
# ============================================================================

create_config_file() {
    local config_name="$1"
    local config_content="$2"
    local config_path="${CONFIG_DIR}/${config_name}"
    
    # Create config directory if it doesn't exist
    mkdir -p "${CONFIG_DIR}"
    
    # Write config file
    echo "$config_content" > "$config_path"
    log_info "Created configuration file: ${config_path}"
}

load_config_file() {
    local config_name="$1"
    local config_path="${CONFIG_DIR}/${config_name}"
    
    if [[ -f "$config_path" ]]; then
        cat "$config_path"
        return 0
    else
        log_error "Configuration file not found: ${config_path}"
        return 1
    fi
}

# ============================================================================
# Progress Tracking
# ============================================================================

show_progress() {
    local current="$1"
    local total="$2"
    local message="${3:-Progress}"
    local percentage=$((current * 100 / total))
    local bar_length=50
    local filled=$((percentage * bar_length / 100))
    local empty=$((bar_length - filled))
    
    # Create progress bar
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="="; done
    for ((i=0; i<empty; i++)); do bar+=" "; done
    
    # Print progress
    printf "\r${BLUE}[%s]${NC} %s: %3d%% (%d/%d)" "$bar" "$message" "$percentage" "$current" "$total"
    
    # New line when complete
    if [[ $current -eq $total ]]; then
        echo ""
    fi
}

# ============================================================================
# Service Management
# ============================================================================

start_service() {
    local service_name="$1"
    local service_file="$2"
    
    log_info "Starting service: ${service_name}"
    
    if [[ -f "$service_file" ]]; then
        systemctl start "${service_name}"
        systemctl enable "${service_name}"
        log_info "Service ${service_name} started and enabled"
        return 0
    else
        log_error "Service file not found: ${service_file}"
        return 1
    fi
}

stop_service() {
    local service_name="$1"
    
    log_info "Stopping service: ${service_name}"
    
    systemctl stop "${service_name}" 2>/dev/null || true
    log_info "Service ${service_name} stopped"
}

restart_service() {
    local service_name="$1"
    
    log_info "Restarting service: ${service_name}"
    systemctl restart "${service_name}"
    log_info "Service ${service_name} restarted"
}

# ============================================================================
# Error Handling
# ============================================================================

handle_error() {
    local error_code="$1"
    local error_message="$2"
    
    log_error "Error ${error_code}: ${error_message}"
    
    # Log stack trace if DEBUG_MODE is enabled
    if [[ "${DEBUG_MODE}" == "true" ]]; then
        log_debug "Stack trace:"
        local i=0
        while caller $i; do
            ((i++))
        done | while read line file; do
            log_debug "  at ${file}:${line}"
        done
    fi
    
    exit "$error_code"
}

set_error_handling() {
    # Enable error handling
    set -e
    set -u
    set -o pipefail
    
    # Set error trap
    trap 'handle_error $? "Command failed at line $LINENO"' ERR
}

# ============================================================================
# Phase Management
# ============================================================================

mark_phase_complete() {
    local phase_name="$1"
    local completion_file="${CONFIG_DIR}/.completed_phases"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    mkdir -p "${CONFIG_DIR}"
    echo "${phase_name}:${timestamp}" >> "${completion_file}"
    log_info "Marked phase as complete: ${phase_name}"
}

check_phase_complete() {
    local phase_name="$1"
    local completion_file="${CONFIG_DIR}/.completed_phases"
    
    if [[ -f "$completion_file" ]]; then
        if grep -q "^${phase_name}:" "$completion_file"; then
            return 0  # Phase is complete
        fi
    fi
    return 1  # Phase not complete
}

get_completed_phases() {
    local completion_file="${CONFIG_DIR}/.completed_phases"
    
    if [[ -f "$completion_file" ]]; then
        cat "$completion_file" | cut -d: -f1
    fi
}

# ============================================================================
# Python Code Generation Helpers
# ============================================================================

create_python_module() {
    local module_path="$1"
    local module_content="$2"
    
    # Create directory structure
    local module_dir=$(dirname "$module_path")
    mkdir -p "$module_dir"
    
    # Write module
    echo "$module_content" > "$module_path"
    log_info "Created Python module: ${module_path}"
}

validate_python_syntax() {
    local python_file="$1"
    
    if python3 -m py_compile "$python_file" 2>/dev/null; then
        log_info "Python syntax validated: ${python_file}"
        return 0
    else
        log_error "Python syntax error in: ${python_file}"
        return 1
    fi
}

# ============================================================================
# Initialization
# ============================================================================

init_common() {
    # Set error handling
    set_error_handling
    
    # Create necessary directories
    mkdir -p "${CONFIG_DIR}"
    mkdir -p "${LOG_DIR}"
    mkdir -p "${BACKUP_DIR}"
    
    log_info "Common utilities initialized"
    log_info "AITBC Root: ${AITBC_ROOT}"
}

# Initialize if this script is sourced
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    init_common
fi
