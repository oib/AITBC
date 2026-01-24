#!/usr/bin/env python3
"""AITBC GPU Mining Service"""

import subprocess
import time
import json
import random
from datetime import datetime
import threading

class AITBCMiner:
    def __init__(self):
        self.running = False
        self.jobs = []
        self.stats = {
            'total_jobs': 0,
            'completed_jobs': 0,
            'failed_jobs': 0,
            'hash_rate': 0,
            'uptime': 0
        }
        self.start_time = None
        
    def start_mining(self):
        """Start the mining service"""
        self.running = True
        self.start_time = time.time()
        print("🚀 AITBC Miner started")
        
        # Start mining threads
        mining_thread = threading.Thread(target=self._mining_loop)
        mining_thread.daemon = True
        mining_thread.start()
        
        # Start status monitoring
        monitor_thread = threading.Thread(target=self._monitor_gpu)
        monitor_thread.daemon = True
        monitor_thread.start()
    
    def stop_mining(self):
        """Stop the mining service"""
        self.running = False
        print("⛔ AITBC Miner stopped")
    
    def _mining_loop(self):
        """Main mining loop"""
        while self.running:
            # Simulate job processing
            if random.random() > 0.7:  # 30% chance of new job
                job = self._create_job()
                self.jobs.append(job)
                self._process_job(job)
            
            time.sleep(1)
    
    def _create_job(self):
        """Create a new mining job"""
        job_types = [
            'Matrix Computation',
            'Hash Validation',
            'Block Verification',
            'Transaction Processing',
            'AI Model Training'
        ]
        
        job = {
            'id': f"job_{int(time.time())}_{random.randint(1000, 9999)}",
            'name': random.choice(job_types),
            'progress': 0,
            'status': 'running',
            'created_at': datetime.now().isoformat()
        }
        
        self.stats['total_jobs'] += 1
        return job
    
    def _process_job(self, job):
        """Process a mining job"""
        processing_thread = threading.Thread(target=self._process_job_thread, args=(job,))
        processing_thread.daemon = True
        processing_thread.start()
    
    def _process_job_thread(self, job):
        """Process job in separate thread"""
        duration = random.randint(5, 30)
        steps = 20
        
        for i in range(steps + 1):
            if not self.running:
                break
                
            job['progress'] = int((i / steps) * 100)
            time.sleep(duration / steps)
        
        if self.running:
            job['status'] = 'completed' if random.random() > 0.05 else 'failed'
            job['completed_at'] = datetime.now().isoformat()
            
            if job['status'] == 'completed':
                self.stats['completed_jobs'] += 1
            else:
                self.stats['failed_jobs'] += 1
    
    def _monitor_gpu(self):
        """Monitor GPU status"""
        while self.running:
            try:
                # Get GPU utilization
                result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'], 
                                      capture_output=True, text=True)
                
                if result.returncode == 0:
                    gpu_util = int(result.stdout.strip())
                    # Simulate hash rate based on GPU utilization
                    self.stats['hash_rate'] = round(gpu_util * 0.5 + random.uniform(-5, 5), 1)
                
            except Exception as e:
                print(f"GPU monitoring error: {e}")
                self.stats['hash_rate'] = random.uniform(40, 60)
            
            # Update uptime
            if self.start_time:
                self.stats['uptime'] = int(time.time() - self.start_time)
            
            time.sleep(2)
    
    def get_status(self):
        """Get current mining status"""
        return {
            'running': self.running,
            'stats': self.stats.copy(),
            'active_jobs': [j for j in self.jobs if j['status'] == 'running'],
            'gpu_info': self._get_gpu_info()
        }
    
    def _get_gpu_info(self):
        """Get GPU information"""
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,utilization.gpu,temperature.gpu,power.draw,memory.used,memory.total', 
                                   '--format=csv,noheader,nounits'], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                values = result.stdout.strip().split(', ')
                return {
                    'name': values[0],
                    'utilization': int(values[1]),
                    'temperature': int(values[2]),
                    'power': float(values[3]),
                    'memory_used': float(values[4]),
                    'memory_total': float(values[5])
                }
        except:
            pass
        
        return {
            'name': 'NVIDIA GeForce RTX 4060 Ti',
            'utilization': 0,
            'temperature': 43,
            'power': 18,
            'memory_used': 2902,
            'memory_total': 16380
        }

# Global miner instance
miner = AITBCMiner()

if __name__ == "__main__":
    print("AITBC GPU Mining Service")
    print("=" * 40)
    
    try:
        miner.start_mining()
        
        # Keep running
        while True:
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        miner.stop_mining()
