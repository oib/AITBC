#!/bin/bash

echo "=== AITBC Miner Dashboard - Host Setup ==="
echo ""
echo "This script sets up the dashboard on the HOST machine (at1)"
echo "NOT in the container (aitbc)"
echo ""

# Check if we have GPU access
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ ERROR: nvidia-smi not found!"
    echo "This script must be run on the HOST with GPU access"
    exit 1
fi

echo "✅ GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader)"

# Create dashboard directory
mkdir -p ~/miner-dashboard
cd ~/miner-dashboard

# Create HTML dashboard
cat > index.html << 'HTML'
<!DOCTYPE html>
<html>
<head>
    <title>AITBC GPU Miner Dashboard - HOST</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="container mx-auto px-6 py-8">
        <header class="mb-8">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-4">
                    <i class="fas fa-microchip text-4xl text-purple-500"></i>
                    <div>
                        <h1 class="text-3xl font-bold">AITBC GPU Miner Dashboard</h1>
                        <p class="text-gray-400">Running on HOST with direct GPU access</p>
                    </div>
                </div>
                <div class="flex items-center space-x-2">
                    <span class="w-3 h-3 bg-green-500 rounded-full animate-pulse"></span>
                    <span class="text-green-500">GPU Connected</span>
                </div>
            </div>
        </header>

        <div class="bg-gradient-to-r from-purple-600 to-blue-600 rounded-xl p-8 mb-8 text-white">
            <h2 class="text-2xl font-bold mb-6">GPU Status Monitor</h2>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
                <div class="bg-white/10 backdrop-blur rounded-lg p-4 text-center">
                    <i class="fas fa-chart-line text-3xl mb-2"></i>
                    <p class="text-sm opacity-80">Utilization</p>
                    <p class="text-3xl font-bold" id="utilization">0%</p>
                </div>
                <div class="bg-white/10 backdrop-blur rounded-lg p-4 text-center">
                    <i class="fas fa-thermometer-half text-3xl mb-2"></i>
                    <p class="text-sm opacity-80">Temperature</p>
                    <p class="text-3xl font-bold" id="temperature">--°C</p>
                </div>
                <div class="bg-white/10 backdrop-blur rounded-lg p-4 text-center">
                    <i class="fas fa-bolt text-3xl mb-2"></i>
                    <p class="text-sm opacity-80">Power</p>
                    <p class="text-3xl font-bold" id="power">--W</p>
                </div>
                <div class="bg-white/10 backdrop-blur rounded-lg p-4 text-center">
                    <i class="fas fa-memory text-3xl mb-2"></i>
                    <p class="text-sm opacity-80">Memory</p>
                    <p class="text-3xl font-bold" id="memory">--GB</p>
                </div>
            </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div class="bg-gray-800 rounded-xl p-6">
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-cog text-green-500 mr-2"></i>
                    Mining Operations
                </h3>
                <div class="space-y-4">
                    <div class="bg-gray-700 rounded-lg p-4">
                        <div class="flex justify-between items-center mb-2">
                            <span class="font-semibold">Status</span>
                            <span class="bg-yellow-600 px-3 py-1 rounded-full text-sm">Idle</span>
                        </div>
                        <p class="text-sm text-gray-400">Miner is ready to accept jobs</p>
                    </div>
                    <div class="bg-gray-700 rounded-lg p-4">
                        <div class="flex justify-between items-center mb-2">
                            <span class="font-semibold">Hash Rate</span>
                            <span class="text-green-400">0 MH/s</span>
                        </div>
                        <div class="w-full bg-gray-600 rounded-full h-2">
                            <div class="bg-green-500 h-2 rounded-full" style="width: 0%"></div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-gray-800 rounded-xl p-6">
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-server text-blue-500 mr-2"></i>
                    GPU Services
                </h3>
                <div class="space-y-3">
                    <div class="flex justify-between items-center p-3 bg-gray-700 rounded-lg">
                        <span>CUDA Computing</span>
                        <span class="bg-green-600 px-2 py-1 rounded text-xs">Active</span>
                    </div>
                    <div class="flex justify-between items-center p-3 bg-gray-700 rounded-lg">
                        <span>Parallel Processing</span>
                        <span class="bg-green-600 px-2 py-1 rounded text-xs">Active</span>
                    </div>
                    <div class="flex justify-between items-center p-3 bg-gray-700 rounded-lg">
                        <span>Hash Generation</span>
                        <span class="bg-yellow-600 px-2 py-1 rounded text-xs">Standby</span>
                    </div>
                    <div class="flex justify-between items-center p-3 bg-gray-700 rounded-lg">
                        <span>AI Model Training</span>
                        <span class="bg-gray-600 px-2 py-1 rounded text-xs">Available</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="mt-8 bg-gray-800 rounded-xl p-6">
            <h3 class="text-xl font-bold mb-4">System Information</h3>
            <div class="grid grid-cols-3 gap-6 text-center">
                <div>
                    <p class="text-sm text-gray-400">Location</p>
                    <p class="font-semibold text-green-400">HOST System</p>
                </div>
                <div>
                    <p class="text-sm text-gray-400">GPU Access</p>
                    <p class="font-semibold text-green-400">Direct</p>
                </div>
                <div>
                    <p class="text-sm text-gray-400">Container</p>
                    <p class="font-semibold text-red-400">Not Used</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Simulate real-time GPU data
        function updateGPU() {
            // In real implementation, this would fetch from an API
            const util = Math.random() * 20; // 0-20% idle usage
            const temp = 43 + Math.random() * 10;
            const power = 18 + util * 0.5;
            const mem = 2.9 + Math.random() * 0.5;
            
            document.getElementById('utilization').textContent = Math.round(util) + '%';
            document.getElementById('temperature').textContent = Math.round(temp) + '°C';
            document.getElementById('power').textContent = Math.round(power) + 'W';
            document.getElementById('memory').textContent = mem.toFixed(1) + 'GB';
        }
        
        // Update every 2 seconds
        setInterval(updateGPU, 2000);
        updateGPU();
    </script>
</body>
</html>
HTML

# Create simple server
cat > serve.sh << 'EOF'
#!/bin/bash
cd ~/miner-dashboard
echo "Starting GPU Miner Dashboard on HOST..."
echo "Access at: http://localhost:8080"
echo "Press Ctrl+C to stop"
python3 -m http.server 8080 --bind 0.0.0.0
EOF

chmod +x serve.sh

echo ""
echo "✅ Dashboard created on HOST!"
echo ""
echo "To run the dashboard:"
echo "  ~/miner-dashboard/serve.sh"
echo ""
echo "Dashboard will be available at:"
echo "  - Local: http://localhost:8080"
echo "  - Network: http://$(hostname -I | awk '{print $1}'):8080"
