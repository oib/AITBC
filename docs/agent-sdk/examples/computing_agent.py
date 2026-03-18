#!/usr/bin/env python3
"""
AITBC Agent SDK Example: Computing Agent
Demonstrates how to create an agent that provides computing services
"""

import asyncio
import logging
from typing import Dict, Any, List
from aitbc_agent_sdk import Agent, AgentConfig
from aitbc_agent_sdk.blockchain import BlockchainClient
from aitbc_agent_sdk.ai import AIModel
from aitbc_agent_sdk.computing import ComputingEngine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComputingAgentExample:
    """Example computing agent implementation"""
    
    def __init__(self):
        # Configure agent
        self.config = AgentConfig(
            name="computing-agent-example",
            blockchain_network="testnet",
            rpc_url="https://testnet-rpc.aitbc.net",
            ai_model="gpt-3.5-turbo",
            max_cpu_cores=4,
            max_memory_gb=8,
            max_gpu_count=1
        )
        
        # Initialize components
        self.agent = Agent(self.config)
        self.blockchain_client = BlockchainClient(self.config)
        self.computing_engine = ComputingEngine(self.config)
        self.ai_model = AIModel(self.config)
        
        # Agent state
        self.is_running = False
        self.active_tasks = {}
        
    async def start(self):
        """Start the computing agent"""
        logger.info("Starting computing agent...")
        
        # Register with network
        agent_address = await self.agent.register_with_network()
        logger.info(f"Agent registered at address: {agent_address}")
        
        # Register computing services
        await self.register_computing_services()
        
        # Start task processing loop
        self.is_running = True
        asyncio.create_task(self.task_processing_loop())
        
        logger.info("Computing agent started successfully!")
        
    async def stop(self):
        """Stop the computing agent"""
        logger.info("Stopping computing agent...")
        self.is_running = False
        await self.agent.stop()
        logger.info("Computing agent stopped")
        
    async def register_computing_services(self):
        """Register available computing services with the network"""
        services = [
            {
                "type": "neural_network_inference",
                "description": "Neural network inference with GPU acceleration",
                "price_per_hour": 0.1,
                "requirements": {"gpu": True, "memory_gb": 4}
            },
            {
                "type": "data_processing",
                "description": "Large-scale data processing and analysis",
                "price_per_hour": 0.05,
                "requirements": {"cpu_cores": 2, "memory_gb": 8}
            },
            {
                "type": "encryption_services",
                "description": "Cryptographic operations and data encryption",
                "price_per_hour": 0.02,
                "requirements": {"cpu_cores": 1}
            }
        ]
        
        for service in services:
            service_id = await self.blockchain_client.register_service(service)
            logger.info(f"Registered service: {service['type']} (ID: {service_id})")
            
    async def task_processing_loop(self):
        """Main loop for processing incoming tasks"""
        while self.is_running:
            try:
                # Check for new tasks
                tasks = await self.blockchain_client.get_available_tasks()
                
                for task in tasks:
                    if task.id not in self.active_tasks:
                        asyncio.create_task(self.process_task(task))
                        
                # Process active tasks
                await self.update_active_tasks()
                
                # Sleep before next iteration
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in task processing loop: {e}")
                await asyncio.sleep(10)
                
    async def process_task(self, task):
        """Process a single computing task"""
        logger.info(f"Processing task {task.id}: {task.type}")
        
        try:
            # Add to active tasks
            self.active_tasks[task.id] = {
                "status": "processing",
                "start_time": asyncio.get_event_loop().time(),
                "task": task
            }
            
            # Execute task based on type
            if task.type == "neural_network_inference":
                result = await self.process_neural_network_task(task)
            elif task.type == "data_processing":
                result = await self.process_data_task(task)
            elif task.type == "encryption_services":
                result = await self.process_encryption_task(task)
            else:
                raise ValueError(f"Unknown task type: {task.type}")
                
            # Submit result to blockchain
            await self.blockchain_client.submit_task_result(task.id, result)
            
            # Update task status
            self.active_tasks[task.id]["status"] = "completed"
            self.active_tasks[task.id]["result"] = result
            
            logger.info(f"Task {task.id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error processing task {task.id}: {e}")
            
            # Submit error result
            await self.blockchain_client.submit_task_result(
                task.id, 
                {"error": str(e), "status": "failed"}
            )
            
            # Update task status
            self.active_tasks[task.id]["status"] = "failed"
            self.active_tasks[task.id]["error"] = str(e)
            
    async def process_neural_network_task(self, task) -> Dict[str, Any]:
        """Process neural network inference task"""
        logger.info("Executing neural network inference...")
        
        # Load model from task data
        model_data = await self.blockchain_client.get_data(task.data_hash)
        model = self.ai_model.load_model(model_data)
        
        # Load input data
        input_data = await self.blockchain_client.get_data(task.input_data_hash)
        
        # Execute inference
        start_time = asyncio.get_event_loop().time()
        predictions = model.predict(input_data)
        execution_time = asyncio.get_event_loop().time() - start_time
        
        # Prepare result
        result = {
            "predictions": predictions.tolist(),
            "execution_time": execution_time,
            "model_info": {
                "type": model.model_type,
                "parameters": model.parameter_count
            },
            "agent_info": {
                "name": self.config.name,
                "address": self.agent.address
            }
        }
        
        return result
        
    async def process_data_task(self, task) -> Dict[str, Any]:
        """Process data analysis task"""
        logger.info("Executing data processing...")
        
        # Load data
        data = await self.blockchain_client.get_data(task.data_hash)
        
        # Process data based on task parameters
        processing_type = task.parameters.get("processing_type", "basic_analysis")
        
        if processing_type == "basic_analysis":
            result = self.computing_engine.basic_analysis(data)
        elif processing_type == "statistical_analysis":
            result = self.computing_engine.statistical_analysis(data)
        elif processing_type == "machine_learning":
            result = await self.computing_engine.machine_learning_analysis(data)
        else:
            raise ValueError(f"Unknown processing type: {processing_type}")
            
        # Add metadata
        result["metadata"] = {
            "data_size": len(data),
            "processing_time": result.get("execution_time", 0),
            "agent_address": self.agent.address
        }
        
        return result
        
    async def process_encryption_task(self, task) -> Dict[str, Any]:
        """Process encryption/decryption task"""
        logger.info("Executing encryption operations...")
        
        # Get operation type
        operation = task.parameters.get("operation", "encrypt")
        data = await self.blockchain_client.get_data(task.data_hash)
        
        if operation == "encrypt":
            result = self.computing_engine.encrypt_data(data, task.parameters)
        elif operation == "decrypt":
            result = self.computing_engine.decrypt_data(data, task.parameters)
        elif operation == "hash":
            result = self.computing_engine.hash_data(data, task.parameters)
        else:
            raise ValueError(f"Unknown operation: {operation}")
            
        # Add metadata
        result["metadata"] = {
            "operation": operation,
            "data_size": len(data),
            "agent_address": self.agent.address
        }
        
        return result
        
    async def update_active_tasks(self):
        """Update status of active tasks"""
        current_time = asyncio.get_event_loop().time()
        
        for task_id, task_info in list(self.active_tasks.items()):
            # Check for timeout (30 minutes)
            if current_time - task_info["start_time"] > 1800:
                logger.warning(f"Task {task_id} timed out")
                await self.blockchain_client.submit_task_result(
                    task_id,
                    {"error": "Task timeout", "status": "failed"}
                )
                del self.active_tasks[task_id]
                
    async def get_agent_status(self) -> Dict[str, Any]:
        """Get current agent status"""
        balance = await self.agent.get_balance()
        
        return {
            "name": self.config.name,
            "address": self.agent.address,
            "is_running": self.is_running,
            "balance": balance,
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len([
                t for t in self.active_tasks.values() 
                if t["status"] == "completed"
            ]),
            "failed_tasks": len([
                t for t in self.active_tasks.values() 
                if t["status"] == "failed"
            ])
        }

async def main():
    """Main function to run the computing agent example"""
    # Create agent
    agent = ComputingAgentExample()
    
    try:
        # Start agent
        await agent.start()
        
        # Keep running
        while True:
            # Print status every 30 seconds
            status = await agent.get_agent_status()
            logger.info(f"Agent status: {status}")
            await asyncio.sleep(30)
            
    except KeyboardInterrupt:
        logger.info("Shutting down agent...")
        await agent.stop()
    except Exception as e:
        logger.error(f"Agent error: {e}")
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
