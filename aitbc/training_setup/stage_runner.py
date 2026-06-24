"""
Schema-driven stage execution for AITBC training.
Loads JSON stage definitions, runs commands, and validates expected conditions.
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Command:
    """Represents a single command in a stage."""

    cmd: str
    args: list[str]
    expected_re: str | None = None
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
    commands: list[Command]
    expected: dict[str, ExpectedCondition]
    prerequisites: list[str] | None = None


class StageRunner:
    """
    Executes training stages from JSON schema definitions.
    Runs commands, validates output, and checks expected conditions.
    """

    def __init__(self, aitbc_cli: str = "/opt/aitbc/aitbc-cli"):
        self.aitbc_cli = aitbc_cli
        self.results: dict[str, Any] = {}

    def load_stage_from_json(self, json_path: str) -> StageDefinition:
        """
        Load a stage definition from JSON file.

        Args:
            json_path: Path to JSON file

        Returns:
            StageDefinition object
        """
        with open(json_path) as f:
            data = json.load(f)
        commands = []
        for cmd_data in data.get("commands", []):
            commands.append(
                Command(
                    cmd=cmd_data["cmd"],
                    args=cmd_data.get("args", []),
                    expected_re=cmd_data.get("re"),
                    expected_exit_code=cmd_data.get("exit_code", 0),
                )
            )
        expected = {}
        for key, cond_data in data.get("expected", {}).items():
            expected[key] = ExpectedCondition(type=cond_data.get("type", "value"), value=cond_data.get("value"))
        return StageDefinition(
            stage=data["stage"],
            title=data.get("title", f"Stage {data['stage']}"),
            commands=commands,
            expected=expected,
            prerequisites=data.get("prerequisites"),
        )

    def run_command(self, command: Command) -> dict[str, Any]:
        """
        Execute a single command and validate output.

        Args:
            command: Command to execute

        Returns:
            Dictionary with execution results
        """
        log.info("Running: %s %s", command.cmd, " ".join(command.args))
        if command.cmd == "sleep":
            import time

            try:
                sleep_time = int(command.args[0]) if command.args else 1
                log.info("Sleeping for %s seconds", sleep_time)
                time.sleep(sleep_time)
                return {"success": True, "exit_code": 0, "output": f"Slept for {sleep_time} seconds"}
            except Exception as e:
                log.error("Sleep command failed: %s", e)
                return {"success": False, "error": str(e)}
        cmd_list = [self.aitbc_cli, *command.cmd.split(), *command.args]
        try:
            result = subprocess.run(cmd_list, capture_output=True, text=True, timeout=30)
            output = result.stdout + result.stderr
            if result.returncode != command.expected_exit_code:
                log.error("Command failed with exit code %s", result.returncode)
                log.error("Output: %s", output)
                return {
                    "success": False,
                    "exit_code": result.returncode,
                    "output": output,
                    "error": f"Unexpected exit code: {result.returncode}",
                }
            if command.expected_re and not re.search(command.expected_re, output):
                log.error("Output does not match expected pattern: %s", command.expected_re)
                return {
                    "success": False,
                    "exit_code": result.returncode,
                    "output": output,
                    "error": f"Output does not match pattern: {command.expected_re}",
                }
            tx_hash = self._extract_tx_hash(output)
            log.info("✓ Command succeeded")
            return {"success": True, "exit_code": result.returncode, "output": output, "tx_hash": tx_hash}
        except subprocess.TimeoutExpired:
            log.error("Command timed out")
            return {"success": False, "error": "Command timed out"}
        except Exception as e:
            log.error("Command execution failed: %s", e)
            return {"success": False, "error": str(e)}

    def _extract_tx_hash(self, output: str) -> str | None:
        """
        Extract transaction hash from command output.

        Args:
            output: Command output text

        Returns:
            Transaction hash if found, None otherwise
        """
        patterns = [
            "tx_hash[:\\s]+([a-fA-F0-9]{64})",
            "transaction[:\\s]+([a-fA-F0-9]{64})",
            "hash[:\\s]+([a-fA-F0-9]{64})",
            "([a-fA-F0-9]{64})",
        ]
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                tx_hash = match.group(1)
                log.info("Transaction hash extracted: %s", tx_hash)
                return tx_hash
        return None

    def _extract_value(self, key: str, combined_output: str, command_results: list[dict[str, Any]]) -> Any:
        """
        Extract a value from command results for condition validation.

        Looks for the key in command result fields first, then tries parsing
        key=value patterns from combined output.

        Args:
            key: The condition key to look up
            combined_output: Combined stdout/stderr from all successful commands
            command_results: List of command execution results

        Returns:
            The extracted value, or None if not found
        """
        for result in command_results:
            if not result.get("success"):
                continue
            if key in result:
                return result[key]
        match = re.search(rf"{re.escape(key)}\s*[:=]\s*(\S+)", combined_output)
        if match:
            return match.group(1).strip().strip("\"'")
        return None

    @staticmethod
    def _coerce_value(value: Any) -> Any:
        """Coerce a value for comparison — try int, float, bool, then fall back to string."""
        if value is None or not isinstance(value, str):
            return value
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        try:
            return int(value)
        except (ValueError, TypeError):
            pass
        try:
            return float(value)
        except (ValueError, TypeError):
            pass
        return value

    def validate_conditions(
        self, expected: dict[str, ExpectedCondition], command_results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Validate expected conditions after command execution.

        Args:
            expected: Dictionary of expected conditions
            command_results: List of command execution results from run_stage

        Returns:
            Dictionary with validation results
        """
        combined_output = "\n".join(r.get("output", "") for r in command_results if r.get("success"))
        results = {}
        for key, condition in expected.items():
            log.info("Validating condition: %s", key)
            if condition.type == "value":
                actual = self._extract_value(key, combined_output, command_results)
                actual_coerced = self._coerce_value(actual)
                expected_coerced = self._coerce_value(condition.value)
                passed = actual_coerced == expected_coerced
                results[key] = {"expected": condition.value, "actual": actual, "passed": passed}
                if not passed:
                    log.error("✗ Condition %s failed: expected %s, got %s", key, condition.value, actual)
                else:
                    log.info("✓ Condition %s validated", key)
            elif condition.type == "regex":
                pattern = str(condition.value)
                match = re.search(pattern, combined_output)
                passed = match is not None
                results[key] = {"pattern": pattern, "matched": bool(passed), "passed": passed}
                if not passed:
                    log.error("✗ Condition %s failed: pattern %s not found in output", key, pattern)
                else:
                    log.info("✓ Condition %s validated", key)
            else:
                log.warning("Unknown condition type: %s for %s", condition.type, key)
                results[key] = {"passed": False, "error": f"Unknown condition type: {condition.type}"}
        return results

    def run_stage(self, stage: StageDefinition) -> dict[str, Any]:
        """
        Execute a complete training stage.

        Args:
            stage: StageDefinition to execute

        Returns:
            Dictionary with stage execution results
        """
        log.info("=== Starting Stage %s: %s ===", stage.stage, stage.title)
        results: dict[str, Any] = {
            "stage": stage.stage,
            "title": stage.title,
            "commands": [],
            "conditions": {},
            "success": True,
        }
        if stage.prerequisites:
            log.info("Checking prerequisites: %s", stage.prerequisites)
        for command in stage.commands:
            cmd_result = self.run_command(command)
            results["commands"].append(cmd_result)
            if not cmd_result.get("success"):
                results["success"] = False
                log.error("Stage failed at command: %s", command.cmd)
                break
        if results["success"]:
            results["conditions"] = self.validate_conditions(stage.expected, results["commands"])
        log.info("=== Stage %s completed: %s ===", stage.stage, "SUCCESS" if results["success"] else "FAILED")
        return results

    def run_stage_from_json(self, json_path: str) -> dict[str, Any]:
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
        "title": "Foundation - Wallets & Accounts",
        "prerequisites": ["AITBC node running", "Genesis wallet funded"],
        "commands": [
            {"cmd": "wallet create", "args": ["training-w1", "--password", "abc123"], "exit_code": 0},
            {"cmd": "wallet list", "args": [], "re": "training-w1"},
            {"cmd": "wallet send", "args": ["--password", "", "genesis", "training-w1", "100"], "exit_code": 0},
        ],
        "expected": {
            "wallet_exists": {"type": "value", "value": True},
            "balance": {"type": "value", "value": {"symbol": "AIT", "amount": 100}},
        },
    }
    with open(output_path, "w") as f:
        json.dump(example_stage, f, indent=2)
    log.info("Example stage JSON created at %s", output_path)
