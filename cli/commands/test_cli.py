"""
AITBC CLI Testing Commands
Provides testing and debugging utilities for the AITBC CLI
"""

import click
import json
import time
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import Mock, patch

from utils import output, success, error, warning
from config import get_config


@click.group()
def test():
    """Testing and debugging commands for AITBC CLI"""
    pass


@test.command()
@click.option('--format', type=click.Choice(['json', 'table', 'yaml']), default='table', help='Output format')
@click.pass_context
def environment(ctx, format):
    """Test CLI environment and configuration"""
    config = ctx.obj['config']
    
    env_info = {
        'coordinator_url': config.coordinator_url,
        'api_key': config.api_key,
        'output_format': ctx.obj['output_format'],
        'test_mode': ctx.obj['test_mode'],
        'dry_run': ctx.obj['dry_run'],
        'timeout': ctx.obj['timeout'],
        'no_verify': ctx.obj['no_verify'],
        'log_level': ctx.obj['log_level']
    }
    
    if format == 'json':
        output(json.dumps(env_info, indent=2))
    else:
        output("CLI Environment Test Results:")
        output(f"  Coordinator URL: {env_info['coordinator_url']}")
        output(f"  API Key: {env_info['api_key'][:10]}..." if env_info['api_key'] else "  API Key: None")
        output(f"  Output Format: {env_info['output_format']}")
        output(f"  Test Mode: {env_info['test_mode']}")
        output(f"  Dry Run: {env_info['dry_run']}")
        output(f"  Timeout: {env_info['timeout']}s")
        output(f"  No Verify: {env_info['no_verify']}")
        output(f"  Log Level: {env_info['log_level']}")


@test.command()
@click.option('--endpoint', default='health', help='API endpoint to test')
@click.option('--method', default='GET', help='HTTP method')
@click.option('--data', help='JSON data to send (for POST/PUT)')
@click.pass_context
def api(ctx, endpoint, method, data):
    """Test API connectivity"""
    config = ctx.obj['config']
    
    try:
        import httpx
        
        # Prepare request
        url = f"{config.coordinator_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {}
        if config.api_key:
            headers['Authorization'] = f"Bearer {config.api_key}"
        
        # Prepare data
        json_data = None
        if data and method in ['POST', 'PUT']:
            json_data = json.loads(data)
        
        # Make request
        with httpx.Client(verify=not ctx.obj['no_verify'], timeout=ctx.obj['timeout']) as client:
            if method == 'GET':
                response = client.get(url, headers=headers)
            elif method == 'POST':
                response = client.post(url, headers=headers, json=json_data)
            elif method == 'PUT':
                response = client.put(url, headers=headers, json=json_data)
            else:
                raise ValueError(f"Unsupported method: {method}")
        
        # Display results
        output(f"API Test Results:")
        output(f"  URL: {url}")
        output(f"  Method: {method}")
        output(f"  Status Code: {response.status_code}")
        output(f"  Response Time: {response.elapsed.total_seconds():.3f}s")
        
        if response.status_code == 200:
            success("✅ API test successful")
            try:
                response_data = response.json()
                output("Response Data:")
                output(json.dumps(response_data, indent=2))
            except:
                output(f"Response: {response.text}")
        else:
            error(f"❌ API test failed with status {response.status_code}")
            output(f"Response: {response.text}")
            
    except ImportError:
        error("❌ httpx not installed. Install with: pip install httpx")
    except Exception as e:
        error(f"❌ API test failed: {str(e)}")


@test.command()
@click.option('--wallet-name', default='test-wallet', help='Test wallet name')
@click.option('--test-operations', is_flag=True, default=True, help='Test wallet operations')
@click.pass_context
def wallet(ctx, wallet_name, test_operations):
    """Test wallet functionality"""
    from commands.wallet import wallet as wallet_cmd
    
    output(f"Testing wallet functionality with wallet: {wallet_name}")
    
    # Test wallet creation
    try:
        result = ctx.invoke(wallet_cmd, ['create', wallet_name])
        if result.exit_code == 0:
            success(f"✅ Wallet '{wallet_name}' created successfully")
        else:
            error(f"❌ Wallet creation failed: {result.output}")
            return
    except Exception as e:
        error(f"❌ Wallet creation error: {str(e)}")
        return
    
    if test_operations:
        # Test wallet balance
        try:
            result = ctx.invoke(wallet_cmd, ['balance'])
            if result.exit_code == 0:
                success("✅ Wallet balance check successful")
                output(f"Balance output: {result.output}")
            else:
                warning(f"⚠️ Wallet balance check failed: {result.output}")
        except Exception as e:
            warning(f"⚠️ Wallet balance check error: {str(e)}")
        
        # Test wallet info
        try:
            result = ctx.invoke(wallet_cmd, ['info'])
            if result.exit_code == 0:
                success("✅ Wallet info check successful")
                output(f"Info output: {result.output}")
            else:
                warning(f"⚠️ Wallet info check failed: {result.output}")
        except Exception as e:
            warning(f"⚠️ Wallet info check error: {str(e)}")


@test.command()
@click.option('--job-type', default='ml_inference', help='Type of job to test')
@click.option('--test-data', default='{"model": "test-model", "input": "test-data"}', help='Test job data')
@click.pass_context
def job(ctx, job_type, test_data):
    """Test job submission and management"""
    from commands.client import client as client_cmd
    
    output(f"Testing job submission with type: {job_type}")
    
    try:
        # Parse test data
        job_data = json.loads(test_data)
        job_data['type'] = job_type
        
        # Test job submission
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(job_data, f)
            temp_file = f.name
        
        try:
            result = ctx.invoke(client_cmd, ['submit', '--job-file', temp_file])
            if result.exit_code == 0:
                success("✅ Job submission successful")
                output(f"Submission output: {result.output}")
                
                # Extract job ID if present
                if 'job_id' in result.output:
                    import re
                    job_id_match = re.search(r'job[_\s-]?id[:\s]+(\w+)', result.output, re.IGNORECASE)
                    if job_id_match:
                        job_id = job_id_match.group(1)
                        output(f"Extracted job ID: {job_id}")
                        
                        # Test job status
                        try:
                            status_result = ctx.invoke(client_cmd, ['status', job_id])
                            if status_result.exit_code == 0:
                                success("✅ Job status check successful")
                                output(f"Status output: {status_result.output}")
                            else:
                                warning(f"⚠️ Job status check failed: {status_result.output}")
                        except Exception as e:
                            warning(f"⚠️ Job status check error: {str(e)}")
            else:
                error(f"❌ Job submission failed: {result.output}")
        finally:
            # Clean up temp file
            Path(temp_file).unlink(missing_ok=True)
            
    except json.JSONDecodeError:
        error(f"❌ Invalid test data JSON: {test_data}")
    except Exception as e:
        error(f"❌ Job test failed: {str(e)}")


@test.command()
@click.option('--gpu-type', default='RTX 3080', help='GPU type to test')
@click.option('--price', type=float, default=0.1, help='Price to test')
@click.pass_context
def marketplace(ctx, gpu_type, price):
    """Test marketplace functionality"""
    from commands.marketplace import marketplace as marketplace_cmd
    
    output(f"Testing marketplace functionality for {gpu_type} at {price} AITBC/hour")
    
    # Test marketplace offers listing
    try:
        result = ctx.invoke(marketplace_cmd, ['offers', 'list'])
        if result.exit_code == 0:
            success("✅ Marketplace offers list successful")
            output(f"Offers output: {result.output}")
        else:
            warning(f"⚠️ Marketplace offers list failed: {result.output}")
    except Exception as e:
        warning(f"⚠️ Marketplace offers list error: {str(e)}")
    
    # Test marketplace pricing
    try:
        result = ctx.invoke(marketplace_cmd, ['pricing', gpu_type])
        if result.exit_code == 0:
            success("✅ Marketplace pricing check successful")
            output(f"Pricing output: {result.output}")
        else:
            warning(f"⚠️ Marketplace pricing check failed: {result.output}")
    except Exception as e:
        warning(f"⚠️ Marketplace pricing check error: {str(e)}")


@test.command()
@click.option('--test-endpoints', is_flag=True, default=True, help='Test blockchain endpoints')
@click.pass_context
def blockchain(ctx, test_endpoints):
    """Test blockchain functionality"""
    from commands.blockchain import blockchain as blockchain_cmd
    
    output("Testing blockchain functionality")
    
    if test_endpoints:
        # Test blockchain info
        try:
            result = ctx.invoke(blockchain_cmd, ['info'])
            if result.exit_code == 0:
                success("✅ Blockchain info successful")
                output(f"Info output: {result.output}")
            else:
                warning(f"⚠️ Blockchain info failed: {result.output}")
        except Exception as e:
            warning(f"⚠️ Blockchain info error: {str(e)}")
        
        # Test chain status
        try:
            result = ctx.invoke(blockchain_cmd, ['status'])
            if result.exit_code == 0:
                success("✅ Blockchain status successful")
                output(f"Status output: {result.output}")
            else:
                warning(f"⚠️ Blockchain status failed: {result.output}")
        except Exception as e:
            warning(f"⚠️ Blockchain status error: {str(e)}")


@test.command()
@click.option('--component', help='Specific component to test (wallet, job, marketplace, blockchain, api)')
@click.option('--verbose', is_flag=True, help='Verbose test output')
@click.pass_context
def integration(ctx, component, verbose):
    """Run integration tests"""
    
    if component:
        output(f"Running integration tests for: {component}")
        
        if component == 'wallet':
            ctx.invoke(wallet, ['--test-operations'])
        elif component == 'job':
            ctx.invoke(job, [])
        elif component == 'marketplace':
            ctx.invoke(marketplace)
        elif component == 'blockchain':
            ctx.invoke(blockchain, [])
        elif component == 'api':
            ctx.invoke(api, endpoint='health')
        else:
            error(f"Unknown component: {component}")
            return
    else:
        output("Running full integration test suite...")
        
        # Test API connectivity first
        output("1. Testing API connectivity...")
        ctx.invoke(api, endpoint='health')
        
        # Test wallet functionality
        output("2. Testing wallet functionality...")
        ctx.invoke(wallet, ['--wallet-name', 'integration-test-wallet'])
        
        # Test marketplace functionality
        output("3. Testing marketplace functionality...")
        ctx.invoke(marketplace)
        
        # Test blockchain functionality
        output("4. Testing blockchain functionality...")
        ctx.invoke(blockchain, [])
        
        # Test job functionality
        output("5. Testing job functionality...")
        ctx.invoke(job, [])
        
        success("✅ Integration test suite completed")


@test.command()
@click.option('--output-file', help='Save test results to file')
@click.pass_context
def diagnostics(ctx, output_file):
    """Run comprehensive diagnostics"""
    
    diagnostics_data = {
        'timestamp': time.time(),
        'test_mode': ctx.obj['test_mode'],
        'dry_run': ctx.obj['dry_run'],
        'config': {
            'coordinator_url': ctx.obj['config'].coordinator_url,
            'api_key_present': bool(ctx.obj['config'].api_key),
            'output_format': ctx.obj['output_format']
        }
    }
    
    output("Running comprehensive diagnostics...")
    
    # Test 1: Environment
    output("1. Testing environment...")
    try:
        ctx.invoke(environment, format='json')
        diagnostics_data['environment'] = 'PASS'
    except Exception as e:
        diagnostics_data['environment'] = f'FAIL: {str(e)}'
        error(f"Environment test failed: {str(e)}")
    
    # Test 2: API Connectivity
    output("2. Testing API connectivity...")
    try:
        ctx.invoke(api, endpoint='health')
        diagnostics_data['api_connectivity'] = 'PASS'
    except Exception as e:
        diagnostics_data['api_connectivity'] = f'FAIL: {str(e)}'
        error(f"API connectivity test failed: {str(e)}")
    
    # Test 3: Wallet Creation
    output("3. Testing wallet creation...")
    try:
        ctx.invoke(wallet, wallet_name='diagnostics-test', test_operations=True)
        diagnostics_data['wallet_creation'] = 'PASS'
    except Exception as e:
        diagnostics_data['wallet_creation'] = f'FAIL: {str(e)}'
        error(f"Wallet creation test failed: {str(e)}")
    
    # Test 4: Marketplace
    output("4. Testing marketplace...")
    try:
        ctx.invoke(marketplace)
        diagnostics_data['marketplace'] = 'PASS'
    except Exception as e:
        diagnostics_data['marketplace'] = f'FAIL: {str(e)}'
        error(f"Marketplace test failed: {str(e)}")
    
    # Generate summary
    passed_tests = sum(1 for v in diagnostics_data.values() if isinstance(v, str) and v == 'PASS')
    total_tests = len([k for k in diagnostics_data.keys() if k in ['environment', 'api_connectivity', 'wallet_creation', 'marketplace']])
    
    diagnostics_data['summary'] = {
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'failed_tests': total_tests - passed_tests,
        'success_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0
    }
    
    # Display results
    output("\n" + "="*50)
    output("DIAGNOSTICS SUMMARY")
    output("="*50)
    output(f"Total Tests: {diagnostics_data['summary']['total_tests']}")
    output(f"Passed: {diagnostics_data['summary']['passed_tests']}")
    output(f"Failed: {diagnostics_data['summary']['failed_tests']}")
    output(f"Success Rate: {diagnostics_data['summary']['success_rate']:.1f}%")
    
    if diagnostics_data['summary']['success_rate'] == 100:
        success("✅ All diagnostics passed!")
    else:
        warning(f"⚠️ {diagnostics_data['summary']['failed_tests']} test(s) failed")
    
    # Save to file if requested
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(diagnostics_data, f, indent=2)
        output(f"Diagnostics saved to: {output_file}")


@test.command()
def mock():
    """Generate mock data for testing"""
    
    mock_data = {
        'wallet': {
            'name': 'test-wallet',
            'address': 'aitbc1test123456789abcdef',
            'balance': 1000.0,
            'transactions': []
        },
        'job': {
            'id': 'test-job-123',
            'type': 'ml_inference',
            'status': 'pending',
            'requirements': {
                'gpu_type': 'RTX 3080',
                'memory_gb': 8,
                'duration_minutes': 30
            }
        },
        'marketplace': {
            'offers': [
                {
                    'id': 'offer-1',
                    'provider': 'test-provider',
                    'gpu_type': 'RTX 3080',
                    'price_per_hour': 0.1,
                    'available': True
                }
            ]
        },
        'blockchain': {
            'chain_id': 'aitbc-testnet',
            'block_height': 1000,
            'network_status': 'active'
        }
    }
    
    output("Mock data for testing:")
    output(json.dumps(mock_data, indent=2))
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(mock_data, f, indent=2)
        temp_file = f.name
    
    output(f"Mock data saved to: {temp_file}")
    return temp_file
