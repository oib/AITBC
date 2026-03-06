#!/usr/bin/env python3
"""
Validate the CLI Level 1 test structure
"""

import os
import sys
from pathlib import Path

def validate_test_structure():
    """Validate that all test files and directories exist"""
    
    base_dir = Path(__file__).parent
    
    required_files = [
        "test_level1_commands.py",
        "run_tests.py",
        "README.md",
        "utils/test_helpers.py", 
        "utils/command_tester.py",
        "fixtures/mock_config.py",
        "fixtures/mock_responses.py",
        "fixtures/test_wallets/test-wallet-1.json"
    ]
    
    missing_files = []
    
    for file_path in required_files:
        full_path = base_dir / file_path
        if not full_path.exists():
            missing_files.append(str(file_path))
        else:
            print(f"✅ {file_path}")
    
    if missing_files:
        print(f"\n❌ Missing files: {len(missing_files)}")
        for file in missing_files:
            print(f"  - {file}")
        return False
    else:
        print(f"\n🎉 All {len(required_files)} required files present!")
        return True

def validate_imports():
    """Validate that all imports work correctly"""
    
    try:
        # Test main test script import
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import test_level1_commands
        print("✅ test_level1_commands.py imports successfully")
        
        # Test utilities import
        from utils.test_helpers import TestEnvironment, MockConfig
        print("✅ utils.test_helpers imports successfully")
        
        from utils.command_tester import CommandTester
        print("✅ utils.command_tester imports successfully")
        
        # Test fixtures import
        from fixtures.mock_config import MOCK_CONFIG_DATA
        print("✅ fixtures.mock_config imports successfully")
        
        from fixtures.mock_responses import MockApiResponse
        print("✅ fixtures.mock_responses imports successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    """Main validation function"""
    print("🔍 Validating AITBC CLI Level 1 Test Structure")
    print("=" * 50)
    
    structure_ok = validate_test_structure()
    imports_ok = validate_imports()
    
    print("\n" + "=" * 50)
    print("📊 VALIDATION RESULTS")
    print("=" * 50)
    
    if structure_ok and imports_ok:
        print("🎉 ALL VALIDATIONS PASSED!")
        print("The CLI Level 1 test suite is ready to run.")
        return True
    else:
        print("❌ SOME VALIDATIONS FAILED!")
        print("Please fix the issues before running the tests.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
