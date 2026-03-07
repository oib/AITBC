#!/usr/bin/env python3
"""
Deploy Enhanced Genesis Block with New Features
"""

import sys
import os
import subprocess
import yaml
from datetime import datetime

def load_genesis_config(config_path):
    """Load genesis configuration"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def deploy_to_container(container_name, genesis_config):
    """Deploy genesis block to container"""
    print(f"🚀 Deploying enhanced genesis to {container_name}...")
    
    # Copy genesis file to container
    subprocess.run([
        'scp', 
        '/home/oib/windsurf/aitbc/genesis_enhanced_devnet.yaml',
        f'{container_name}:/opt/aitbc/genesis_enhanced_devnet.yaml'
    ], check=True)
    
    # Stop blockchain services
    print(f"⏹️  Stopping blockchain services on {container_name}...")
    subprocess.run([
        'ssh', container_name, 
        'sudo systemctl stop aitbc-blockchain-node.service aitbc-blockchain-rpc.service'
    ], check=False)  # Don't fail if services aren't running
    
    # Clear existing blockchain data
    print(f"🧹 Clearing existing blockchain data on {container_name}...")
    subprocess.run([
        'ssh', container_name,
        'sudo rm -f /opt/aitbc/apps/blockchain-node/data/chain.db'
    ], check=False)
    
    # Initialize new genesis
    print(f"🔧 Initializing enhanced genesis on {container_name}...")
    result = subprocess.run([
        'ssh', container_name,
        'cd /opt/aitbc/apps/blockchain-node && python create_genesis.py --config /opt/aitbc/genesis_enhanced_devnet.yaml'
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ Genesis initialization successful on {container_name}")
        print(f"Output: {result.stdout}")
    else:
        print(f"❌ Genesis initialization failed on {container_name}")
        print(f"Error: {result.stderr}")
        return False
    
    # Start blockchain services
    print(f"▶️  Starting blockchain services on {container_name}...")
    subprocess.run([
        'ssh', container_name,
        'sudo systemctl start aitbc-blockchain-node.service aitbc-blockchain-rpc.service'
    ], check=True)
    
    # Wait for services to start
    import time
    time.sleep(5)
    
    # Verify genesis block
    print(f"🔍 Verifying genesis block on {container_name}...")
    result = subprocess.run([
        'ssh', container_name,
        'curl -s http://localhost:8005/rpc/head'
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ Genesis verification successful on {container_name}")
        print(f"Response: {result.stdout}")
        return True
    else:
        print(f"❌ Genesis verification failed on {container_name}")
        print(f"Error: {result.stderr}")
        return False

def enable_new_services(container_name):
    """Enable new enhanced services"""
    print(f"🔧 Enabling enhanced services on {container_name}...")
    
    services = [
        'aitbc-explorer.service',
        'aitbc-marketplace-enhanced.service',
    ]
    
    for service in services:
        try:
            subprocess.run([
                'ssh', container_name,
                f'sudo systemctl enable {service} && sudo systemctl start {service}'
            ], check=True)
            print(f"✅ {service} enabled and started")
        except subprocess.CalledProcessError:
            print(f"⚠️  {service} not available, skipping")

def verify_features(container_name):
    """Verify new features are working"""
    print(f"🧪 Verifying enhanced features on {container_name}...")
    
    # Check blockchain height (should be 0 for fresh genesis)
    result = subprocess.run([
        'ssh', container_name,
        'curl -s http://localhost:8005/rpc/head | jq ".height"'
    ], capture_output=True, text=True)
    
    if result.returncode == 0 and result.stdout.strip() == '0':
        print("✅ Genesis block height verified (0)")
    else:
        print(f"⚠️  Unexpected blockchain height: {result.stdout}")
    
    # Check if explorer is accessible
    result = subprocess.run([
        'ssh', container_name,
        'curl -s -o /dev/null -w "%{http_code}" http://localhost:8016'
    ], capture_output=True, text=True)
    
    if result.returncode == 0 and result.stdout.strip() == '200':
        print("✅ Blockchain Explorer accessible")
    else:
        print(f"⚠️  Explorer not accessible (HTTP {result.stdout})")

def main():
    """Main deployment function"""
    print("🌟 AITBC Enhanced Genesis Block Deployment")
    print("=" * 50)
    
    # Load genesis configuration
    genesis_config = load_genesis_config('/home/oib/windsurf/aitbc/genesis_enhanced_devnet.yaml')
    
    print(f"📋 Chain ID: {genesis_config['genesis']['chain_id']}")
    print(f"📋 Chain Type: {genesis_config['genesis']['chain_type']}")
    print(f"📋 Purpose: {genesis_config['genesis']['purpose']}")
    print(f"📋 Features: {', '.join(genesis_config['genesis']['features'].keys())}")
    print()
    
    # Deploy to containers
    containers = ['aitbc-cascade', 'aitbc1-cascade']
    success_count = 0
    
    for container in containers:
        print(f"\n🌐 Processing {container}...")
        if deploy_to_container(container, genesis_config):
            enable_new_services(container)
            verify_features(container)
            success_count += 1
        print("-" * 40)
    
    # Summary
    print(f"\n📊 Deployment Summary:")
    print(f"✅ Successful deployments: {success_count}/{len(containers)}")
    print(f"🔗 Chain ID: {genesis_config['genesis']['chain_id']}")
    print(f"🕐 Deployment time: {datetime.now().isoformat()}")
    
    if success_count == len(containers):
        print("🎉 All deployments successful!")
    else:
        print("⚠️  Some deployments failed - check logs above")
    
    print("\n🔗 Next Steps:")
    print("1. Test the new AI Trading Engine: curl http://localhost:8010/health")
    print("2. Check AI Surveillance: curl http://localhost:8011/status")
    print("3. View Advanced Analytics: curl http://localhost:8012/metrics")
    print("4. Access Blockchain Explorer: http://localhost:8016")
    print("5. Test CLI commands: aitbc --test-mode wallet list")

if __name__ == "__main__":
    main()
