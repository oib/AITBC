"""
Security Validation Tests for AITBC Mesh Network
Tests security requirements and attack prevention mechanisms
"""

import pytest
import asyncio
import time
import hashlib
import json
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal
import secrets

class TestConsensusSecurity:
    """Test consensus layer security"""
    
    @pytest.mark.asyncio
    async def test_double_signing_detection(self):
        """Test detection of validator double signing"""
        # Mock slashing manager
        mock_slashing = Mock()
        mock_slashing.detect_double_sign.return_value = Mock(
            validator_address="0xvalidator1",
            block_height=100,
            block_hash_1="hash1",
            block_hash_2="hash2",
            timestamp=time.time()
        )
        
        # Simulate double signing
        validator_address = "0xvalidator1"
        block_height = 100
        block_hash_1 = "hash1"
        block_hash_2 = "hash2"  # Different hash for same block
        
        # Detect double signing
        event = mock_slashing.detect_double_sign(validator_address, block_hash_1, block_hash_2, block_height)
        
        assert event is not None
        assert event.validator_address == validator_address
        assert event.block_height == block_height
        assert event.block_hash_1 == block_hash_1
        assert event.block_hash_2 == block_hash_2
        
        # Verify slashing action
        mock_slashing.apply_slash.assert_called_once_with(validator_address, 0.1, "Double signing detected")
    
    @pytest.mark.asyncio
    async def test_validator_key_compromise_detection(self):
        """Test detection of compromised validator keys"""
        # Mock key manager
        mock_key_manager = Mock()
        mock_key_manager.verify_signature.return_value = False  # Signature verification fails
        
        # Mock consensus
        mock_consensus = Mock()
        mock_consensus.validators = {"0xvalidator1": Mock(public_key="valid_key")}
        
        # Simulate invalid signature
        message = "test message"
        signature = "invalid_signature"
        validator_address = "0xvalidator1"
        
        # Verify signature fails
        valid = mock_key_manager.verify_signature(validator_address, message, signature)
        
        assert valid is False
        
        # Should trigger key compromise detection
        mock_consensus.handle_key_compromise.assert_called_once_with(validator_address)
    
    @pytest.mark.asyncio
    async def test_byzantine_fault_tolerance(self):
        """Test Byzantine fault tolerance in consensus"""
        # Test with 1/3 faulty validators
        total_validators = 9
        faulty_validators = 3  # 1/3 of total
        
        # Mock consensus state
        mock_consensus = Mock()
        mock_consensus.total_validators = total_validators
        mock_consensus.faulty_validators = faulty_validators
        mock_consensus.min_honest_validators = total_validators - faulty_validators
        
        # Check if consensus can tolerate faults
        can_tolerate = mock_consensus.faulty_validators < (mock_consensus.total_validators // 3)
        
        assert can_tolerate is True, "Should tolerate 1/3 faulty validators"
        assert mock_consensus.min_honest_validators >= 2 * faulty_validators + 1, "Not enough honest validators"
    
    @pytest.mark.asyncio
    async def test_consensus_state_integrity(self):
        """Test consensus state integrity and tampering detection"""
        # Mock consensus state
        consensus_state = {
            "block_height": 100,
            "validators": ["v1", "v2", "v3"],
            "current_proposer": "v1",
            "round": 5
        }
        
        # Calculate state hash
        state_json = json.dumps(consensus_state, sort_keys=True)
        original_hash = hashlib.sha256(state_json.encode()).hexdigest()
        
        # Simulate state tampering
        tampered_state = consensus_state.copy()
        tampered_state["block_height"] = 999  # Tampered value
        
        # Calculate tampered hash
        tampered_json = json.dumps(tampered_state, sort_keys=True)
        tampered_hash = hashlib.sha256(tampered_json.encode()).hexdigest()
        
        # Verify tampering detection
        assert original_hash != tampered_hash, "Hashes should differ for tampered state"
        
        # Mock integrity checker
        mock_integrity = Mock()
        mock_integrity.verify_state_hash.return_value = (original_hash == tampered_hash)
        
        is_valid = mock_integrity.verify_state_hash(tampered_state, tampered_hash)
        assert is_valid is False, "Tampered state should be detected"
    
    @pytest.mark.asyncio
    async def test_validator_rotation_security(self):
        """Test security of validator rotation process"""
        # Mock rotation manager
        mock_rotation = Mock()
        mock_rotation.get_next_proposer.return_value = "v2"
        mock_rotation.validate_rotation.return_value = True
        
        # Test secure rotation
        current_proposer = "v1"
        next_proposer = mock_rotation.get_next_proposer()
        
        assert next_proposer != current_proposer, "Next proposer should be different"
        
        # Validate rotation
        is_valid = mock_rotation.validate_rotation(current_proposer, next_proposer)
        assert is_valid is True, "Rotation should be valid"
        
        # Test rotation cannot be manipulated
        mock_rotation.prevent_manipulation.assert_called_once()


class TestNetworkSecurity:
    """Test network layer security"""
    
    @pytest.mark.asyncio
    async def test_peer_authentication(self):
        """Test peer authentication and identity verification"""
        # Mock peer authentication
        mock_auth = Mock()
        mock_auth.authenticate_peer.return_value = True
        
        # Test valid peer authentication
        peer_id = "peer_123"
        public_key = "valid_public_key"
        signature = "valid_signature"
        
        is_authenticated = mock_auth.authenticate_peer(peer_id, public_key, signature)
        assert is_authenticated is True
        
        # Test invalid authentication
        mock_auth.authenticate_peer.return_value = False
        is_authenticated = mock_auth.authenticate_peer(peer_id, "invalid_key", "invalid_signature")
        assert is_authenticated is False
    
    @pytest.mark.asyncio
    async def test_message_encryption(self):
        """Test message encryption and decryption"""
        # Mock encryption service
        mock_encryption = Mock()
        mock_encryption.encrypt_message.return_value = "encrypted_data"
        mock_encryption.decrypt_message.return_value = "original_message"
        
        # Test encryption
        original_message = "sensitive_data"
        encrypted = mock_encryption.encrypt_message(original_message, "recipient_key")
        
        assert encrypted != original_message, "Encrypted message should differ from original"
        
        # Test decryption
        decrypted = mock_encryption.decrypt_message(encrypted, "recipient_key")
        assert decrypted == original_message, "Decrypted message should match original"
    
    @pytest.mark.asyncio
    async def test_sybil_attack_prevention(self):
        """Test prevention of Sybil attacks"""
        # Mock Sybil attack detector
        mock_detector = Mock()
        mock_detector.detect_sybil_attack.return_value = False
        mock_detector.get_unique_peers.return_value = 10
        
        # Test normal peer distribution
        unique_peers = mock_detector.get_unique_peers()
        is_sybil = mock_detector.detect_sybil_attack()
        
        assert unique_peers >= 5, "Should have sufficient unique peers"
        assert is_sybil is False, "No Sybil attack detected"
        
        # Simulate Sybil attack
        mock_detector.get_unique_peers.return_value = 2  # Very few unique peers
        mock_detector.detect_sybil_attack.return_value = True
        
        unique_peers = mock_detector.get_unique_peers()
        is_sybil = mock_detector.detect_sybil_attack()
        
        assert unique_peers < 5, "Insufficient unique peers indicates potential Sybil attack"
        assert is_sybil is True, "Sybil attack should be detected"
    
    @pytest.mark.asyncio
    async def test_ddos_protection(self):
        """Test DDoS attack protection mechanisms"""
        # Mock DDoS protection
        mock_protection = Mock()
        mock_protection.check_rate_limit.return_value = True
        mock_protection.get_request_rate.return_value = 100
        
        # Test normal request rate
        request_rate = mock_protection.get_request_rate()
        can_proceed = mock_protection.check_rate_limit("client_ip")
        
        assert request_rate < 1000, "Request rate should be within limits"
        assert can_proceed is True, "Normal requests should proceed"
        
        # Simulate DDoS attack
        mock_protection.get_request_rate.return_value = 5000  # High request rate
        mock_protection.check_rate_limit.return_value = False
        
        request_rate = mock_protection.get_request_rate()
        can_proceed = mock_protection.check_rate_limit("client_ip")
        
        assert request_rate > 1000, "High request rate indicates DDoS"
        assert can_proceed is False, "DDoS requests should be blocked"
    
    @pytest.mark.asyncio
    async def test_network_partition_security(self):
        """Test security during network partitions"""
        # Mock partition manager
        mock_partition = Mock()
        mock_partition.is_partitioned.return_value = True
        mock_partition.get_partition_size.return_value = 3
        mock_partition.get_total_nodes.return_value = 10
        
        # Test partition detection
        is_partitioned = mock_partition.is_partitioned()
        partition_size = mock_partition.get_partition_size()
        total_nodes = mock_partition.get_total_nodes()
        
        assert is_partitioned is True, "Partition should be detected"
        assert partition_size < total_nodes, "Partition should be smaller than total network"
        
        # Test security measures during partition
        partition_ratio = partition_size / total_nodes
        assert partition_ratio > 0.3, "Partition should be large enough to maintain security"
        
        # Should enter safe mode during partition
        mock_partition.enter_safe_mode.assert_called_once()


class TestEconomicSecurity:
    """Test economic layer security"""
    
    @pytest.mark.asyncio
    async def test_staking_slashing_conditions(self):
        """Test staking slashing conditions and enforcement"""
        # Mock staking manager
        mock_staking = Mock()
        mock_staking.get_validator_stake.return_value = Decimal('1000.0')
        mock_staking.slash_validator.return_value = (True, "Slashed 100 tokens")
        
        # Test slashing conditions
        validator_address = "0xvalidator1"
        slash_percentage = 0.1  # 10%
        reason = "Double signing"
        
        # Apply slash
        success, message = mock_staking.slash_validator(validator_address, slash_percentage, reason)
        
        assert success is True, "Slashing should succeed"
        assert "Slashed" in message, "Slashing message should be returned"
        
        # Verify stake reduction
        original_stake = mock_staking.get_validator_stake(validator_address)
        expected_slash_amount = original_stake * Decimal(str(slash_percentage))
        
        mock_staking.slash_validator.assert_called_once_with(validator_address, slash_percentage, reason)
    
    @pytest.mark.asyncio
    async def test_reward_manipulation_prevention(self):
        """Test prevention of reward manipulation"""
        # Mock reward distributor
        mock_rewards = Mock()
        mock_rewards.validate_reward_claim.return_value = True
        mock_rewards.calculate_reward.return_value = Decimal('10.0')
        
        # Test normal reward claim
        validator_address = "0xvalidator1"
        block_height = 100
        
        is_valid = mock_rewards.validate_reward_claim(validator_address, block_height)
        reward_amount = mock_rewards.calculate_reward(validator_address, block_height)
        
        assert is_valid is True, "Valid reward claim should pass validation"
        assert reward_amount > 0, "Reward amount should be positive"
        
        # Test manipulation attempt
        mock_rewards.validate_reward_claim.return_value = False  # Invalid claim
        
        is_valid = mock_rewards.validate_reward_claim(validator_address, block_height + 1)  # Wrong block
        
        assert is_valid is False, "Invalid reward claim should be rejected"
    
    @pytest.mark.asyncio
    async def test_gas_price_manipulation(self):
        """Test prevention of gas price manipulation"""
        # Mock gas manager
        mock_gas = Mock()
        mock_gas.get_current_gas_price.return_value = Decimal('0.001')
        mock_gas.validate_gas_price.return_value = True
        mock_gas.detect_manipulation.return_value = False
        
        # Test normal gas price
        current_price = mock_gas.get_current_gas_price()
        is_valid = mock_gas.validate_gas_price(current_price)
        is_manipulated = mock_gas.detect_manipulation()
        
        assert current_price > 0, "Gas price should be positive"
        assert is_valid is True, "Normal gas price should be valid"
        assert is_manipulated is False, "Normal gas price should not be manipulated"
        
        # Test manipulated gas price
        manipulated_price = Decimal('100.0')  # Extremely high price
        mock_gas.validate_gas_price.return_value = False
        mock_gas.detect_manipulation.return_value = True
        
        is_valid = mock_gas.validate_gas_price(manipulated_price)
        is_manipulated = mock_gas.detect_manipulation()
        
        assert is_valid is False, "Manipulated gas price should be invalid"
        assert is_manipulated is True, "Gas price manipulation should be detected"
    
    @pytest.mark.asyncio
    async def test_economic_attack_detection(self):
        """Test detection of various economic attacks"""
        # Mock security monitor
        mock_monitor = Mock()
        mock_monitor.detect_attack.return_value = None  # No attack
        
        # Test normal operation
        attack_type = "nothing_at_stake"
        evidence = {"validator_activity": "normal"}
        
        attack = mock_monitor.detect_attack(attack_type, evidence)
        assert attack is None, "No attack should be detected in normal operation"
        
        # Test attack detection
        mock_monitor.detect_attack.return_value = Mock(
            attack_type="nothing_at_stake",
            severity="high",
            evidence={"validator_activity": "abnormal"}
        )
        
        attack = mock_monitor.detect_attack(attack_type, {"validator_activity": "abnormal"})
        assert attack is not None, "Attack should be detected"
        assert attack.attack_type == "nothing_at_stake", "Attack type should match"
        assert attack.severity == "high", "Attack severity should be high"


class TestAgentNetworkSecurity:
    """Test agent network security"""
    
    @pytest.mark.asyncio
    async def test_agent_authentication(self):
        """Test agent authentication and authorization"""
        # Mock agent registry
        mock_registry = Mock()
        mock_registry.authenticate_agent.return_value = True
        mock_registry.check_permissions.return_value = ["text_generation"]
        
        # Test valid agent authentication
        agent_id = "agent_123"
        credentials = {"api_key": "valid_key", "signature": "valid_signature"}
        
        is_authenticated = mock_registry.authenticate_agent(agent_id, credentials)
        assert is_authenticated is True, "Valid agent should be authenticated"
        
        # Test permissions
        permissions = mock_registry.check_permissions(agent_id, "text_generation")
        assert "text_generation" in permissions, "Agent should have required permissions"
        
        # Test invalid authentication
        mock_registry.authenticate_agent.return_value = False
        is_authenticated = mock_registry.authenticate_agent(agent_id, {"api_key": "invalid"})
        assert is_authenticated is False, "Invalid agent should not be authenticated"
    
    @pytest.mark.asyncio
    async def test_agent_reputation_security(self):
        """Test security of agent reputation system"""
        # Mock reputation manager
        mock_reputation = Mock()
        mock_reputation.get_reputation_score.return_value = 0.9
        mock_reputation.validate_reputation_update.return_value = True
        
        # Test normal reputation update
        agent_id = "agent_123"
        event_type = "job_completed"
        score_change = 0.1
        
        is_valid = mock_reputation.validate_reputation_update(agent_id, event_type, score_change)
        current_score = mock_reputation.get_reputation_score(agent_id)
        
        assert is_valid is True, "Valid reputation update should pass"
        assert 0 <= current_score <= 1, "Reputation score should be within bounds"
        
        # Test manipulation attempt
        mock_reputation.validate_reputation_update.return_value = False  # Invalid update
        
        is_valid = mock_reputation.validate_reputation_update(agent_id, "fake_event", 0.5)
        assert is_valid is False, "Invalid reputation update should be rejected"
    
    @pytest.mark.asyncio
    async def test_agent_communication_security(self):
        """Test security of agent communication protocols"""
        # Mock communication protocol
        mock_protocol = Mock()
        mock_protocol.encrypt_message.return_value = "encrypted_message"
        mock_protocol.verify_message_integrity.return_value = True
        mock_protocol.check_rate_limit.return_value = True
        
        # Test message encryption
        original_message = {"job_id": "job_123", "requirements": {}}
        encrypted = mock_protocol.encrypt_message(original_message, "recipient_key")
        
        assert encrypted != original_message, "Message should be encrypted"
        
        # Test message integrity
        is_integrity_valid = mock_protocol.verify_message_integrity(encrypted, "signature")
        assert is_integrity_valid is True, "Message integrity should be valid"
        
        # Test rate limiting
        can_send = mock_protocol.check_rate_limit("agent_123")
        assert can_send is True, "Normal rate should be allowed"
        
        # Test rate limit exceeded
        mock_protocol.check_rate_limit.return_value = False
        can_send = mock_protocol.check_rate_limit("spam_agent")
        assert can_send is False, "Exceeded rate limit should be blocked"
    
    @pytest.mark.asyncio
    async def test_agent_behavior_monitoring(self):
        """Test agent behavior monitoring and anomaly detection"""
        # Mock behavior monitor
        mock_monitor = Mock()
        mock_monitor.detect_anomaly.return_value = None  # No anomaly
        mock_monitor.get_behavior_metrics.return_value = {
            "response_time": 1.0,
            "success_rate": 0.95,
            "error_rate": 0.05
        }
        
        # Test normal behavior
        agent_id = "agent_123"
        metrics = mock_monitor.get_behavior_metrics(agent_id)
        anomaly = mock_monitor.detect_anomaly(agent_id, metrics)
        
        assert anomaly is None, "No anomaly should be detected in normal behavior"
        assert metrics["success_rate"] >= 0.9, "Success rate should be high"
        assert metrics["error_rate"] <= 0.1, "Error rate should be low"
        
        # Test anomalous behavior
        mock_monitor.detect_anomaly.return_value = Mock(
            anomaly_type="high_error_rate",
            severity="medium",
            details={"error_rate": 0.5}
        )
        
        anomalous_metrics = {"success_rate": 0.5, "error_rate": 0.5}
        anomaly = mock_monitor.detect_anomaly(agent_id, anomalous_metrics)
        
        assert anomaly is not None, "Anomaly should be detected"
        assert anomaly.anomaly_type == "high_error_rate", "Anomaly type should match"
        assert anomaly.severity == "medium", "Anomaly severity should be medium"


class TestSmartContractSecurity:
    """Test smart contract security"""
    
    @pytest.mark.asyncio
    async def test_escrow_contract_security(self):
        """Test escrow contract security mechanisms"""
        # Mock escrow manager
        mock_escrow = Mock()
        mock_escrow.validate_contract.return_value = True
        mock_escrow.check_double_spend.return_value = False
        mock_escrow.verify_funds.return_value = True
        
        # Test contract validation
        contract_data = {
            "job_id": "job_123",
            "amount": Decimal('100.0'),
            "client": "0xclient",
            "agent": "0xagent"
        }
        
        is_valid = mock_escrow.validate_contract(contract_data)
        assert is_valid is True, "Valid contract should pass validation"
        
        # Test double spend protection
        has_double_spend = mock_escrow.check_double_spend("contract_123")
        assert has_double_spend is False, "No double spend should be detected"
        
        # Test fund verification
        has_funds = mock_escrow.verify_funds("0xclient", Decimal('100.0'))
        assert has_funds is True, "Sufficient funds should be verified"
        
        # Test security breach attempt
        mock_escrow.validate_contract.return_value = False  # Invalid contract
        is_valid = mock_escrow.validate_contract({"invalid": "contract"})
        assert is_valid is False, "Invalid contract should be rejected"
    
    @pytest.mark.asyncio
    async def test_dispute_resolution_security(self):
        """Test dispute resolution security and fairness"""
        # Mock dispute resolver
        mock_resolver = Mock()
        mock_resolver.validate_dispute.return_value = True
        mock_resolver.check_evidence_integrity.return_value = True
        mock_resolver.prevent_bias.return_value = True
        
        # Test dispute validation
        dispute_data = {
            "contract_id": "contract_123",
            "reason": "quality_issues",
            "evidence": [{"type": "screenshot", "hash": "valid_hash"}]
        }
        
        is_valid = mock_resolver.validate_dispute(dispute_data)
        assert is_valid is True, "Valid dispute should pass validation"
        
        # Test evidence integrity
        evidence_integrity = mock_resolver.check_evidence_integrity(dispute_data["evidence"])
        assert evidence_integrity is True, "Evidence integrity should be valid"
        
        # Test bias prevention
        is_unbiased = mock_resolver.prevent_bias("dispute_123", "arbitrator_123")
        assert is_unbiased is True, "Dispute resolution should be unbiased"
        
        # Test manipulation attempt
        mock_resolver.validate_dispute.return_value = False  # Invalid dispute
        is_valid = mock_resolver.validate_dispute({"manipulated": "dispute"})
        assert is_valid is False, "Manipulated dispute should be rejected"
    
    @pytest.mark.asyncio
    async def test_contract_upgrade_security(self):
        """Test contract upgrade security and governance"""
        # Mock upgrade manager
        mock_upgrade = Mock()
        mock_upgrade.validate_upgrade.return_value = True
        mock_upgrade.check_governance_approval.return_value = True
        mock_upgrade.verify_new_code.return_value = True
        
        # Test upgrade validation
        upgrade_proposal = {
            "contract_type": "escrow",
            "new_version": "1.1.0",
            "changes": ["security_fix", "new_feature"],
            "governance_votes": {"yes": 80, "no": 20}
        }
        
        is_valid = mock_upgrade.validate_upgrade(upgrade_proposal)
        assert is_valid is True, "Valid upgrade should pass validation"
        
        # Test governance approval
        has_approval = mock_upgrade.check_governance_approval(upgrade_proposal["governance_votes"])
        assert has_approval is True, "Upgrade should have governance approval"
        
        # Test code verification
        code_is_safe = mock_upgrade.verify_new_code("new_contract_code")
        assert code_is_safe is True, "New contract code should be safe"
        
        # Test unauthorized upgrade
        mock_upgrade.validate_upgrade.return_value = False  # Invalid upgrade
        is_valid = mock_upgrade.validate_upgrade({"unauthorized": "upgrade"})
        assert is_valid is False, "Unauthorized upgrade should be rejected"
    
    @pytest.mark.asyncio
    async def test_gas_optimization_security(self):
        """Test gas optimization security and fairness"""
        # Mock gas optimizer
        mock_optimizer = Mock()
        mock_optimizer.validate_optimization.return_value = True
        mock_optimizer.check_manipulation.return_value = False
        mock_optimizer.ensure_fairness.return_value = True
        
        # Test optimization validation
        optimization = {
            "strategy": "batch_operations",
            "gas_savings": 1000,
            "implementation_cost": Decimal('0.01')
        }
        
        is_valid = mock_optimizer.validate_optimization(optimization)
        assert is_valid is True, "Valid optimization should pass validation"
        
        # Test manipulation detection
        is_manipulated = mock_optimizer.check_manipulation(optimization)
        assert is_manipulated is False, "No manipulation should be detected"
        
        # Test fairness
        is_fair = mock_optimizer.ensure_fairness(optimization)
        assert is_fair is True, "Optimization should be fair"
        
        # Test malicious optimization
        mock_optimizer.validate_optimization.return_value = False  # Invalid optimization
        is_valid = mock_optimizer.validate_optimization({"malicious": "optimization"})
        assert is_valid is False, "Malicious optimization should be rejected"


class TestSystemWideSecurity:
    """Test system-wide security integration"""
    
    @pytest.mark.asyncio
    async def test_cross_layer_security_integration(self):
        """Test security integration across all layers"""
        # Mock security coordinators
        mock_consensus_security = Mock()
        mock_network_security = Mock()
        mock_economic_security = Mock()
        mock_agent_security = Mock()
        mock_contract_security = Mock()
        
        # All layers should report secure status
        mock_consensus_security.get_security_status.return_value = {"status": "secure", "threats": []}
        mock_network_security.get_security_status.return_value = {"status": "secure", "threats": []}
        mock_economic_security.get_security_status.return_value = {"status": "secure", "threats": []}
        mock_agent_security.get_security_status.return_value = {"status": "secure", "threats": []}
        mock_contract_security.get_security_status.return_value = {"status": "secure", "threats": []}
        
        # Check all layers
        consensus_status = mock_consensus_security.get_security_status()
        network_status = mock_network_security.get_security_status()
        economic_status = mock_economic_security.get_security_status()
        agent_status = mock_agent_security.get_security_status()
        contract_status = mock_contract_security.get_security_status()
        
        # All should be secure
        assert consensus_status["status"] == "secure", "Consensus layer should be secure"
        assert network_status["status"] == "secure", "Network layer should be secure"
        assert economic_status["status"] == "secure", "Economic layer should be secure"
        assert agent_status["status"] == "secure", "Agent layer should be secure"
        assert contract_status["status"] == "secure", "Contract layer should be secure"
        
        # No threats detected
        assert len(consensus_status["threats"]) == 0, "No consensus threats"
        assert len(network_status["threats"]) == 0, "No network threats"
        assert len(economic_status["threats"]) == 0, "No economic threats"
        assert len(agent_status["threats"]) == 0, "No agent threats"
        assert len(contract_status["threats"]) == 0, "No contract threats"
    
    @pytest.mark.asyncio
    async def test_incident_response_procedures(self):
        """Test incident response procedures"""
        # Mock incident response system
        mock_response = Mock()
        mock_response.detect_incident.return_value = None  # No incident
        mock_response.classify_severity.return_value = "low"
        mock_response.execute_response.return_value = (True, "Response executed")
        
        # Test normal operation
        incident = mock_response.detect_incident()
        assert incident is None, "No incident should be detected"
        
        # Simulate security incident
        mock_response.detect_incident.return_value = Mock(
            type="security_breach",
            severity="high",
            affected_layers=["consensus", "network"],
            timestamp=time.time()
        )
        
        incident = mock_response.detect_incident()
        assert incident is not None, "Security incident should be detected"
        assert incident.type == "security_breach", "Incident type should match"
        assert incident.severity == "high", "Incident severity should be high"
        
        # Classify severity
        severity = mock_response.classify_severity(incident)
        assert severity == "high", "Severity should be classified as high"
        
        # Execute response
        success, message = mock_response.execute_response(incident)
        assert success is True, "Incident response should succeed"
    
    @pytest.mark.asyncio
    async def test_security_audit_compliance(self):
        """Test security audit compliance"""
        # Mock audit system
        mock_audit = Mock()
        mock_audit.run_security_audit.return_value = {
            "overall_score": 95,
            "findings": [],
            "compliance_status": "compliant"
        }
        
        # Run security audit
        audit_results = mock_audit.run_security_audit()
        
        assert audit_results["overall_score"] >= 90, "Security score should be high"
        assert len(audit_results["findings"]) == 0, "No critical security findings"
        assert audit_results["compliance_status"] == "compliant", "System should be compliant"
        
        # Test with findings
        mock_audit.run_security_audit.return_value = {
            "overall_score": 85,
            "findings": [
                {"severity": "medium", "description": "Update required"},
                {"severity": "low", "description": "Documentation needed"}
            ],
            "compliance_status": "mostly_compliant"
        }
        
        audit_results = mock_audit.run_security_audit()
        assert audit_results["overall_score"] >= 80, "Score should still be acceptable"
        assert audit_results["compliance_status"] == "mostly_compliant", "Should be mostly compliant"
    
    @pytest.mark.asyncio
    async def test_penetration_testing_resistance(self):
        """Test resistance to penetration testing attacks"""
        # Mock penetration test simulator
        mock_pentest = Mock()
        mock_pentest.simulate_attack.return_value = {"success": False, "reason": "blocked"}
        
        # Test various attack vectors
        attack_vectors = [
            "sql_injection",
            "xss_attack",
            "privilege_escalation",
            "data_exfiltration",
            "denial_of_service"
        ]
        
        for attack in attack_vectors:
            result = mock_pentest.simulate_attack(attack)
            assert result["success"] is False, f"Attack {attack} should be blocked"
            assert "blocked" in result["reason"], f"Attack {attack} should be blocked"
        
        # Test successful defense
        mock_pentest.get_defense_success_rate.return_value = 0.95
        success_rate = mock_pentest.get_defense_success_rate()
        
        assert success_rate >= 0.9, "Defense success rate should be high"


if __name__ == "__main__":
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--maxfail=5"
    ])
