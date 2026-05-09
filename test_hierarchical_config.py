#!/usr/bin/env python3
"""Test hierarchical config implementation"""

import sys
import os
import tempfile
from pathlib import Path

# Add the aitbc module to path
sys.path.insert(0, '/opt/aitbc')

def test_hierarchical_config():
    print("Testing Hierarchical Configuration System...")
    
    try:
        from aitbc.hierarchical_config import load_config, ValidatedAITBCConfig, create_config_template
        print("✓ Imports successful")
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False
    
    # Test 1: Default loading
    try:
        config = load_config()
        print(f"✓ Default config loaded: env={config.environment}, port={config.port}")
    except Exception as e:
        print(f"✗ Default config failed: {e}")
        return False
    
    # Test 2: File-based config
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('''
environment: production
port: 9000
debug: false
log_level: WARNING
secret_key: "test-secret"
jwt_secret: "test-jwt"
''')
            temp_path = f.name
        
        config = load_config(config_file=temp_path)
        print(f"✓ File config loaded: env={config.environment}, port={config.port}")
        os.unlink(temp_path)
    except Exception as e:
        print(f"✗ File config failed: {e}")
        return False
    
    # Test 3: Validation
    try:
        # Set up for production validation
        os.environ['AITBC_ENVIRONMENT'] = 'production'
        os.environ['AITBC_SECRET_KEY'] = 'test-key'
        os.environ['AITBC_JWT_SECRET'] = 'test-jwt'
        config = ValidatedAITBCConfig()
        print('✓ Production validation passed')
        
        # Should fail without secrets
        del os.environ['AITBC_SECRET_KEY']
        try:
            config = ValidatedAITBCConfig()
            print('✗ Validation should have failed')
            return False
        except Exception:
            print('✓ Validation correctly rejected missing secret')
            os.environ['AITBC_SECRET_KEY'] = 'test-key'  # restore
            
    except Exception as e:
        print(f'✗ Validation test failed: {e}')
        return False

    # Test 4: Templates
    try:
        dev = create_config_template('development')
        prod = create_config_template('production')
        print(f'✓ Templates created: dev_debug={dev["debug"]}, prod_workers={prod["workers"]}')
    except Exception as e:
        print(f'✗ Template test failed: {e}')
        return False
        
    print("✓ All hierarchical config tests passed!")
    return True

if __name__ == "__main__":
    success = test_hierarchical_config()
    sys.exit(0 if success else 1)
