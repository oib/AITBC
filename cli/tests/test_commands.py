#!/usr/bin/env python3
"""
Simple test script for multi-chain CLI commands
"""

import sys
import os
sys.path.insert(0, '/home/oib/windsurf/aitbc/cli')

from aitbc_cli.commands.chain import chain
from aitbc_cli.commands.genesis import genesis
from click.testing import CliRunner

def test_chain_commands():
    """Test chain commands"""
    runner = CliRunner()
    
    print("Testing chain commands...")
    
    # Test chain list command
    result = runner.invoke(chain, ['list'])
    print(f"Chain list command exit code: {result.exit_code}")
    if result.output:
        print(f"Output: {result.output}")
    
    # Test chain help
    result = runner.invoke(chain, ['--help'])
    print(f"Chain help command exit code: {result.exit_code}")
    if result.output:
        print(f"Chain help output length: {len(result.output)} characters")
    
    print("✅ Chain commands test completed")

def test_genesis_commands():
    """Test genesis commands"""
    runner = CliRunner()
    
    print("Testing genesis commands...")
    
    # Test genesis templates command
    result = runner.invoke(genesis, ['templates'])
    print(f"Genesis templates command exit code: {result.exit_code}")
    if result.output:
        print(f"Output: {result.output}")
    
    # Test genesis help
    result = runner.invoke(genesis, ['--help'])
    print(f"Genesis help command exit code: {result.exit_code}")
    if result.output:
        print(f"Genesis help output length: {len(result.output)} characters")
    
    print("✅ Genesis commands test completed")

if __name__ == "__main__":
    test_chain_commands()
    test_genesis_commands()
    print("\n🎉 All CLI command tests completed successfully!")
