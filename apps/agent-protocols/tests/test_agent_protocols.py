#!/usr/bin/env python3
"""
Test suite for AITBC Agent Protocols
"""

import unittest
import asyncio
import json
import tempfile
import os
from datetime import datetime

# Add parent directory to path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.message_protocol import MessageProtocol, MessageTypes, AgentMessageClient
from src.task_manager import TaskManager, TaskStatus, TaskPriority

class TestMessageProtocol(unittest.TestCase):
    """Test message protocol functionality"""
    
    def setUp(self):
        self.protocol = MessageProtocol()
        self.sender_id = "agent-001"
        self.receiver_id = "agent-002"
    
    def test_message_creation(self):
        """Test message creation"""
        message = self.protocol.create_message(
            sender_id=self.sender_id,
            receiver_id=self.receiver_id,
            message_type=MessageTypes.TASK_ASSIGNMENT,
            payload={"task": "test_task", "data": "test_data"}
        )
        
        self.assertEqual(message["sender_id"], self.sender_id)
        self.assertEqual(message["receiver_id"], self.receiver_id)
        self.assertEqual(message["message_type"], MessageTypes.TASK_ASSIGNMENT)
        self.assertIsNotNone(message["signature"])
    
    def test_message_verification(self):
        """Test message verification"""
        message = self.protocol.create_message(
            sender_id=self.sender_id,
            receiver_id=self.receiver_id,
            message_type=MessageTypes.TASK_ASSIGNMENT,
            payload={"task": "test_task"}
        )
        
        # Valid message should verify
        self.assertTrue(self.protocol.verify_message(message))
        
        # Tampered message should not verify
        message["payload"] = "tampered"
        self.assertFalse(self.protocol.verify_message(message))
    
    def test_message_encryption(self):
        """Test message encryption/decryption"""
        original_payload = {"sensitive": "data", "numbers": [1, 2, 3]}
        
        message = self.protocol.create_message(
            sender_id=self.sender_id,
            receiver_id=self.receiver_id,
            message_type=MessageTypes.DATA_RESPONSE,
            payload=original_payload
        )
        
        # Decrypt message
        decrypted = self.protocol.decrypt_message(message)
        
        self.assertEqual(decrypted["payload"], original_payload)
    
    def test_message_queueing(self):
        """Test message queuing and delivery"""
        message = self.protocol.create_message(
            sender_id=self.sender_id,
            receiver_id=self.receiver_id,
            message_type=MessageTypes.HEARTBEAT,
            payload={"status": "active"}
        )
        
        # Send message
        success = self.protocol.send_message(message)
        self.assertTrue(success)
        
        # Receive message
        messages = self.protocol.receive_messages(self.receiver_id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["message_type"], MessageTypes.HEARTBEAT)

class TestTaskManager(unittest.TestCase):
    """Test task manager functionality"""
    
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        self.task_manager = TaskManager(self.temp_db.name)
    
    def tearDown(self):
        os.unlink(self.temp_db.name)
    
    def test_task_creation(self):
        """Test task creation"""
        task = self.task_manager.create_task(
            task_type="market_analysis",
            payload={"symbol": "AITBC/BTC"},
            required_capabilities=["market_data", "analysis"],
            priority=TaskPriority.HIGH
        )
        
        self.assertIsNotNone(task.id)
        self.assertEqual(task.task_type, "market_analysis")
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.priority, TaskPriority.HIGH)
    
    def test_task_assignment(self):
        """Test task assignment"""
        task = self.task_manager.create_task(
            task_type="trading",
            payload={"symbol": "AITBC/BTC", "side": "buy"},
            required_capabilities=["trading", "market_access"]
        )
        
        success = self.task_manager.assign_task(task.id, "agent-001")
        self.assertTrue(success)
        
        # Verify assignment
        updated_task = self.task_manager.get_agent_tasks("agent-001")[0]
        self.assertEqual(updated_task.id, task.id)
        self.assertEqual(updated_task.assigned_agent_id, "agent-001")
        self.assertEqual(updated_task.status, TaskStatus.ASSIGNED)
    
    def test_task_completion(self):
        """Test task completion"""
        task = self.task_manager.create_task(
            task_type="compliance_check",
            payload={"user_id": "user001"},
            required_capabilities=["compliance"]
        )
        
        # Assign and start task
        self.task_manager.assign_task(task.id, "agent-002")
        self.task_manager.start_task(task.id)
        
        # Complete task
        result = {"status": "passed", "checks": ["kyc", "aml"]}
        success = self.task_manager.complete_task(task.id, result)
        self.assertTrue(success)
        
        # Verify completion
        completed_task = self.task_manager.get_agent_tasks("agent-002")[0]
        self.assertEqual(completed_task.status, TaskStatus.COMPLETED)
        self.assertEqual(completed_task.result, result)
    
    def test_task_statistics(self):
        """Test task statistics"""
        # Create multiple tasks
        for i in range(5):
            self.task_manager.create_task(
                task_type=f"task_{i}",
                payload={"index": i},
                required_capabilities=["basic"]
            )
        
        stats = self.task_manager.get_task_statistics()
        
        self.assertIn("task_counts", stats)
        self.assertIn("agent_statistics", stats)
        self.assertEqual(stats["task_counts"]["pending"], 5)

class TestAgentMessageClient(unittest.TestCase):
    """Test agent message client"""
    
    def setUp(self):
        self.client = AgentMessageClient("agent-001", "http://localhost:8003")
    
    def test_task_assignment_message(self):
        """Test task assignment message creation"""
        task_data = {"task": "test_task", "parameters": {"param1": "value1"}}
        
        success = self.client.send_task_assignment("agent-002", task_data)
        self.assertTrue(success)
        
        # Check message queue
        messages = self.client.receive_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["message_type"], MessageTypes.TASK_ASSIGNMENT)
    
    def test_coordination_message(self):
        """Test coordination message"""
        coordination_data = {"action": "coordinate", "details": {"target": "goal"}}
        
        success = self.client.send_coordination_message("agent-003", coordination_data)
        self.assertTrue(success)
        
        # Check message queue
        messages = self.client.get_coordination_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["message_type"], MessageTypes.COORDINATION)

if __name__ == "__main__":
    unittest.main()
