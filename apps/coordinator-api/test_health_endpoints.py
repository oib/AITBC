#!/usr/bin/env python3
"""
Test script for enhanced services health endpoints
Validates all 6 enhanced services are responding correctly
"""

import asyncio
import httpx
import json
import sys
from datetime import datetime
from typing import Dict, Any, List

# Enhanced services configuration
SERVICES = {
    "multimodal": {
        "name": "Multi-Modal Agent Service",
        "port": 8002,
        "url": "http://localhost:8002",
        "description": "Text, image, audio, video processing"
    },
    "gpu_multimodal": {
        "name": "GPU Multi-Modal Service", 
        "port": 8003,
        "url": "http://localhost:8003",
        "description": "CUDA-optimized processing"
    },
    "modality_optimization": {
        "name": "Modality Optimization Service",
        "port": 8004,
        "url": "http://localhost:8004", 
        "description": "Specialized optimization strategies"
    },
    "adaptive_learning": {
        "name": "Adaptive Learning Service",
        "port": 8005,
        "url": "http://localhost:8005",
        "description": "Reinforcement learning frameworks"
    },
    "marketplace_enhanced": {
        "name": "Enhanced Marketplace Service",
        "port": 8006,
        "url": "http://localhost:8006",
        "description": "NFT 2.0, royalties, analytics"
    },
    "openclaw_enhanced": {
        "name": "OpenClaw Enhanced Service",
        "port": 8007,
        "url": "http://localhost:8007",
        "description": "Agent orchestration, edge computing"
    }
}


def print_header(title: str):
    """Print formatted header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_success(message: str):
    """Print success message"""
    print(f"✅ {message}")


def print_warning(message: str):
    """Print warning message"""
    print(f"⚠️  {message}")


def print_error(message: str):
    """Print error message"""
    print(f"❌ {message}")


async def test_service_health(client: httpx.AsyncClient, service_id: str, service_info: Dict[str, Any]) -> Dict[str, Any]:
    """Test health endpoint of a specific service"""
    try:
        response = await client.get(f"{service_info['url']}/health", timeout=5.0)
        
        if response.status_code == 200:
            health_data = response.json()
            return {
                "service_id": service_id,
                "status": "healthy",
                "http_status": response.status_code,
                "response_time": str(response.elapsed.total_seconds()) + "s",
                "health_data": health_data
            }
        else:
            return {
                "service_id": service_id,
                "status": "unhealthy",
                "http_status": response.status_code,
                "error": f"HTTP {response.status_code}",
                "response_time": str(response.elapsed.total_seconds()) + "s"
            }
            
    except httpx.TimeoutException:
        return {
            "service_id": service_id,
            "status": "unhealthy",
            "error": "timeout",
            "response_time": ">5s"
        }
    except httpx.ConnectError:
        return {
            "service_id": service_id,
            "status": "unhealthy",
            "error": "connection refused",
            "response_time": "N/A"
        }
    except Exception as e:
        return {
            "service_id": service_id,
            "status": "unhealthy",
            "error": str(e),
            "response_time": "N/A"
        }


async def test_deep_health(client: httpx.AsyncClient, service_id: str, service_info: Dict[str, Any]) -> Dict[str, Any]:
    """Test deep health endpoint of a specific service"""
    try:
        response = await client.get(f"{service_info['url']}/health/deep", timeout=10.0)
        
        if response.status_code == 200:
            health_data = response.json()
            return {
                "service_id": service_id,
                "deep_status": "healthy",
                "http_status": response.status_code,
                "response_time": str(response.elapsed.total_seconds()) + "s",
                "deep_health_data": health_data
            }
        else:
            return {
                "service_id": service_id,
                "deep_status": "unhealthy",
                "http_status": response.status_code,
                "error": f"HTTP {response.status_code}",
                "response_time": str(response.elapsed.total_seconds()) + "s"
            }
            
    except Exception as e:
        return {
            "service_id": service_id,
            "deep_status": "unhealthy",
            "error": str(e),
            "response_time": "N/A"
        }


async def main():
    """Main test function"""
    print_header("AITBC Enhanced Services Health Check")
    print(f"Testing {len(SERVICES)} enhanced services...")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    
    # Test basic health endpoints
    print_header("Basic Health Check")
    
    async with httpx.AsyncClient() as client:
        # Test all services basic health
        basic_tasks = []
        for service_id, service_info in SERVICES.items():
            task = test_service_health(client, service_id, service_info)
            basic_tasks.append(task)
        
        basic_results = await asyncio.gather(*basic_tasks)
        
        # Display basic health results
        healthy_count = 0
        for result in basic_results:
            service_id = result["service_id"]
            service_info = SERVICES[service_id]
            
            if result["status"] == "healthy":
                healthy_count += 1
                print_success(f"{service_info['name']} (:{service_info['port']}) - {result['response_time']}")
                if "health_data" in result:
                    health_data = result["health_data"]
                    print(f"   Service: {health_data.get('service', 'unknown')}")
                    print(f"   Capabilities: {len(health_data.get('capabilities', {}))} available")
                    print(f"   Performance: {health_data.get('performance', {})}")
            else:
                print_error(f"{service_info['name']} (:{service_info['port']}) - {result['error']}")
        
        # Test deep health endpoints for healthy services
        print_header("Deep Health Check")
        
        deep_tasks = []
        for result in basic_results:
            if result["status"] == "healthy":
                service_id = result["service_id"]
                service_info = SERVICES[service_id]
                task = test_deep_health(client, service_id, service_info)
                deep_tasks.append(task)
        
        if deep_tasks:
            deep_results = await asyncio.gather(*deep_tasks)
            
            for result in deep_results:
                service_id = result["service_id"]
                service_info = SERVICES[service_id]
                
                if result["deep_status"] == "healthy":
                    print_success(f"{service_info['name']} (:{service_info['port']}) - {result['response_time']}")
                    if "deep_health_data" in result:
                        deep_data = result["deep_health_data"]
                        overall_health = deep_data.get("overall_health", "unknown")
                        print(f"   Overall Health: {overall_health}")
                        
                        # Show specific test results if available
                        if "modality_tests" in deep_data:
                            tests = deep_data["modality_tests"]
                            passed = len([t for t in tests.values() if t.get("status") == "pass"])
                            total = len(tests)
                            print(f"   Modality Tests: {passed}/{total} passed")
                        elif "cuda_tests" in deep_data:
                            tests = deep_data["cuda_tests"]
                            passed = len([t for t in tests.values() if t.get("status") == "pass"])
                            total = len(tests)
                            print(f"   CUDA Tests: {passed}/{total} passed")
                        elif "feature_tests" in deep_data:
                            tests = deep_data["feature_tests"]
                            passed = len([t for t in tests.values() if t.get("status") == "pass"])
                            total = len(tests)
                            print(f"   Feature Tests: {passed}/{total} passed")
                else:
                    print_warning(f"{service_info['name']} (:{service_info['port']}) - {result['error']}")
        else:
            print_warning("No healthy services available for deep health check")
    
    # Summary
    print_header("Summary")
    total_services = len(SERVICES)
    print(f"Total Services: {total_services}")
    print(f"Healthy Services: {healthy_count}")
    print(f"Unhealthy Services: {total_services - healthy_count}")
    
    if healthy_count == total_services:
        print_success("🎉 All enhanced services are healthy!")
        return 0
    else:
        print_warning(f"⚠️  {total_services - healthy_count} services are unhealthy")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print_warning("\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
