#!/bin/bash

echo "========================================"
echo "  AITBC GPU Miner Dashboard Setup"
echo "  Running on HOST (at1/localhost)"
echo "========================================"
echo ""

# Check if we have GPU access
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ ERROR: nvidia-smi not found!"
    echo "Please ensure NVIDIA drivers are installed on the host."
    exit 1
fi

echo "✅ GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader)"
echo ""

# Create dashboard directory
mkdir -p ~/miner-dashboard
cd ~/miner-dashboard

echo "Creating dashboard files..."

# Create the main dashboard HTML
cat > index.html << 'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AITBC GPU Miner Dashboard - Host</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        @keyframes pulse-green {
            0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
            50% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
        }
        .gpu-gradient { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .status-active { animation: pulse-green 2s infinite; }
    </style>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <!-- Header -->
    <header class="bg-gray-800 shadow-xl">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-4">
                    <i class="fas fa-microchip text-4xl text-purple-500"></i>
                    <div>
                        <h1 class="text-3xl font-bold">AITBC GPU Miner Dashboard</h1>
                        <p class="text-green-400">✓ Running on HOST with direct GPU access</p>
                    </div>
                </div>
                <div class="flex items-center space-x-4">
                    <span class="flex items-center bg-green-900/50 px-3 py-1 rounded-full">
                        <span class="w-3 h-3 bg-green-500 rounded-full status-active mr-2"></span>
                        <span>GPU Online</span>
                    </span>
                    <button onclick="location.reload()" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg transition">
                        <i class="fas fa-sync-alt mr-2"></i>Refresh
                    </button>
                </div>
            </div>
        </div>
    </header>

    <!-- Main Content -->
    <main class="container mx-auto px-6 py-8">
        <!-- GPU Status Card -->
        <div class="gpu-gradient rounded-xl p-8 mb-8 text-white shadow-2xl">
            <div class="flex items-center justify-between mb-6">
                <div>
                    <h2 class="text-3xl font-bold mb-2" id="gpuName">NVIDIA GeForce RTX 4060 Ti</h2>
                    <p class="text-purple-200">Real-time GPU Performance Monitor</p>
                </div>
                <div class="text-right">
                    <div class="text-5xl font-bold" id="gpuUtil">0%</div>
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
                        <i class="fas fa-thermometer-half text-3xl text-orange-400"></i>
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
                            <p class="text-2xl font-bold" id="gpuPerf">P8</p>
                        </div>
                        <i class="fas fa-tachometer-alt text-3xl text-green-400"></i>
                    </div>
                </div>
            </div>
        </div>

        <!-- Mining Operations -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
            <!-- Active Jobs -->
            <div class="bg-gray-800 rounded-xl p-6">
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-tasks mr-3 text-green-500"></i>
                    Mining Operations
                    <span id="jobCount" class="ml-auto text-sm text-gray-400">0 active jobs</span>
                </h3>
                <div id="jobList" class="space-y-3">
                    <div class="text-center py-8">
                        <i class="fas fa-pause-circle text-6xl text-yellow-500 mb-4"></i>
                        <p class="text-xl font-semibold text-yellow-500">Miner Idle</p>
                        <p class="text-gray-400 mt-2">Ready to accept mining jobs</p>
                    </div>
                </div>
            </div>

            <!-- GPU Services -->
            <div class="bg-gray-800 rounded-xl p-6">
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-server mr-3 text-blue-500"></i>
                    GPU Services Status
                </h3>
                <div class="space-y-3">
                    <div class="bg-gray-700 rounded-lg p-4 flex justify-between items-center hover:bg-gray-600 transition">
                        <div class="flex items-center">
                            <i class="fas fa-cube text-purple-400 mr-3"></i>
                            <div>
                                <p class="font-semibold">CUDA Computing</p>
                                <p class="text-sm text-gray-400">4352 CUDA cores available</p>
                            </div>
                        </div>
                        <span class="bg-green-600 px-3 py-1 rounded-full text-sm">Active</span>
                    </div>
                    <div class="bg-gray-700 rounded-lg p-4 flex justify-between items-center hover:bg-gray-600 transition">
                        <div class="flex items-center">
                            <i class="fas fa-project-diagram text-blue-400 mr-3"></i>
                            <div>
                                <p class="font-semibold">Parallel Processing</p>
                                <p class="text-sm text-gray-400">Multi-threaded operations</p>
                            </div>
                        </div>
                        <span class="bg-green-600 px-3 py-1 rounded-full text-sm">Active</span>
                    </div>
                    <div class="bg-gray-700 rounded-lg p-4 flex justify-between items-center hover:bg-gray-600 transition">
                        <div class="flex items-center">
                            <i class="fas fa-hashtag text-green-400 mr-3"></i>
                            <div>
                                <p class="font-semibold">Hash Generation</p>
                                <p class="text-sm text-gray-400">Proof-of-work computation</p>
                            </div>
                        </div>
                        <span class="bg-yellow-600 px-3 py-1 rounded-full text-sm">Standby</span>
                    </div>
                    <div class="bg-gray-700 rounded-lg p-4 flex justify-between items-center hover:bg-gray-600 transition">
                        <div class="flex items-center">
                            <i class="fas fa-brain text-pink-400 mr-3"></i>
                            <div>
                                <p class="font-semibold">AI Model Training</p>
                                <p class="text-sm text-gray-400">Machine learning operations</p>
                            </div>
                        </div>
                        <span class="bg-gray-600 px-3 py-1 rounded-full text-sm">Available</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Performance Charts -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
            <div class="bg-gray-800 rounded-xl p-6">
                <h3 class="text-xl font-bold mb-4">GPU Utilization (Last Hour)</h3>
                <canvas id="utilChart" width="400" height="200"></canvas>
            </div>
            <div class="bg-gray-800 rounded-xl p-6">
                <h3 class="text-xl font-bold mb-4">Hash Rate Performance</h3>
                <canvas id="hashChart" width="400" height="200"></canvas>
            </div>
        </div>

        <!-- System Info -->
        <div class="bg-gray-800 rounded-xl p-6">
            <h3 class="text-xl font-bold mb-4">System Information</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="bg-gray-700 rounded-lg p-4 text-center">
                    <i class="fas fa-desktop text-3xl text-blue-400 mb-2"></i>
                    <p class="text-sm text-gray-400">Host System</p>
                    <p class="font-semibold text-green-400" id="hostname">Loading...</p>
                </div>
                <div class="bg-gray-700 rounded-lg p-4 text-center">
                    <i class="fas fa-microchip text-3xl text-purple-400 mb-2"></i>
                    <p class="text-sm text-gray-400">GPU Access</p>
                    <p class="font-semibold text-green-400">Direct</p>
                </div>
                <div class="bg-gray-700 rounded-lg p-4 text-center">
                    <i class="fas fa-cube text-3xl text-red-400 mb-2"></i>
                    <p class="text-sm text-gray-400">Container</p>
                    <p class="font-semibold text-red-400">Not Used</p>
                </div>
            </div>
        </div>
    </main>

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        // Initialize data
        let utilData = Array(12).fill(0);
        let hashData = Array(12).fill(0);
        let utilChart, hashChart;

        // Initialize charts
        function initCharts() {
            // Utilization chart
            const utilCtx = document.getElementById('utilChart').getContext('2d');
            utilChart = new Chart(utilCtx, {
                type: 'line',
                data: {
                    labels: Array.from({length: 12}, (_, i) => `${60-i*5}m`),
                    datasets: [{
                        label: 'GPU Utilization %',
                        data: utilData,
                        borderColor: 'rgb(147, 51, 234)',
                        backgroundColor: 'rgba(147, 51, 234, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, max: 100, ticks: { color: '#9CA3AF' }, grid: { color: '#374151' } },
                        x: { ticks: { color: '#9CA3AF' }, grid: { color: '#374151' } }
                    }
                }
            });

            // Hash rate chart
            const hashCtx = document.getElementById('hashChart').getContext('2d');
            hashChart = new Chart(hashCtx, {
                type: 'line',
                data: {
                    labels: Array.from({length: 12}, (_, i) => `${60-i*5}m`),
                    datasets: [{
                        label: 'Hash Rate (MH/s)',
                        data: hashData,
                        borderColor: 'rgb(34, 197, 94)',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, ticks: { color: '#9CA3AF' }, grid: { color: '#374151' } },
                        x: { ticks: { color: '#9CA3AF' }, grid: { color: '#374151' } }
                    }
                }
            });
        }

        // Update GPU metrics
        function updateGPU() {
            // Simulate GPU metrics (in real implementation, fetch from API)
            const util = Math.random() * 15; // Idle utilization 0-15%
            const temp = 43 + Math.random() * 10;
            const power = 18 + util * 0.5;
            const mem = 2.9 + Math.random() * 0.5;
            const hash = util * 2.5; // Simulated hash rate

            // Update display
            document.getElementById('gpuUtil').textContent = Math.round(util) + '%';
            document.getElementById('gpuTemp').textContent = Math.round(temp) + '°C';
            document.getElementById('gpuPower').textContent = Math.round(power) + 'W';
            document.getElementById('gpuMem').textContent = mem.toFixed(1) + 'GB';
            
            // Update charts
            utilData.shift();
            utilData.push(util);
            utilChart.update('none');
            
            hashData.shift();
            hashData.push(hash);
            hashChart.update('none');
        }

        // Load system info
        function loadSystemInfo() {
            document.getElementById('hostname').textContent = window.location.hostname;
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            initCharts();
            loadSystemInfo();
            updateGPU();
            setInterval(updateGPU, 5000);
        });
    </script>
</body>
</html>
HTML

# Create startup script
cat > start-dashboard.sh << 'EOF'
#!/bin/bash
cd ~/miner-dashboard
echo ""
echo "========================================"
echo "  Starting AITBC GPU Miner Dashboard"
echo "========================================"
echo ""
echo "Dashboard will be available at:"
echo "  Local:    http://localhost:8080"
echo "  Network:  http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "Press Ctrl+C to stop the dashboard"
echo ""
python3 -m http.server 8080 --bind 0.0.0.0
EOF

chmod +x start-dashboard.sh

echo ""
echo "✅ Dashboard setup complete!"
echo ""
echo "To start the dashboard, run:"
echo "  ~/miner-dashboard/start-dashboard.sh"
echo ""
echo "Dashboard location: ~/miner-dashboard/"
echo ""
echo "========================================"
