"""
Marketplace GPU Resource Optimizer
Optimizes GPU acceleration and resource utilization specifically for marketplace AI power trading
"""

import os
import sys
import time
import json
import asyncio
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import threading
import multiprocessing

from aitbc import get_logger

# Try to import pycuda, fallback if not available
try:
    import pycuda.driver as cuda
    import pycuda.autoinit
    from pycuda.compiler import SourceModule
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    print("Warning: PyCUDA not available. GPU optimization will run in simulation mode.")

logger = logging.getLogger(__name__)

class MarketplaceGPUOptimizer:
    """Optimizes GPU resources for marketplace AI power trading"""
    
    def __init__(self, simulation_mode: bool = not CUDA_AVAILABLE):
        self.simulation_mode = simulation_mode
        self.gpu_devices = []
        self.gpu_memory_pools = {}
        self.active_jobs = {}
        self.resource_metrics = {
            'total_utilization': 0.0,
            'memory_utilization': 0.0,
            'compute_utilization': 0.0,
            'energy_efficiency': 0.0,
            'jobs_processed': 0,
            'failed_jobs': 0
        }
        
        # Optimization configuration
        self.config = {
            'memory_fragmentation_threshold': 0.15,  # 15%
            'dynamic_batching_enabled': True,
            'max_batch_size': 128,
            'idle_power_state': 'P8',
            'active_power_state': 'P0',
            'thermal_throttle_threshold': 85.0  # Celsius
        }
        
        self.lock = threading.Lock()
        self._initialize_gpu_devices()
        
    def _initialize_gpu_devices(self):
        """Initialize available GPU devices"""
        if self.simulation_mode:
            # Create simulated GPUs
            self.gpu_devices = [
                {
                    'id': 0,
                    'name': 'Simulated RTX 4090',
                    'total_memory': 24 * 1024 * 1024 * 1024,  # 24GB
                    'free_memory': 24 * 1024 * 1024 * 1024,
                    'compute_capability': (8, 9),
                    'utilization': 0.0,
                    'temperature': 45.0,
                    'power_draw': 30.0,
                    'power_limit': 450.0,
                    'status': 'idle'
                },
                {
                    'id': 1,
                    'name': 'Simulated RTX 4090',
                    'total_memory': 24 * 1024 * 1024 * 1024,
                    'free_memory': 24 * 1024 * 1024 * 1024,
                    'compute_capability': (8, 9),
                    'utilization': 0.0,
                    'temperature': 42.0,
                    'power_draw': 28.0,
                    'power_limit': 450.0,
                    'status': 'idle'
                }
            ]
            logger.info(f"Initialized {len(self.gpu_devices)} simulated GPU devices")
        else:
            try:
                # Initialize real GPUs via PyCUDA
                num_devices = cuda.Device.count()
                for i in range(num_devices):
                    dev = cuda.Device(i)
                    free_mem, total_mem = cuda.mem_get_info()
                    
                    self.gpu_devices.append({
                        'id': i,
                        'name': dev.name(),
                        'total_memory': total_mem,
                        'free_memory': free_mem,
                        'compute_capability': dev.compute_capability(),
                        'utilization': 0.0,  # Would need NVML for real utilization
                        'temperature': 0.0,  # Would need NVML
                        'power_draw': 0.0,   # Would need NVML
                        'power_limit': 0.0,  # Would need NVML
                        'status': 'idle'
                    })
                logger.info(f"Initialized {len(self.gpu_devices)} real GPU devices")
            except Exception as e:
                logger.error(f"Error initializing GPUs: {e}")
                self.simulation_mode = True
                self._initialize_gpu_devices()  # Fallback to simulation
                
        # Initialize memory pools for each device
        for gpu in self.gpu_devices:
            self.gpu_memory_pools[gpu['id']] = {
                'allocated_blocks': [],
                'free_blocks': [{'start': 0, 'size': gpu['total_memory']}],
                'fragmentation': 0.0
            }
            
    async def optimize_resource_allocation(self, job_requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize GPU resource allocation for a new marketplace job
        Returns the allocation plan or rejection if resources unavailable
        """
        required_memory = job_requirements.get('memory_bytes', 1024 * 1024 * 1024)  # Default 1GB
        required_compute = job_requirements.get('compute_units', 1.0)
        max_latency = job_requirements.get('max_latency_ms', 1000)
        priority = job_requirements.get('priority', 1)  # 1 (low) to 10 (high)
        
        with self.lock:
            # 1. Find optimal GPU
            best_gpu_id = -1
            best_score = -1.0
            
            for gpu in self.gpu_devices:
                # Check constraints
                if gpu['free_memory'] < required_memory:
                    continue
                    
                if gpu['temperature'] > self.config['thermal_throttle_threshold'] and priority < 8:
                    continue # Reserve hot GPUs for high priority only
                    
                # Calculate optimization score (higher is better)
                # We want to balance load but also minimize fragmentation
                mem_utilization = 1.0 - (gpu['free_memory'] / gpu['total_memory'])
                comp_utilization = gpu['utilization']
                
                # Formula: Favor GPUs with enough space but try to pack jobs efficiently
                # Penalty for high temp and high current utilization
                score = 100.0
                score -= (comp_utilization * 40.0)
                score -= ((gpu['temperature'] - 40.0) * 1.5)
                
                # Memory fit score: tighter fit is better to reduce fragmentation
                mem_fit_ratio = required_memory / gpu['free_memory']
                score += (mem_fit_ratio * 20.0)
                
                if score > best_score:
                    best_score = score
                    best_gpu_id = gpu['id']
                    
            if best_gpu_id == -1:
                # No GPU available, try optimization strategies
                if await self._attempt_memory_defragmentation():
                    return await self.optimize_resource_allocation(job_requirements)
                elif await self._preempt_low_priority_jobs(priority, required_memory):
                    return await self.optimize_resource_allocation(job_requirements)
                else:
                    return {
                        'success': False,
                        'reason': 'Insufficient GPU resources available even after optimization',
                        'queued': True,
                        'estimated_wait_ms': 5000
                    }
                    
            # 2. Allocate resources on best GPU
            job_id = f"job_{uuid4().hex[:8]}" if 'job_id' not in job_requirements else job_requirements['job_id']
            
            allocation = self._allocate_memory(best_gpu_id, required_memory, job_id)
            if not allocation['success']:
                return {
                    'success': False,
                    'reason': 'Memory allocation failed due to fragmentation',
                    'queued': True
                }
                
            # 3. Update state
            for i, gpu in enumerate(self.gpu_devices):
                if gpu['id'] == best_gpu_id:
                    self.gpu_devices[i]['free_memory'] -= required_memory
                    self.gpu_devices[i]['utilization'] = min(1.0, self.gpu_devices[i]['utilization'] + (required_compute * 0.1))
                    self.gpu_devices[i]['status'] = 'active'
                    break
                    
            self.active_jobs[job_id] = {
                'gpu_id': best_gpu_id,
                'memory_allocated': required_memory,
                'compute_allocated': required_compute,
                'priority': priority,
                'start_time': time.time(),
                'status': 'running'
            }
            
            self._update_metrics()
            
            return {
                'success': True,
                'job_id': job_id,
                'gpu_id': best_gpu_id,
                'allocation_plan': {
                    'memory_blocks': allocation['blocks'],
                    'dynamic_batching': self.config['dynamic_batching_enabled'],
                    'power_state_enforced': self.config['active_power_state']
                },
                'estimated_completion_ms': int(required_compute * 100)
            }
            
    def _allocate_memory(self, gpu_id: int, size: int, job_id: str) -> Dict[str, Any]:
        """Custom memory allocator designed to minimize fragmentation"""
        pool = self.gpu_memory_pools[gpu_id]
        
        # Sort free blocks by size (Best Fit algorithm)
        pool['free_blocks'].sort(key=lambda x: x['size'])
        
        allocated_blocks = []
        remaining_size = size
        
        # Try contiguous allocation first (Best Fit)
        for i, block in enumerate(pool['free_blocks']):
            if block['size'] >= size:
                # Perfect or larger fit found
                allocated_block = {
                    'job_id': job_id,
                    'start': block['start'],
                    'size': size
                }
                allocated_blocks.append(allocated_block)
                pool['allocated_blocks'].append(allocated_block)
                
                # Update free block
                if block['size'] == size:
                    pool['free_blocks'].pop(i)
                else:
                    block['start'] += size
                    block['size'] -= size
                    
                self._recalculate_fragmentation(gpu_id)
                return {'success': True, 'blocks': allocated_blocks}
                
        # If we reach here, we need to do scatter allocation (virtual memory mapping)
        # This is more complex and less performant, but prevents OOM on fragmented memory
        if sum(b['size'] for b in pool['free_blocks']) >= size:
            # We have enough total memory, just fragmented
            blocks_to_remove = []
            
            for i, block in enumerate(pool['free_blocks']):
                if remaining_size <= 0:
                    break
                    
                take_size = min(block['size'], remaining_size)
                
                allocated_block = {
                    'job_id': job_id,
                    'start': block['start'],
                    'size': take_size
                }
                allocated_blocks.append(allocated_block)
                pool['allocated_blocks'].append(allocated_block)
                
                if take_size == block['size']:
                    blocks_to_remove.append(i)
                else:
                    block['start'] += take_size
                    block['size'] -= take_size
                    
                remaining_size -= take_size
                
            # Remove fully utilized free blocks (in reverse order to not mess up indices)
            for i in reversed(blocks_to_remove):
                pool['free_blocks'].pop(i)
                
            self._recalculate_fragmentation(gpu_id)
            return {'success': True, 'blocks': allocated_blocks, 'fragmented': True}
            
        return {'success': False}
        
    def release_resources(self, job_id: str) -> bool:
        """Release resources when a job is complete"""
        with self.lock:
            if job_id not in self.active_jobs:
                return False
                
            job = self.active_jobs[job_id]
            gpu_id = job['gpu_id']
            pool = self.gpu_memory_pools[gpu_id]
            
            # Find and remove allocated blocks
            blocks_to_free = []
            new_allocated = []
            
            for block in pool['allocated_blocks']:
                if block['job_id'] == job_id:
                    blocks_to_free.append({'start': block['start'], 'size': block['size']})
                else:
                    new_allocated.append(block)
                    
            pool['allocated_blocks'] = new_allocated
            
            # Add back to free blocks and merge adjacent
            pool['free_blocks'].extend(blocks_to_free)
            self._merge_free_blocks(gpu_id)
            
            # Update GPU state
            for i, gpu in enumerate(self.gpu_devices):
                if gpu['id'] == gpu_id:
                    self.gpu_devices[i]['free_memory'] += job['memory_allocated']
                    self.gpu_devices[i]['utilization'] = max(0.0, self.gpu_devices[i]['utilization'] - (job['compute_allocated'] * 0.1))
                    
                    if self.gpu_devices[i]['utilization'] <= 0.05:
                        self.gpu_devices[i]['status'] = 'idle'
                    break
                    
            # Update metrics
            self.resource_metrics['jobs_processed'] += 1
            if job['status'] == 'failed':
                self.resource_metrics['failed_jobs'] += 1
                
            del self.active_jobs[job_id]
            self._update_metrics()
            
            return True
            
    def _merge_free_blocks(self, gpu_id: int):
        """Merge adjacent free memory blocks to reduce fragmentation"""
        pool = self.gpu_memory_pools[gpu_id]
        if len(pool['free_blocks']) <= 1:
            return
            
        # Sort by start address
        pool['free_blocks'].sort(key=lambda x: x['start'])
        
        merged = [pool['free_blocks'][0]]
        for current in pool['free_blocks'][1:]:
            previous = merged[-1]
            # Check if adjacent
            if previous['start'] + previous['size'] == current['start']:
                previous['size'] += current['size']
            else:
                merged.append(current)
                
        pool['free_blocks'] = merged
        self._recalculate_fragmentation(gpu_id)
        
    def _recalculate_fragmentation(self, gpu_id: int):
        """Calculate memory fragmentation index (0.0 to 1.0)"""
        pool = self.gpu_memory_pools[gpu_id]
        if not pool['free_blocks']:
            pool['fragmentation'] = 0.0
            return
            
        total_free = sum(b['size'] for b in pool['free_blocks'])
        if total_free == 0:
            pool['fragmentation'] = 0.0
            return
            
        max_block = max(b['size'] for b in pool['free_blocks'])
        
        # Fragmentation is high if the largest free block is much smaller than total free memory
        pool['fragmentation'] = 1.0 - (max_block / total_free)
        
    async def _attempt_memory_defragmentation(self) -> bool:
        """Attempt to defragment GPU memory by moving active allocations"""
        # In a real scenario, this involves pausing kernels and cudaMemcpyDeviceToDevice
        # Here we simulate the process if fragmentation is above threshold
        
        defrag_occurred = False
        for gpu_id, pool in self.gpu_memory_pools.items():
            if pool['fragmentation'] > self.config['memory_fragmentation_threshold']:
                logger.info(f"Defragmenting GPU {gpu_id} (frag: {pool['fragmentation']:.2f})")
                await asyncio.sleep(0.1) # Simulate defrag time
                
                # Simulate perfect defragmentation
                total_allocated = sum(b['size'] for b in pool['allocated_blocks'])
                
                # Rebuild blocks optimally
                new_allocated = []
                current_ptr = 0
                for block in pool['allocated_blocks']:
                    new_allocated.append({
                        'job_id': block['job_id'],
                        'start': current_ptr,
                        'size': block['size']
                    })
                    current_ptr += block['size']
                    
                pool['allocated_blocks'] = new_allocated
                
                gpu = next((g for g in self.gpu_devices if g['id'] == gpu_id), None)
                if gpu:
                    pool['free_blocks'] = [{
                        'start': total_allocated,
                        'size': gpu['total_memory'] - total_allocated
                    }]
                
                pool['fragmentation'] = 0.0
                defrag_occurred = True
                
        return defrag_occurred
        

    async def schedule_job(self, job_id: str, priority: int, memory_required: int, computation_complexity: float) -> bool:
        """Dynamic Priority Queue: Schedule a job and potentially preempt running jobs"""
        job_data = {
            'job_id': job_id,
            'priority': priority,
            'memory_required': memory_required,
            'computation_complexity': computation_complexity,
            'status': 'queued',
            'submitted_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Calculate scores and find best GPU
        best_gpu = -1
        best_score = -float('inf')
        
        for gpu_id, status in self.gpu_status.items():
            pool = self.gpu_memory_pools[gpu_id]
            available_mem = pool['total_memory'] - pool['allocated_memory']
            
            # Base score depends on memory availability
            if available_mem >= memory_required:
                score = (available_mem / pool['total_memory']) * 100
                if score > best_score:
                    best_score = score
                    best_gpu = gpu_id
                    
        # If we found a GPU with enough free memory, allocate directly
        if best_gpu >= 0:
            alloc_result = self._allocate_memory(best_gpu, memory_required, job_id)
            if alloc_result['success']:
                job_data['status'] = 'running'
                job_data['gpu_id'] = best_gpu
                job_data['memory_allocated'] = memory_required
                self.active_jobs[job_id] = job_data
                return True
                
        # If no GPU is available, try to preempt lower priority jobs
        logger.info(f"No GPU has {memory_required}MB free for job {job_id}. Attempting preemption...")
        preempt_success = await self._preempt_low_priority_jobs(priority, memory_required)
        
        if preempt_success:
            # We successfully preempted, now we should be able to allocate
            for gpu_id, pool in self.gpu_memory_pools.items():
                if (pool['total_memory'] - pool['allocated_memory']) >= memory_required:
                    alloc_result = self._allocate_memory(gpu_id, memory_required, job_id)
                    if alloc_result['success']:
                        job_data['status'] = 'running'
                        job_data['gpu_id'] = gpu_id
                        job_data['memory_allocated'] = memory_required
                        self.active_jobs[job_id] = job_data
                        return True
                        
        logger.warning(f"Job {job_id} remains queued. Insufficient resources even after preemption.")
        return False

    async def _preempt_low_priority_jobs(self, incoming_priority: int, required_memory: int) -> bool:
        """Preempt lower priority jobs to make room for higher priority ones"""
        preemptable_jobs = []
        for job_id, job in self.active_jobs.items():
            if job['priority'] < incoming_priority:
                preemptable_jobs.append((job_id, job))
                
        # Sort by priority (lowest first) then memory (largest first)
        preemptable_jobs.sort(key=lambda x: (x[1]['priority'], -x[1]['memory_allocated']))
        
        freed_memory = 0
        jobs_to_preempt = []
        
        for job_id, job in preemptable_jobs:
            jobs_to_preempt.append(job_id)
            freed_memory += job['memory_allocated']
            if freed_memory >= required_memory:
                break
                
        if freed_memory >= required_memory:
            # Preempt the jobs
            for job_id in jobs_to_preempt:
                logger.info(f"Preempting low priority job {job_id} for higher priority request")
                # In real scenario, would save state/checkpoint before killing
                self.release_resources(job_id)
                
                # Notify job owner (simulated)
                # event_bus.publish('job_preempted', {'job_id': job_id})
                
            return True
            
        return False
        
    def _update_metrics(self):
        """Update overall system metrics"""
        total_util = 0.0
        total_mem_util = 0.0
        
        for gpu in self.gpu_devices:
            mem_util = 1.0 - (gpu['free_memory'] / gpu['total_memory'])
            total_mem_util += mem_util
            total_util += gpu['utilization']
            
            # Simulate dynamic temperature and power based on utilization
            if self.simulation_mode:
                target_temp = 35.0 + (gpu['utilization'] * 50.0)
                gpu['temperature'] = gpu['temperature'] * 0.9 + target_temp * 0.1
                
                target_power = 20.0 + (gpu['utilization'] * (gpu['power_limit'] - 20.0))
                gpu['power_draw'] = gpu['power_draw'] * 0.8 + target_power * 0.2
        
        n_gpus = len(self.gpu_devices)
        if n_gpus > 0:
            self.resource_metrics['compute_utilization'] = total_util / n_gpus
            self.resource_metrics['memory_utilization'] = total_mem_util / n_gpus
            self.resource_metrics['total_utilization'] = (self.resource_metrics['compute_utilization'] + self.resource_metrics['memory_utilization']) / 2
            
            # Calculate energy efficiency (flops per watt approx)
            total_power = sum(g['power_draw'] for g in self.gpu_devices)
            if total_power > 0:
                self.resource_metrics['energy_efficiency'] = (self.resource_metrics['compute_utilization'] * 100) / total_power
                
    def get_system_status(self) -> Dict[str, Any]:
        """Get current system status and metrics"""
        with self.lock:
            self._update_metrics()
            
            devices_info = []
            for gpu in self.gpu_devices:
                pool = self.gpu_memory_pools[gpu['id']]
                devices_info.append({
                    'id': gpu['id'],
                    'name': gpu['name'],
                    'utilization': round(gpu['utilization'] * 100, 2),
                    'memory_used_gb': round((gpu['total_memory'] - gpu['free_memory']) / (1024**3), 2),
                    'memory_total_gb': round(gpu['total_memory'] / (1024**3), 2),
                    'temperature_c': round(gpu['temperature'], 1),
                    'power_draw_w': round(gpu['power_draw'], 1),
                    'status': gpu['status'],
                    'fragmentation': round(pool['fragmentation'] * 100, 2)
                })
                
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'active_jobs': len(self.active_jobs),
                'metrics': {
                    'overall_utilization_pct': round(self.resource_metrics['total_utilization'] * 100, 2),
                    'compute_utilization_pct': round(self.resource_metrics['compute_utilization'] * 100, 2),
                    'memory_utilization_pct': round(self.resource_metrics['memory_utilization'] * 100, 2),
                    'energy_efficiency_score': round(self.resource_metrics['energy_efficiency'], 4),
                    'jobs_processed_total': self.resource_metrics['jobs_processed']
                },
                'devices': devices_info
            }

# Example usage function
async def optimize_marketplace_batch(jobs: List[Dict[str, Any]]):
    """Process a batch of marketplace jobs through the optimizer"""
    optimizer = MarketplaceGPUOptimizer()
    
    results = []
    for job in jobs:
        res = await optimizer.optimize_resource_allocation(job)
        results.append(res)
        
    return results, optimizer.get_system_status()
