"""
Client-to-Miner End-to-End Workflow Test
Tests complete pipeline from client request to miner processing with enhanced services
"""

import asyncio
import httpx
import pytest
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import AsyncMock, patch

# Service endpoints
COORDINATOR_API = "http://localhost:8000"
ENHANCED_SERVICES = {
    "multimodal": "http://localhost:8002",
    "gpu_multimodal": "http://localhost:8003",
    "modality_optimization": "http://localhost:8004",
    "adaptive_learning": "http://localhost:8005",
    "marketplace_enhanced": "http://localhost:8006",
    "openclaw_enhanced": "http://localhost:8007"
}


class ClientToMinerWorkflowTester:
    """Test framework for client-to-miner workflows"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.workflow_data = self._generate_workflow_data()
        self.job_id = None
        self.execution_id = None
    
    def _generate_workflow_data(self) -> Dict[str, Any]:
        """Generate realistic workflow test data"""
        return {
            "client_request": {
                "job_type": "multimodal_analysis",
                "input_data": {
                    "text": "Analyze this product review for sentiment and extract key features.",
                    "image_url": "https://example.com/product-image.jpg",
                    "metadata": {
                        "priority": "high",
                        "deadline": "2026-02-25T12:00:00Z",
                        "quality_threshold": 0.9
                    }
                },
                "processing_requirements": {
                    "sentiment_analysis": True,
                    "feature_extraction": True,
                    "gpu_acceleration": True,
                    "optimization_level": "balanced"
                }
            },
            "agent_workflow": {
                "workflow_id": "advanced-multimodal-agent",
                "steps": [
                    {
                        "step_id": "text_processing",
                        "service": "multimodal",
                        "operation": "process_text",
                        "inputs": {"text": "{{input_data.text}}"},
                        "expected_duration": 0.02
                    },
                    {
                        "step_id": "image_processing", 
                        "service": "gpu_multimodal",
                        "operation": "process_image",
                        "inputs": {"image_url": "{{input_data.image_url}}"},
                        "expected_duration": 0.15
                    },
                    {
                        "step_id": "data_optimization",
                        "service": "modality_optimization",
                        "operation": "optimize_multimodal",
                        "inputs": {"multimodal_data": "{{previous_results}}"},
                        "expected_duration": 0.05
                    },
                    {
                        "step_id": "adaptive_analysis",
                        "service": "adaptive_learning",
                        "operation": "analyze_with_learning",
                        "inputs": {"optimized_data": "{{previous_results}}"},
                        "expected_duration": 0.12
                    }
                ],
                "verification_level": "full",
                "max_execution_time": 60,
                "max_cost_budget": 1.0
            }
        }
    
    async def setup_test_environment(self) -> bool:
        """Setup test environment and verify all services"""
        print("🔧 Setting up client-to-miner test environment...")
        
        # Check coordinator API
        try:
            response = await self.client.get(f"{COORDINATOR_API}/v1/health")
            if response.status_code != 200:
                print("❌ Coordinator API not healthy")
                return False
            print("✅ Coordinator API is healthy")
        except Exception as e:
            print(f"❌ Coordinator API unavailable: {e}")
            return False
        
        # Check enhanced services
        healthy_services = []
        for service_name, service_url in ENHANCED_SERVICES.items():
            try:
                response = await self.client.get(f"{service_url}/health")
                if response.status_code == 200:
                    healthy_services.append(service_name)
                    print(f"✅ {service_name} is healthy")
                else:
                    print(f"❌ {service_name} is unhealthy: {response.status_code}")
            except Exception as e:
                print(f"❌ {service_name} is unavailable: {e}")
        
        if len(healthy_services) < 4:  # At least 4 services needed for workflow
            print(f"⚠️  Only {len(healthy_services)}/{len(ENHANCED_SERVICES)} services healthy")
            return False
        
        print("✅ Test environment ready")
        return True
    
    async def cleanup_test_environment(self):
        """Cleanup test environment"""
        print("🧹 Cleaning up test environment...")
        await self.client.aclose()
    
    async def submit_client_request(self) -> Dict[str, Any]:
        """Step 1: Submit client request to coordinator"""
        print("\n📤 Step 1: Submitting client request...")
        
        try:
            # Submit job to coordinator
            response = await self.client.post(
                f"{COORDINATOR_API}/v1/jobs",
                json=self.workflow_data["client_request"]
            )
            
            if response.status_code == 200:
                job_result = response.json()
                self.job_id = job_result.get("job_id")
                
                print(f"✅ Job submitted: {self.job_id}")
                return {
                    "status": "success",
                    "job_id": self.job_id,
                    "estimated_cost": job_result.get("estimated_cost", "unknown"),
                    "estimated_duration": job_result.get("estimated_duration", "unknown")
                }
            else:
                print(f"❌ Job submission failed: {response.status_code}")
                return {"status": "failed", "error": str(response.status_code)}
                
        except Exception as e:
            print(f"❌ Job submission error: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def create_agent_workflow(self) -> Dict[str, Any]:
        """Step 2: Create agent workflow for processing"""
        print("\n🤖 Step 2: Creating agent workflow...")
        
        try:
            # Create workflow via agent service
            response = await self.client.post(
                f"{ENHANCED_SERVICES['multimodal']}/workflows/create",
                json=self.workflow_data["agent_workflow"]
            )
            
            if response.status_code == 200:
                workflow_result = response.json()
                workflow_id = workflow_result.get("workflow_id")
                
                print(f"✅ Agent workflow created: {workflow_id}")
                return {
                    "status": "success",
                    "workflow_id": workflow_id,
                    "total_steps": len(self.workflow_data["agent_workflow"]["steps"])
                }
            else:
                print(f"❌ Workflow creation failed: {response.status_code}")
                return {"status": "failed", "error": str(response.status_code)}
                
        except Exception as e:
            print(f"❌ Workflow creation error: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def execute_agent_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Step 3: Execute agent workflow"""
        print("\n⚡ Step 3: Executing agent workflow...")
        
        try:
            # Execute workflow
            response = await self.client.post(
                f"{ENHANCED_SERVICES['multimodal']}/workflows/{workflow_id}/execute",
                json={
                    "inputs": self.workflow_data["client_request"]["input_data"],
                    "verification_level": "full"
                }
            )
            
            if response.status_code == 200:
                execution_result = response.json()
                self.execution_id = execution_result.get("execution_id")
                
                print(f"✅ Workflow execution started: {self.execution_id}")
                return {
                    "status": "success",
                    "execution_id": self.execution_id,
                    "estimated_completion": execution_result.get("estimated_completion", "unknown")
                }
            else:
                print(f"❌ Workflow execution failed: {response.status_code}")
                return {"status": "failed", "error": str(response.status_code)}
                
        except Exception as e:
            print(f"❌ Workflow execution error: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def monitor_workflow_execution(self) -> Dict[str, Any]:
        """Step 4: Monitor workflow execution progress"""
        print("\n📊 Step 4: Monitoring workflow execution...")
        
        if not self.execution_id:
            return {"status": "failed", "error": "No execution ID"}
        
        try:
            # Monitor execution with timeout
            max_wait_time = 30.0
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                response = await self.client.get(
                    f"{ENHANCED_SERVICES['multimodal']}/executions/{self.execution_id}/status"
                )
                
                if response.status_code == 200:
                    status_result = response.json()
                    current_status = status_result.get("status", "unknown")
                    current_step = status_result.get("current_step", 0)
                    total_steps = status_result.get("total_steps", 4)
                    
                    print(f"   📈 Progress: {current_step}/{total_steps} steps, Status: {current_status}")
                    
                    if current_status in ["completed", "failed"]:
                        break
                
                await asyncio.sleep(1.0)
            
            # Get final status
            final_response = await self.client.get(
                f"{ENHANCED_SERVICES['multimodal']}/executions/{self.execution_id}/status"
            )
            
            if final_response.status_code == 200:
                final_result = final_response.json()
                final_status = final_result.get("status", "unknown")
                
                if final_status == "completed":
                    print(f"✅ Workflow completed successfully")
                    return {
                        "status": "success",
                        "final_status": final_status,
                        "total_steps": final_result.get("total_steps", 4),
                        "execution_time": final_result.get("execution_time", "unknown"),
                        "final_result": final_result.get("final_result", {})
                    }
                else:
                    print(f"❌ Workflow failed: {final_status}")
                    return {
                        "status": "failed",
                        "final_status": final_status,
                        "error": final_result.get("error", "Unknown error")
                    }
            else:
                print(f"❌ Failed to get final status: {final_response.status_code}")
                return {"status": "failed", "error": "Status check failed"}
                
        except Exception as e:
            print(f"❌ Monitoring error: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def verify_execution_receipt(self) -> Dict[str, Any]:
        """Step 5: Verify execution receipt"""
        print("\n🔍 Step 5: Verifying execution receipt...")
        
        if not self.execution_id:
            return {"status": "failed", "error": "No execution ID"}
        
        try:
            # Get execution receipt
            response = await self.client.get(
                f"{ENHANCED_SERVICES['multimodal']}/executions/{self.execution_id}/receipt"
            )
            
            if response.status_code == 200:
                receipt_result = response.json()
                
                # Verify receipt components
                receipt_components = {
                    "execution_id": receipt_result.get("execution_id"),
                    "workflow_id": receipt_result.get("workflow_id"),
                    "timestamp": receipt_result.get("timestamp"),
                    "results_hash": receipt_result.get("results_hash"),
                    "verification_proof": receipt_result.get("verification_proof"),
                    "cost_breakdown": receipt_result.get("cost_breakdown")
                }
                
                # Check if all components are present
                missing_components = [k for k, v in receipt_components.items() if not v]
                
                if not missing_components:
                    print(f"✅ Execution receipt verified")
                    return {
                        "status": "success",
                        "receipt_components": receipt_components,
                        "total_cost": receipt_result.get("total_cost", "unknown"),
                        "verification_level": receipt_result.get("verification_level", "unknown")
                    }
                else:
                    print(f"⚠️  Receipt missing components: {missing_components}")
                    return {
                        "status": "partial",
                        "missing_components": missing_components,
                        "receipt_components": receipt_components
                    }
            else:
                print(f"❌ Receipt retrieval failed: {response.status_code}")
                return {"status": "failed", "error": str(response.status_code)}
                
        except Exception as e:
            print(f"❌ Receipt verification error: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def submit_to_marketplace(self) -> Dict[str, Any]:
        """Step 6: Submit successful workflow to marketplace"""
        print("\n🏪 Step 6: Submitting to marketplace...")
        
        if not self.execution_id:
            return {"status": "failed", "error": "No execution ID"}
        
        try:
            # Create marketplace listing for the successful workflow
            response = await self.client.post(
                f"{ENHANCED_SERVICES['marketplace_enhanced']}/v1/models/mint",
                json={
                    "title": "Multi-Modal Analysis Agent",
                    "description": "Advanced multi-modal agent with sentiment analysis and feature extraction",
                    "model_type": "agent_workflow",
                    "workflow_id": self.execution_id,
                    "capabilities": [
                        "sentiment_analysis",
                        "feature_extraction", 
                        "gpu_acceleration",
                        "adaptive_optimization"
                    ],
                    "performance_metrics": {
                        "accuracy": 0.94,
                        "processing_time": 0.08,
                        "cost_efficiency": 0.85
                    },
                    "pricing": {
                        "execution_price": 0.15,
                        "subscription_price": 25.0
                    },
                    "royalties": {
                        "creator_percentage": 12.0,
                        "platform_percentage": 5.0
                    }
                }
            )
            
            if response.status_code == 200:
                marketplace_result = response.json()
                
                print(f"✅ Submitted to marketplace: {marketplace_result.get('model_id')}")
                return {
                    "status": "success",
                    "model_id": marketplace_result.get("model_id"),
                    "token_id": marketplace_result.get("token_id"),
                    "listing_price": marketplace_result.get("pricing", {}).get("execution_price", "unknown")
                }
            else:
                print(f"❌ Marketplace submission failed: {response.status_code}")
                return {"status": "failed", "error": str(response.status_code)}
                
        except Exception as e:
            print(f"❌ Marketplace submission error: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def run_complete_workflow(self) -> Dict[str, Any]:
        """Run complete client-to-miner workflow"""
        print("🚀 Starting Complete Client-to-Miner Workflow")
        print("="*60)
        
        workflow_start = time.time()
        results = {}
        
        # Step 1: Submit client request
        results["client_request"] = await self.submit_client_request()
        if results["client_request"]["status"] != "success":
            return {"overall_status": "failed", "failed_at": "client_request", "results": results}
        
        # Step 2: Create agent workflow
        results["workflow_creation"] = await self.create_agent_workflow()
        if results["workflow_creation"]["status"] != "success":
            return {"overall_status": "failed", "failed_at": "workflow_creation", "results": results}
        
        # Step 3: Execute workflow
        results["workflow_execution"] = await self.execute_agent_workflow(
            results["workflow_creation"]["workflow_id"]
        )
        if results["workflow_execution"]["status"] != "success":
            return {"overall_status": "failed", "failed_at": "workflow_execution", "results": results}
        
        # Step 4: Monitor execution
        results["execution_monitoring"] = await self.monitor_workflow_execution()
        if results["execution_monitoring"]["status"] != "success":
            return {"overall_status": "failed", "failed_at": "execution_monitoring", "results": results}
        
        # Step 5: Verify receipt
        results["receipt_verification"] = await self.verify_execution_receipt()
        
        # Step 6: Submit to marketplace (optional)
        if results["execution_monitoring"]["status"] == "success":
            results["marketplace_submission"] = await self.submit_to_marketplace()
        
        workflow_duration = time.time() - workflow_start
        
        # Calculate overall success
        successful_steps = len([r for r in results.values() if r.get("status") == "success"])
        total_steps = len(results)
        success_rate = successful_steps / total_steps
        
        print("\n" + "="*60)
        print("  WORKFLOW COMPLETION SUMMARY")
        print("="*60)
        print(f"Total Duration: {workflow_duration:.2f}s")
        print(f"Successful Steps: {successful_steps}/{total_steps}")
        print(f"Success Rate: {success_rate:.1%}")
        print(f"Overall Status: {'✅ SUCCESS' if success_rate >= 0.8 else '⚠️  PARTIAL'}")
        
        return {
            "overall_status": "success" if success_rate >= 0.8 else "partial_failure",
            "workflow_duration": workflow_duration,
            "success_rate": success_rate,
            "successful_steps": successful_steps,
            "total_steps": total_steps,
            "results": results
        }


# Pytest test functions
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_to_miner_complete_workflow():
    """Test complete client-to-miner workflow"""
    tester = ClientToMinerWorkflowTester()
    
    try:
        # Setup test environment
        if not await tester.setup_test_environment():
            pytest.skip("Services not available for testing")
        
        # Run complete workflow
        result = await tester.run_complete_workflow()
        
        # Assertions
        assert result["overall_status"] in ["success", "partial_failure"], f"Workflow failed: {result}"
        assert result["workflow_duration"] < 60.0, "Workflow took too long"
        assert result["success_rate"] >= 0.6, "Success rate too low"
        
        # Verify critical steps
        results = result["results"]
        assert results.get("client_request", {}).get("status") == "success", "Client request failed"
        assert results.get("workflow_creation", {}).get("status") == "success", "Workflow creation failed"
        assert results.get("workflow_execution", {}).get("status") == "success", "Workflow execution failed"
        
        print(f"✅ Client-to-miner workflow: {result['success_rate']:.1%} success rate")
        
    finally:
        await tester.cleanup_test_environment()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_enhanced_services_integration():
    """Test integration of all enhanced services in workflow"""
    tester = ClientToMinerWorkflowTester()
    
    try:
        # Setup test environment
        if not await tester.setup_test_environment():
            pytest.skip("Services not available for testing")
        
        print("\n🔗 Testing Enhanced Services Integration...")
        
        # Test service-to-service communication
        integration_tests = []
        
        # Test 1: Multi-modal to GPU Multi-modal
        print("  🤖➡️🚀 Testing Multi-modal to GPU Multi-modal...")
        try:
            response = await tester.client.post(
                f"{ENHANCED_SERVICES['multimodal']}/process",
                json={
                    "agent_id": "integration-test",
                    "inputs": {"text": "Test integration workflow"},
                    "processing_mode": "gpu_offload"
                }
            )
            if response.status_code == 200:
                integration_tests.append({"test": "multimodal_to_gpu", "status": "success"})
                print("    ✅ Integration successful")
            else:
                integration_tests.append({"test": "multimodal_to_gpu", "status": "failed", "error": response.status_code})
                print(f"    ❌ Integration failed: {response.status_code}")
        except Exception as e:
            integration_tests.append({"test": "multimodal_to_gpu", "status": "error", "error": str(e)})
            print(f"    ❌ Integration error: {e}")
        
        # Test 2: Optimization to Marketplace
        print("  ⚡➡️🏪 Testing Optimization to Marketplace...")
        try:
            response = await tester.client.post(
                f"{ENHANCED_SERVICES['modality_optimization']}/optimize",
                json={
                    "modality": "text",
                    "data": {"content": "Test marketplace integration"},
                    "strategy": "marketplace_ready"
                }
            )
            if response.status_code == 200:
                optimized_data = response.json()
                # Try to submit optimized data to marketplace
                marketplace_response = await tester.client.post(
                    f"{ENHANCED_SERVICES['marketplace_enhanced']}/v1/offers/create",
                    json={
                        "model_id": "integration-test-model",
                        "offer_type": "sale",
                        "price": 0.1,
                        "optimized_data": optimized_data.get("result", {})
                    }
                )
                if marketplace_response.status_code == 200:
                    integration_tests.append({"test": "optimization_to_marketplace", "status": "success"})
                    print("    ✅ Integration successful")
                else:
                    integration_tests.append({"test": "optimization_to_marketplace", "status": "failed", "error": marketplace_response.status_code})
                    print(f"    ❌ Marketplace integration failed: {marketplace_response.status_code}")
            else:
                integration_tests.append({"test": "optimization_to_marketplace", "status": "failed", "error": response.status_code})
                print(f"    ❌ Optimization failed: {response.status_code}")
        except Exception as e:
            integration_tests.append({"test": "optimization_to_marketplace", "status": "error", "error": str(e)})
            print(f"    ❌ Integration error: {e}")
        
        # Test 3: Adaptive Learning to OpenClaw
        print("  🧠➡️🌐 Testing Adaptive Learning to OpenClaw...")
        try:
            # Create learning agent
            agent_response = await tester.client.post(
                f"{ENHANCED_SERVICES['adaptive_learning']}/create-agent",
                json={
                    "agent_id": "integration-test-agent",
                    "algorithm": "q_learning",
                    "config": {"learning_rate": 0.01}
                }
            )
            if agent_response.status_code == 200:
                # Deploy to OpenClaw
                openclaw_response = await tester.client.post(
                    f"{ENHANCED_SERVICES['openclaw_enhanced']}/deploy-agent",
                    json={
                        "agent_id": "integration-test-agent",
                        "deployment_config": {"execution_mode": "hybrid"}
                    }
                )
                if openclaw_response.status_code == 200:
                    integration_tests.append({"test": "learning_to_openclaw", "status": "success"})
                    print("    ✅ Integration successful")
                else:
                    integration_tests.append({"test": "learning_to_openclaw", "status": "failed", "error": openclaw_response.status_code})
                    print(f"    ❌ OpenClaw deployment failed: {openclaw_response.status_code}")
            else:
                integration_tests.append({"test": "learning_to_openclaw", "status": "failed", "error": agent_response.status_code})
                print(f"    ❌ Agent creation failed: {agent_response.status_code}")
        except Exception as e:
            integration_tests.append({"test": "learning_to_openclaw", "status": "error", "error": str(e)})
            print(f"    ❌ Integration error: {e}")
        
        # Evaluate integration results
        successful_integrations = len([t for t in integration_tests if t["status"] == "success"])
        total_integrations = len(integration_tests)
        integration_rate = successful_integrations / total_integrations
        
        print(f"\n📊 Integration Test Results:")
        print(f"Successful: {successful_integrations}/{total_integrations}")
        print(f"Integration Rate: {integration_rate:.1%}")
        
        # Assertions
        assert integration_rate >= 0.6, "Integration rate too low"
        
        print(f"✅ Enhanced services integration: {integration_rate:.1%} success rate")
        
    finally:
        await tester.cleanup_test_environment()


if __name__ == "__main__":
    # Run tests manually
    async def main():
        tester = ClientToMinerWorkflowTester()
        
        try:
            if await tester.setup_test_environment():
                result = await tester.run_complete_workflow()
                
                print(f"\n🎯 Final Result: {result['overall_status']}")
                print(f"📊 Success Rate: {result['success_rate']:.1%}")
                print(f"⏱️  Duration: {result['workflow_duration']:.2f}s")
                
        finally:
            await tester.cleanup_test_environment()
    
    asyncio.run(main())
