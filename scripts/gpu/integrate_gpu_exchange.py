#!/usr/bin/env python3
"""
Integrate GPU Miner with existing Trade Exchange
"""

import httpx
import json
import subprocess
import time
from datetime import datetime

# Configuration
EXCHANGE_URL = "http://localhost:3002"
GPU_REGISTRY_URL = "http://localhost:8091"

def update_exchange_with_gpu():
    """Update the exchange frontend to show registered GPUs"""
    
    # Read the exchange HTML
    with open('/home/oib/windsurf/aitbc/apps/trade-exchange/index.html', 'r') as f:
        html_content = f.read()
    
    # Add GPU marketplace integration
    gpu_integration = """
    <script>
    // GPU Integration
    async function loadRealGPUOffers() {
        try {
            const response = await fetch('http://localhost:8091/miners/list');
            const data = await response.json();
            
            if (data.gpus && data.gpus.length > 0) {
                displayRealGPUOffers(data.gpus);
            } else {
                displayDemoOffers();
            }
        } catch (error) {
            console.log('Using demo GPU offers');
            displayDemoOffers();
        }
    }
    
    function displayRealGPUOffers(gpus) {
        const container = document.getElementById('gpuList');
        container.innerHTML = '';
        
        gpus.forEach(gpu => {
            const gpuCard = `
                <div class="bg-white rounded-lg shadow-lg p-6 card-hover">
                    <div class="flex justify-between items-start mb-4">
                        <h3 class="text-lg font-semibold">${gpu.capabilities.gpu.model}</h3>
                        <span class="bg-green-100 text-green-800 px-2 py-1 rounded text-sm">Available</span>
                    </div>
                    <div class="space-y-2 text-sm text-gray-600 mb-4">
                        <p><i data-lucide="monitor" class="w-4 h-4 inline mr-1"></i>Memory: ${gpu.capabilities.gpu.memory_gb} GB</p>
                        <p><i data-lucide="zap" class="w-4 h-4 inline mr-1"></i>CUDA: ${gpu.capabilities.gpu.cuda_version}</p>
                        <p><i data-lucide="cpu" class="w-4 h-4 inline mr-1"></i>Concurrency: ${gpu.concurrency}</p>
                        <p><i data-lucide="map-pin" class="w-4 h-4 inline mr-1"></i>Region: ${gpu.region}</p>
                    </div>
                    <div class="flex justify-between items-center">
                        <span class="text-2xl font-bold text-purple-600">50 AITBC/hr</span>
                        <button onclick="purchaseGPU('${gpu.id}')" class="bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700 transition">
                            Purchase
                        </button>
                    </div>
                </div>
            `;
            container.innerHTML += gpuCard;
        });
        
        lucide.createIcons();
    }
    
    // Override the loadGPUOffers function
    const originalLoadGPUOffers = loadGPUOffers;
    loadGPUOffers = loadRealGPUOffers;
    </script>
    """
    
    # Insert before closing body tag
    if '</body>' in html_content:
        html_content = html_content.replace('</body>', gpu_integration + '</body>')
        
        # Write back to file
        with open('/home/oib/windsurf/aitbc/apps/trade-exchange/index.html', 'w') as f:
            f.write(html_content)
        
        print("✅ Updated exchange with GPU integration!")
    else:
        print("❌ Could not find </body> tag in exchange HTML")

def create_gpu_api_endpoint():
    """Create an API endpoint in the exchange to serve GPU data"""
    
    api_code = """
@app.get("/api/gpu/offers")
async def get_gpu_offers():
    \"\"\"Get available GPU offers\"\"\"
    try:
        # Fetch from GPU registry
        response = httpx.get("http://localhost:8091/miners/list")
        if response.status_code == 200:
            data = response.json()
            return {"offers": data.get("gpus", [])}
    except:
        pass
    
    # Return demo data if registry not available
    return {
        "offers": [{
            "id": "demo-gpu-1",
            "model": "NVIDIA RTX 4060 Ti",
            "memory_gb": 16,
            "price_per_hour": 50,
            "available": True
        }]
    }
"""
    
    print("\n📝 To add GPU API endpoint to exchange, add this code to simple_exchange_api.py:")
    print(api_code)

def main():
    print("🔗 Integrating GPU Miner with Trade Exchange...")
    
    # Update exchange frontend
    update_exchange_with_gpu()
    
    # Show API integration code
    create_gpu_api_endpoint()
    
    print("\n📊 Integration Summary:")
    print("1. ✅ Exchange frontend updated to show real GPUs")
    print("2. 📝 See above for API endpoint code")
    print("3. 🌐 Access the exchange at: http://localhost:3002")
    print("4. 🎯 GPU Registry available at: http://localhost:8091/miners/list")
    
    print("\n🔄 To see the integrated GPU marketplace:")
    print("1. Restart the trade exchange if needed:")
    print("   cd /home/oib/windsurf/aitbc/apps/trade-exchange")
    print("   python simple_exchange_api.py")
    print("2. Open http://localhost:3002 in browser")
    print("3. Click 'Browse GPU Marketplace'")

if __name__ == "__main__":
    main()
