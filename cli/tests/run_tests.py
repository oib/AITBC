#!/usr/bin/env python3
"""
Simple test runner for AITBC CLI Level 1 commands
"""

import sys
import os

# Add CLI to path
sys.path.insert(0, '/home/oib/windsurf/aitbc/cli')

def main():
    """Main test runner"""
    print("🚀 AITBC CLI Level 1 Commands Test Runner")
    print("=" * 50)
    
    try:
        # Import and run the main test
        from test_level1_commands import main as test_main
        success = test_main()
        
        if success:
            print("\n🎉 All tests completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Some tests failed!")
            sys.exit(1)
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're running from the tests directory")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
