#!/usr/bin/env python3
"""
AITBC Miner Management Module
Complete command-line interface for AI compute miner operations including:
- Miner Registration
- Status Management  
- Job Polling & Execution
- Marketplace Integration
- Payment Management
"""

import json
import time
import requests
from typing import Optional, Dict, Any

# Default configuration
DEFAULT_COORDINATOR_URL = "http://localhost:8000"
DEFAULT_API_KEY = "miner_prod_key_use_real_value"


def register_miner(
    miner_id: str,
    wallet: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    capabilities: Optional[str] = None,
    gpu_memory: Optional[int] = None,
    models: Optional[list] = None,
    pricing: Optional[float] = None,
    concurrency: int = 1,
    region: Optional[str] = None
) -> Optional[Dict]:
    """Register miner as AI compute provider"""
    try:
        headers = {
            "X-Api-Key": api_key,
            "X-Miner-ID": miner_id,
            "Content-Type": "application/json"
        }
        
        # Build capabilities from arguments
        caps = {}
        
        if gpu_memory:
            caps["gpu_memory"] = gpu_memory
            caps["gpu_memory_gb"] = gpu_memory
        if models:
            caps["models"] = models
            caps["supported_models"] = models
        if pricing:
            caps["pricing_per_hour"] = pricing
            caps["price_per_hour"] = pricing
            caps["gpu"] = "AI-GPU"
            caps["gpu_count"] = 1
            caps["cuda_version"] = "12.0"
        
        # Override with capabilities JSON if provided
        if capabilities:
            caps.update(json.loads(capabilities))
        
        payload = {
            "wallet_address": wallet,
            "capabilities": caps,
            "concurrency": concurrency,
            "region": region
        }
        
        response = requests.post(
            f"{coordinator_url}/v1/miners/register",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            result = response.json()
            return {
                "action": "register",
                "miner_id": miner_id,
                "status": "✅ Registered successfully",
                "session_token": result.get("session_token"),
                "coordinator_url": coordinator_url,
                "capabilities": caps
            }
        else:
            return {
                "action": "register",
                "status": "❌ Registration failed",
                "error": response.text,
                "status_code": response.status_code
            }
            
    except requests.exceptions.ConnectionError as e:
        return {"action": "register", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "register", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "register", "status": f"❌ HTTP error: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"action": "register", "status": f"❌ JSON decode error: {str(e)}"}
    except Exception as e:
        return {"action": "register", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def get_miner_status(
    miner_id: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL
) -> Optional[Dict]:
    """Get miner status and statistics"""
    try:
        # Use admin API key to get miner status
        admin_api_key = api_key.replace("miner_", "admin_")
        headers = {"X-Api-Key": admin_api_key}
        
        response = requests.get(
            f"{coordinator_url}/v1/admin/miners",
            headers=headers
        )
        
        if response.status_code == 200:
            miners = response.json().get("items", [])
            miner_info = next((m for m in miners if m["miner_id"] == miner_id), None)
            
            if miner_info:
                return {
                    "action": "status",
                    "miner_id": miner_id,
                    "status": f"✅ {miner_info['status']}",
                    "inflight": miner_info["inflight"],
                    "concurrency": miner_info["concurrency"],
                    "region": miner_info["region"],
                    "last_heartbeat": miner_info["last_heartbeat"],
                    "jobs_completed": miner_info["jobs_completed"],
                    "jobs_failed": miner_info["jobs_failed"],
                    "average_job_duration_ms": miner_info["average_job_duration_ms"],
                    "success_rate": (
                        miner_info["jobs_completed"] / 
                        max(1, miner_info["jobs_completed"] + miner_info["jobs_failed"]) * 100
                    )
                }
            else:
                return {
                    "action": "status",
                    "miner_id": miner_id,
                    "status": "❌ Miner not found"
                }
        else:
            return {"action": "status", "status": "❌ Failed to get status", "error": response.text}
            
    except requests.exceptions.ConnectionError as e:
        return {"action": "status", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "status", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "status", "status": f"❌ HTTP error: {str(e)}"}
    except (KeyError, StopIteration) as e:
        return {"action": "status", "status": f"❌ Data processing error: {str(e)}"}
    except Exception as e:
        return {"action": "status", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def send_heartbeat(
    miner_id: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    inflight: int = 0,
    status: str = "ONLINE"
) -> Optional[Dict]:
    """Send miner heartbeat"""
    try:
        headers = {
            "X-Api-Key": api_key,
            "X-Miner-ID": miner_id,
            "Content-Type": "application/json"
        }
        
        payload = {
            "inflight": inflight,
            "status": status,
            "metadata": {
                "timestamp": time.time(),
                "version": "1.0.0",
                "system_info": "AI Compute Miner"
            }
        }
        
        response = requests.post(
            f"{coordinator_url}/v1/miners/heartbeat",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            return {
                "action": "heartbeat",
                "miner_id": miner_id,
                "status": "✅ Heartbeat sent successfully",
                "inflight": inflight,
                "miner_status": status
            }
        else:
            return {"action": "heartbeat", "status": "❌ Heartbeat failed", "error": response.text}
            
    except requests.exceptions.ConnectionError as e:
        return {"action": "heartbeat", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "heartbeat", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "heartbeat", "status": f"❌ HTTP error: {str(e)}"}
    except Exception as e:
        return {"action": "heartbeat", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def poll_jobs(
    miner_id: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    max_wait: int = 30,
    auto_execute: bool = False
) -> Optional[Dict]:
    """Poll for available jobs"""
    try:
        headers = {
            "X-Api-Key": api_key,
            "X-Miner-ID": miner_id,
            "Content-Type": "application/json"
        }
        
        payload = {"max_wait_seconds": max_wait}
        
        response = requests.post(
            f"{coordinator_url}/v1/miners/poll",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200 and response.content:
            job = response.json()
            result = {
                "action": "poll",
                "miner_id": miner_id,
                "status": "✅ Job assigned",
                "job_id": job.get("job_id"),
                "payload": job.get("payload"),
                "constraints": job.get("constraints"),
                "assigned_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            if auto_execute:
                result["auto_execution"] = "🤖 Job execution would start here"
                result["execution_status"] = "Ready to execute"
            
            return result
        elif response.status_code == 204:
            return {
                "action": "poll",
                "miner_id": miner_id,
                "status": "⏸️ No jobs available",
                "message": "No jobs in queue"
            }
        else:
            return {"action": "poll", "status": "❌ Poll failed", "error": response.text}
            
    except requests.exceptions.ConnectionError as e:
        return {"action": "poll", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "poll", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "poll", "status": f"❌ HTTP error: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"action": "poll", "status": f"❌ JSON decode error: {str(e)}"}
    except Exception as e:
        return {"action": "poll", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def submit_job_result(
    job_id: str,
    miner_id: str,
    result: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    success: bool = True,
    duration: Optional[int] = None,
    result_file: Optional[str] = None
) -> Optional[Dict]:
    """Submit job result"""
    try:
        headers = {
            "X-Api-Key": api_key,
            "X-Miner-ID": miner_id,
            "Content-Type": "application/json"
        }
        
        # Load result from file if specified
        if result_file:
            with open(result_file, 'r') as f:
                result = f.read()
        
        payload = {
            "result": result,
            "success": success,
            "metrics": {
                "duration_ms": duration,
                "completed_at": time.time()
            }
        }
        
        response = requests.post(
            f"{coordinator_url}/v1/miners/{job_id}/result",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            return {
                "action": "result",
                "job_id": job_id,
                "miner_id": miner_id,
                "status": "✅ Result submitted successfully",
                "success": success,
                "duration_ms": duration
            }
        else:
            return {"action": "result", "status": "❌ Result submission failed", "error": response.text}
            
    except requests.exceptions.ConnectionError as e:
        return {"action": "result", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "result", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "result", "status": f"❌ HTTP error: {str(e)}"}
    except (FileNotFoundError, PermissionError, IOError) as e:
        return {"action": "result", "status": f"❌ File error: {type(e).__name__}: {str(e)}"}
    except Exception as e:
        return {"action": "result", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def update_capabilities(
    miner_id: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    capabilities: Optional[str] = None,
    gpu_memory: Optional[int] = None,
    models: Optional[list] = None,
    pricing: Optional[float] = None,
    concurrency: Optional[int] = None,
    region: Optional[str] = None,
    wallet: Optional[str] = None
) -> Optional[Dict]:
    """Update miner capabilities"""
    try:
        headers = {
            "X-Api-Key": api_key,
            "X-Miner-ID": miner_id,
            "Content-Type": "application/json"
        }
        
        # Build capabilities from arguments
        caps = {}
        if gpu_memory:
            caps["gpu_memory"] = gpu_memory
            caps["gpu_memory_gb"] = gpu_memory
        if models:
            caps["models"] = models
            caps["supported_models"] = models
        if pricing:
            caps["pricing_per_hour"] = pricing
            caps["price_per_hour"] = pricing
        
        # Override with capabilities JSON if provided
        if capabilities:
            caps.update(json.loads(capabilities))
        
        payload = {
            "capabilities": caps,
            "concurrency": concurrency,
            "region": region
        }
        
        if wallet:
            payload["wallet_address"] = wallet
        
        response = requests.put(
            f"{coordinator_url}/v1/miners/{miner_id}/capabilities",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            return {
                "action": "update",
                "miner_id": miner_id,
                "status": "✅ Capabilities updated successfully",
                "updated_capabilities": caps
            }
        else:
            return {"action": "update", "status": "❌ Update failed", "error": response.text}
            
    except requests.exceptions.ConnectionError as e:
        return {"action": "update", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "update", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "update", "status": f"❌ HTTP error: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"action": "update", "status": f"❌ JSON decode error: {str(e)}"}
    except Exception as e:
        return {"action": "update", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def check_earnings(
    miner_id: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    period: str = "all"
) -> Optional[Dict]:
    """Check miner earnings (placeholder for payment integration)"""
    try:
        # This would integrate with payment system when implemented
        return {
            "action": "earnings",
            "miner_id": miner_id,
            "period": period,
            "status": "📊 Earnings calculation",
            "total_earnings": 0.0,
            "jobs_completed": 0,
            "average_payment": 0.0,
            "note": "Payment integration coming soon"
        }
        
    except Exception as e:
        return {"action": "earnings", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def list_marketplace_offers(
    miner_id: Optional[str] = None,
    region: Optional[str] = None,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL
) -> Optional[Dict]:
    """List marketplace offers"""
    try:
        admin_headers = {"X-Api-Key": api_key.replace("miner_", "admin_")}
        
        params = {}
        if region:
            params["region"] = region
        
        response = requests.get(
            f"{coordinator_url}/v1/marketplace/miner-offers",
            headers=admin_headers,
            params=params
        )
        
        if response.status_code == 200:
            offers = response.json()
            
            # Filter by miner if specified
            if miner_id:
                offers = [o for o in offers if miner_id in str(o).lower()]
            
            return {
                "action": "marketplace_list",
                "status": "✅ Offers retrieved",
                "offers": offers,
                "count": len(offers),
                "region_filter": region,
                "miner_filter": miner_id
            }
        else:
            return {"action": "marketplace_list", "status": "❌ Failed to get offers", "error": response.text}
            
    except requests.exceptions.ConnectionError as e:
        return {"action": "marketplace_list", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "marketplace_list", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "marketplace_list", "status": f"❌ HTTP error: {str(e)}"}
    except Exception as e:
        return {"action": "marketplace_list", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def create_marketplace_offer(
    miner_id: str,
    price: float,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    capacity: int = 1,
    region: Optional[str] = None
) -> Optional[Dict]:
    """Create marketplace offer"""
    try:
        admin_headers = {"X-Api-Key": api_key.replace("miner_", "admin_")}
        
        payload = {
            "miner_id": miner_id,
            "price": price,
            "capacity": capacity,
            "region": region
        }
        
        response = requests.post(
            f"{coordinator_url}/v1/marketplace/offers",
            headers=admin_headers,
            json=payload
        )
        
        if response.status_code == 200:
            return {
                "action": "marketplace_create",
                "miner_id": miner_id,
                "status": "✅ Offer created successfully",
                "price": price,
                "capacity": capacity,
                "region": region
            }
        else:
            return {"action": "marketplace_create", "status": "❌ Offer creation failed", "error": response.text}
            
    except requests.exceptions.ConnectionError as e:
        return {"action": "marketplace_create", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "marketplace_create", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "marketplace_create", "status": f"❌ HTTP error: {str(e)}"}
    except Exception as e:
        return {"action": "marketplace_create", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


# Main function for CLI integration
def miner_cli_dispatcher(action: str, **kwargs) -> Optional[Dict]:
    """Main dispatcher for miner management CLI commands"""
    
    actions = {
        "register": register_miner,
        "status": get_miner_status,
        "heartbeat": send_heartbeat,
        "poll": poll_jobs,
        "result": submit_job_result,
        "update": update_capabilities,
        "earnings": check_earnings,
        "marketplace_list": list_marketplace_offers,
        "marketplace_create": create_marketplace_offer
    }
    
    if action in actions:
        return actions[action](**kwargs)
    else:
        return {
            "action": action,
            "status": f"❌ Unknown action. Available: {', '.join(actions.keys())}"
        }


if __name__ == "__main__":
    # Test the module
    print("🚀 AITBC Miner Management Module")
    print("Available functions:")
    for func in [register_miner, get_miner_status, send_heartbeat, poll_jobs, 
                submit_job_result, update_capabilities, check_earnings,
                list_marketplace_offers, create_marketplace_offer]:
        print(f"  - {func.__name__}")
