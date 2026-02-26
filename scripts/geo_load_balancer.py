#!/usr/bin/env python3
"""
Geographic Load Balancer for AITBC Marketplace
"""

import asyncio
import aiohttp
from aiohttp import web
import json
from datetime import datetime
import os

# Regional endpoints configuration
regions = {
    'us-east': {'url': 'http://127.0.0.1:18000', 'weight': 3, 'healthy': True, 'edge_node': 'aitbc-edge-primary'},
    'us-west': {'url': 'http://127.0.0.1:18001', 'weight': 2, 'healthy': True, 'edge_node': 'aitbc1-edge-secondary'},
    'eu-central': {'url': 'http://127.0.0.1:8006', 'weight': 2, 'healthy': True, 'edge_node': 'localhost'},
    'eu-west': {'url': 'http://127.0.0.1:18000', 'weight': 1, 'healthy': True, 'edge_node': 'aitbc-edge-primary'},
    'ap-southeast': {'url': 'http://127.0.0.1:18001', 'weight': 2, 'healthy': True, 'edge_node': 'aitbc1-edge-secondary'},
    'ap-northeast': {'url': 'http://127.0.0.1:8006', 'weight': 1, 'healthy': True, 'edge_node': 'localhost'}
}

class GeoLoadBalancer:
    def __init__(self):
        self.current_region = 0
        self.health_check_interval = 30
        
    async def health_check(self, region_config):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{region_config['url']}/health/live", timeout=5) as response:
                    region_config['healthy'] = response.status == 200
                    region_config['last_check'] = datetime.now().isoformat()
        except Exception as e:
            region_config['healthy'] = False
            region_config['last_check'] = datetime.now().isoformat()
            region_config['error'] = str(e)
            
    async def get_healthy_region(self):
        healthy_regions = [(name, config) for name, config in regions.items() if config['healthy']]
        if not healthy_regions:
            return None, None
            
        # Simple weighted round-robin
        total_weight = sum(config['weight'] for _, config in healthy_regions)
        if total_weight == 0:
            return healthy_regions[0]
            
        import random
        rand = random.randint(1, total_weight)
        current_weight = 0
        
        for name, config in healthy_regions:
            current_weight += config['weight']
            if rand <= current_weight:
                return name, config
                
        return healthy_regions[0]
        
    async def proxy_request(self, request):
        region_name, region_config = await self.get_healthy_region()
        if not region_config:
            return web.json_response({'error': 'No healthy regions available'}, status=503)
            
        try:
            # Forward request to selected region
            target_url = f"{region_config['url']}{request.path_qs}"
            
            async with aiohttp.ClientSession() as session:
                # Prepare headers (remove host header)
                headers = dict(request.headers)
                headers.pop('Host', None)
                
                async with session.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    data=await request.read()
                ) as response:
                    # Read response
                    body = await response.read()
                    
                    # Create response
                    resp = web.Response(
                        body=body,
                        status=response.status,
                        headers=dict(response.headers)
                    )
                    
                    # Add routing headers
                    resp.headers['X-Region'] = region_name
                    resp.headers['X-Backend-Url'] = region_config['url']
                    
                    return resp
                    
        except Exception as e:
            return web.json_response({
                'error': 'Proxy error',
                'message': str(e),
                'region': region_name
            }, status=502)

async def handle_all_requests(request):
    balancer = request.app['balancer']
    return await balancer.proxy_request(request)

async def health_check_handler(request):
    balancer = request.app['balancer']
    
    # Perform health checks on all regions
    tasks = [balancer.health_check(config) for config in regions.values()]
    await asyncio.gather(*tasks)
    
    return web.json_response({
        'status': 'healthy',
        'load_balancer': 'geographic',
        'regions': regions,
        'timestamp': datetime.now().isoformat()
    })

async def status_handler(request):
    balancer = request.app['balancer']
    healthy_count = sum(1 for config in regions.values() if config['healthy'])
    
    return web.json_response({
        'total_regions': len(regions),
        'healthy_regions': healthy_count,
        'health_ratio': healthy_count / len(regions),
        'current_time': datetime.now().isoformat(),
        'regions': {name: {
            'healthy': config['healthy'],
            'weight': config['weight'],
            'last_check': config.get('last_check')
        } for name, config in regions.items()}
    })

async def create_app():
    app = web.Application()
    balancer = GeoLoadBalancer()
    app['balancer'] = balancer
    
    # Add routes
    app.router.add_route('*', '/{path:.*}', handle_all_requests)
    app.router.add_get('/health', health_check_handler)
    app.router.add_get('/status', status_handler)
    
    return app

if __name__ == '__main__':
    app = asyncio.run(create_app())
    web.run_app(app, host='127.0.0.1', port=8080)
