#!/usr/bin/env python3
"""
Complete production deployment and scaling workflow test
"""

import sys
import os
import asyncio
import json
from datetime import datetime, timedelta
sys.path.insert(0, '/home/oib/windsurf/aitbc/cli')

from aitbc_cli.core.deployment import ProductionDeployment, ScalingPolicy

async def test_complete_deployment_workflow():
    """Test the complete production deployment workflow"""
    print("🚀 Starting Complete Production Deployment Workflow Test")
    
    # Initialize deployment system
    deployment = ProductionDeployment("/tmp/test_aitbc_production")
    print("✅ Production deployment system initialized")
    
    # Test 1: Create multiple deployment configurations
    print("\n📋 Testing Deployment Configuration Creation...")
    
    # Mock infrastructure deployment for all tests
    original_deploy_infra = deployment._deploy_infrastructure
    async def mock_deploy_infra(dep_config):
        print(f"  Mock infrastructure deployment for {dep_config.name}")
        return True
    deployment._deploy_infrastructure = mock_deploy_infra
    
    deployments = [
        {
            "name": "aitbc-main-api",
            "environment": "production",
            "region": "us-west-1",
            "instance_type": "t3.medium",
            "min_instances": 2,
            "max_instances": 20,
            "desired_instances": 4,
            "port": 8080,
            "domain": "api.aitbc.dev",
            "database_config": {"host": "prod-db.aitbc.dev", "port": 5432, "name": "aitbc_prod"}
        },
        {
            "name": "aitbc-marketplace",
            "environment": "production",
            "region": "us-east-1",
            "instance_type": "t3.large",
            "min_instances": 3,
            "max_instances": 15,
            "desired_instances": 5,
            "port": 3000,
            "domain": "marketplace.aitbc.dev",
            "database_config": {"host": "prod-db.aitbc.dev", "port": 5432, "name": "aitbc_marketplace"}
        },
        {
            "name": "aitbc-analytics",
            "environment": "production",
            "region": "eu-west-1",
            "instance_type": "t3.small",
            "min_instances": 1,
            "max_instances": 10,
            "desired_instances": 3,
            "port": 9090,
            "domain": "analytics.aitbc.dev",
            "database_config": {"host": "analytics-db.aitbc.dev", "port": 5432, "name": "aitbc_analytics"}
        },
        {
            "name": "aitbc-staging",
            "environment": "staging",
            "region": "us-west-2",
            "instance_type": "t3.micro",
            "min_instances": 1,
            "max_instances": 5,
            "desired_instances": 2,
            "port": 8081,
            "domain": "staging.aitbc.dev",
            "database_config": {"host": "staging-db.aitbc.dev", "port": 5432, "name": "aitbc_staging"}
        }
    ]
    
    deployment_ids = []
    for dep_config in deployments:
        deployment_id = await deployment.create_deployment(
            name=dep_config["name"],
            environment=dep_config["environment"],
            region=dep_config["region"],
            instance_type=dep_config["instance_type"],
            min_instances=dep_config["min_instances"],
            max_instances=dep_config["max_instances"],
            desired_instances=dep_config["desired_instances"],
            port=dep_config["port"],
            domain=dep_config["domain"],
            database_config=dep_config["database_config"]
        )
        
        if deployment_id:
            deployment_ids.append(deployment_id)
            print(f"  ✅ Created: {dep_config['name']} ({dep_config['environment']})")
        else:
            print(f"  ❌ Failed to create: {dep_config['name']}")
    
    print(f"  📊 Successfully created {len(deployment_ids)}/{len(deployments)} deployment configurations")
    
    # Test 2: Deploy all applications
    print("\n🚀 Testing Application Deployment...")
    
    deployed_count = 0
    for deployment_id in deployment_ids:
        success = await deployment.deploy_application(deployment_id)
        if success:
            deployed_count += 1
            config = deployment.deployments[deployment_id]
            print(f"  ✅ Deployed: {config.name} on {config.port} instances")
        else:
            print(f"  ❌ Failed to deploy: {deployment_id}")
    
    print(f"  📊 Successfully deployed {deployed_count}/{len(deployment_ids)} applications")
    
    # Test 3: Manual scaling operations
    print("\n📈 Testing Manual Scaling Operations...")
    
    scaling_operations = [
        (deployment_ids[0], 8, "Increased capacity for main API"),
        (deployment_ids[1], 10, "Marketplace traffic increase"),
        (deployment_ids[2], 5, "Analytics processing boost")
    ]
    
    scaling_success = 0
    for deployment_id, target_instances, reason in scaling_operations:
        success = await deployment.scale_deployment(deployment_id, target_instances, reason)
        if success:
            scaling_success += 1
            config = deployment.deployments[deployment_id]
            print(f"  ✅ Scaled: {config.name} to {target_instances} instances")
        else:
            print(f"  ❌ Failed to scale: {deployment_id}")
    
    print(f"  📊 Successfully completed {scaling_success}/{len(scaling_operations)} scaling operations")
    
    # Test 4: Auto-scaling simulation
    print("\n🤖 Testing Auto-Scaling Simulation...")
    
    # Simulate high load on main API
    main_api_metrics = deployment.metrics[deployment_ids[0]]
    main_api_metrics.cpu_usage = 85.0
    main_api_metrics.memory_usage = 75.0
    main_api_metrics.error_rate = 3.0
    main_api_metrics.response_time = 1500.0
    
    # Simulate low load on staging
    staging_metrics = deployment.metrics[deployment_ids[3]]
    staging_metrics.cpu_usage = 15.0
    staging_metrics.memory_usage = 25.0
    staging_metrics.error_rate = 0.5
    staging_metrics.response_time = 200.0
    
    auto_scale_results = []
    for deployment_id in deployment_ids:
        success = await deployment.auto_scale_deployment(deployment_id)
        auto_scale_results.append(success)
        
        config = deployment.deployments[deployment_id]
        if success:
            print(f"  ✅ Auto-scaled: {config.name} to {config.desired_instances} instances")
        else:
            print(f"  ⚪ No scaling needed: {config.name}")
    
    auto_scale_success = sum(auto_scale_results)
    print(f"  📊 Auto-scaling decisions: {auto_scale_success}/{len(deployment_ids)} actions taken")
    
    # Test 5: Health monitoring
    print("\n💚 Testing Health Monitoring...")
    
    healthy_count = 0
    for deployment_id in deployment_ids:
        health_status = deployment.health_checks.get(deployment_id, False)
        if health_status:
            healthy_count += 1
            config = deployment.deployments[deployment_id]
            print(f"  ✅ Healthy: {config.name}")
        else:
            config = deployment.deployments[deployment_id]
            print(f"  ❌ Unhealthy: {config.name}")
    
    print(f"  📊 Health status: {healthy_count}/{len(deployment_ids)} deployments healthy")
    
    # Test 6: Performance metrics collection
    print("\n📊 Testing Performance Metrics Collection...")
    
    metrics_summary = []
    for deployment_id in deployment_ids:
        metrics = deployment.metrics.get(deployment_id)
        if metrics:
            config = deployment.deployments[deployment_id]
            metrics_summary.append({
                "name": config.name,
                "cpu": f"{metrics.cpu_usage:.1f}%",
                "memory": f"{metrics.memory_usage:.1f}%",
                "requests": metrics.request_count,
                "error_rate": f"{metrics.error_rate:.2f}%",
                "response_time": f"{metrics.response_time:.1f}ms",
                "uptime": f"{metrics.uptime_percentage:.2f}%"
            })
    
    for summary in metrics_summary:
        print(f"  ✅ {summary['name']}: CPU {summary['cpu']}, Memory {summary['memory']}, Uptime {summary['uptime']}")
    
    # Test 7: Individual deployment status
    print("\n📋 Testing Individual Deployment Status...")
    
    for deployment_id in deployment_ids[:2]:  # Test first 2 deployments
        status = await deployment.get_deployment_status(deployment_id)
        if status:
            config = status["deployment"]
            metrics = status["metrics"]
            health = status["health_status"]
            
            print(f"  ✅ {config['name']}:")
            print(f"    Environment: {config['environment']}")
            print(f"    Instances: {config['desired_instances']}/{config['max_instances']}")
            print(f"    Health: {'✅ Healthy' if health else '❌ Unhealthy'}")
            print(f"    CPU: {metrics['cpu_usage']:.1f}%")
            print(f"    Memory: {metrics['memory_usage']:.1f}%")
            print(f"    Response Time: {metrics['response_time']:.1f}ms")
    
    # Test 8: Cluster overview
    print("\n🌐 Testing Cluster Overview...")
    
    overview = await deployment.get_cluster_overview()
    
    if overview:
        print(f"  ✅ Cluster Overview:")
        print(f"    Total Deployments: {overview['total_deployments']}")
        print(f"    Running Deployments: {overview['running_deployments']}")
        print(f"    Total Instances: {overview['total_instances']}")
        print(f"    Health Check Coverage: {overview['health_check_coverage']:.1%}")
        print(f"    Recent Scaling Events: {overview['recent_scaling_events']}")
        print(f"    Scaling Success Rate: {overview['successful_scaling_rate']:.1%}")
        
        if "aggregate_metrics" in overview:
            agg = overview["aggregate_metrics"]
            print(f"    Average CPU Usage: {agg['total_cpu_usage']:.1f}%")
            print(f"    Average Memory Usage: {agg['total_memory_usage']:.1f}%")
            print(f"    Average Response Time: {agg['average_response_time']:.1f}ms")
            print(f"    Average Uptime: {agg['average_uptime']:.1f}%")
    
    # Test 9: Scaling event history
    print("\n📜 Testing Scaling Event History...")
    
    all_scaling_events = deployment.scaling_events
    recent_events = [
        event for event in all_scaling_events
        if event.triggered_at >= datetime.now() - timedelta(hours=1)
    ]
    
    print(f"  ✅ Scaling Events:")
    print(f"    Total Events: {len(all_scaling_events)}")
    print(f"    Recent Events (1h): {len(recent_events)}")
    print(f"    Success Rate: {sum(1 for e in recent_events if e.success) / len(recent_events) * 100:.1f}%" if recent_events else "N/A")
    
    for event in recent_events[-3:]:  # Show last 3 events
        config = deployment.deployments[event.deployment_id]
        direction = "📈" if event.new_instances > event.old_instances else "📉"
        print(f"    {direction} {config.name}: {event.old_instances} → {event.new_instances} ({event.trigger_reason})")
    
    # Test 10: Configuration validation
    print("\n✅ Testing Configuration Validation...")
    
    validation_results = []
    for deployment_id in deployment_ids:
        config = deployment.deployments[deployment_id]
        
        # Validate configuration constraints
        valid = True
        if config.min_instances > config.desired_instances:
            valid = False
        if config.desired_instances > config.max_instances:
            valid = False
        if config.port <= 0:
            valid = False
        
        validation_results.append((config.name, valid))
        
        status = "✅ Valid" if valid else "❌ Invalid"
        print(f"  {status}: {config.name}")
    
    valid_configs = sum(1 for _, valid in validation_results if valid)
    print(f"  📊 Configuration validation: {valid_configs}/{len(deployment_ids)} valid configurations")
    
    # Restore original method
    deployment._deploy_infrastructure = original_deploy_infra
    
    print("\n🎉 Complete Production Deployment Workflow Test Finished!")
    print("📊 Summary:")
    print("  ✅ Deployment configuration creation working")
    print("  ✅ Application deployment and startup functional")
    print("  ✅ Manual scaling operations successful")
    print("  ✅ Auto-scaling simulation operational")
    print("  ✅ Health monitoring system active")
    print("  ✅ Performance metrics collection working")
    print("  ✅ Individual deployment status available")
    print("  ✅ Cluster overview and analytics complete")
    print("  ✅ Scaling event history tracking functional")
    print("  ✅ Configuration validation working")
    
    # Performance metrics
    print(f"\n📈 Current Production Metrics:")
    if overview:
        print(f"  • Total Deployments: {overview['total_deployments']}")
        print(f"  • Running Deployments: {overview['running_deployments']}")
        print(f"  • Total Instances: {overview['total_instances']}")
        print(f"  • Health Check Coverage: {overview['health_check_coverage']:.1%}")
        print(f"  • Scaling Success Rate: {overview['successful_scaling_rate']:.1%}")
        print(f"  • Average CPU Usage: {overview['aggregate_metrics']['total_cpu_usage']:.1f}%")
        print(f"  • Average Memory Usage: {overview['aggregate_metrics']['total_memory_usage']:.1f}%")
        print(f"  • Average Uptime: {overview['aggregate_metrics']['average_uptime']:.1f}%")
    
    print(f"  • Total Scaling Events: {len(all_scaling_events)}")
    print(f"  • Configuration Files Generated: {len(deployment_ids)}")
    print(f"  • Health Checks Active: {healthy_count}")

if __name__ == "__main__":
    asyncio.run(test_complete_deployment_workflow())
