#!/usr/bin/env python3
"""
Comprehensive Multi-Site AITBC Test Suite
Tests localhost, aitbc, and aitbc1 with all CLI features and user scenarios
"""

import subprocess
import json
import time
import sys
from pathlib import Path

class MultiSiteTester:
    def __init__(self):
        self.test_results = []
        self.failed_tests = []
        
    def log_test(self, test_name, success, details=""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = f"{status}: {test_name}"
        if details:
            result += f" - {details}"
        
        print(result)
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })
        
        if not success:
            self.failed_tests.append(test_name)
    
    def run_command(self, cmd, description, expected_success=True):
        """Run a command and check result"""
        try:
            print(f"\n🔧 Running: {description}")
            print(f"Command: {cmd}")
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            success = result.returncode == 0 if expected_success else result.returncode != 0
            
            if success:
                self.log_test(description, True, f"Exit code: {result.returncode}")
                if result.stdout.strip():
                    print(f"Output: {result.stdout.strip()}")
            else:
                self.log_test(description, False, f"Exit code: {result.returncode}")
                if result.stderr.strip():
                    print(f"Error: {result.stderr.strip()}")
                if result.stdout.strip():
                    print(f"Output: {result.stdout.strip()}")
            
            return success, result
            
        except subprocess.TimeoutExpired:
            self.log_test(description, False, "Command timed out")
            return False, None
        except Exception as e:
            self.log_test(description, False, f"Exception: {str(e)}")
            return False, None
    
    def test_connectivity(self):
        """Test basic connectivity to all sites"""
        print("\n" + "="*60)
        print("🌐 TESTING CONNECTIVITY")
        print("="*60)
        
        # Test aitbc connectivity
        success, _ = self.run_command(
            "curl -s http://127.0.0.1:18000/v1/health",
            "aitbc health check"
        )
        
        # Test aitbc1 connectivity
        success, _ = self.run_command(
            "curl -s http://127.0.0.1:18001/v1/health",
            "aitbc1 health check"
        )
        
        # Test Ollama (localhost GPU)
        success, _ = self.run_command(
            "ollama list",
            "Ollama GPU service check"
        )
    
    def test_cli_features(self):
        """Test all CLI features across sites"""
        print("\n" + "="*60)
        print("🔧 TESTING CLI FEATURES")
        print("="*60)
        
        # Test chain management
        self.run_command(
            "aitbc chain list --node-endpoint http://127.0.0.1:18000",
            "Chain listing on aitbc"
        )
        
        self.run_command(
            "aitbc chain list --node-endpoint http://127.0.0.1:18001",
            "Chain listing on aitbc1"
        )
        
        # Test analytics
        self.run_command(
            "aitbc analytics summary --node-endpoint http://127.0.0.1:18000",
            "Analytics on aitbc"
        )
        
        self.run_command(
            "aitbc analytics summary --node-endpoint http://127.0.0.1:18001",
            "Analytics on aitbc1"
        )
        
        # Test marketplace
        self.run_command(
            "aitbc marketplace list --marketplace-url http://127.0.0.1:18000",
            "Marketplace listing on aitbc"
        )
        
        self.run_command(
            "aitbc marketplace list --marketplace-url http://127.0.0.1:18001",
            "Marketplace listing on aitbc1"
        )
        
        # Test deployment
        self.run_command(
            "aitbc deploy overview --format table",
            "Deployment overview"
        )
    
    def test_gpu_services(self):
        """Test GPU service registration and access"""
        print("\n" + "="*60)
        print("🚀 TESTING GPU SERVICES")
        print("="*60)
        
        # Test miner1 registration
        self.run_command(
            '''aitbc marketplace gpu register \
              --miner-id miner1 \
              --wallet 0x1234567890abcdef1234567890abcdef12345678 \
              --region localhost \
              --gpu-model "NVIDIA-RTX-4060Ti" \
              --gpu-memory "16GB" \
              --compute-capability "8.9" \
              --price-per-hour "0.001" \
              --models "gemma3:1b" \
              --endpoint "http://localhost:11434" \
              --marketplace-url "http://127.0.0.1:18000"''',
            "miner1 GPU registration on aitbc"
        )
        
        # Wait for synchronization
        print("⏳ Waiting for marketplace synchronization...")
        time.sleep(10)
        
        # Test discovery from aitbc1
        self.run_command(
            "curl -s http://127.0.0.1:18001/v1/marketplace/offers | jq '.[] | select(.miner_id == \"miner1\")'",
            "miner1 discovery on aitbc1"
        )
        
        # Test direct Ollama access
        self.run_command(
            '''curl -X POST http://localhost:11434/api/generate \
              -H "Content-Type: application/json" \
              -d '{"model": "gemma3:1b", "prompt": "Test prompt", "stream": false"}''',
            "Direct Ollama inference test"
        )
    
    def test_agent_communication(self):
        """Test agent communication across sites"""
        print("\n" + "="*60)
        print("🤖 TESTING AGENT COMMUNICATION")
        print("="*60)
        
        # Register agents on different sites
        self.run_command(
            '''aitbc agent_comm register \
              --agent-id agent-local \
              --name "Local Agent" \
              --chain-id test-chain-local \
              --node-endpoint http://127.0.0.1:18000 \
              --capabilities "analytics,monitoring"''',
            "Agent registration on aitbc"
        )
        
        self.run_command(
            '''aitbc agent_comm register \
              --agent-id agent-remote \
              --name "Remote Agent" \
              --chain-id test-chain-remote \
              --node-endpoint http://127.0.0.1:18001 \
              --capabilities "trading,analysis"''',
            "Agent registration on aitbc1"
        )
        
        # Test agent discovery
        self.run_command(
            "aitbc agent_comm list --node-endpoint http://127.0.0.1:18000",
            "Agent listing on aitbc"
        )
        
        self.run_command(
            "aitbc agent_comm list --node-endpoint http://127.0.0.1:18001",
            "Agent listing on aitbc1"
        )
        
        # Test network overview
        self.run_command(
            "aitbc agent_comm network --node-endpoint http://127.0.0.1:18000",
            "Agent network overview"
        )
    
    def test_blockchain_operations(self):
        """Test blockchain operations across sites"""
        print("\n" + "="*60)
        print("⛓️ TESTING BLOCKCHAIN OPERATIONS")
        print("="*60)
        
        # Test blockchain sync status
        self.run_command(
            "curl -s http://127.0.0.1:18000/v1/blockchain/sync/status | jq .",
            "Blockchain sync status on aitbc"
        )
        
        self.run_command(
            "curl -s http://127.0.0.1:18001/v1/blockchain/sync/status | jq .",
            "Blockchain sync status on aitbc1"
        )
        
        # Test node connectivity
        self.run_command(
            "aitbc node connect --node-endpoint http://127.0.0.1:18000",
            "Node connectivity test on aitbc"
        )
        
        self.run_command(
            "aitbc node connect --node-endpoint http://127.0.0.1:18001",
            "Node connectivity test on aitbc1"
        )
    
    def test_container_access(self):
        """Test container access to localhost GPU services"""
        print("\n" + "="*60)
        print("🏢 TESTING CONTAINER ACCESS")
        print("="*60)
        
        # Test service discovery from aitbc container
        self.run_command(
            '''ssh aitbc-cascade "curl -s http://localhost:8000/v1/marketplace/offers | jq '.[] | select(.miner_id == \\"miner1\\')'"''',
            "Service discovery from aitbc container"
        )
        
        # Test service discovery from aitbc1 container
        self.run_command(
            '''ssh aitbc1-cascade "curl -s http://localhost:8000/v1/marketplace/offers | jq '.[] | select(.miner_id == \\"miner1\\')'"''',
            "Service discovery from aitbc1 container"
        )
        
        # Test container health
        self.run_command(
            "ssh aitbc-cascade 'curl -s http://localhost:8000/v1/health'",
            "aitbc container health"
        )
        
        self.run_command(
            "ssh aitbc1-cascade 'curl -s http://localhost:8000/v1/health'",
            "aitbc1 container health"
        )
    
    def test_performance(self):
        """Test performance and load handling"""
        print("\n" + "="*60)
        print("⚡ TESTING PERFORMANCE")
        print("="*60)
        
        # Test concurrent requests
        print("🔄 Testing concurrent marketplace requests...")
        for i in range(3):
            self.run_command(
                f"curl -s http://127.0.0.1:18000/v1/marketplace/offers",
                f"Concurrent request {i+1}"
            )
        
        # Test response times
        start_time = time.time()
        success, _ = self.run_command(
            "curl -s http://127.0.0.1:18000/v1/health",
            "Response time measurement"
        )
        if success:
            response_time = time.time() - start_time
            self.log_test("Response time check", response_time < 2.0, f"{response_time:.2f}s")
    
    def test_cross_site_integration(self):
        """Test cross-site integration scenarios"""
        print("\n" + "="*60)
        print("🔗 TESTING CROSS-SITE INTEGRATION")
        print("="*60)
        
        # Test marketplace synchronization
        self.run_command(
            "curl -s http://127.0.0.1:18000/v1/marketplace/stats | jq .",
            "Marketplace stats on aitbc"
        )
        
        self.run_command(
            "curl -s http://127.0.0.1:18001/v1/marketplace/stats | jq .",
            "Marketplace stats on aitbc1"
        )
        
        # Test analytics cross-chain
        self.run_command(
            "aitbc analytics cross-chain --node-endpoint http://127.0.0.1:18000 --primary-chain test-chain-local --secondary-chain test-chain-remote",
            "Cross-chain analytics"
        )
    
    def generate_report(self):
        """Generate comprehensive test report"""
        print("\n" + "="*60)
        print("📊 TEST REPORT")
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["success"]])
        failed_tests = len(self.failed_tests)
        
        print(f"\n📈 Summary:")
        print(f"  Total Tests: {total_tests}")
        print(f"  Passed: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
        print(f"  Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
        
        if self.failed_tests:
            print(f"\n❌ Failed Tests:")
            for test in self.failed_tests:
                print(f"  • {test}")
        
        print(f"\n✅ Test Coverage:")
        print(f"  • Connectivity Tests")
        print(f"  • CLI Feature Tests")
        print(f"  • GPU Service Tests")
        print(f"  • Agent Communication Tests")
        print(f"  • Blockchain Operation Tests")
        print(f"  • Container Access Tests")
        print(f"  • Performance Tests")
        print(f"  • Cross-Site Integration Tests")
        
        # Save detailed report
        report_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "total": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "success_rate": passed_tests/total_tests*100
            },
            "results": self.test_results,
            "failed_tests": self.failed_tests
        }
        
        report_file = Path("/home/oib/windsurf/aitbc/test_report.json")
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        print(f"\n📄 Detailed report saved to: {report_file}")
        
        return failed_tests == 0

def main():
    """Main test execution"""
    print("🚀 Starting Comprehensive Multi-Site AITBC Test Suite")
    print("Testing localhost, aitbc, and aitbc1 with all CLI features")
    
    tester = MultiSiteTester()
    
    try:
        # Run all test phases
        tester.test_connectivity()
        tester.test_cli_features()
        tester.test_gpu_services()
        tester.test_agent_communication()
        tester.test_blockchain_operations()
        tester.test_container_access()
        tester.test_performance()
        tester.test_cross_site_integration()
        
        # Generate final report
        success = tester.generate_report()
        
        if success:
            print("\n🎉 ALL TESTS PASSED!")
            print("Multi-site AITBC ecosystem is fully functional")
            sys.exit(0)
        else:
            print("\n⚠️ SOME TESTS FAILED")
            print("Check the failed tests and fix issues")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test execution failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
