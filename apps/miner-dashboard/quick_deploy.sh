#!/bin/bash

echo "=== Quick AITBC Miner Dashboard Setup ==="

# Create directory
sudo mkdir -p /opt/aitbc-miner-dashboard

# Create simple dashboard
cat > /opt/aitbc-miner-dashboard/index.html << 'HTML'
<!DOCTYPE html>
<html>
<head>
    <title>AITBC Miner Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="container mx-auto px-6 py-8">
        <div class="flex items-center justify-between mb-8">
            <h1 class="text-3xl font-bold flex items-center">
                <i class="fas fa-microchip text-purple-500 mr-3"></i>
                AITBC Miner Dashboard
            </h1>
            <div class="flex items-center">
                <span class="w-3 h-3 bg-green-500 rounded-full mr-2"></span>
                <span>GPU Connected</span>
            </div>
        </div>
        
        <div class="bg-gradient-to-r from-purple-600 to-blue-600 rounded-xl p-6 mb-8">
            <h2 class="text-2xl font-bold mb-4">NVIDIA GeForce RTX 4060 Ti</h2>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div class="bg-white/10 backdrop-blur rounded-lg p-4">
                    <p class="text-sm opacity-80">Utilization</p>
                    <p class="text-2xl font-bold" id="util">0%</p>
                </div>
                <div class="bg-white/10 backdrop-blur rounded-lg p-4">
                    <p class="text-sm opacity-80">Temperature</p>
                    <p class="text-2xl font-bold" id="temp">43°C</p>
                </div>
                <div class="bg-white/10 backdrop-blur rounded-lg p-4">
                    <p class="text-sm opacity-80">Power</p>
                    <p class="text-2xl font-bold" id="power">18W</p>
                </div>
                <div class="bg-white/10 backdrop-blur rounded-lg p-4">
                    <p class="text-sm opacity-80">Memory</p>
                    <p class="text-2xl font-bold" id="mem">2.9GB</p>
                </div>
            </div>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div class="bg-gray-800 rounded-xl p-6">
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-tasks text-green-500 mr-2"></i>
                    Mining Jobs
                </h3>
                <div class="text-center text-gray-500 py-12">
                    <i class="fas fa-inbox text-5xl mb-4"></i>
                    <p>No active jobs</p>
                    <p class="text-sm mt-2">Miner is ready to receive jobs</p>
                </div>
            </div>
            
            <div class="bg-gray-800 rounded-xl p-6">
                <h3 class="text-xl font-bold mb-4 flex items-center">
                    <i class="fas fa-server text-blue-500 mr-2"></i>
                    Available Services
                </h3>
                <div class="space-y-3">
                    <div class="bg-gray-700 rounded-lg p-3 flex justify-between items-center">
                        <span>GPU Computing</span>
                        <span class="bg-green-600 px-2 py-1 rounded text-xs">Active</span>
                    </div>
                    <div class="bg-gray-700 rounded-lg p-3 flex justify-between items-center">
                        <span>Parallel Processing</span>
                        <span class="bg-green-600 px-2 py-1 rounded text-xs">Active</span>
                    </div>
                    <div class="bg-gray-700 rounded-lg p-3 flex justify-between items-center">
                        <span>Hash Generation</span>
                        <span class="bg-yellow-600 px-2 py-1 rounded text-xs">Standby</span>
                    </div>
                    <div class="bg-gray-700 rounded-lg p-3 flex justify-between items-center">
                        <span>AI Model Training</span>
                        <span class="bg-gray-600 px-2 py-1 rounded text-xs">Available</span>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="mt-8 bg-gray-800 rounded-xl p-6">
            <h3 class="text-xl font-bold mb-4">Mining Statistics</h3>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                <div>
                    <p class="text-3xl font-bold text-green-500">0</p>
                    <p class="text-sm text-gray-400">Jobs Completed</p>
                </div>
                <div>
                    <p class="text-3xl font-bold text-blue-500">0s</p>
                    <p class="text-sm text-gray-400">Avg Job Time</p>
                </div>
                <div>
                    <p class="text-3xl font-bold text-purple-500">100%</p>
                    <p class="text-sm text-gray-400">Success Rate</p>
                </div>
                <div>
                    <p class="text-3xl font-bold text-yellow-500">0 MH/s</p>
                    <p class="text-sm text-gray-400">Hash Rate</p>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // Simulate real-time updates
        let util = 0;
        let temp = 43;
        let power = 18;
        
        function updateStats() {
            // Simulate GPU usage
            util = Math.max(0, Math.min(100, util + (Math.random() - 0.5) * 10));
            temp = Math.max(35, Math.min(85, temp + (Math.random() - 0.5) * 2));
            power = Math.max(10, Math.min(165, util * 1.5 + (Math.random() - 0.5) * 5));
            
            document.getElementById('util').textContent = Math.round(util) + '%';
            document.getElementById('temp').textContent = Math.round(temp) + '°C';
            document.getElementById('power').textContent = Math.round(power) + 'W';
            document.getElementById('mem').textContent = (2.9 + util * 0.1).toFixed(1) + 'GB';
        }
        
        // Update every 2 seconds
        setInterval(updateStats, 2000);
        updateStats();
    </script>
</body>
</html>
HTML

# Create simple Python server
cat > /opt/aitbc-miner-dashboard/serve.py << 'PY'
import http.server
import socketserver
import os

PORT = 8080
os.chdir('/opt/aitbc-miner-dashboard')

Handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Dashboard running at http://localhost:{PORT}")
    httpd.serve_forever()
PY

# Create systemd service
cat > /etc/systemd/system/aitbc-miner-dashboard.service << 'EOF'
[Unit]
Description=AITBC Miner Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aitbc-miner-dashboard
ExecStart=/usr/bin/python3 serve.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Start service
systemctl daemon-reload
systemctl enable aitbc-miner-dashboard
systemctl start aitbc-miner-dashboard

echo ""
echo "✅ Dashboard deployed!"
echo "Access at: http://localhost:8080"
echo "Check status: systemctl status aitbc-miner-dashboard"
