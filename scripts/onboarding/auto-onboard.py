#!/usr/bin/env python3
"""
auto-onboard.py - Automated onboarding for AITBC agents

This script provides automated onboarding for new agents joining the AITBC network.
It handles capability assessment, agent type recommendation, registration, and swarm integration.
"""

import asyncio
import json
import sys
import os
import subprocess
import logging
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AgentOnboarder:
    """Automated agent onboarding system"""
    
    def __init__(self):
        self.session = {
            'start_time': datetime.utcnow(),
            'steps_completed': [],
            'errors': [],
            'agent': None
        }
    
    async def run_auto_onboarding(self):
        """Run complete automated onboarding"""
        try:
            logger.info("🤖 Starting AITBC Agent Network Automated Onboarding")
            logger.info("=" * 60)
            
            # Step 1: Environment Check
            await self.check_environment()
            
            # Step 2: Capability Assessment
            capabilities = await self.assess_capabilities()
            
            # Step 3: Agent Type Recommendation
            agent_type = await self.recommend_agent_type(capabilities)
            
            # Step 4: Agent Creation
            agent = await self.create_agent(agent_type, capabilities)
            
            # Step 5: Network Registration
            await self.register_agent(agent)
            
            # Step 6: Swarm Integration
            await self.join_swarm(agent, agent_type)
            
            # Step 7: Start Participation
            await self.start_participation(agent)
            
            # Step 8: Generate Report
            report = await self.generate_onboarding_report(agent)
            
            logger.info("🎉 Automated onboarding completed successfully!")
            self.print_success_summary(agent, report)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Onboarding failed: {e}")
            self.session['errors'].append(str(e))
            return False
    
    async def check_environment(self):
        """Check if environment meets requirements"""
        logger.info("📋 Step 1: Checking environment requirements...")
        
        try:
            # Check Python version
            python_version = sys.version_info
            if python_version < (3, 13):
                raise Exception(f"Python 3.13+ required, found {python_version.major}.{python_version.minor}")
            
            # Check required packages
            required_packages = ['torch', 'numpy', 'requests']
            for package in required_packages:
                try:
                    __import__(package)
                except ImportError:
                    logger.warning(f"⚠️  Package {package} not found, installing...")
                    subprocess.run([sys.executable, '-m', 'pip', 'install', package], check=True)
            
            # Check network connectivity
            import requests
            try:
                response = requests.get('https://api.aitbc.bubuit.net/v1/health', timeout=10)
                if response.status_code != 200:
                    raise Exception("Network connectivity check failed")
            except Exception as e:
                raise Exception(f"Network connectivity issue: {e}")
            
            logger.info("✅ Environment check passed")
            self.session['steps_completed'].append('environment_check')
            
        except Exception as e:
            logger.error(f"❌ Environment check failed: {e}")
            raise
    
    async def assess_capabilities(self):
        """Assess agent capabilities"""
        logger.info("🔍 Step 2: Assessing agent capabilities...")
        
        capabilities = {}
        
        # Check GPU capabilities
        try:
            import torch
            if torch.cuda.is_available():
                capabilities['gpu_available'] = True
                capabilities['gpu_memory'] = torch.cuda.get_device_properties(0).total_memory // 1024 // 1024
                capabilities['gpu_count'] = torch.cuda.device_count()
                capabilities['cuda_version'] = torch.version.cuda
                logger.info(f"✅ GPU detected: {capabilities['gpu_memory']}MB memory")
            else:
                capabilities['gpu_available'] = False
                logger.info("ℹ️  No GPU detected")
        except ImportError:
            capabilities['gpu_available'] = False
            logger.warning("⚠️  PyTorch not available for GPU detection")
        
        # Check CPU capabilities
        import psutil
        capabilities['cpu_count'] = psutil.cpu_count()
        capabilities['memory_total'] = psutil.virtual_memory().total // 1024 // 1024  # MB
        logger.info(f"✅ CPU: {capabilities['cpu_count']} cores, Memory: {capabilities['memory_total']}MB")
        
        # Check storage
        capabilities['disk_space'] = psutil.disk_usage('/').free // 1024 // 1024  # MB
        logger.info(f"✅ Available disk space: {capabilities['disk_space']}MB")
        
        # Check network bandwidth (simplified)
        try:
            start_time = datetime.utcnow()
            requests.get('https://api.aitbc.bubuit.net/v1/health', timeout=5)
            latency = (datetime.utcnow() - start_time).total_seconds()
            capabilities['network_latency'] = latency
            logger.info(f"✅ Network latency: {latency:.2f}s")
        except:
            capabilities['network_latency'] = None
            logger.warning("⚠️  Could not measure network latency")
        
        # Determine specialization
        capabilities['specializations'] = []
        if capabilities.get('gpu_available'):
            capabilities['specializations'].append('gpu_computing')
        if capabilities['memory_total'] > 8192:  # >8GB
            capabilities['specializations'].append('large_models')
        if capabilities['cpu_count'] >= 8:
            capabilities['specializations'].append('parallel_processing')
        
        logger.info(f"✅ Capabilities assessed: {len(capabilities['specializations'])} specializations")
        self.session['steps_completed'].append('capability_assessment')
        
        return capabilities
    
    async def recommend_agent_type(self, capabilities):
        """Recommend optimal agent type based on capabilities"""
        logger.info("🎯 Step 3: Determining optimal agent type...")
        
        # Decision logic
        score = {}
        
        # Compute Provider Score
        provider_score = 0
        if capabilities.get('gpu_available'):
            provider_score += 40
            if capabilities['gpu_memory'] >= 8192:  # >=8GB
                provider_score += 20
            if capabilities['gpu_memory'] >= 16384:  # >=16GB
                provider_score += 20
        if capabilities['network_latency'] and capabilities['network_latency'] < 0.1:
            provider_score += 10
        score['compute_provider'] = provider_score
        
        # Compute Consumer Score
        consumer_score = 30  # Base score for being able to consume
        if capabilities['memory_total'] >= 4096:
            consumer_score += 20
        if capabilities['network_latency'] and capabilities['network_latency'] < 0.2:
            consumer_score += 10
        score['compute_consumer'] = consumer_score
        
        # Platform Builder Score
        builder_score = 20  # Base score
        if capabilities['disk_space'] >= 10240:  # >=10GB
            builder_score += 20
        if capabilities['memory_total'] >= 4096:
            builder_score += 15
        if capabilities['cpu_count'] >= 4:
            builder_score += 15
        score['platform_builder'] = builder_score
        
        # Swarm Coordinator Score
        coordinator_score = 25  # Base score
        if capabilities['network_latency'] and capabilities['network_latency'] < 0.15:
            coordinator_score += 25
        if capabilities['cpu_count'] >= 4:
            coordinator_score += 15
        if capabilities['memory_total'] >= 2048:
            coordinator_score += 10
        score['swarm_coordinator'] = coordinator_score
        
        # Find best match
        best_type = max(score, key=score.get)
        confidence = score[best_type] / 100
        
        logger.info(f"✅ Recommended agent type: {best_type} (confidence: {confidence:.2%})")
        logger.info(f"   Scores: {score}")
        
        self.session['steps_completed'].append('agent_type_recommendation')
        return best_type
    
    async def create_agent(self, agent_type, capabilities):
        """Create agent instance"""
        logger.info(f"🔐 Step 4: Creating {agent_type} agent...")
        
        try:
            # Import here to avoid circular imports
            sys.path.append('/home/oib/windsurf/aitbc/packages/py/aitbc-agent-sdk')
            
            if agent_type == 'compute_provider':
                from aitbc_agent import ComputeProvider
                agent = ComputeProvider.register(
                    agent_name=f"auto-provider-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    capabilities={
                        "compute_type": "inference",
                        "gpu_memory": capabilities.get('gpu_memory', 0),
                        "performance_score": 0.9
                    },
                    pricing_model={"base_rate": 0.1}
                )
                
            elif agent_type == 'compute_consumer':
                from aitbc_agent import ComputeConsumer
                agent = ComputeConsumer.create(
                    agent_name=f"auto-consumer-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    capabilities={
                        "compute_type": "inference",
                        "task_requirements": {"min_performance": 0.8}
                    }
                )
                
            elif agent_type == 'platform_builder':
                from aitbc_agent import PlatformBuilder
                agent = PlatformBuilder.create(
                    agent_name=f"auto-builder-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    capabilities={
                        "specializations": capabilities.get('specializations', [])
                    }
                )
                
            elif agent_type == 'swarm_coordinator':
                from aitbc_agent import SwarmCoordinator
                agent = SwarmCoordinator.create(
                    agent_name=f"auto-coordinator-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    capabilities={
                        "specialization": "load_balancing",
                        "analytical_skills": "high"
                    }
                )
            else:
                raise Exception(f"Unknown agent type: {agent_type}")
            
            logger.info(f"✅ Agent created: {agent.identity.id}")
            self.session['agent'] = agent
            self.session['steps_completed'].append('agent_creation')
            
            return agent
            
        except Exception as e:
            logger.error(f"❌ Agent creation failed: {e}")
            raise
    
    async def register_agent(self, agent):
        """Register agent on AITBC network"""
        logger.info("🌐 Step 5: Registering on AITBC network...")
        
        try:
            success = await agent.register()
            if not success:
                raise Exception("Registration failed")
            
            logger.info(f"✅ Agent registered successfully")
            self.session['steps_completed'].append('network_registration')
            
        except Exception as e:
            logger.error(f"❌ Registration failed: {e}")
            raise
    
    async def join_swarm(self, agent, agent_type):
        """Join appropriate swarm"""
        logger.info("🐝 Step 6: Joining swarm intelligence...")
        
        try:
            # Determine appropriate swarm based on agent type
            swarm_config = {
                'compute_provider': {
                    'swarm_type': 'load_balancing',
                    'config': {
                        'role': 'resource_provider',
                        'contribution_level': 'medium',
                        'data_sharing': True
                    }
                },
                'compute_consumer': {
                    'swarm_type': 'pricing',
                    'config': {
                        'role': 'market_participant',
                        'contribution_level': 'low',
                        'data_sharing': True
                    }
                },
                'platform_builder': {
                    'swarm_type': 'innovation',
                    'config': {
                        'role': 'contributor',
                        'contribution_level': 'medium',
                        'data_sharing': True
                    }
                },
                'swarm_coordinator': {
                    'swarm_type': 'load_balancing',
                    'config': {
                        'role': 'coordinator',
                        'contribution_level': 'high',
                        'data_sharing': True
                    }
                }
            }
            
            swarm_info = swarm_config.get(agent_type)
            if not swarm_info:
                raise Exception(f"No swarm configuration for agent type: {agent_type}")
            
            joined = await agent.join_swarm(swarm_info['swarm_type'], swarm_info['config'])
            if not joined:
                raise Exception("Swarm join failed")
            
            logger.info(f"✅ Joined {swarm_info['swarm_type']} swarm")
            self.session['steps_completed'].append('swarm_integration')
            
        except Exception as e:
            logger.error(f"❌ Swarm integration failed: {e}")
            # Don't fail completely - agent can still function without swarm
            logger.warning("⚠️  Continuing without swarm integration")
    
    async def start_participation(self, agent):
        """Start agent participation"""
        logger.info("🚀 Step 7: Starting network participation...")
        
        try:
            await agent.start_contribution()
            logger.info("✅ Agent participation started")
            self.session['steps_completed'].append('participation_started')
            
        except Exception as e:
            logger.error(f"❌ Failed to start participation: {e}")
            # Don't fail completely
            logger.warning("⚠️  Agent can still function manually")
    
    async def generate_onboarding_report(self, agent):
        """Generate comprehensive onboarding report"""
        logger.info("📊 Step 8: Generating onboarding report...")
        
        report = {
            'onboarding': {
                'timestamp': datetime.utcnow().isoformat(),
                'duration_minutes': (datetime.utcnow() - self.session['start_time']).total_seconds() / 60,
                'status': 'success',
                'agent_id': agent.identity.id,
                'agent_name': agent.identity.name,
                'agent_address': agent.identity.address,
                'steps_completed': self.session['steps_completed'],
                'errors': self.session['errors']
            },
            'agent_capabilities': {
                'gpu_available': agent.capabilities.gpu_memory > 0,
                'specialization': agent.capabilities.compute_type,
                'performance_score': agent.capabilities.performance_score
            },
            'network_status': {
                'registered': agent.registered,
                'swarm_joined': len(agent.joined_swarms) > 0 if hasattr(agent, 'joined_swarms') else False,
                'participating': True
            }
        }
        
        # Save report to file
        report_file = f"/tmp/aitbc-onboarding-{agent.identity.id}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"✅ Report saved to: {report_file}")
        self.session['steps_completed'].append('report_generated')
        
        return report
    
    def print_success_summary(self, agent, report):
        """Print success summary"""
        print("\n" + "=" * 60)
        print("🎉 AUTOMATED ONBOARDING COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print()
        print("🤖 AGENT INFORMATION:")
        print(f"   ID: {agent.identity.id}")
        print(f"   Name: {agent.identity.name}")
        print(f"   Address: {agent.identity.address}")
        print(f"   Type: {agent.capabilities.compute_type}")
        print()
        print("📊 ONBOARDING SUMMARY:")
        print(f"   Duration: {report['onboarding']['duration_minutes']:.1f} minutes")
        print(f"   Steps Completed: {len(report['onboarding']['steps_completed'])}/7")
        print(f"   Status: {report['onboarding']['status']}")
        print()
        print("🌐 NETWORK STATUS:")
        print(f"   Registered: {'✅' if report['network_status']['registered'] else '❌'}")
        print(f"   Swarm Joined: {'✅' if report['network_status']['swarm_joined'] else '❌'}")
        print(f"   Participating: {'✅' if report['network_status']['participating'] else '❌'}")
        print()
        print("🔗 USEFUL LINKS:")
        print(f"   Agent Dashboard: https://aitbc.bubuit.net/agents/{agent.identity.id}")
        print(f"   Documentation: https://aitbc.bubuit.net/docs/11_agents/")
        print(f"   API Reference: https://aitbc.bubuit.net/docs/agents/agent-api-spec.json")
        print(f"   Community: https://discord.gg/aitbc-agents")
        print()
        print("🚀 NEXT STEPS:")
        
        if agent.capabilities.compute_type == 'inference' and agent.capabilities.gpu_memory > 0:
            print("   1. Monitor your GPU utilization and earnings")
            print("   2. Adjust pricing based on market demand")
            print("   3. Build reputation through reliability")
        else:
            print("   1. Submit your first computational job")
            print("   2. Monitor job completion and costs")
            print("   3. Participate in swarm intelligence")
        
        print("   4. Check your agent dashboard regularly")
        print("   5. Join the community Discord for support")
        print()
        print("💾 Session data saved to local files")
        print("   📊 Report: /tmp/aitbc-onboarding-*.json")
        print("   🔐 Keys: ~/.aitbc/agent_keys/")
        print()
        print("🎊 Welcome to the AITBC Agent Network!")

def main():
    """Main entry point"""
    onboarder = AgentOnboarder()
    
    try:
        success = asyncio.run(onboarder.run_auto_onboarding())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Onboarding interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
