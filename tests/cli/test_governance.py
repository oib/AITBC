"""Tests for governance CLI commands"""

import json
import pytest
import shutil
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from aitbc_cli.commands.governance import governance


def extract_json_from_output(output_text):
    """Extract JSON from output that may contain Rich panels"""
    lines = output_text.strip().split('\n')
    json_lines = []
    in_json = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            in_json = True
        if in_json:
            json_lines.append(stripped)
        if in_json and (stripped.endswith('}') or stripped.endswith(']')):
            try:
                return json.loads('\n'.join(json_lines))
            except json.JSONDecodeError:
                continue
    if json_lines:
        return json.loads('\n'.join(json_lines))
    return json.loads(output_text)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.coordinator_url = "http://localhost:8000"
    config.api_key = "test_key"
    return config


@pytest.fixture
def governance_dir(tmp_path):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir()
    with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', gov_dir):
        yield gov_dir


class TestGovernanceCommands:

    def test_propose_general(self, runner, mock_config, governance_dir):
        """Test creating a general proposal"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            result = runner.invoke(governance, [
                'propose', 'Test Proposal',
                '--description', 'A test proposal',
                '--duration', '7'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code == 0
            data = extract_json_from_output(result.output)
            assert data['title'] == 'Test Proposal'
            assert data['type'] == 'general'
            assert data['status'] == 'active'
            assert 'proposal_id' in data

    def test_propose_parameter_change(self, runner, mock_config, governance_dir):
        """Test creating a parameter change proposal"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            result = runner.invoke(governance, [
                'propose', 'Change Block Size',
                '--description', 'Increase block size to 2MB',
                '--type', 'parameter_change',
                '--parameter', 'block_size',
                '--value', '2000000'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code == 0
            data = extract_json_from_output(result.output)
            assert data['type'] == 'parameter_change'

    def test_propose_funding(self, runner, mock_config, governance_dir):
        """Test creating a funding proposal"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            result = runner.invoke(governance, [
                'propose', 'Dev Fund',
                '--description', 'Fund development',
                '--type', 'funding',
                '--amount', '10000'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code == 0
            data = extract_json_from_output(result.output)
            assert data['type'] == 'funding'

    def test_vote_for(self, runner, mock_config, governance_dir):
        """Test voting for a proposal"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            # Create proposal
            result = runner.invoke(governance, [
                'propose', 'Vote Test',
                '--description', 'Test voting'
            ], obj={'config': mock_config, 'output_format': 'json'})
            proposal_id = extract_json_from_output(result.output)['proposal_id']

            # Vote
            result = runner.invoke(governance, [
                'vote', proposal_id, 'for',
                '--voter', 'alice'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code == 0
            data = extract_json_from_output(result.output)
            assert data['choice'] == 'for'
            assert data['voter'] == 'alice'
            assert data['current_tally']['for'] == 1.0

    def test_vote_against(self, runner, mock_config, governance_dir):
        """Test voting against a proposal"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            result = runner.invoke(governance, [
                'propose', 'Against Test',
                '--description', 'Test against'
            ], obj={'config': mock_config, 'output_format': 'json'})
            proposal_id = extract_json_from_output(result.output)['proposal_id']

            result = runner.invoke(governance, [
                'vote', proposal_id, 'against',
                '--voter', 'bob'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code == 0
            data = extract_json_from_output(result.output)
            assert data['choice'] == 'against'

    def test_vote_weighted(self, runner, mock_config, governance_dir):
        """Test weighted voting"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            result = runner.invoke(governance, [
                'propose', 'Weight Test',
                '--description', 'Test weights'
            ], obj={'config': mock_config, 'output_format': 'json'})
            proposal_id = extract_json_from_output(result.output)['proposal_id']

            result = runner.invoke(governance, [
                'vote', proposal_id, 'for',
                '--voter', 'whale', '--weight', '10.0'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code == 0
            data = extract_json_from_output(result.output)
            assert data['weight'] == 10.0
            assert data['current_tally']['for'] == 10.0

    def test_vote_duplicate_rejected(self, runner, mock_config, governance_dir):
        """Test that duplicate votes are rejected"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            result = runner.invoke(governance, [
                'propose', 'Dup Test',
                '--description', 'Test duplicate'
            ], obj={'config': mock_config, 'output_format': 'json'})
            proposal_id = extract_json_from_output(result.output)['proposal_id']

            runner.invoke(governance, [
                'vote', proposal_id, 'for', '--voter', 'alice'
            ], obj={'config': mock_config, 'output_format': 'json'})

            result = runner.invoke(governance, [
                'vote', proposal_id, 'for', '--voter', 'alice'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code != 0
            assert 'already voted' in result.output

    def test_vote_invalid_proposal(self, runner, mock_config, governance_dir):
        """Test voting on nonexistent proposal"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            result = runner.invoke(governance, [
                'vote', 'nonexistent', 'for'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code != 0
            assert 'not found' in result.output

    def test_list_proposals(self, runner, mock_config, governance_dir):
        """Test listing proposals"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            # Create two proposals
            runner.invoke(governance, [
                'propose', 'Prop A', '--description', 'First'
            ], obj={'config': mock_config, 'output_format': 'json'})
            runner.invoke(governance, [
                'propose', 'Prop B', '--description', 'Second'
            ], obj={'config': mock_config, 'output_format': 'json'})

            result = runner.invoke(governance, [
                'list'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 2

    def test_list_filter_by_status(self, runner, mock_config, governance_dir):
        """Test listing proposals filtered by status"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            runner.invoke(governance, [
                'propose', 'Active Prop', '--description', 'Active'
            ], obj={'config': mock_config, 'output_format': 'json'})

            result = runner.invoke(governance, [
                'list', '--status', 'active'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]['status'] == 'active'

    def test_result_command(self, runner, mock_config, governance_dir):
        """Test viewing proposal results"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            result = runner.invoke(governance, [
                'propose', 'Result Test',
                '--description', 'Test results'
            ], obj={'config': mock_config, 'output_format': 'json'})
            proposal_id = extract_json_from_output(result.output)['proposal_id']

            # Cast votes
            runner.invoke(governance, [
                'vote', proposal_id, 'for', '--voter', 'alice'
            ], obj={'config': mock_config, 'output_format': 'json'})
            runner.invoke(governance, [
                'vote', proposal_id, 'against', '--voter', 'bob'
            ], obj={'config': mock_config, 'output_format': 'json'})
            runner.invoke(governance, [
                'vote', proposal_id, 'for', '--voter', 'charlie'
            ], obj={'config': mock_config, 'output_format': 'json'})

            result = runner.invoke(governance, [
                'result', proposal_id
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code == 0
            data = extract_json_from_output(result.output)
            assert data['votes_for'] == 2.0
            assert data['votes_against'] == 1.0
            assert data['total_votes'] == 3.0
            assert data['voter_count'] == 3

    def test_result_invalid_proposal(self, runner, mock_config, governance_dir):
        """Test result for nonexistent proposal"""
        with patch('aitbc_cli.commands.governance.GOVERNANCE_DIR', governance_dir):
            result = runner.invoke(governance, [
                'result', 'nonexistent'
            ], obj={'config': mock_config, 'output_format': 'json'})

            assert result.exit_code != 0
            assert 'not found' in result.output
