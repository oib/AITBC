#!/bin/bash

# ============================================================================
# AITBC Mesh Network - GPU Marketplace Workflow (Fixed)
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
VENV_DIR="$AITBC_ROOT/venv"
PYTHON_CMD="$VENV_DIR/bin/python"

echo -e "${BLUE}🎯 GPU MARKETPLACE WORKFLOW${NC}"
echo "========================"
echo "1. Agent from AITBC server bids on GPU"
echo "2. aitbc1 confirms the bid"
echo "3. AITBC server sends Ollama task"
echo "4. aitbc1 receives payment over blockchain"
echo ""

# Step 1: Create GPU listing on marketplace
echo -e "${CYAN}📦 Step 1: Create GPU Listing${NC}"
echo "============================="

cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import json
import time
import uuid

# Create GPU marketplace data
gpu_listing = {
    'id': f'gpu_{uuid.uuid4().hex[:8]}',
    'provider': 'aitbc1',
    'gpu_type': 'NVIDIA RTX 4090',
    'memory_gb': 24,
    'compute_capability': '8.9',
    'price_per_hour': 50.0,
    'availability': 'immediate',
    'location': 'aitbc1-node',
    'status': 'listed',
    'created_at': time.time(),
    'specs': {
        'cuda_cores': 16384,
        'tensor_cores': 512,
        'memory_bandwidth': '1008 GB/s',
        'power_consumption': '450W'
    }
}

# Save GPU listing
with open('/opt/aitbc/data/gpu_marketplace.json', 'w') as f:
    json.dump({'gpu_listings': {gpu_listing['id']: gpu_listing}}, f, indent=2)

print(f'✅ GPU Listing Created:')
print(f'   ID: {gpu_listing[\"id\"]}')
print(f'   Type: {gpu_listing[\"gpu_type\"]}')
print(f'   Price: {gpu_listing[\"price_per_hour\"]} AITBC/hour')
print(f'   Provider: {gpu_listing[\"provider\"]}')
print(f'   Status: {gpu_listing[\"status\"]}')
"

echo ""

# Step 2: Agent from AITBC server bids on GPU
echo -e "${CYAN}🤖 Step 2: Agent Bids on GPU${NC}"
echo "============================"

cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import json
import time

# Load GPU marketplace
with open('/opt/aitbc/data/gpu_marketplace.json', 'r') as f:
    marketplace = json.load(f)

# Load agent registry
with open('/opt/aitbc/data/agent_registry.json', 'r') as f:
    registry = json.load(f)

# Get first GPU listing and agent
gpu_id = list(marketplace['gpu_listings'].keys())[0]
gpu_listing = marketplace['gpu_listings'][gpu_id]
agent_id = list(registry['agents'].keys())[0]
agent = registry['agents'][agent_id]

# Create bid
bid = {
    'id': f'bid_{int(time.time())}',
    'gpu_id': gpu_id,
    'agent_id': agent_id,
    'agent_name': agent['name'],
    'bid_price': 45.0,
    'duration_hours': 4,
    'total_cost': 45.0 * 4,
    'purpose': 'Ollama LLM inference task',
    'status': 'pending',
    'created_at': time.time(),
    'expires_at': time.time() + 3600
}

# Add bid to GPU listing
if 'bids' not in gpu_listing:
    gpu_listing['bids'] = {}
gpu_listing['bids'][bid['id']] = bid

# Save updated marketplace
with open('/opt/aitbc/data/gpu_marketplace.json', 'w') as f:
    json.dump(marketplace, f, indent=2)

print(f'✅ Agent Bid Created:')
print(f'   Agent: {agent[\"name\"]} ({agent_id})')
print(f'   GPU: {gpu_listing[\"gpu_type\"]} ({gpu_id})')
print(f'   Bid Price: {bid[\"bid_price\"]} AITBC/hour')
print(f'   Duration: {bid[\"duration_hours\"]} hours')
print(f'   Total Cost: {bid[\"total_cost\"]} AITBC')
print(f'   Purpose: {bid[\"purpose\"]}')
print(f'   Status: {bid[\"status\"]}')
"

echo ""

# Step 3: Sync to aitbc1 for confirmation
echo -e "${CYAN}🔄 Step 3: Sync to aitbc1${NC}"
echo "======================"

scp /opt/aitbc/data/gpu_marketplace.json aitbc1:/opt/aitbc/data/
echo "✅ GPU marketplace synced to aitbc1"

echo ""

# Step 4: aitbc1 confirms the bid
echo -e "${CYAN}✅ Step 4: aitbc1 Confirms Bid${NC}"
echo "=========================="

# Create a Python script for aitbc1 to run
cat > /tmp/confirm_bid.py << 'EOF'
import json
import time

# Load GPU marketplace
with open('/opt/aitbc/data/gpu_marketplace.json', 'r') as f:
    marketplace = json.load(f)

# Get the bid
gpu_id = list(marketplace['gpu_listings'].keys())[0]
gpu_listing = marketplace['gpu_listings'][gpu_id]
bid_id = list(gpu_listing['bids'].keys())[0]
bid = gpu_listing['bids'][bid_id]

# Confirm the bid
bid['status'] = 'confirmed'
bid['confirmed_at'] = time.time()
bid['confirmed_by'] = 'aitbc1'

# Update GPU status
gpu_listing['status'] = 'reserved'
gpu_listing['reserved_by'] = bid['agent_id']
gpu_listing['reservation_expires'] = time.time() + (bid['duration_hours'] * 3600)

# Save updated marketplace
with open('/opt/aitbc/data/gpu_marketplace.json', 'w') as f:
    json.dump(marketplace, f, indent=2)

print(f'✅ Bid Confirmed by aitbc1:')
print(f'   Bid ID: {bid_id}')
print(f'   Agent: {bid["agent_name"]}')
print(f'   GPU: {gpu_listing["gpu_type"]}')
print(f'   Status: {bid["status"]}')
print(f'   Confirmed At: {time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(bid["confirmed_at"]))}')
print(f'   Reservation Expires: {time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(gpu_listing["reservation_expires"]))}')
EOF

scp /tmp/confirm_bid.py aitbc1:/tmp/
ssh aitbc1 "cd /opt/aitbc && python3 /tmp/confirm_bid.py"

echo ""

# Step 5: Sync back to AITBC server
echo -e "${CYAN}🔄 Step 5: Sync Back to Server${NC}"
echo "=========================="

scp aitbc1:/opt/aitbc/data/gpu_marketplace.json /opt/aitbc/data/
echo "✅ Confirmed bid synced back to server"

echo ""

# Step 6: AITBC server sends Ollama task
echo -e "${CYAN}🚀 Step 6: Send Ollama Task${NC}"
echo "=========================="

cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import json
import time

# Load GPU marketplace
with open('/opt/aitbc/data/gpu_marketplace.json', 'r') as f:
    marketplace = json.load(f)

# Get the confirmed bid
gpu_id = list(marketplace['gpu_listings'].keys())[0]
gpu_listing = marketplace['gpu_listings'][gpu_id]
bid_id = list(gpu_listing['bids'].keys())[0]
bid = gpu_listing['bids'][bid_id]

# Create Ollama task
task = {
    'id': f'task_{int(time.time())}',
    'bid_id': bid_id,
    'gpu_id': gpu_id,
    'agent_id': bid['agent_id'],
    'task_type': 'ollama_inference',
    'model': 'llama2',
    'prompt': 'Explain the concept of decentralized AI economies',
    'parameters': {
        'temperature': 0.7,
        'max_tokens': 500,
        'top_p': 0.9
    },
    'status': 'sent',
    'sent_at': time.time(),
    'timeout': 300
}

# Add task to bid
bid['task'] = task
bid['status'] = 'task_sent'

# Save updated marketplace
with open('/opt/aitbc/data/gpu_marketplace.json', 'w') as f:
    json.dump(marketplace, f, indent=2)

print(f'✅ Ollama Task Sent:')
print(f'   Task ID: {task[\"id\"]}')
print(f'   Model: {task[\"model\"]}')
print(f'   Prompt: {task[\"prompt\"]}')
print(f'   Agent: {bid[\"agent_name\"]}')
print(f'   GPU: {gpu_listing[\"gpu_type\"]}')
print(f'   Status: {task[\"status\"]}')
"

echo ""

# Step 7: Sync task to aitbc1
echo -e "${CYAN}🔄 Step 7: Sync Task to aitbc1${NC}"
echo "=========================="

scp /opt/aitbc/data/gpu_marketplace.json aitbc1:/opt/aitbc/data/
echo "✅ Task synced to aitbc1"

echo ""

# Step 8: aitbc1 executes task and completes
echo -e "${CYAN}⚡ Step 8: aitbc1 Executes Task${NC}"
echo "==========================="

# Create execution script for aitbc1
cat > /tmp/execute_task.py << 'EOF'
import json
import time

# Load GPU marketplace
with open('/opt/aitbc/data/gpu_marketplace.json', 'r') as f:
    marketplace = json.load(f)

# Get the task
gpu_id = list(marketplace['gpu_listings'].keys())[0]
gpu_listing = marketplace['gpu_listings'][gpu_id]
bid_id = list(gpu_listing['bids'].keys())[0]
bid = gpu_listing['bids'][bid_id]
task = bid['task']

# Simulate task execution
time.sleep(2)

# Complete the task
task['status'] = 'completed'
task['completed_at'] = time.time()
task['result'] = 'Decentralized AI economies represent a paradigm shift in how artificial intelligence services are bought, sold, and delivered. Instead of relying on centralized platforms, these economies leverage blockchain technology and distributed networks to enable direct peer-to-peer transactions between AI service providers and consumers.'

# Update bid status
bid['status'] = 'completed'
bid['completed_at'] = time.time()

# Update GPU status
gpu_listing['status'] = 'available'
del gpu_listing['reserved_by']
del gpu_listing['reservation_expires']

# Save updated marketplace
with open('/opt/aitbc/data/gpu_marketplace.json', 'w') as f:
    json.dump(marketplace, f, indent=2)

print(f'✅ Task Completed by aitbc1:')
print(f'   Task ID: {task[\"id\"]}')
print(f'   Status: {task[\"status\"]}')
print(f'   Completed At: {time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(task[\"completed_at\"])}')
print(f'   Result Length: {len(task[\"result\"])} characters')
print(f'   GPU Status: {gpu_listing[\"status\"]}')
EOF

scp /tmp/execute_task.py aitbc1:/tmp/
ssh aitbc1 "cd /opt/aitbc && python3 /tmp/execute_task.py"

echo ""

# Step 9: Sync completion back to server
echo -e "${CYAN}🔄 Step 9: Sync Completion to Server${NC}"
echo "==========================="

scp aitbc1:/opt/aitbc/data/gpu_marketplace.json /opt/aitbc/data/
echo "✅ Task completion synced to server"

echo ""

# Step 10: Process blockchain payment
echo -e "${CYAN}💰 Step 10: Process Blockchain Payment${NC}"
echo "==========================="

cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import json
import time

# Load GPU marketplace
with open('/opt/aitbc/data/gpu_marketplace.json', 'r') as f:
    marketplace = json.load(f)

# Load economic system
with open('/opt/aitbc/data/economic_system.json', 'r') as f:
    economics = json.load(f)

# Load agent registry
with open('/opt/aitbc/data/agent_registry.json', 'r') as f:
    registry = json.load(f)

# Get the completed bid
gpu_id = list(marketplace['gpu_listings'].keys())[0]
gpu_listing = marketplace['gpu_listings'][gpu_id]
bid_id = list(gpu_listing['bids'].keys())[0]
bid = gpu_listing['bids'][bid_id]

# Create blockchain transaction
transaction = {
    'id': f'tx_{int(time.time())}',
    'type': 'gpu_payment',
    'from_agent': bid['agent_id'],
    'to_provider': gpu_listing['provider'],
    'amount': bid['total_cost'],
    'gpu_id': gpu_id,
    'bid_id': bid_id,
    'task_id': bid['task']['id'],
    'status': 'confirmed',
    'confirmed_at': time.time(),
    'block_number': economics['network_metrics']['total_transactions'] + 1,
    'gas_used': 21000,
    'gas_price': 0.00002
}

# Add transaction to economic system
if 'gpu_transactions' not in economics:
    economics['gpu_transactions'] = {}
economics['gpu_transactions'][transaction['id']] = transaction

# Update network metrics
economics['network_metrics']['total_transactions'] += 1
economics['network_metrics']['total_value_locked'] += bid['total_cost']

# Update agent stats
agent = registry['agents'][bid['agent_id']]
agent['total_earnings'] += bid['total_cost']
agent['jobs_completed'] += 1

# Update bid with transaction
bid['payment_transaction'] = transaction['id']
bid['payment_status'] = 'paid'
bid['paid_at'] = time.time()

# Save all updated files
with open('/opt/aitbc/data/gpu_marketplace.json', 'w') as f:
    json.dump(marketplace, f, indent=2)

with open('/opt/aitbc/data/economic_system.json', 'w') as f:
    json.dump(economics, f, indent=2)

with open('/opt/aitbc/data/agent_registry.json', 'w') as f:
    json.dump(registry, f, indent=2)

print(f'✅ Blockchain Payment Processed:')
print(f'   Transaction ID: {transaction[\"id\"]}')
print(f'   From Agent: {agent[\"name\"]}')
print(f'   To Provider: {gpu_listing[\"provider\"]}')
print(f'   Amount: {transaction[\"amount\"]} AITBC')
print(f'   Block Number: {transaction[\"block_number\"]}')
print(f'   Status: {transaction[\"status\"]}')
print(f'   Agent Total Earnings: {agent[\"total_earnings\"]} AITBC')
"

echo ""

# Step 11: Final sync to aitbc1
echo -e "${CYAN}🔄 Step 11: Final Sync to aitbc1${NC}"
echo "=========================="

scp /opt/aitbc/data/gpu_marketplace.json /opt/aitbc/data/economic_system.json /opt/aitbc/data/agent_registry.json aitbc1:/opt/aitbc/data/
echo "✅ Final payment data synced to aitbc1"

echo ""

echo -e "${GREEN}🎉 GPU MARKETPLACE WORKFLOW COMPLETED!${NC}"
echo "=================================="
echo ""
echo "✅ Workflow Summary:"
echo "   1. GPU listed on marketplace"
echo "   2. Agent bid on GPU (45 AITBC/hour for 4 hours)"
echo "   3. aitbc1 confirmed the bid"
echo "   4. AITBC server sent Ollama task"
echo "   5. aitbc1 executed the task"
echo "   6. Blockchain payment processed (180 AITBC)"
echo ""
echo -e "${BLUE}📊 Final Status:${NC}"
cd "$AITBC_ROOT"
"$PYTHON_CMD" -c "
import json

# Load final data
with open('/opt/aitbc/data/gpu_marketplace.json', 'r') as f:
    marketplace = json.load(f)

with open('/opt/aitbc/data/economic_system.json', 'r') as f:
    economics = json.load(f)

gpu_id = list(marketplace['gpu_listings'].keys())[0]
gpu_listing = marketplace['gpu_listings'][gpu_id]
bid_id = list(gpu_listing['bids'].keys())[0]
bid = gpu_listing['bids'][bid_id]
tx_id = bid['payment_transaction']

print(f'GPU: {gpu_listing[\"gpu_type\"]} - {gpu_listing[\"status\"]}')
print(f'Agent: {bid[\"agent_name\"]} - {bid[\"status\"]}')
print(f'Task: {bid[\"task\"][\"status\"]}')
print(f'Payment: {bid[\"payment_status\"]} - {bid[\"total_cost\"]} AITBC')
print(f'Transaction: {tx_id}')
print(f'Total Network Transactions: {economics[\"network_metrics\"][\"total_transactions\"]}')
"
