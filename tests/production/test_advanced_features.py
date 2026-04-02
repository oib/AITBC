"""
Comprehensive Advanced Features Test
Tests all advanced AI/ML and consensus features
"""

import pytest
import requests
import json
from typing import Dict, Any

class TestAdvancedFeatures:
    """Test advanced AI/ML and consensus features"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_advanced_features_status(self):
        """Test advanced features status endpoint"""
        response = requests.get(f"{self.BASE_URL}/advanced-features/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "features" in data
        assert "realtime_learning" in data["features"]
        assert "advanced_ai" in data["features"]
        assert "distributed_consensus" in data["features"]
    
    def test_realtime_learning_experience(self):
        """Test real-time learning experience recording"""
        experience_data = {
            "context": {
                "system_load": 0.7,
                "agents": 5,
                "task_queue_size": 25
            },
            "action": "scale_resources",
            "outcome": "success",
            "performance_metrics": {
                "response_time": 0.5,
                "throughput": 100,
                "error_rate": 0.02
            },
            "reward": 0.8
        }
        
        response = requests.post(
            f"{self.BASE_URL}/ai/learning/experience",
            json=experience_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "experience_id" in data
    
    def test_learning_statistics(self):
        """Test learning statistics endpoint"""
        response = requests.get(f"{self.BASE_URL}/ai/learning/statistics")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "total_experiences" in data
        assert "learning_rate" in data
    
    def test_performance_prediction(self):
        """Test performance prediction"""
        context = {
            "system_load": 0.6,
            "agents": 4,
            "task_queue_size": 20
        }
        
        response = requests.post(
            f"{self.BASE_URL}/ai/learning/predict",
            params={"action": "scale_resources"},
            json=context,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        # Performance model may not be available, which is expected
        if data["status"] == "error":
            assert "Performance model not available" in data["message"]
        else:
            assert data["status"] == "success"
            assert "predicted_performance" in data
            assert "confidence" in data
    
    def test_action_recommendation(self):
        """Test AI action recommendation"""
        context = {
            "system_load": 0.8,
            "agents": 3,
            "task_queue_size": 30
        }
        available_actions = ["scale_resources", "allocate_agents", "maintain_status"]
        
        response = requests.post(
            f"{self.BASE_URL}/ai/learning/recommend",
            json=context,
            params={"available_actions": available_actions},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "recommended_action" in data
        assert data["recommended_action"] in available_actions
    
    def test_neural_network_creation(self):
        """Test neural network creation"""
        config = {
            "network_id": "test_nn_001",
            "input_size": 10,
            "hidden_sizes": [64, 32],
            "output_size": 1,
            "learning_rate": 0.01
        }
        
        response = requests.post(
            f"{self.BASE_URL}/ai/neural-network/create",
            json=config,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "network_id" in data
        assert "architecture" in data
    
    def test_ml_model_creation(self):
        """Test ML model creation"""
        config = {
            "model_id": "test_ml_001",
            "model_type": "linear_regression",
            "features": ["system_load", "agent_count"],
            "target": "performance_score"
        }
        
        response = requests.post(
            f"{self.BASE_URL}/ai/ml-model/create",
            json=config,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "model_id" in data
        assert data["model_type"] == "linear_regression"
    
    def test_ai_statistics(self):
        """Test comprehensive AI statistics"""
        response = requests.get(f"{self.BASE_URL}/ai/statistics")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "total_models" in data
        assert "total_neural_networks" in data
        assert "total_predictions" in data
    
    def test_consensus_node_registration(self):
        """Test consensus node registration"""
        node_data = {
            "node_id": "consensus_node_001",
            "endpoint": "http://localhost:9002",
            "reputation_score": 0.9,
            "voting_power": 1.0
        }
        
        response = requests.post(
            f"{self.BASE_URL}/consensus/node/register",
            json=node_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "node_id" in data
        assert data["node_id"] == "consensus_node_001"
    
    def test_consensus_proposal_creation(self):
        """Test consensus proposal creation"""
        proposal_data = {
            "proposer_id": "node_001",
            "content": {
                "action": "system_update",
                "version": "1.1.0",
                "description": "Update system to new version"
            }
        }
        
        response = requests.post(
            f"{self.BASE_URL}/consensus/proposal/create",
            json=proposal_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "proposal_id" in data
        assert "required_votes" in data
    
    def test_consensus_algorithm_setting(self):
        """Test consensus algorithm setting"""
        response = requests.put(
            f"{self.BASE_URL}/consensus/algorithm",
            params={"algorithm": "supermajority"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["algorithm"] == "supermajority"
    
    def test_consensus_statistics(self):
        """Test consensus statistics"""
        response = requests.get(f"{self.BASE_URL}/consensus/statistics")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "total_proposals" in data
        assert "active_nodes" in data
        assert "success_rate" in data
        assert "current_algorithm" in data

class TestAdvancedFeaturesIntegration:
    """Integration tests for advanced features"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_end_to_end_learning_cycle(self):
        """Test complete learning cycle"""
        # Step 1: Record multiple experiences
        experiences = [
            {
                "context": {"load": 0.5, "agents": 4},
                "action": "maintain",
                "outcome": "success",
                "performance_metrics": {"response_time": 0.3},
                "reward": 0.7
            },
            {
                "context": {"load": 0.8, "agents": 2},
                "action": "scale",
                "outcome": "success",
                "performance_metrics": {"response_time": 0.6},
                "reward": 0.9
            },
            {
                "context": {"load": 0.9, "agents": 2},
                "action": "maintain",
                "outcome": "failure",
                "performance_metrics": {"response_time": 1.2},
                "reward": 0.3
            }
        ]
        
        for exp in experiences:
            response = requests.post(
                f"{self.BASE_URL}/ai/learning/experience",
                json=exp,
                headers={"Content-Type": "application/json"}
            )
            assert response.status_code == 200
        
        # Step 2: Get learning statistics
        response = requests.get(f"{self.BASE_URL}/ai/learning/statistics")
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_experiences"] >= 3
        
        # Step 3: Get recommendation
        context = {"load": 0.85, "agents": 2}
        actions = ["maintain", "scale", "allocate"]
        
        response = requests.post(
            f"{self.BASE_URL}/ai/learning/recommend",
            json=context,
            params={"available_actions": actions},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        recommendation = response.json()
        assert recommendation["recommended_action"] in actions
    
    def test_end_to_end_consensus_cycle(self):
        """Test complete consensus cycle"""
        # Step 1: Register multiple nodes
        nodes = [
            {"node_id": "node_001", "endpoint": "http://localhost:9002"},
            {"node_id": "node_002", "endpoint": "http://localhost:9003"},
            {"node_id": "node_003", "endpoint": "http://localhost:9004"}
        ]
        
        for node in nodes:
            response = requests.post(
                f"{self.BASE_URL}/consensus/node/register",
                json=node,
                headers={"Content-Type": "application/json"}
            )
            assert response.status_code == 200
        
        # Step 2: Create proposal
        proposal = {
            "proposer_id": "node_001",
            "content": {"action": "test_consensus", "value": "test_value"}
        }
        
        response = requests.post(
            f"{self.BASE_URL}/consensus/proposal/create",
            json=proposal,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        proposal_data = response.json()
        proposal_id = proposal_data["proposal_id"]
        
        # Step 3: Cast votes
        for node_id in ["node_001", "node_002", "node_003"]:
            response = requests.post(
                f"{self.BASE_URL}/consensus/proposal/{proposal_id}/vote",
                params={"node_id": node_id, "vote": "true"}
            )
            assert response.status_code == 200
        
        # Step 4: Check proposal status
        response = requests.get(f"{self.BASE_URL}/consensus/proposal/{proposal_id}")
        assert response.status_code == 200
        status = response.json()
        assert status["proposal_id"] == proposal_id
        assert status["current_votes"]["total"] == 3
        
        # Step 5: Get consensus statistics
        response = requests.get(f"{self.BASE_URL}/consensus/statistics")
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_proposals"] >= 1
        assert stats["active_nodes"] >= 3

if __name__ == '__main__':
    pytest.main([__file__])
