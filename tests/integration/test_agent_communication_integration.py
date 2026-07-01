"""
Integration tests for Advanced Agent Communication features
Tests message protocols, encryption, workflow orchestration, and discovery
"""

import asyncio
from datetime import UTC, datetime

import pytest

pytest.skip("Legacy agent communication modules removed in context refactor", allow_module_level=True)


class TestMessageEncryption:
    """Test message encryption and decryption"""

    @pytest.mark.asyncio
    async def test_key_pair_generation(self):
        """Test RSA key pair generation"""
        from app.encryption import get_encryptor

        encryptor = get_encryptor()
        key_pair = encryptor.generate_key_pair("test_agent_001")

        assert key_pair.agent_id == "test_agent_001"
        assert key_pair.public_key is not None
        assert key_pair.private_key is not None
        assert len(key_pair.key_id) > 0

    @pytest.mark.asyncio
    async def test_message_encryption_decryption(self):
        """Test end-to-end message encryption and decryption"""
        from app.encryption import get_encryptor

        encryptor = get_encryptor()

        # Generate key pairs for sender and recipient
        encryptor.generate_key_pair("agent_sender")
        encryptor.generate_key_pair("agent_recipient")

        # Encrypt message
        message = {"content": "Hello, world!", "timestamp": datetime.now(UTC).isoformat()}
        encrypted = encryptor.encrypt_message(message=message, sender_id="agent_sender", recipient_id="agent_recipient")

        assert encrypted is not None
        assert encrypted.ciphertext is not None
        assert encrypted.sender_id == "agent_sender"

        # Decrypt message
        decrypted = encryptor.decrypt_message(encrypted, "agent_recipient")

        assert decrypted is not None
        assert decrypted["content"] == "Hello, world!"

    @pytest.mark.asyncio
    async def test_signature_verification(self):
        """Test message signature verification"""
        from app.encryption import get_encryptor

        encryptor = get_encryptor()

        # Generate key pairs
        encryptor.generate_key_pair("agent_sender")
        encryptor.generate_key_pair("agent_recipient")

        # Encrypt and sign message
        message = {"content": "Signed message", "timestamp": datetime.now(UTC).isoformat()}
        encrypted = encryptor.encrypt_message(message=message, sender_id="agent_sender", recipient_id="agent_recipient")

        # Verify signature
        verified = encryptor.verify_signature(encrypted, "agent_sender")
        assert verified is True


class TestWorkflowOrchestration:
    """Test workflow orchestration engine"""

    @pytest.mark.asyncio
    async def test_workflow_creation(self):
        """Test workflow definition creation"""
        from app.workflow import get_orchestrator

        orchestrator = get_orchestrator()
        await orchestrator.start()

        steps = [
            {"agent_id": "agent_001", "action": "transcribe", "parameters": {"model": "whisper"}, "dependencies": []},
            {
                "agent_id": "agent_002",
                "action": "translate",
                "parameters": {"target_lang": "en"},
                "dependencies": ["wf_step_0"],
            },
        ]

        workflow = await orchestrator.create_workflow(name="test_workflow", steps=steps, created_by="test_user")

        assert workflow.workflow_id is not None
        assert workflow.name == "test_workflow"
        assert len(workflow.steps) == 2

        await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_workflow_execution(self):
        """Test workflow execution"""
        from app.workflow import WorkflowStatus, get_orchestrator

        orchestrator = get_orchestrator()
        await orchestrator.start()

        # Create workflow
        steps = [{"agent_id": "agent_001", "action": "test_action", "parameters": {}, "dependencies": []}]

        workflow = await orchestrator.create_workflow(name="execution_test", steps=steps, created_by="test_user")

        # Execute workflow
        execution = await orchestrator.execute_workflow(
            workflow_id=workflow.workflow_id, input_parameters={"test_input": "value"}
        )

        assert execution.execution_id is not None
        assert execution.status in [
            "running",
            "WorkflowStatus.RUNNING",
            WorkflowStatus.RUNNING,
            "pending",
            "WorkflowStatus.PENDING",
            WorkflowStatus.PENDING,
        ]
        assert execution.workflow_id == workflow.workflow_id

        # Wait for execution to start
        await asyncio.sleep(0.5)

        # Check status after execution starts
        status = await orchestrator.get_execution_status(execution.execution_id)
        assert status is not None
        assert status.status in [
            "completed",
            "running",
            "WorkflowStatus.COMPLETED",
            "WorkflowStatus.RUNNING",
            WorkflowStatus.COMPLETED,
            WorkflowStatus.RUNNING,
        ]

        await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_workflow_cancellation(self):
        """Test workflow cancellation"""
        from app.workflow import WorkflowStatus, get_orchestrator

        orchestrator = get_orchestrator()
        await orchestrator.start()

        # Create and execute workflow
        steps = [{"agent_id": "agent_001", "action": "long_task", "parameters": {}, "dependencies": []}]
        workflow = await orchestrator.create_workflow("cancel_test", steps, "test_user")
        execution = await orchestrator.execute_workflow(workflow.workflow_id)

        # Cancel execution
        cancelled = await orchestrator.cancel_execution(execution.execution_id)
        assert cancelled is True

        # Verify cancellation
        status = await orchestrator.get_execution_status(execution.execution_id)
        assert status.status == WorkflowStatus.CANCELLED

        await orchestrator.stop()


class TestAgentDiscovery:
    """Test agent capability discovery"""

    @pytest.mark.asyncio
    async def test_agent_registration_and_discovery(self):
        """Test agent registration and discovery by capability"""
        from app.routing.agent_discovery import AgentInfo, AgentRegistry, AgentStatus, AgentType

        registry = AgentRegistry()
        await registry.start()

        # Register agents
        agent1 = AgentInfo(
            agent_id="agent_001",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["whisper", "transcription"],
            services=["transcribe"],
            endpoints={"http": "http://localhost:8001"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
        )

        agent2 = AgentInfo(
            agent_id="agent_002",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["ollama", "inference"],
            services=["inference"],
            endpoints={"http": "http://localhost:8002"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
        )

        await registry.register_agent(agent1)
        await registry.register_agent(agent2)

        # Discover by capability
        whisper_agents = await registry.discover_agents({"capabilities": ["whisper"]})
        assert len(whisper_agents) == 1
        assert whisper_agents[0].agent_id == "agent_001"

        # Discover by service
        inference_agents = await registry.get_agents_by_service("inference")
        assert len(inference_agents) == 1
        assert inference_agents[0].agent_id == "agent_002"

        await registry.stop()


class TestMessageProtocols:
    """Test structured message protocols"""

    @pytest.mark.asyncio
    async def test_request_response_pattern(self):
        """Test request/response message pattern"""
        from app.protocols.communication import AgentMessage, CommunicationManager, MessageType, Priority, create_protocol

        comm_manager = CommunicationManager("agent_001")
        protocol = create_protocol("peer_to_peer", "agent_001")
        comm_manager.add_protocol("p2p", protocol)

        # Create request message
        request = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.DIRECT,
            priority=Priority.NORMAL,
            payload={"action": "get_status"},
        )

        assert request.message_type == MessageType.DIRECT
        assert request.priority == Priority.NORMAL

    @pytest.mark.asyncio
    async def test_broadcast_protocol(self):
        """Test broadcast message protocol"""
        from app.protocols.communication import BroadcastProtocol

        broadcast = BroadcastProtocol("agent_001", "global")

        # Subscribe agents
        await broadcast.subscribe("agent_002")
        await broadcast.subscribe("agent_003")

        assert len(broadcast.subscribers) == 2
        assert "agent_002" in broadcast.subscribers

        # Unsubscribe
        await broadcast.unsubscribe("agent_002")
        assert len(broadcast.subscribers) == 1

    @pytest.mark.asyncio
    async def test_message_ttl(self):
        """Test message TTL and expiry"""
        from app.protocols.communication import AgentMessage, MessageType, Priority

        # Create message with short TTL
        message = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.DIRECT,
            priority=Priority.NORMAL,
            payload={"data": "test"},
            ttl=1,  # 1 second TTL
        )

        # Check if expired (simulate time passing)
        from datetime import timedelta

        message.timestamp = datetime.now(UTC) - timedelta(seconds=2)

        # The protocol would check this during receive_message
        age = (datetime.now(UTC) - message.timestamp).total_seconds()
        assert age > message.ttl  # Message should be expired


class TestMessagePriorityQueue:
    """Test message queue with priority"""

    @pytest.mark.asyncio
    async def test_priority_levels(self):
        """Test message priority levels"""
        from app.protocols.communication import Priority

        # Test priority ordering
        priorities = [Priority.LOW, Priority.NORMAL, Priority.HIGH, Priority.CRITICAL]

        # Create messages with different priorities
        messages = []
        for i, priority in enumerate(priorities):
            from app.protocols.communication import AgentMessage, MessageType

            msg = AgentMessage(
                sender_id=f"agent_{i}",
                receiver_id="agent_target",
                message_type=MessageType.DIRECT,
                priority=priority,
                payload={"index": i},
            )
            messages.append(msg)

        # Verify priorities
        assert messages[0].priority == Priority.LOW
        assert messages[3].priority == Priority.CRITICAL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
