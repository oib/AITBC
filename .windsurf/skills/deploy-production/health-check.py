#!/usr/bin/env python3
"""
AITBC Production Health Check Script
Verifies the health of all AITBC services after deployment
"""

import requests
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Tuple

# Configuration
SERVICES = {
    "coordinator": {
        "url": "http://localhost:8080/health",
        "expected_status": 200,
        "timeout": 10
    },
    "blockchain-node": {
        "url": "http://localhost:8545",
        "method": "POST",
        "payload": {
            "jsonrpc": "2.0",
            "method": "eth_blockNumber",
            "params": [],
            "id": 1
        },
        "expected_status": 200,
        "timeout": 10
    },
    "dashboard": {
        "url": "https://aitbc.io/health",
        "expected_status": 200,
        "timeout": 10
    },
    "api": {
        "url": "https://api.aitbc.io/v1/status",
        "expected_status": 200,
        "timeout": 10
    },
    "miner": {
        "url": "http://localhost:8081/api/status",
        "expected_status": 200,
        "timeout": 10
    }
}

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'

def print_status(message: str, status: str = "INFO"):
    """Print colored status message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if status == "SUCCESS":
        print(f"{Colors.GREEN}[✓]{Colors.ENDC} {timestamp} - {message}")
    elif status == "ERROR":
        print(f"{Colors.RED}[✗]{Colors.ENDC} {timestamp} - {message}")
    elif status == "WARNING":
        print(f"{Colors.YELLOW}[⚠]{Colors.ENDC} {timestamp} - {message}")
    else:
        print(f"{Colors.BLUE}[ℹ]{Colors.ENDC} {timestamp} - {message}")

def check_service(name: str, config: Dict) -> Tuple[bool, str]:
    """Check individual service health"""
    try:
        method = config.get('method', 'GET')
        timeout = config.get('timeout', 10)
        expected_status = config.get('expected_status', 200)
        
        if method == 'POST':
            response = requests.post(
                config['url'],
                json=config.get('payload', {}),
                timeout=timeout,
                headers={'Content-Type': 'application/json'}
            )
        else:
            response = requests.get(config['url'], timeout=timeout)
        
        if response.status_code == expected_status:
            # Additional checks for specific services
            if name == "blockchain-node":
                data = response.json()
                if 'result' in data:
                    block_number = int(data['result'], 16)
                    return True, f"Block number: {block_number}"
                return False, "Invalid response format"
            
            elif name == "coordinator":
                data = response.json()
                if data.get('status') == 'healthy':
                    return True, f"Version: {data.get('version', 'unknown')}"
                return False, f"Status: {data.get('status')}"
            
            return True, f"Status: {response.status_code}"
        else:
            return False, f"HTTP {response.status_code}"
            
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused"
    except Exception as e:
        return False, str(e)

def check_database() -> Tuple[bool, str]:
    """Check database connectivity"""
    try:
        # This would use your actual database connection
        import psycopg2
        conn = psycopg2.connect(
            host="localhost",
            database="aitbc_prod",
            user="postgres",
            password="your_password"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return True, "Database connected"
    except Exception as e:
        return False, str(e)

def check_redis() -> Tuple[bool, str]:
    """Check Redis connectivity"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        return True, "Redis connected"
    except Exception as e:
        return False, str(e)

def check_disk_space() -> Tuple[bool, str]:
    """Check disk space usage"""
    import shutil
    total, used, free = shutil.disk_usage("/")
    percent_used = (used / total) * 100
    if percent_used < 80:
        return True, f"Disk usage: {percent_used:.1f}%"
    else:
        return False, f"Disk usage critical: {percent_used:.1f}%"

def check_ssl_certificates() -> Tuple[bool, str]:
    """Check SSL certificate validity"""
    import ssl
    import socket
    from datetime import datetime
    
    try:
        context = ssl.create_default_context()
        with socket.create_connection(("aitbc.io", 443)) as sock:
            with context.wrap_socket(sock, server_hostname="aitbc.io") as ssock:
                cert = ssock.getpeercert()
                expiry_date = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                days_until_expiry = (expiry_date - datetime.now()).days
                
                if days_until_expiry > 7:
                    return True, f"SSL valid for {days_until_expiry} days"
                else:
                    return False, f"SSL expires in {days_until_expiry} days"
    except Exception as e:
        return False, str(e)

def main():
    """Main health check function"""
    print_status("Starting AITBC Production Health Check", "INFO")
    print("=" * 60)
    
    all_passed = True
    failed_services = []
    
    # Check all services
    print_status("\n=== Service Health Checks ===")
    for name, config in SERVICES.items():
        success, message = check_service(name, config)
        if success:
            print_status(f"{name}: {message}", "SUCCESS")
        else:
            print_status(f"{name}: {message}", "ERROR")
            all_passed = False
            failed_services.append(name)
    
    # Check infrastructure components
    print_status("\n=== Infrastructure Checks ===")
    
    # Database
    db_success, db_message = check_database()
    if db_success:
        print_status(f"Database: {db_message}", "SUCCESS")
    else:
        print_status(f"Database: {db_message}", "ERROR")
        all_passed = False
    
    # Redis
    redis_success, redis_message = check_redis()
    if redis_success:
        print_status(f"Redis: {redis_message}", "SUCCESS")
    else:
        print_status(f"Redis: {redis_message}", "ERROR")
        all_passed = False
    
    # Disk space
    disk_success, disk_message = check_disk_space()
    if disk_success:
        print_status(f"Disk: {disk_message}", "SUCCESS")
    else:
        print_status(f"Disk: {disk_message}", "ERROR")
        all_passed = False
    
    # SSL certificates
    ssl_success, ssl_message = check_ssl_certificates()
    if ssl_success:
        print_status(f"SSL: {ssl_message}", "SUCCESS")
    else:
        print_status(f"SSL: {ssl_message}", "ERROR")
        all_passed = False
    
    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print_status("All checks passed! System is healthy.", "SUCCESS")
        sys.exit(0)
    else:
        print_status(f"Health check failed! Failed services: {', '.join(failed_services)}", "ERROR")
        print_status("Please check the logs and investigate the issues.", "WARNING")
        sys.exit(1)

if __name__ == "__main__":
    main()
