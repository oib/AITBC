"""Tests for aitbc.training_setup.stage_runner"""

import json
import tempfile
from unittest.mock import patch

from aitbc.training_setup.stage_runner import (
    Command,
    ExpectedCondition,
    StageDefinition,
    StageRunner,
    create_example_stage_json,
)


class TestStageRunner:
    def test_init(self):
        runner = StageRunner()
        assert runner.aitbc_cli == "/opt/aitbc/aitbc-cli"

    def test_load_stage_from_json(self):
        data = {
            "stage": 1,
            "title": "Test",
            "commands": [{"cmd": "echo", "args": ["hello"]}],
            "expected": {"ok": {"type": "value", "value": True}},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        runner = StageRunner()
        stage = runner.load_stage_from_json(path)
        assert stage.stage == 1
        assert stage.title == "Test"
        assert len(stage.commands) == 1

    def test_run_command_sleep(self):
        runner = StageRunner()
        cmd = Command(cmd="sleep", args=["0"])
        result = runner.run_command(cmd)
        assert result["success"] is True

    def test_run_command_subprocess_success(self):
        runner = StageRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "hello\n"
            mock_run.return_value.stderr = ""
            cmd = Command(cmd="echo", args=["hello"])
            result = runner.run_command(cmd)
        assert result["success"] is True
        assert "hello" in result["output"]

    def test_run_command_expected_re(self):
        runner = StageRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "hello world\n"
            mock_run.return_value.stderr = ""
            cmd = Command(cmd="echo", args=["hello"], expected_re="world")
            result = runner.run_command(cmd)
        assert result["success"] is True

    def test_run_command_expected_re_fail(self):
        runner = StageRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "hello\n"
            mock_run.return_value.stderr = ""
            cmd = Command(cmd="echo", args=["hello"], expected_re="xyz")
            result = runner.run_command(cmd)
        assert result["success"] is False

    def test_run_command_wrong_exit_code(self):
        runner = StageRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            cmd = Command(cmd="echo", args=["hello"], expected_exit_code=1)
            result = runner.run_command(cmd)
        assert result["success"] is False

    def test_extract_tx_hash(self):
        runner = StageRunner()
        output = "Transaction hash: abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        result = runner._extract_tx_hash(output)
        assert result is not None

    def test_extract_tx_hash_none(self):
        runner = StageRunner()
        result = runner._extract_tx_hash("no hash here")
        assert result is None

    def test_validate_conditions(self):
        runner = StageRunner()
        conditions = {
            "ok": ExpectedCondition(type="value", value=True),
            "match": ExpectedCondition(type="regex", value="test"),
        }
        command_results = [
            {"success": True, "output": "ok: true\ntest output here", "exit_code": 0},
        ]
        result = runner.validate_conditions(conditions, command_results)
        assert result["ok"]["passed"] is True
        assert result["match"]["passed"] is True

    def test_run_stage(self):
        runner = StageRunner()
        with patch.object(runner, "run_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}
            stage = StageDefinition(
                stage=1,
                title="Test",
                commands=[Command(cmd="echo", args=["hello"])],
                expected={"ok": ExpectedCondition(type="value", value=True)},
            )
            result = runner.run_stage(stage)
        assert result["success"] is True
        assert result["stage"] == 1

    def test_run_stage_failure(self):
        runner = StageRunner()
        stage = StageDefinition(stage=1, title="Test", commands=[Command(cmd="false", args=[])], expected={})
        result = runner.run_stage(stage)
        assert result["success"] is False

    def test_create_example_stage_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        create_example_stage_json(path)
        with open(path) as f:
            data = json.load(f)
        assert data["stage"] == 1
