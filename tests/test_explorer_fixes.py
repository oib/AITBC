"""
Test Explorer fixes - simplified integration tests
"""

import pytest
import configparser
import os


class TestExplorerFixes:
    """Test the Explorer fixes implemented"""
    
    def test_pytest_configuration_restored(self):
        """Test that pytest.ini now includes full test coverage"""
        # Read pytest.ini
        config_path = os.path.join(os.path.dirname(__file__), '../pytest.ini')
        config = configparser.ConfigParser()
        config.read(config_path)
        
        # Verify pytest section exists
        assert 'pytest' in config, "pytest section not found in pytest.ini"
        
        # Verify testpaths includes full tests directory
        testpaths = config.get('pytest', 'testpaths')
        assert testpaths == 'tests', f"Expected 'tests', got '{testpaths}'"
        
        # Verify it's not limited to CLI only
        assert 'tests/cli' not in testpaths, "testpaths should not be limited to CLI only"
        
        print("✅ pytest.ini test coverage restored to full 'tests' directory")
    
    def test_explorer_file_contains_transaction_endpoint(self):
        """Test that Explorer main.py contains the transaction endpoint"""
        explorer_path = os.path.join(os.path.dirname(__file__), '../apps/blockchain-explorer/main.py')
        
        with open(explorer_path, 'r') as f:
            content = f.read()
        
        # Check for transaction endpoint
        assert '@app.get("/api/transactions/{tx_hash}")' in content, "Transaction endpoint not found"
        
        # Check for correct RPC URL (should be /rpc/tx/ not /tx/)
        assert 'BLOCKCHAIN_RPC_URL}/rpc/tx/{tx_hash}' in content, "Incorrect RPC URL for transaction"
        
        # Check for field mapping
        assert '"hash": tx.get("tx_hash")' in content, "Field mapping for hash not found"
        assert '"from": tx.get("sender")' in content, "Field mapping for from not found"
        assert '"to": tx.get("recipient")' in content, "Field mapping for to not found"
        
        print("✅ Transaction endpoint with correct RPC URL and field mapping found")
    
    def test_explorer_contains_robust_timestamp_handling(self):
        """Test that Explorer contains robust timestamp handling"""
        explorer_path = os.path.join(os.path.dirname(__file__), '../apps/blockchain-explorer/main.py')
        
        with open(explorer_path, 'r') as f:
            content = f.read()
        
        # Check for robust timestamp handling (flexible matching)
        assert 'typeof timestamp' in content, "Timestamp type checking not found"
        assert 'new Date(timestamp)' in content, "Date creation not found"
        assert 'timestamp * 1000' in content, "Numeric timestamp conversion not found"
        assert 'toLocaleString()' in content, "Date formatting not found"
        
        print("✅ Robust timestamp handling for both ISO strings and numbers found")
    
    def test_field_mapping_completeness(self):
        """Test that all required field mappings are present"""
        explorer_path = os.path.join(os.path.dirname(__file__), '../apps/blockchain-explorer/main.py')
        
        with open(explorer_path, 'r') as f:
            content = f.read()
        
        # Required field mappings from RPC to frontend
        required_mappings = {
            "tx_hash": "hash",
            "sender": "from", 
            "recipient": "to",
            "payload.type": "type",
            "payload.amount": "amount",
            "payload.fee": "fee",
            "created_at": "timestamp"
        }
        
        for rpc_field, frontend_field in required_mappings.items():
            if "." in rpc_field:
                # Nested field like payload.type
                base_field, nested_field = rpc_field.split(".")
                assert f'payload.get("{nested_field}"' in content, f"Mapping for {rpc_field} not found"
            else:
                # Simple field mapping
                assert f'tx.get("{rpc_field}")' in content, f"Mapping for {rpc_field} not found"
        
        print("✅ All required field mappings from RPC to frontend found")
    
    def test_explorer_search_functionality(self):
        """Test that Explorer search functionality is present"""
        explorer_path = os.path.join(os.path.dirname(__file__), '../apps/blockchain-explorer/main.py')
        
        with open(explorer_path, 'r') as f:
            content = f.read()
        
        # Check for search functionality
        assert 'async function search()' in content, "Search function not found"
        assert 'fetch(`/api/transactions/${query}`)' in content, "Transaction search API call not found"
        assert '/^[a-fA-F0-9]{64}$/.test(query)' in content, "Transaction hash validation not found"
        
        # Check for transaction display fields
        assert 'tx.hash' in content, "Transaction hash display not found"
        assert 'tx.from' in content, "Transaction from display not found"
        assert 'tx.to' in content, "Transaction to display not found"
        assert 'tx.amount' in content, "Transaction amount display not found"
        assert 'tx.fee' in content, "Transaction fee display not found"
        
        print("✅ Search functionality with proper transaction hash validation found")


class TestRPCIntegration:
    """Test RPC integration expectations"""
    
    def test_rpc_transaction_endpoint_exists(self):
        """Test that blockchain-node has the expected transaction endpoint"""
        rpc_path = os.path.join(os.path.dirname(__file__), '../apps/blockchain-node/src/aitbc_chain/rpc/router.py')
        
        with open(rpc_path, 'r') as f:
            content = f.read()
        
        # Check for RPC transaction endpoint (flexible matching)
        assert 'router.get' in content and '/tx/{tx_hash}' in content, "RPC transaction endpoint not found"
        
        # Check for expected response fields
        assert 'tx_hash' in content, "tx_hash field not found in RPC response"
        assert 'sender' in content, "sender field not found in RPC response"
        assert 'recipient' in content, "recipient field not found in RPC response"
        assert 'payload' in content, "payload field not found in RPC response"
        assert 'created_at' in content, "created_at field not found in RPC response"
        
        print("✅ RPC transaction endpoint with expected fields found")
    
    def test_field_mapping_consistency(self):
        """Test that field mapping between RPC and Explorer is consistent"""
        # RPC fields (from blockchain-node)
        rpc_fields = ["tx_hash", "sender", "recipient", "payload", "created_at", "block_height"]
        
        # Frontend expected fields (from explorer)
        frontend_fields = ["hash", "from", "to", "type", "amount", "fee", "timestamp", "block_height"]
        
        # Load both files and verify mapping
        explorer_path = os.path.join(os.path.dirname(__file__), '../apps/blockchain-explorer/main.py')
        rpc_path = os.path.join(os.path.dirname(__file__), '../apps/blockchain-node/src/aitbc_chain/rpc/router.py')
        
        with open(explorer_path, 'r') as f:
            explorer_content = f.read()
        
        with open(rpc_path, 'r') as f:
            rpc_content = f.read()
        
        # Verify RPC has all required fields
        for field in rpc_fields:
            assert field in rpc_content, f"RPC missing field: {field}"
        
        # Verify Explorer maps all RPC fields
        assert '"hash": tx.get("tx_hash")' in explorer_content, "Missing tx_hash -> hash mapping"
        assert '"from": tx.get("sender")' in explorer_content, "Missing sender -> from mapping"
        assert '"to": tx.get("recipient")' in explorer_content, "Missing recipient -> to mapping"
        assert '"timestamp": tx.get("created_at")' in explorer_content, "Missing created_at -> timestamp mapping"
        
        print("✅ Field mapping consistency between RPC and Explorer verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
