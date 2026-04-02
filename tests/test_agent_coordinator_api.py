"""
Agent Coordinator API Integration Tests
Tests the complete API functionality with real service
"""

import pytest
import asyncio
import requests
import json
from datetime import datetime
from typing import Dict, Any

class TestAgentCoordinatorAPI:
    """Test Agent Coordinator API endpoints"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = requests.get(f"{self.BASE_URL}/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "agent-coordinator"
        assert "timestamp" in data
        assert "version" in data
    
    def test_root_endpoint(self):
        """Test root endpoint"""
        response = requests.get(f"{self.BASE_URL}/")
        assert response.status_code == 200
        
        data = response.json()
        assert "service" in data
        assert "description" in data
        assert "version" in data
        assert "endpoints" in data
    
    def test_agent_registration(self):
        """Test agent registration endpoint"""
        agent_data = {
            "agent_id": "api_test_agent_001",
            "agent_type": "worker",
            "capabilities": ["data_processing", "analysis"],
            "services": ["process_data", "analyze_results"],
            "endpoints": {
                "http": "http://localhost:8001",
                "ws": "ws://localhost:8002"
            },
            "metadata": {
                "version": "1.0.0",
                "region": "test"
            }
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json=agent_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["agent_id"] == "api_test_agent_001"
        assert "registered_at" in data
    
    def test_agent_discovery(self):
        """Test agent discovery endpoint"""
        query = {
            "agent_type": "worker",
            "status": "active"
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/discover",
            json=query,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "agents" in data
        assert "count" in data
        assert isinstance(data["agents"], list)
    
    def test_task_submission(self):
        """Test task submission endpoint"""
        task_data = {
            "task_data": {
                "task_id": "api_test_task_001",
                "task_type": "data_processing",
                "data": {
                    "input": "test_data",
                    "operation": "process"
                },
                "required_capabilities": ["data_processing"]
            },
            "priority": "high",
            "requirements": {
                "agent_type": "worker",
                "min_health_score": 0.8
            }
        }
        
        response = requests.post(
            f"{self.BASE_URL}/tasks/submit",
            json=task_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["task_id"] == "api_test_task_001"
        assert "submitted_at" in data
    
    def test_load_balancer_stats(self):
        """Test load balancer statistics endpoint"""
        response = requests.get(f"{self.BASE_URL}/load-balancer/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "stats" in data
        
        stats = data["stats"]
        assert "strategy" in stats
        assert "total_assignments" in stats
        assert "active_agents" in stats
        assert "success_rate" in stats
    
    def test_load_balancer_strategy_update(self):
        """Test load balancer strategy update endpoint"""
        strategies = ["round_robin", "least_connections", "resource_based"]
        
        for strategy in strategies:
            response = requests.put(
                f"{self.BASE_URL}/load-balancer/strategy",
                params={"strategy": strategy}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["strategy"] == strategy
            assert "updated_at" in data
    
    def test_load_balancer_invalid_strategy(self):
        """Test load balancer with invalid strategy"""
        response = requests.put(
            f"{self.BASE_URL}/load-balancer/strategy",
            params={"strategy": "invalid_strategy"}
        )
        
        assert response.status_code == 400
        assert "Invalid strategy" in response.json()["detail"]
    
    def test_registry_stats(self):
        """Test registry statistics endpoint"""
        response = requests.get(f"{self.BASE_URL}/registry/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "stats" in data
        
        stats = data["stats"]
        assert "total_agents" in stats
        assert "status_counts" in stats
        assert "type_counts" in stats
        assert "service_count" in stats
        assert "capability_count" in stats
    
    def test_agent_status_update(self):
        """Test agent status update endpoint"""
        status_data = {
            "status": "busy",
            "load_metrics": {
                "cpu_usage": 0.7,
                "memory_usage": 0.6,
                "active_tasks": 3
            }
        }
        
        response = requests.put(
            f"{self.BASE_URL}/agents/api_test_agent_001/status",
            json=status_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["agent_id"] == "api_test_agent_001"
        assert data["new_status"] == "busy"
        assert "updated_at" in data
    
    def test_service_based_discovery(self):
        """Test service-based agent discovery"""
        response = requests.get(f"{self.BASE_URL}/agents/service/process_data")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "service" in data
        assert "agents" in data
        assert "count" in data
    
    def test_capability_based_discovery(self):
        """Test capability-based agent discovery"""
        response = requests.get(f"{self.BASE_URL}/agents/capability/data_processing")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "capability" in data
        assert "agents" in data
        assert "count" in data

class TestAPIPerformance:
    """Test API performance and reliability"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_response_times(self):
        """Test API response times"""
        import time
        
        endpoints = [
            "/health",
            "/load-balancer/stats",
            "/registry/stats"
        ]
        
        for endpoint in endpoints:
            start_time = time.time()
            response = requests.get(f"{self.BASE_URL}{endpoint}")
            end_time = time.time()
            
            assert response.status_code == 200
            response_time = end_time - start_time
            assert response_time < 1.0  # Should respond within 1 second
    
    def test_concurrent_requests(self):
        """Test concurrent request handling"""
        import threading
        import time
        
        results = []
        
        def make_request():
            response = requests.get(f"{self.BASE_URL}/health")
            results.append(response.status_code)
        
        # Make 10 concurrent requests
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 10

class TestAPIErrorHandling:
    """Test API error handling"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_nonexistent_agent(self):
        """Test requesting nonexistent agent"""
        response = requests.get(f"{self.BASE_URL}/agents/nonexistent_agent")
        assert response.status_code == 404
        
        data = response.json()
        assert "message" in data
        assert "not found" in data["message"].lower()
    
    def test_invalid_agent_data(self):
        """Test invalid agent registration data"""
        invalid_data = {
            "agent_id": "",  # Empty agent ID
            "agent_type": "invalid_type"
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json=invalid_data,
            headers={"Content-Type": "application/json"}
        )
        
        # Should handle invalid data gracefully - now returns 422 for validation errors
        assert response.status_code == 422
    
    def test_invalid_task_data(self):
        """Test invalid task submission data"""
        # Test with completely malformed JSON that should fail validation
        invalid_task = {
            "invalid_field": "invalid_value"
            # Missing required task_data and priority fields
        }
        
        response = requests.post(
            f"{self.BASE_URL}/tasks/submit",
            json=invalid_task,
            headers={"Content-Type": "application/json"}
        )
        
        # Should handle missing required fields gracefully
        assert response.status_code == 422

if __name__ == '__main__':
    pytest.main([__file__])
