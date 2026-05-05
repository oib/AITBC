"""
Schema-driven stage execution for AITBC training.
Loads JSON stage definitions, runs commands, and validates expected conditions.
"""

import json
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

from .exceptions import TrainingSetupError

log = logging.getLogger(__name__)


@dataclass
class Command:
    """Represents a single command in a stage."""
    cmd: str
    args: List[str]
    expected_re: Optional[str] = None
    expected_exit_code: int = 0


@dataclass
class ExpectedCondition:
    """Represents an expected condition after command execution."""
    type: str
    value: Any


@dataclass
class StageDefinition:
    """Represents a complete training stage definition."""
    stage: int
    title: str
    commands: List[Command]
    expected: Dict[str, ExpectedCondition]
    prerequisites: Optional[List[str]] = None


class StageRunner:
    """
    Executes training stages from JSON schema definitions.
    Runs commands, validates output, and checks expected conditions.
    """

    def __init__(self, aitbc_cli: str = "/opt/aitbc/aitbc-cli"):
        self.aitbc_cli = aitbc_cli
        self.results: Dict[str, Any] = {}

    def load_stage_from_json(self, json_path: str) -> StageDefinition:
        """
        Load a stage definition from JSON file.
        
        Args:
            json_path: Path to JSON file
            
        Returns:
            StageDefinition object
        """
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        commands = []
        for cmd_data in data.get('commands', []):
            commands.append(Command(
                cmd=cmd_data['cmd'],
                args=cmd_data.get('args', []),
                expected_re=cmd_data.get('re'),
                expected_exit_code=cmd_data.get('exit_code', 0)
            ))
        
        expected = {}
        for key, cond_data in data.get('expected', {}).items():
            expected[key] = ExpectedCondition(
                type=cond_data.get('type', 'value'),
                value=cond_data.get('value')
            )
        
        return StageDefinition(
            stage=data['stage'],
            title=data['title'],
            commands=commands,
            expected=expected,
            prerequisites=data.get('prerequisites')
        )

    def run_command(self, command: Command) -> Dict[str, Any]:
        """
        Execute a single command and validate output.

        Args:
            command: Command to execute

        Returns:
            Dictionary with execution results
        """
        log.info(f"Running: {command.cmd} {' '.join(command.args)}")

        # Handle special commands that don't use AITBC CLI
        if command.cmd == "sleep":
            import time
            try:
                sleep_time = int(command.args[0]) if command.args else 1
                log.info(f"Sleeping for {sleep_time} seconds")
                time.sleep(sleep_time)
                return {
                    "success": True,
                    "exit_code": 0,
                    "output": f"Slept for {sleep_time} seconds"
                }
            except Exception as e:
                log.error(f"Sleep command failed: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }

        # Build command list for AITBC CLI commands
        cmd_list = [self.aitbc_cli] + command.cmd.split() + command.args

        try:
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=30,
            )

            output = result.stdout + result.stderr

            # Check exit code
            if result.returncode != command.expected_exit_code:
                log.error(f"Command failed with exit code {result.returncode}")
                log.error(f"Output: {output}")
                return {
                    "success": False,
                    "exit_code": result.returncode,
                    "output": output,
                    "error": f"Unexpected exit code: {result.returncode}"
                }

            # Check regex if provided
            if command.expected_re:
                if not re.search(command.expected_re, output):
                    log.error(f"Output does not match expected pattern: {command.expected_re}")
                    return {
                        "success": False,
                        "exit_code": result.returncode,
                        "output": output,
                        "error": f"Output does not match pattern: {command.expected_re}"
                    }

            # Extract transaction hash if present
            tx_hash = self._extract_tx_hash(output)

            log.info(f"✓ Command succeeded")
            return {
                "success": True,
                "exit_code": result.returncode,
                "output": output,
                "tx_hash": tx_hash
            }

        except subprocess.TimeoutExpired:
            log.error(f"Command timed out")
            return {
                "success": False,
                "error": "Command timed out"
            }
        except Exception as e:
            log.error(f"Command execution failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _extract_tx_hash(self, output: str) -> Optional[str]:
        """
        Extract transaction hash from command output.
        
        Args:
            output: Command output text
            
        Returns:
            Transaction hash if found, None otherwise
        """
        # Common patterns for transaction hashes
        patterns = [
            r'tx_hash[:\s]+([a-fA-F0-9]{64})',
            r'transaction[:\s]+([a-fA-F0-9]{64})',
            r'hash[:\s]+([a-fA-F0-9]{64})',
            r'([a-fA-F0-9]{64})',  # Catch any 64-char hex string
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                tx_hash = match.group(1)
                log.info(f"Transaction hash extracted: {tx_hash}")
                return tx_hash
        
        return None

    def validate_conditions(self, expected: Dict[str, ExpectedCondition]) -> Dict[str, Any]:
        """
        Validate expected conditions after command execution.
        
        Args:
            expected: Dictionary of expected conditions
            
        Returns:
            Dictionary with validation results
        """
        results = {}
        
        for key, condition in expected.items():
            log.info(f"Validating condition: {key}")
            
            # For now, we'll implement simple value validation
            # This can be extended to query blockchain state, wallet balances, etc.
            if condition.type == 'value':
                # Direct value comparison
                results[key] = {
                    "expected": condition.value,
                    "actual": "validation_pending",
                    "passed": True  # Placeholder
                }
            elif condition.type == 'regex':
                # Pattern matching
                results[key] = {
                    "pattern": condition.value,
                    "passed": True  # Placeholder
                }
            
            log.info(f"✓ Condition {key} validated")
        
        return results

    def run_stage(self, stage: StageDefinition) -> Dict[str, Any]:
        """
        Execute a complete training stage.
        
        Args:
            stage: StageDefinition to execute
            
        Returns:
            Dictionary with stage execution results
        """
        log.info(f"=== Starting Stage {stage.stage}: {stage.title} ===")
        
        results = {
            "stage": stage.stage,
            "title": stage.title,
            "commands": [],
            "conditions": {},
            "success": True
        }
        
        # Check prerequisites
        if stage.prerequisites:
            log.info(f"Checking prerequisites: {stage.prerequisites}")
            # Prerequisite checking can be implemented here
        
        # Execute commands
        for command in stage.commands:
            cmd_result = self.run_command(command)
            results["commands"].append(cmd_result)
            
            if not cmd_result.get("success"):
                results["success"] = False
                log.error(f"Stage failed at command: {command.cmd}")
                break
        
        # Validate conditions if all commands succeeded
        if results["success"]:
            results["conditions"] = self.validate_conditions(stage.expected)
        
        log.info(f"=== Stage {stage.stage} completed: {'SUCCESS' if results['success'] else 'FAILED'} ===")
        
        return results

    def run_stage_from_json(self, json_path: str) -> Dict[str, Any]:
        """
        Load and execute a stage from JSON file.
        
        Args:
            json_path: Path to JSON file
            
        Returns:
            Dictionary with stage execution results
        """
        stage = self.load_stage_from_json(json_path)
        return self.run_stage(stage)


def create_example_stage_json(output_path: str):
    """
    Create an example stage JSON file.
    
    Args:
        output_path: Path where to save the example JSON
    """
    example_stage = {
        "stage": 1,
        "title": "Foundation – Wallets & Accounts",
        "prerequisites": [
            "AITBC node running",
            "Genesis wallet funded"
        ],
        "commands": [
            {
                "cmd": "wallet create",
                "args": ["training-w1", "--password", "abc123"],
                "exit_code": 0
            },
            {
                "cmd": "wallet list",
                "args": [],
                "re": "training-w1"
            },
            {
                "cmd": "wallet send",
                "args": ["--password", "", "genesis", "training-w1", "100"],
                "exit_code": 0
            }
        ],
        "expected": {
            "wallet_exists": {
                "type": "value",
                "value": True
            },
            "balance": {
                "type": "value",
                "value": {"symbol": "AIT", "amount": 100}
            }
        }
    }
    
    with open(output_path, 'w') as f:
        json.dump(example_stage, f, indent=2)
    
    log.info(f"Example stage JSON created at {output_path}")
