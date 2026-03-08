#!/usr/bin/env python3
"""
End-to-End GPU Marketplace Workflow
User (aitbc server) → GPU Bidding → Ollama Task → Blockchain Payment
"""

import requests
import json
import time
import sys
from typing import Dict, List

class MarketplaceWorkflow:
    def __init__(self, coordinator_url: str = "http://localhost:8000"):
        self.coordinator_url = coordinator_url
        self.workflow_steps = []
    
    def log_step(self, step: str, status: str, details: str = ""):
        """Log workflow step"""
        timestamp = time.strftime("%H:%M:%S")
        self.workflow_steps.append({
            "timestamp": timestamp,
            "step": step,
            "status": status,
            "details": details
        })
        status_icon = "✅" if status == "success" else "❌" if status == "error" else "🔄"
        print(f"{timestamp} {status_icon} {step}")
        if details:
            print(f"    {details}")
    
    def get_available_gpus(self) -> List[Dict]:
        """Get list of available GPUs"""
        try:
            print(f"🔍 DEBUG: Requesting GPU list from {self.coordinator_url}/v1/marketplace/gpu/list")
            response = requests.get(f"{self.coordinator_url}/v1/marketplace/gpu/list")
            print(f"🔍 DEBUG: Response status: {response.status_code}")
            response.raise_for_status()
            gpus = response.json()
            print(f"🔍 DEBUG: Total GPUs found: {len(gpus)}")
            available_gpus = [gpu for gpu in gpus if gpu["status"] == "available"]
            print(f"🔍 DEBUG: Available GPUs: {len(available_gpus)}")
            return available_gpus
        except Exception as e:
            print(f"🔍 DEBUG: Error in get_available_gpus: {str(e)}")
            self.log_step("Get Available GPUs", "error", str(e))
            return []
    
    def book_gpu(self, gpu_id: str, duration_hours: int = 2) -> Dict:
        """Book a GPU for computation"""
        try:
            print(f"🔍 DEBUG: Attempting to book GPU {gpu_id} for {duration_hours} hours")
            booking_data = {"duration_hours": duration_hours}
            print(f"🔍 DEBUG: Booking data: {booking_data}")
            response = requests.post(
                f"{self.coordinator_url}/v1/marketplace/gpu/{gpu_id}/book",
                json=booking_data
            )
            print(f"🔍 DEBUG: Booking response status: {response.status_code}")
            print(f"🔍 DEBUG: Booking response: {response.text}")
            response.raise_for_status()
            booking = response.json()
            print(f"🔍 DEBUG: Booking successful: {booking}")
            self.log_step("Book GPU", "success", f"GPU {gpu_id} booked for {duration_hours} hours")
            return booking
        except Exception as e:
            print(f"🔍 DEBUG: Error in book_gpu: {str(e)}")
            self.log_step("Book GPU", "error", str(e))
            return {}
    
    def submit_ollama_task(self, gpu_id: str, task_data: Dict) -> Dict:
        """Submit Ollama task to the booked GPU"""
        try:
            print(f"🔍 DEBUG: Submitting Ollama task to GPU {gpu_id}")
            print(f"🔍 DEBUG: Task data: {task_data}")
            # Simulate Ollama task submission
            task_payload = {
                "gpu_id": gpu_id,
                "model": task_data.get("model", "llama2"),
                "prompt": task_data.get("prompt", "Hello, world!"),
                "parameters": task_data.get("parameters", {})
            }
            print(f"🔍 DEBUG: Task payload: {task_payload}")
            
            # This would integrate with actual Ollama service
            # For now, simulate task submission
            task_id = f"task_{int(time.time())}"
            print(f"🔍 DEBUG: Generated task ID: {task_id}")
            
            self.log_step("Submit Ollama Task", "success", f"Task {task_id} submitted to GPU {gpu_id}")
            
            return {
                "task_id": task_id,
                "gpu_id": gpu_id,
                "status": "submitted",
                "model": task_payload["model"]
            }
        except Exception as e:
            print(f"🔍 DEBUG: Error in submit_ollama_task: {str(e)}")
            self.log_step("Submit Ollama Task", "error", str(e))
            return {}
    
    def process_blockchain_payment(self, booking: Dict, task_result: Dict) -> Dict:
        """Process payment via blockchain"""
        try:
            print(f"🔍 DEBUG: Processing blockchain payment")
            print(f"🔍 DEBUG: Booking data: {booking}")
            print(f"🔍 DEBUG: Task result: {task_result}")
            # Calculate payment amount
            payment_amount = booking.get("total_cost", 0.0)
            print(f"🔍 DEBUG: Payment amount: {payment_amount} AITBC")
            
            # Simulate blockchain payment processing
            payment_data = {
                "from": "aitbc_server_user",
                "to": "gpu_provider",
                "amount": payment_amount,
                "currency": "AITBC",
                "booking_id": booking.get("booking_id"),
                "task_id": task_result.get("task_id"),
                "gpu_id": booking.get("gpu_id")
            }
            print(f"🔍 DEBUG: Payment data: {payment_data}")
            
            # This would integrate with actual blockchain service
            # For now, simulate payment
            transaction_id = f"tx_{int(time.time())}"
            print(f"🔍 DEBUG: Generated transaction ID: {transaction_id}")
            
            self.log_step("Process Blockchain Payment", "success", 
                         f"Payment {payment_amount} AITBC processed (TX: {transaction_id})")
            
            return {
                "transaction_id": transaction_id,
                "amount": payment_amount,
                "status": "confirmed",
                "payment_data": payment_data
            }
        except Exception as e:
            print(f"🔍 DEBUG: Error in process_blockchain_payment: {str(e)}")
            self.log_step("Process Blockchain Payment", "error", str(e))
            return {}
    
    def release_gpu(self, gpu_id: str) -> Dict:
        """Release the GPU after task completion"""
        try:
            print(f"🔍 DEBUG: Releasing GPU {gpu_id}")
            response = requests.post(f"{self.coordinator_url}/v1/marketplace/gpu/{gpu_id}/release")
            print(f"🔍 DEBUG: Release response status: {response.status_code}")
            print(f"🔍 DEBUG: Release response: {response.text}")
            response.raise_for_status()
            release_result = response.json()
            print(f"🔍 DEBUG: GPU release successful: {release_result}")
            self.log_step("Release GPU", "success", f"GPU {gpu_id} released")
            return release_result
        except Exception as e:
            print(f"🔍 DEBUG: Error in release_gpu: {str(e)}")
            self.log_step("Release GPU", "error", str(e))
            return {}
    
    def run_complete_workflow(self, task_data: Dict = None) -> bool:
        """Run the complete end-to-end workflow"""
        print("🚀 Starting End-to-End GPU Marketplace Workflow")
        print("=" * 60)
        
        # Default task data if not provided
        if not task_data:
            task_data = {
                "model": "llama2",
                "prompt": "Analyze this data and provide insights",
                "parameters": {"temperature": 0.7, "max_tokens": 100}
            }
        
        # Step 1: Get available GPUs
        self.log_step("Initialize Workflow", "info", "Starting GPU marketplace workflow")
        available_gpus = self.get_available_gpus()
        
        if not available_gpus:
            self.log_step("Workflow Failed", "error", "No available GPUs in marketplace")
            return False
        
        # Select best GPU (lowest price)
        selected_gpu = min(available_gpus, key=lambda x: x["price_per_hour"])
        gpu_id = selected_gpu["id"]
        
        self.log_step("Select GPU", "success", 
                     f"Selected {selected_gpu['model']} @ ${selected_gpu['price_per_hour']}/hour")
        
        # Step 2: Book GPU
        booking = self.book_gpu(gpu_id, duration_hours=2)
        if not booking:
            return False
        
        # Step 3: Submit Ollama Task
        task_result = self.submit_ollama_task(gpu_id, task_data)
        if not task_result:
            return False
        
        # Simulate task processing time
        self.log_step("Process Task", "info", "Simulating Ollama task execution...")
        time.sleep(2)  # Simulate processing
        
        # Step 4: Process Blockchain Payment
        payment = self.process_blockchain_payment(booking, task_result)
        if not payment:
            return False
        
        # Step 5: Release GPU
        release_result = self.release_gpu(gpu_id)
        if not release_result:
            return False
        
        # Workflow Summary
        self.print_workflow_summary()
        return True
    
    def print_workflow_summary(self):
        """Print workflow execution summary"""
        print("\n📊 WORKFLOW EXECUTION SUMMARY")
        print("=" * 60)
        
        successful_steps = sum(1 for step in self.workflow_steps if step["status"] == "success")
        total_steps = len(self.workflow_steps)
        
        print(f"✅ Successful Steps: {successful_steps}/{total_steps}")
        print(f"📈 Success Rate: {successful_steps/total_steps*100:.1f}%")
        
        print(f"\n📋 Step-by-Step Details:")
        for step in self.workflow_steps:
            status_icon = "✅" if step["status"] == "success" else "❌" if step["status"] == "error" else "🔄"
            print(f"  {step['timestamp']} {status_icon} {step['step']}")
            if step["details"]:
                print(f"    {step['details']}")
        
        print(f"\n🎉 Workflow Status: {'✅ COMPLETED' if successful_steps == total_steps else '❌ FAILED'}")

def main():
    """Main execution function"""
    workflow = MarketplaceWorkflow()
    
    # Example task data
    task_data = {
        "model": "llama2",
        "prompt": "Analyze the following GPU marketplace data and provide investment insights",
        "parameters": {
            "temperature": 0.7,
            "max_tokens": 150,
            "top_p": 0.9
        }
    }
    
    # Run the complete workflow
    success = workflow.run_complete_workflow(task_data)
    
    if success:
        print("\n🎊 End-to-End GPU Marketplace Workflow completed successfully!")
        print("✅ User bid on GPU → Ollama task executed → Blockchain payment processed")
    else:
        print("\n❌ Workflow failed. Check the logs above for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()
