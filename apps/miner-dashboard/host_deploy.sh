#!/bin/bash

echo "=== AITBC Miner Dashboard - Host Deployment ==="
echo ""

# Check if running on host with GPU
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ nvidia-smi not found. Please install NVIDIA drivers."
    exit 1
fi

# Create directory
mkdir -p ~/miner-dashboard
cd ~/miner-dashboard

echo "✅ GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader)"

# Create dashboard HTML
cat > index.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AITBC GPU Miner Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        @keyframes pulse-green {
            0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
            50% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
        }
        .status-online { animation: pulse-green 2s infinite; }
        .gpu-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    </style>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <header class="bg-gray-800 shadow-lg">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-4">
                    <i class="fas fa-microchip text-3xl text-purple-500"></i>
                    <div>
                        <h1 class="text-2xl font-bold">AITBC Miner Dashboard</h1>
                        <p class="text-sm text-gray-400">Host GPU Mining Operations</p>
                    </div>
                </div>
                <div class="flex items-center space-x-4">
                    <span class="flex items-center">
                        <span class="w-3 h-3 bg-green-500 rounded-full status-online mr-2"></span>
                        <span class="text-sm">GPU Connected</span>
                    </span>
                    <button onclick="refreshData()" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg transition">
                        <i class="fas fa-sync-alt mr-2"></i>Refresh
                    </button>
                </div>
            </div>
        </div>
    </header>

    <main class="container mx-auto px-6 py-8">
        <!-- GPU Status -->
        <div class="gpu-card rounded-xl p-6 mb-8 text-white">
            <div class="flex items-center justify-between mb-6">
                <div>
                    <h2 class="text-3xl font-bold mb-2" id="gpuName">Loading...</h2>
                    <p class="text-purple-200">Real-time GPU Status</p>
                </div>
                <div class="text-right">
                    <div class="text-4xl font-bold" id="gpuUtil">0%</div>
                    <div class="text-purple-200">GPU Utilization</div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div class="bg-white/10 backdrop-blur rounded-lg p-4">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-purple-200 text-sm">Temperature</p>
                            <p class="text-2xl font-bold" id="gpuTemp">--°C</p>
                        </div>
                        <i class="fas fa-thermometer-half text-3xl text-purple-300"></i>
                    </div>
                </div>
                <div class="bg-white/10 backdrop-blur rounded-lg p-4">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-purple-200 text-sm">Power Usage</p>
                            <p class="text-2xl font-bold" id="gpuPower">--W</p>
                        </div>
                        <i class="fas fa-bolt text-3xl text-yellow-400"></i>
                    </div>
                </div>
                <div class="bg-white/10 backdrop-blur rounded-lg p-4">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-purple-200 text-sm">Memory Used</p>
                            <p class="text-2xl font-bold" id="gpuMem">--GB</p>
                        </div>
                        <i class="fas fa-memory text-3xl text-blue-400"></i>
                    </div>
                </div>
                <div class="bg-white/10 backdrop-blur rounded-lg p-4">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-purple-200 text-sm">Performance</p>
                            <p class="text-2xl font-bold" id="gpuPerf">--</p>
                        </div>
                        <i class="fas fa-tachometer-alt text-3xl text-green-400"></i>
                    </div>
                </div>
            </div>
        </div>

        <!-- Mining Status -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
            <!-- Active Jobs -->
            <div class="bg-gray-800 rounded-xl p-6">
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-tasks mr-3 text-green-500"></i>
                    Mining Status
                </h3>
                <div class="text-center py-8">
                    <i class="fas fa-pause-circle text-6xl text-yellow-500 mb-4"></i>
                    <p class="text-xl font-semibold text-yellow-500">Miner Idle</p>
                    <p class="text-gray-400 mt-2">Ready to accept mining jobs</p>
                    <button onclick="startMiner()" class="mt-4 bg-green-600 hover:bg-green-700 px-6 py-2 rounded-lg transition">
                        <i class="fas fa-play mr-2"></i>Start Mining
                    </button>
                </div>
            </div>

            <!-- Services -->
            <div class="bg-gray-800 rounded-xl p-6">
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-server mr-3 text-blue-500"></i>
                    GPU Services Available
                </h3>
                <div class="space-y-3">
                    <div class="bg-gray-700 rounded-lg p-4 flex justify-between items-center">
                        <div>
                            <p class="font-semibold">GPU Computing</p>
                            <p class="text-sm text-gray-400">CUDA cores ready</p>
                        </div>
                        <span class="bg-green-600 px-3 py-1 rounded-full text-sm">Available</span>
                    </div>
                    <div class="bg-gray-700 rounded-lg p-4 flex justify-between items-center">
                        <div>
                            <p class="font-semibold">Hash Generation</p>
                            <p class="text-sm text-gray-400">Proof-of-work capable</p>
                        </div>
                        <span class="bg-green-600 px-3 py-1 rounded-full text-sm">Available</span>
                    </div>
                    <div class="bg-gray-700 rounded-lg p-4 flex justify-between items-center">
                        <div>
                            <p class="font-semibold">AI Model Training</p>
                            <p class="text-sm text-gray-400">ML operations ready</p>
                        </div>
                        <span class="bg-green-600 px-3 py-1 rounded-full text-sm">Available</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Info -->
        <div class="bg-gray-800 rounded-xl p-6">
            <h3 class="text-xl font-bold mb-4">System Information</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                    <p class="text-sm text-gray-400">Host System</p>
                    <p class="font-semibold" id="hostname">Loading...</p>
                </div>
                <div>
                    <p class="text-sm text-gray-400">GPU Driver</p>
                    <p class="font-semibold" id="driver">Loading...</p>
                </div>
                <div>
                    <p class="text-sm text-gray-400">CUDA Version</p>
                    <p class="font-semibold" id="cuda">Loading...</p>
                </div>
            </div>
        </div>
    </main>

    <script>
        // Load GPU info
        async function loadGPUInfo() {
            try {
                const response = await fetch('/api/gpu');
                const data = await response.json();
                
                document.getElementById('gpuName').textContent = data.name;
                document.getElementById('gpuUtil').textContent = data.utilization + '%';
                document.getElementById('gpuTemp').textContent = data.temperature + '°C';
                document.getElementById('gpuPower').textContent = data.power + 'W';
                document.getElementById('gpuMem').textContent = data.memory_used + 'GB / ' + data.memory_total + 'GB';
                document.getElementById('gpuPerf').textContent = data.performance_state;
                document.getElementById('hostname').textContent = data.hostname;
                document.getElementById('driver').textContent = data.driver_version;
                document.getElementById('cuda').textContent = data.cuda_version;
            } catch (e) {
                console.error('Failed to load GPU info:', e);
            }
        }

        // Refresh data
        function refreshData() {
            const btn = document.querySelector('button[onclick="refreshData()"]');
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Refreshing...';
            
            loadGPUInfo().then(() => {
                btn.innerHTML = '<i class="fas fa-sync-alt mr-2"></i>Refresh';
            });
        }

        // Start miner (placeholder)
        function startMiner() {
            alert('Miner service would start here. This is a demo dashboard.');
        }

        // Initialize
        loadGPUInfo();
        setInterval(loadGPUInfo, 5000);
    </script>
</body>
</html>
EOF

# Create Python server with API
cat > server.py << 'EOF'
import json
import subprocess
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

class MinerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/gpu':
            self.send_json(self.get_gpu_info())
        elif self.path == '/' or self.path == '/index.html':
            self.serve_file('index.html')
        else:
            self.send_error(404)
    
    def get_gpu_info(self):
        try:
            # Get GPU info
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,utilization.gpu,temperature.gpu,power.draw,memory.used,memory.total,driver_version,cuda_version', '--format=csv,noheader,nounits'], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                values = result.stdout.strip().split(', ')
                return {
                    'name': values[0],
                    'utilization': int(values[1]),
                    'temperature': int(values[2]),
                    'power': float(values[3]),
                    'memory_used': float(values[4]) / 1024,
                    'memory_total': float(values[5]) / 1024,
                    'driver_version': values[6],
                    'cuda_version': values[7],
                    'hostname': socket.gethostname(),
                    'performance_state': 'P8'  # Would need additional query
                }
        except Exception as e:
            return {'error': str(e)}
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def serve_file(self, filename):
        try:
            with open(filename, 'r') as f:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(f.read().encode())
        except FileNotFoundError:
            self.send_error(404)

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8080), MinerHandler)
    print('''
╔═══════════════════════════════════════╗
║   AITBC Miner Dashboard               ║
║   Running on HOST with GPU access      ║
╠═══════════════════════════════════════╣
║  Dashboard: http://localhost:8080     ║
║  Host: $(hostname)                     ║
║  GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader) ║
╚═══════════════════════════════════════╝
''')
    server.serve_forever()
EOF

# Make server executable
chmod +x server.py

echo ""
echo "✅ Dashboard created!"
echo ""
echo "To start the dashboard:"
echo "  cd ~/miner-dashboard"
echo "  python3 server.py"
echo ""
echo "Then access at: http://localhost:8080"
echo ""
echo "To auto-start on boot, add to crontab:"
echo "  @reboot cd ~/miner-dashboard && python3 server.py &"
