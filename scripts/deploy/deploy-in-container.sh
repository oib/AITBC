#!/bin/bash

# Deploy blockchain node and explorer inside the container

set -e

echo "🚀 Deploying Inside Container"
echo "============================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check if we're in the container
if [ ! -f /proc/1/environ ] || ! grep -q container=lxc /proc/1/environ 2>/dev/null; then
    if [ "$(hostname)" != "aitbc" ]; then
        print_warning "This script must be run inside the aitbc container"
        exit 1
    fi
fi

# Stop existing services
print_status "Stopping existing services..."
systemctl stop blockchain-node blockchain-rpc nginx 2>/dev/null || true

# Install dependencies
print_status "Installing dependencies..."
apt-get update
apt-get install -y python3 python3-venv python3-pip git curl nginx

# Deploy blockchain node
print_status "Deploying blockchain node..."
cd /opt
rm -rf blockchain-node
# The source is already in blockchain-node-src, copy it properly
cp -r blockchain-node-src blockchain-node
cd blockchain-node

# Check if pyproject.toml exists
if [ ! -f pyproject.toml ]; then
    print_warning "pyproject.toml not found, looking for it..."
    find . -name "pyproject.toml" -type f
    # If it's in a subdirectory, move everything up
    if [ -f blockchain-node-src/pyproject.toml ]; then
        print_status "Moving files from nested directory..."
        mv blockchain-node-src/* .
        rmdir blockchain-node-src
    fi
fi

# Create configuration
print_status "Creating configuration..."
cat > .env << EOL
CHAIN_ID=ait-devnet
DB_PATH=./data/chain.db
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8082
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=7070
PROPOSER_KEY=proposer_key_$(date +%s)
MINT_PER_UNIT=1000
COORDINATOR_RATIO=0.05
GOSSIP_BACKEND=memory
EOL

# Create fresh data directory
rm -rf data
mkdir -p data/devnet

# Setup Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

# Generate genesis
export PYTHONPATH="${PWD}/src:${PWD}/scripts:${PYTHONPATH:-}"
python scripts/make_genesis.py --output data/devnet/genesis.json --force

# Create systemd services
print_status "Creating systemd services..."
cat > /etc/systemd/system/blockchain-node.service << EOL
[Unit]
Description=AITBC Blockchain Node
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=/opt/blockchain-node
Environment=PATH=/opt/blockchain-node/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=/opt/blockchain-node/src:/opt/blockchain-node/scripts
ExecStart=/opt/blockchain-node/.venv/bin/python3 -m aitbc_chain.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

cat > /etc/systemd/system/blockchain-rpc.service << EOL
[Unit]
Description=AITBC Blockchain RPC API
After=blockchain-node.service

[Service]
Type=exec
User=root
WorkingDirectory=/opt/blockchain-node
Environment=PATH=/opt/blockchain-node/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=/opt/blockchain-node/src:/opt/blockchain-node/scripts
ExecStart=/opt/blockchain-node/.venv/bin/python3 -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 8082
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

# Start blockchain services
print_status "Starting blockchain services..."
systemctl daemon-reload
systemctl enable blockchain-node blockchain-rpc
systemctl start blockchain-node blockchain-rpc

# Deploy explorer
print_status "Deploying blockchain explorer..."
cd /opt
rm -rf blockchain-explorer
mkdir -p blockchain-explorer
cd blockchain-explorer

# Create HTML explorer
cat > index.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AITBC Blockchain Explorer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
</head>
<body class="bg-gray-50">
    <header class="bg-blue-600 text-white shadow-lg">
        <div class="container mx-auto px-4 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <i data-lucide="cube" class="w-8 h-8"></i>
                    <h1 class="text-2xl font-bold">AITBC Blockchain Explorer</h1>
                </div>
                <button onclick="refreshData()" class="bg-blue-500 hover:bg-blue-400 px-3 py-1 rounded flex items-center space-x-1">
                    <i data-lucide="refresh-cw" class="w-4 h-4"></i>
                    <span>Refresh</span>
                </button>
            </div>
        </div>
    </header>

    <main class="container mx-auto px-4 py-8">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-gray-500 text-sm">Current Height</p>
                        <p class="text-2xl font-bold" id="chain-height">-</p>
                    </div>
                    <i data-lucide="trending-up" class="w-10 h-10 text-green-500"></i>
                </div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-gray-500 text-sm">Latest Block</p>
                        <p class="text-lg font-mono" id="latest-hash">-</p>
                    </div>
                    <i data-lucide="hash" class="w-10 h-10 text-blue-500"></i>
                </div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-gray-500 text-sm">Node Status</p>
                        <p class="text-lg font-semibold" id="node-status">-</p>
                    </div>
                    <i data-lucide="activity" class="w-10 h-10 text-purple-500"></i>
                </div>
            </div>
        </div>

        <div class="bg-white rounded-lg shadow">
            <div class="px-6 py-4 border-b">
                <h2 class="text-xl font-semibold flex items-center">
                    <i data-lucide="blocks" class="w-5 h-5 mr-2"></i>
                    Latest Blocks
                </h2>
            </div>
            <div class="p-6">
                <table class="w-full">
                    <thead>
                        <tr class="text-left text-gray-500 text-sm">
                            <th class="pb-3">Height</th>
                            <th class="pb-3">Hash</th>
                            <th class="pb-3">Timestamp</th>
                            <th class="pb-3">Transactions</th>
                        </tr>
                    </thead>
                    <tbody id="blocks-table">
                        <tr>
                            <td colspan="4" class="text-center py-8 text-gray-500">
                                Loading blocks...
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </main>

    <script>
        lucide.createIcons();
        
        const RPC_URL = 'http://localhost:8082';
        
        async function refreshData() {
            try {
                const response = await fetch(`${RPC_URL}/rpc/head`);
                const head = await response.json();
                
                document.getElementById('chain-height').textContent = head.height || '-';
                document.getElementById('latest-hash').textContent = head.hash ? head.hash.substring(0, 16) + '...' : '-';
                document.getElementById('node-status').innerHTML = '<span class="text-green-500">Online</span>';
                
                // Load last 10 blocks
                const tbody = document.getElementById('blocks-table');
                tbody.innerHTML = '';
                
                for (let i = 0; i < 10 && head.height - i >= 0; i++) {
                    const blockResponse = await fetch(`${RPC_URL}/rpc/blocks/${head.height - i}`);
                    const block = await blockResponse.json();
                    
                    const row = tbody.insertRow();
                    row.innerHTML = `
                        <td class="py-3 font-mono">${block.height}</td>
                        <td class="py-3 font-mono text-sm">${block.hash ? block.hash.substring(0, 16) + '...' : '-'}</td>
                        <td class="py-3 text-sm">${new Date(block.timestamp * 1000).toLocaleString()}</td>
                        <td class="py-3">${block.transactions ? block.transactions.length : 0}</td>
                    `;
                }
            } catch (error) {
                console.error('Error:', error);
                document.getElementById('node-status').innerHTML = '<span class="text-red-500">Error</span>';
            }
        }
        
        refreshData();
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
EOF

# Configure nginx
print_status "Configuring nginx..."
cat > /etc/nginx/sites-available/blockchain-explorer << EOL
server {
    listen 3000;
    server_name _;
    root /opt/blockchain-explorer;
    index index.html;
    
    location / {
        try_files \$uri \$uri/ =404;
    }
}
EOL

ln -sf /etc/nginx/sites-available/blockchain-explorer /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# Wait for services to start
print_status "Waiting for services to start..."
sleep 5

# Check services
print_status "Checking service status..."
systemctl status blockchain-node blockchain-rpc nginx --no-pager | grep -E 'Active:|Main PID:'

print_success "✅ Deployment complete in container!"
echo ""
echo "Services:"
echo "  - Blockchain Node RPC: http://localhost:8082"
echo "  - Blockchain Explorer: http://localhost:3000"
echo ""
echo "These are accessible from the host via port forwarding."
