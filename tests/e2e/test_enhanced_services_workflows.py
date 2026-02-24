"""
End-to-End Workflow Tests for Enhanced Services
Tests complete workflows across all 6 enhanced AI agent services
"""

import asyncio
import httpx
import pytest
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import AsyncMock, patch

# Enhanced services configuration
ENHANCED_SERVICES = {
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


class EnhancedServicesWorkflowTester:
    """Test framework for enhanced services end-to-end workflows"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.test_data = self._generate_test_data()
        self.workflow_results = {}
    
    def _generate_test_data(self) -> Dict[str, Any]:
        """Generate test data for multi-modal workflows"""
        return {
            "text_data": {
                "content": "This is a test document for AI processing.",
                "language": "en",
                "type": "analysis"
            },
            "image_data": {
                "url": "https://example.com/test-image.jpg",
                "format": "jpeg",
                "size": "1024x768"
            },
            "audio_data": {
                "url": "https://example.com/test-audio.wav",
                "format": "wav",
                "duration": 30.5
            },
            "video_data": {
                "url": "https://example.com/test-video.mp4",
                "format": "mp4",
                "duration": 120.0,
                "resolution": "1920x1080"
            },
            "tabular_data": {
                "headers": ["feature1", "feature2", "target"],
                "rows": [
                    [1.0, 2.0, 0],
                    [2.0, 3.0, 1],
                    [3.0, 4.0, 0]
                ]
            },
            "graph_data": {
                "nodes": ["A", "B", "C"],
                "edges": [("A", "B"), ("B", "C"), ("C", "A")]
            }
        }
    
    async def setup_test_environment(self) -> bool:
        """Setup test environment and verify all services are healthy"""
        print("🔧 Setting up test environment...")
        
        # Check all services are healthy
        healthy_services = []
        for service_id, service_info in ENHANCED_SERVICES.items():
            try:
                response = await self.client.get(f"{service_info['url']}/health")
                if response.status_code == 200:
                    healthy_services.append(service_id)
                    print(f"✅ {service_info['name']} is healthy")
                else:
                    print(f"❌ {service_info['name']} is unhealthy: {response.status_code}")
            except Exception as e:
                print(f"❌ {service_info['name']} is unavailable: {e}")
        
        if len(healthy_services) != len(ENHANCED_SERVICES):
            print(f"⚠️  Only {len(healthy_services)}/{len(ENHANCED_SERVICES)} services are healthy")
            return False
        
        print("✅ All enhanced services are healthy")
        return True
    
    async def cleanup_test_environment(self):
        """Cleanup test environment"""
        print("🧹 Cleaning up test environment...")
        await self.client.aclose()
    
    async def test_multimodal_processing_workflow(self) -> Dict[str, Any]:
        """Test complete multi-modal processing workflow"""
        print("\n🤖 Testing Multi-Modal Processing Workflow...")
        
        workflow_start = time.time()
        results = {}
        
        try:
            # Step 1: Process text data
            print("  📝 Processing text data...")
            text_response = await self.client.post(
                f"{ENHANCED_SERVICES['multimodal']['url']}/process",
                json={
                    "agent_id": "test-agent-001",
                    "inputs": self.test_data["text_data"],
                    "processing_mode": "text_analysis"
                }
            )
            if text_response.status_code == 200:
                results["text_processing"] = {
                    "status": "success",
                    "processing_time": text_response.json().get("processing_time", "unknown"),
                    "result": text_response.json().get("result", {})
                }
                print(f"    ✅ Text processed in {results['text_processing']['processing_time']}")
            else:
                results["text_processing"] = {"status": "failed", "error": str(text_response.status_code)}
                print(f"    ❌ Text processing failed: {text_response.status_code}")
            
            # Step 2: Process image data with GPU acceleration
            print("  🖼️  Processing image data with GPU...")
            image_response = await self.client.post(
                f"{ENHANCED_SERVICES['gpu_multimodal']['url']}/process",
                json={
                    "modality": "image",
                    "data": self.test_data["image_data"],
                    "acceleration": "cuda"
                }
            )
            if image_response.status_code == 200:
                results["image_processing"] = {
                    "status": "success",
                    "processing_time": image_response.json().get("processing_time", "unknown"),
                    "gpu_utilization": image_response.json().get("gpu_utilization", "unknown"),
                    "result": image_response.json().get("result", {})
                }
                print(f"    ✅ Image processed with GPU in {results['image_processing']['processing_time']}")
            else:
                results["image_processing"] = {"status": "failed", "error": str(image_response.status_code)}
                print(f"    ❌ Image processing failed: {image_response.status_code}")
            
            # Step 3: Optimize processed data
            print("  ⚡ Optimizing processed data...")
            optimization_response = await self.client.post(
                f"{ENHANCED_SERVICES['modality_optimization']['url']}/optimize-multimodal",
                json={
                    "multimodal_data": {
                        "text": self.test_data["text_data"],
                        "image": self.test_data["image_data"]
                    },
                    "strategy": "balanced"
                }
            )
            if optimization_response.status_code == 200:
                results["optimization"] = {
                    "status": "success",
                    "optimization_ratio": optimization_response.json().get("compression_ratio", "unknown"),
                    "speedup": optimization_response.json().get("speedup", "unknown"),
                    "result": optimization_response.json().get("result", {})
                }
                print(f"    ✅ Data optimized with {results['optimization']['speedup']} speedup")
            else:
                results["optimization"] = {"status": "failed", "error": str(optimization_response.status_code)}
                print(f"    ❌ Optimization failed: {optimization_response.status_code}")
            
            # Step 4: Create adaptive learning agent
            print("  🧠 Creating adaptive learning agent...")
            agent_response = await self.client.post(
                f"{ENHANCED_SERVICES['adaptive_learning']['url']}/create-agent",
                json={
                    "agent_id": "test-adaptive-agent",
                    "algorithm": "deep_q_network",
                    "config": {
                        "learning_rate": 0.001,
                        "batch_size": 32,
                        "network_size": "medium"
                    }
                }
            )
            if agent_response.status_code == 200:
                results["agent_creation"] = {
                    "status": "success",
                    "agent_id": agent_response.json().get("agent_id", "unknown"),
                    "algorithm": agent_response.json().get("algorithm", "unknown")
                }
                print(f"    ✅ Agent created: {results['agent_creation']['agent_id']}")
            else:
                results["agent_creation"] = {"status": "failed", "error": str(agent_response.status_code)}
                print(f"    ❌ Agent creation failed: {agent_response.status_code}")
            
            # Step 5: Deploy to OpenClaw edge
            print("  🌐 Deploying to OpenClaw edge...")
            edge_response = await self.client.post(
                f"{ENHANCED_SERVICES['openclaw_enhanced']['url']}/deploy-agent",
                json={
                    "agent_id": "test-adaptive-agent",
                    "deployment_config": {
                        "execution_mode": "hybrid",
                        "edge_locations": ["us-east", "eu-west"],
                        "resource_allocation": "auto"
                    }
                }
            )
            if edge_response.status_code == 200:
                results["edge_deployment"] = {
                    "status": "success",
                    "deployment_id": edge_response.json().get("deployment_id", "unknown"),
                    "edge_nodes": edge_response.json().get("edge_nodes", []),
                    "execution_mode": edge_response.json().get("execution_mode", "unknown")
                }
                print(f"    ✅ Deployed to {len(results['edge_deployment']['edge_nodes'])} edge nodes")
            else:
                results["edge_deployment"] = {"status": "failed", "error": str(edge_response.status_code)}
                print(f"    ❌ Edge deployment failed: {edge_response.status_code}")
            
            # Step 6: Create marketplace listing
            print("  🏪 Creating marketplace listing...")
            marketplace_response = await self.client.post(
                f"{ENHANCED_SERVICES['marketplace_enhanced']['url']}/v1/models/mint",
                json={
                    "title": "Multi-Modal AI Agent",
                    "description": "Advanced multi-modal agent with edge deployment",
                    "model_type": "multimodal_agent",
                    "capabilities": ["text_analysis", "image_processing", "edge_computing"],
                    "pricing": {
                        "execution_price": 0.05,
                        "subscription_price": 10.0
                    },
                    "royalties": {
                        "creator_percentage": 10.0,
                        "platform_percentage": 5.0
                    }
                }
            )
            if marketplace_response.status_code == 200:
                results["marketplace_listing"] = {
                    "status": "success",
                    "model_id": marketplace_response.json().get("model_id", "unknown"),
                    "token_id": marketplace_response.json().get("token_id", "unknown"),
                    "pricing": marketplace_response.json().get("pricing", {})
                }
                print(f"    ✅ Marketplace listing created: {results['marketplace_listing']['model_id']}")
            else:
                results["marketplace_listing"] = {"status": "failed", "error": str(marketplace_response.status_code)}
                print(f"    ❌ Marketplace listing failed: {marketplace_response.status_code}")
            
            workflow_duration = time.time() - workflow_start
            
            # Calculate overall success
            successful_steps = len([r for r in results.values() if r.get("status") == "success"])
            total_steps = len(results)
            
            return {
                "workflow_name": "multimodal_processing",
                "total_steps": total_steps,
                "successful_steps": successful_steps,
                "success_rate": successful_steps / total_steps,
                "workflow_duration": workflow_duration,
                "results": results,
                "overall_status": "success" if successful_steps == total_steps else "partial_failure"
            }
            
        except Exception as e:
            return {
                "workflow_name": "multimodal_processing",
                "error": str(e),
                "overall_status": "failed",
                "workflow_duration": time.time() - workflow_start
            }
    
    async def test_gpu_acceleration_workflow(self) -> Dict[str, Any]:
        """Test GPU acceleration workflow"""
        print("\n🚀 Testing GPU Acceleration Workflow...")
        
        workflow_start = time.time()
        results = {}
        
        try:
            # Step 1: Check GPU availability
            print("  🔍 Checking GPU availability...")
            gpu_health = await self.client.get(f"{ENHANCED_SERVICES['gpu_multimodal']['url']}/health")
            if gpu_health.status_code == 200:
                gpu_info = gpu_health.json().get("gpu", {})
                results["gpu_availability"] = {
                    "status": "success",
                    "gpu_name": gpu_info.get("name", "unknown"),
                    "memory_total": gpu_info.get("memory_total_gb", "unknown"),
                    "memory_free": gpu_info.get("memory_free_gb", "unknown"),
                    "utilization": gpu_info.get("utilization_percent", "unknown")
                }
                print(f"    ✅ GPU available: {results['gpu_availability']['gpu_name']}")
            else:
                results["gpu_availability"] = {"status": "failed", "error": "GPU not available"}
                print("    ❌ GPU not available")
                return {"workflow_name": "gpu_acceleration", "overall_status": "failed", "error": "GPU not available"}
            
            # Step 2: Test cross-modal attention
            print("  🧠 Testing cross-modal attention...")
            attention_response = await self.client.post(
                f"{ENHANCED_SERVICES['gpu_multimodal']['url']}/attention",
                json={
                    "modality_features": {
                        "text": [0.1, 0.2, 0.3, 0.4, 0.5],
                        "image": [0.5, 0.4, 0.3, 0.2, 0.1],
                        "audio": [0.3, 0.3, 0.3, 0.3, 0.3]
                    },
                    "attention_config": {
                        "attention_type": "cross_modal",
                        "num_heads": 8,
                        "dropout": 0.1
                    }
                }
            )
            if attention_response.status_code == 200:
                attention_result = attention_response.json()
                results["cross_modal_attention"] = {
                    "status": "success",
                    "processing_time": attention_result.get("processing_time", "unknown"),
                    "speedup": attention_result.get("speedup", "unknown"),
                    "memory_usage": attention_result.get("memory_usage", "unknown"),
                    "attention_weights": attention_result.get("attention_weights", [])
                }
                print(f"    ✅ Cross-modal attention: {results['cross_modal_attention']['speedup']} speedup")
            else:
                results["cross_modal_attention"] = {"status": "failed", "error": str(attention_response.status_code)}
                print(f"    ❌ Cross-modal attention failed: {attention_response.status_code}")
            
            # Step 3: Test multi-modal fusion
            print("  🔀 Testing multi-modal fusion...")
            fusion_response = await self.client.post(
                f"{ENHANCED_SERVICES['gpu_multimodal']['url']}/fusion",
                json={
                    "modality_data": {
                        "text_features": [0.1, 0.2, 0.3],
                        "image_features": [0.4, 0.5, 0.6],
                        "audio_features": [0.7, 0.8, 0.9]
                    },
                    "fusion_config": {
                        "fusion_type": "attention_based",
                        "output_dim": 256
                    }
                }
            )
            if fusion_response.status_code == 200:
                fusion_result = fusion_response.json()
                results["multi_modal_fusion"] = {
                    "status": "success",
                    "processing_time": fusion_result.get("processing_time", "unknown"),
                    "speedup": fusion_result.get("speedup", "unknown"),
                    "fused_features": fusion_result.get("fused_features", [])[:10]  # First 10 features
                }
                print(f"    ✅ Multi-modal fusion: {results['multi_modal_fusion']['speedup']} speedup")
            else:
                results["multi_modal_fusion"] = {"status": "failed", "error": str(fusion_response.status_code)}
                print(f"    ❌ Multi-modal fusion failed: {fusion_response.status_code}")
            
            # Step 4: Compare CPU vs GPU performance
            print("  ⏱️  Comparing CPU vs GPU performance...")
            
            # CPU processing (mock)
            cpu_start = time.time()
            await asyncio.sleep(0.5)  # Simulate CPU processing time
            cpu_time = time.time() - cpu_start
            
            # GPU processing
            gpu_start = time.time()
            gpu_response = await self.client.post(
                f"{ENHANCED_SERVICES['gpu_multimodal']['url']}/benchmark",
                json={"operation": "matrix_multiplication", "size": 1024}
            )
            gpu_time = time.time() - gpu_start
            
            if gpu_response.status_code == 200:
                speedup = cpu_time / gpu_time
                results["performance_comparison"] = {
                    "status": "success",
                    "cpu_time": f"{cpu_time:.3f}s",
                    "gpu_time": f"{gpu_time:.3f}s",
                    "speedup": f"{speedup:.1f}x"
                }
                print(f"    ✅ Performance comparison: {speedup:.1f}x speedup")
            else:
                results["performance_comparison"] = {"status": "failed", "error": "Benchmark failed"}
                print("    ❌ Performance comparison failed")
            
            workflow_duration = time.time() - workflow_start
            successful_steps = len([r for r in results.values() if r.get("status") == "success"])
            total_steps = len(results)
            
            return {
                "workflow_name": "gpu_acceleration",
                "total_steps": total_steps,
                "successful_steps": successful_steps,
                "success_rate": successful_steps / total_steps,
                "workflow_duration": workflow_duration,
                "results": results,
                "overall_status": "success" if successful_steps == total_steps else "partial_failure"
            }
            
        except Exception as e:
            return {
                "workflow_name": "gpu_acceleration",
                "error": str(e),
                "overall_status": "failed",
                "workflow_duration": time.time() - workflow_start
            }
    
    async def test_marketplace_transaction_workflow(self) -> Dict[str, Any]:
        """Test complete marketplace transaction workflow"""
        print("\n🏪 Testing Marketplace Transaction Workflow...")
        
        workflow_start = time.time()
        results = {}
        
        try:
            # Step 1: Create AI model as NFT
            print("  🎨 Creating AI model NFT...")
            mint_response = await self.client.post(
                f"{ENHANCED_SERVICES['marketplace_enhanced']['url']}/v1/models/mint",
                json={
                    "title": "Advanced Text Analyzer",
                    "description": "AI model for advanced text analysis with 95% accuracy",
                    "model_type": "text_classification",
                    "capabilities": ["sentiment_analysis", "entity_extraction", "topic_classification"],
                    "model_metadata": {
                        "accuracy": 0.95,
                        "training_data_size": "1M samples",
                        "model_size": "125MB",
                        "inference_time": "0.02s"
                    },
                    "pricing": {
                        "execution_price": 0.001,
                        "subscription_price": 1.0,
                        "license_type": "commercial"
                    },
                    "royalties": {
                        "creator_percentage": 15.0,
                        "platform_percentage": 5.0,
                        "resale_royalty": 2.5
                    }
                }
            )
            if mint_response.status_code == 200:
                mint_result = mint_response.json()
                results["model_minting"] = {
                    "status": "success",
                    "model_id": mint_result.get("model_id", "unknown"),
                    "token_id": mint_result.get("token_id", "unknown"),
                    "contract_address": mint_result.get("contract_address", "unknown"),
                    "transaction_hash": mint_result.get("transaction_hash", "unknown")
                }
                print(f"    ✅ Model minted: {results['model_minting']['model_id']}")
            else:
                results["model_minting"] = {"status": "failed", "error": str(mint_response.status_code)}
                print(f"    ❌ Model minting failed: {mint_response.status_code}")
                return {"workflow_name": "marketplace_transaction", "overall_status": "failed", "error": "Model minting failed"}
            
            # Step 2: List model on marketplace
            print("  📋 Listing model on marketplace...")
            listing_response = await self.client.post(
                f"{ENHANCED_SERVICES['marketplace_enhanced']['url']}/v1/offers/create",
                json={
                    "model_id": results["model_minting"]["model_id"],
                    "offer_type": "sale",
                    "price": 0.5,
                    "quantity": 100,
                    "duration_days": 30,
                    "description": "Limited time offer for advanced text analyzer"
                }
            )
            if listing_response.status_code == 200:
                listing_result = listing_response.json()
                results["marketplace_listing"] = {
                    "status": "success",
                    "offer_id": listing_result.get("offer_id", "unknown"),
                    "listing_price": listing_result.get("price", "unknown"),
                    "quantity_available": listing_result.get("quantity", "unknown")
                }
                print(f"    ✅ Listed on marketplace: {results['marketplace_listing']['offer_id']}")
            else:
                results["marketplace_listing"] = {"status": "failed", "error": str(listing_response.status_code)}
                print(f"    ❌ Marketplace listing failed: {listing_response.status_code}")
            
            # Step 3: Place bid for model
            print("  💰 Placing bid for model...")
            bid_response = await self.client.post(
                f"{ENHANCED_SERVICES['marketplace_enhanced']['url']}/v1/trading/bid",
                json={
                    "offer_id": results["marketplace_listing"]["offer_id"],
                    "bid_price": 0.45,
                    "quantity": 10,
                    "bidder_address": "0x1234567890123456789012345678901234567890",
                    "expiration_hours": 24
                }
            )
            if bid_response.status_code == 200:
                bid_result = bid_response.json()
                results["bid_placement"] = {
                    "status": "success",
                    "bid_id": bid_result.get("bid_id", "unknown"),
                    "bid_price": bid_result.get("bid_price", "unknown"),
                    "quantity": bid_result.get("quantity", "unknown")
                }
                print(f"    ✅ Bid placed: {results['bid_placement']['bid_id']}")
            else:
                results["bid_placement"] = {"status": "failed", "error": str(bid_response.status_code)}
                print(f"    ❌ Bid placement failed: {bid_response.status_code}")
            
            # Step 4: Execute transaction
            print("  ⚡ Executing transaction...")
            execute_response = await self.client.post(
                f"{ENHANCED_SERVICES['marketplace_enhanced']['url']}/v1/trading/execute",
                json={
                    "bid_id": results["bid_placement"]["bid_id"],
                    "buyer_address": "0x1234567890123456789012345678901234567890",
                    "payment_method": "crypto"
                }
            )
            if execute_response.status_code == 200:
                execute_result = execute_response.json()
                results["transaction_execution"] = {
                    "status": "success",
                    "transaction_id": execute_result.get("transaction_id", "unknown"),
                    "final_price": execute_result.get("final_price", "unknown"),
                    "royalties_distributed": execute_result.get("royalties_distributed", "unknown"),
                    "transaction_hash": execute_result.get("transaction_hash", "unknown")
                }
                print(f"    ✅ Transaction executed: {results['transaction_execution']['transaction_id']}")
            else:
                results["transaction_execution"] = {"status": "failed", "error": str(execute_response.status_code)}
                print(f"    ❌ Transaction execution failed: {execute_response.status_code}")
            
            # Step 5: Verify royalties distribution
            print("  🔍 Verifying royalties distribution...")
            royalties_response = await self.client.get(
                f"{ENHANCED_SERVICES['marketplace_enhanced']['url']}/v1/analytics/royalties",
                params={"model_id": results["model_minting"]["model_id"]}
            )
            if royalties_response.status_code == 200:
                royalties_result = royalties_response.json()
                results["royalties_verification"] = {
                    "status": "success",
                    "total_royalties": royalties_result.get("total_royalties", "unknown"),
                    "creator_share": royalties_result.get("creator_share", "unknown"),
                    "platform_share": royalties_result.get("platform_share", "unknown"),
                    "distribution_history": royalties_result.get("distribution_history", [])
                }
                print(f"    ✅ Royalties distributed: {results['royalties_verification']['total_royalties']}")
            else:
                results["royalties_verification"] = {"status": "failed", "error": str(royalties_response.status_code)}
                print(f"    ❌ Royalties verification failed: {royalties_response.status_code}")
            
            # Step 6: Generate analytics report
            print("  📊 Generating analytics report...")
            analytics_response = await self.client.post(
                f"{ENHANCED_SERVICES['marketplace_enhanced']['url']}/v1/analytics/report",
                json={
                    "model_id": results["model_minting"]["model_id"],
                    "report_type": "transaction_summary",
                    "timeframe_days": 7
                }
            )
            if analytics_response.status_code == 200:
                analytics_result = analytics_response.json()
                results["analytics_report"] = {
                    "status": "success",
                    "report_id": analytics_result.get("report_id", "unknown"),
                    "total_transactions": analytics_result.get("total_transactions", "unknown"),
                    "total_revenue": analytics_result.get("total_revenue", "unknown"),
                    "average_price": analytics_result.get("average_price", "unknown")
                }
                print(f"    ✅ Analytics report: {results['analytics_report']['report_id']}")
            else:
                results["analytics_report"] = {"status": "failed", "error": str(analytics_response.status_code)}
                print(f"    ❌ Analytics report failed: {analytics_response.status_code}")
            
            workflow_duration = time.time() - workflow_start
            successful_steps = len([r for r in results.values() if r.get("status") == "success"])
            total_steps = len(results)
            
            return {
                "workflow_name": "marketplace_transaction",
                "total_steps": total_steps,
                "successful_steps": successful_steps,
                "success_rate": successful_steps / total_steps,
                "workflow_duration": workflow_duration,
                "results": results,
                "overall_status": "success" if successful_steps == total_steps else "partial_failure"
            }
            
        except Exception as e:
            return {
                "workflow_name": "marketplace_transaction",
                "error": str(e),
                "overall_status": "failed",
                "workflow_duration": time.time() - workflow_start
            }


# Pytest test functions
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_multimodal_processing_workflow():
    """Test complete multi-modal processing workflow"""
    tester = EnhancedServicesWorkflowTester()
    
    try:
        # Setup test environment
        if not await tester.setup_test_environment():
            pytest.skip("Enhanced services not available")
        
        # Run workflow
        result = await tester.test_multimodal_processing_workflow()
        
        # Assertions
        assert result["overall_status"] in ["success", "partial_failure"], f"Workflow failed: {result}"
        assert result["workflow_duration"] < 30.0, "Workflow took too long"
        assert result["success_rate"] >= 0.5, "Too many failed steps"
        
        # Verify key steps
        if "results" in result:
            results = result["results"]
            assert results.get("text_processing", {}).get("status") == "success", "Text processing failed"
            assert results.get("image_processing", {}).get("status") == "success", "Image processing failed"
        
        print(f"✅ Multi-modal workflow completed: {result['success_rate']:.1%} success rate")
        
    finally:
        await tester.cleanup_test_environment()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_gpu_acceleration_workflow():
    """Test GPU acceleration workflow"""
    tester = EnhancedServicesWorkflowTester()
    
    try:
        # Setup test environment
        if not await tester.setup_test_environment():
            pytest.skip("Enhanced services not available")
        
        # Run workflow
        result = await tester.test_gpu_acceleration_workflow()
        
        # Assertions
        assert result["overall_status"] in ["success", "partial_failure"], f"Workflow failed: {result}"
        assert result["workflow_duration"] < 20.0, "Workflow took too long"
        
        # Verify GPU availability
        if "results" in result:
            results = result["results"]
            gpu_check = results.get("gpu_availability", {})
            assert gpu_check.get("status") == "success", "GPU not available"
        
        print(f"✅ GPU acceleration workflow completed: {result['success_rate']:.1%} success rate")
        
    finally:
        await tester.cleanup_test_environment()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_marketplace_transaction_workflow():
    """Test marketplace transaction workflow"""
    tester = EnhancedServicesWorkflowTester()
    
    try:
        # Setup test environment
        if not await tester.setup_test_environment():
            pytest.skip("Enhanced services not available")
        
        # Run workflow
        result = await tester.test_marketplace_transaction_workflow()
        
        # Assertions
        assert result["overall_status"] in ["success", "partial_failure"], f"Workflow failed: {result}"
        assert result["workflow_duration"] < 45.0, "Workflow took too long"
        assert result["success_rate"] >= 0.6, "Too many failed steps"
        
        # Verify key marketplace steps
        if "results" in result:
            results = result["results"]
            assert results.get("model_minting", {}).get("status") == "success", "Model minting failed"
            assert results.get("marketplace_listing", {}).get("status") == "success", "Marketplace listing failed"
        
        print(f"✅ Marketplace transaction workflow completed: {result['success_rate']:.1%} success rate")
        
    finally:
        await tester.cleanup_test_environment()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_all_workflows_integration():
    """Test all workflows together for system integration"""
    tester = EnhancedServicesWorkflowTester()
    
    try:
        # Setup test environment
        if not await tester.setup_test_environment():
            pytest.skip("Enhanced services not available")
        
        print("\n🔄 Running all workflows for integration testing...")
        
        # Run all workflows
        workflows = [
            tester.test_multimodal_processing_workflow(),
            tester.test_gpu_acceleration_workflow(),
            tester.test_marketplace_transaction_workflow()
        ]
        
        results = await asyncio.gather(*workflows, return_exceptions=True)
        
        # Analyze results
        successful_workflows = 0
        total_duration = 0
        
        for result in results:
            if isinstance(result, Exception):
                print(f"❌ Workflow failed with exception: {result}")
                continue
            
            if result["overall_status"] == "success":
                successful_workflows += 1
            
            total_duration += result["workflow_duration"]
        
        # Assertions
        success_rate = successful_workflows / len(results)
        assert success_rate >= 0.6, f"Too many failed workflows: {success_rate:.1%}"
        assert total_duration < 120.0, "All workflows took too long"
        
        print(f"✅ Integration testing completed:")
        print(f"   Successful workflows: {successful_workflows}/{len(results)}")
        print(f"   Success rate: {success_rate:.1%}")
        print(f"   Total duration: {total_duration:.1f}s")
        
    finally:
        await tester.cleanup_test_environment()


if __name__ == "__main__":
    # Run tests manually
    async def main():
        tester = EnhancedServicesWorkflowTester()
        
        try:
            if await tester.setup_test_environment():
                # Run all workflows
                workflows = [
                    tester.test_multimodal_processing_workflow(),
                    tester.test_gpu_acceleration_workflow(),
                    tester.test_marketplace_transaction_workflow()
                ]
                
                results = await asyncio.gather(*workflows, return_exceptions=True)
                
                print("\n" + "="*60)
                print("  END-TO-END WORKFLOW TEST RESULTS")
                print("="*60)
                
                for result in results:
                    if isinstance(result, Exception):
                        print(f"❌ {result}")
                    else:
                        status_emoji = "✅" if result["overall_status"] == "success" else "⚠️"
                        print(f"{status_emoji} {result['workflow_name']}: {result['success_rate']:.1%} success rate")
                
        finally:
            await tester.cleanup_test_environment()
    
    asyncio.run(main())
