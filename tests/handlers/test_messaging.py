"""
Messaging Handler Tests
Tests for messaging contract handlers
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest
from handlers.messaging import (
    handle_messaging_deploy,
    handle_messaging_state,
    handle_messaging_topics,
    handle_messaging_create_topic,
    handle_messaging_messages,
    handle_messaging_post,
    handle_messaging_vote,
    handle_messaging_search,
    handle_messaging_reputation,
    handle_messaging_moderate,
)


class TestHandleMessagingDeploy:
    """Test handle_messaging_deploy function"""

    @patch('handlers.messaging.requests.post')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_deploy_success(self, mock_exit, mock_logger, mock_post):
        """Test successful messaging contract deployment"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"contract_address": "0x123", "status": "deployed"}
        mock_post.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_deploy(args, "http://localhost:8006", render_mapping)
        
        mock_post.assert_called_once()

    @patch('handlers.messaging.requests.post')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_deploy_http_error(self, mock_exit, mock_logger, mock_post):
        """Test messaging contract deployment with HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_deploy(args, "http://localhost:8006", render_mapping)
        
        mock_exit.assert_called_with(1)


class TestHandleMessagingState:
    """Test handle_messaging_state function"""

    @patch('handlers.messaging.requests.get')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_state_json(self, mock_exit, mock_logger, mock_get):
        """Test messaging state query with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"topics": 10, "messages": 100}
        mock_get.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        
        def output_format(args):
            return "json"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_state(args, "http://localhost:8006", output_format, render_mapping)
        
        mock_get.assert_called_once()

    @patch('handlers.messaging.requests.get')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_state_text(self, mock_exit, mock_logger, mock_get):
        """Test messaging state query with text output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"topics": 10, "messages": 100}
        mock_get.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        
        def output_format(args):
            return "text"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_state(args, "http://localhost:8006", output_format, render_mapping)
        
        mock_get.assert_called_once()


class TestHandleMessagingTopics:
    """Test handle_messaging_topics function"""

    @patch('handlers.messaging.requests.get')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_topics_json(self, mock_exit, mock_logger, mock_get):
        """Test topics query with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"topic_id": 1, "title": "Topic 1"}]
        mock_get.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        
        def output_format(args):
            return "json"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_topics(args, "http://localhost:8006", output_format, render_mapping)
        
        mock_get.assert_called_once()

    @patch('handlers.messaging.requests.get')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_topics_text(self, mock_exit, mock_logger, mock_get):
        """Test topics query with text output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"topic_id": 1, "title": "Topic 1"}]
        mock_get.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        
        def output_format(args):
            return "text"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_topics(args, "http://localhost:8006", output_format, render_mapping)
        
        mock_get.assert_called_once()


class TestHandleMessagingCreateTopic:
    """Test handle_messaging_create_topic function"""

    @patch('handlers.messaging.requests.post')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_create_topic_success(self, mock_exit, mock_logger, mock_post):
        """Test successful topic creation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"topic_id": 1, "title": "New Topic"}
        mock_post.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.title = "New Topic"
        args.content = "Topic content"
        args.wallet = None
        args.password_file = None
        
        def read_password(args):
            return "password"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_create_topic(args, "http://localhost:8006", read_password, render_mapping)
        
        mock_post.assert_called_once()

    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_create_topic_missing_params(self, mock_exit, mock_logger):
        """Test topic creation with missing parameters"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.title = None
        args.content = None
        args.wallet = None
        args.password_file = None
        
        def read_password(args):
            return "password"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_create_topic(args, "http://localhost:8006", read_password, render_mapping)
        
        mock_exit.assert_called_with(1)


class TestHandleMessagingMessages:
    """Test handle_messaging_messages function"""

    @patch('handlers.messaging.requests.get')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_messages_json(self, mock_exit, mock_logger, mock_get):
        """Test messages query with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"message_id": 1, "author": "user1"}]
        mock_get.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.topic_id = 1
        
        def output_format(args):
            return "json"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_messages(args, "http://localhost:8006", output_format, render_mapping)
        
        mock_get.assert_called_once()

    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_messages_missing_topic_id(self, mock_exit, mock_logger):
        """Test messages query with missing topic ID"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.topic_id = None
        
        def output_format(args):
            return "json"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_messages(args, "http://localhost:8006", output_format, render_mapping)
        
        mock_exit.assert_called_with(1)


class TestHandleMessagingPost:
    """Test handle_messaging_post function"""

    @patch('handlers.messaging.requests.post')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_post_success(self, mock_exit, mock_logger, mock_post):
        """Test successful message posting"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message_id": 1, "content": "Posted"}
        mock_post.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.topic_id = 1
        args.content = "Message content"
        args.wallet = None
        args.password_file = None
        
        def read_password(args):
            return "password"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_post(args, "http://localhost:8006", read_password, render_mapping)
        
        mock_post.assert_called_once()

    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_post_missing_params(self, mock_exit, mock_logger):
        """Test message posting with missing parameters"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.topic_id = None
        args.content = None
        args.wallet = None
        args.password_file = None
        
        def read_password(args):
            return "password"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_post(args, "http://localhost:8006", read_password, render_mapping)
        
        mock_exit.assert_called_with(1)


class TestHandleMessagingVote:
    """Test handle_messaging_vote function"""

    @patch('handlers.messaging.requests.post')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_vote_success(self, mock_exit, mock_logger, mock_post):
        """Test successful voting"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message_id": 1, "vote": "up"}
        mock_post.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.message_id = 1
        args.vote = "up"
        args.wallet = None
        args.password_file = None
        
        def read_password(args):
            return "password"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_vote(args, "http://localhost:8006", read_password, render_mapping)
        
        mock_post.assert_called_once()

    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_vote_missing_params(self, mock_exit, mock_logger):
        """Test voting with missing parameters"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.message_id = None
        args.vote = None
        args.wallet = None
        args.password_file = None
        
        def read_password(args):
            return "password"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_vote(args, "http://localhost:8006", read_password, render_mapping)
        
        mock_exit.assert_called_with(1)


class TestHandleMessagingSearch:
    """Test handle_messaging_search function"""

    @patch('handlers.messaging.requests.get')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_search_json(self, mock_exit, mock_logger, mock_get):
        """Test message search with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"message_id": 1, "content": "match"}]
        mock_get.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.query = "search term"
        
        def output_format(args):
            return "json"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_search(args, "http://localhost:8006", output_format, render_mapping)
        
        mock_get.assert_called_once()

    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_search_missing_query(self, mock_exit, mock_logger):
        """Test message search with missing query"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.query = None
        
        def output_format(args):
            return "json"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_search(args, "http://localhost:8006", output_format, render_mapping)
        
        mock_exit.assert_called_with(1)


class TestHandleMessagingReputation:
    """Test handle_messaging_reputation function"""

    @patch('handlers.messaging.requests.get')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_reputation_json(self, mock_exit, mock_logger, mock_get):
        """Test reputation query with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"agent_id": "agent1", "score": 100}
        mock_get.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.agent_id = "agent1"
        
        def output_format(args):
            return "json"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_reputation(args, "http://localhost:8006", output_format, render_mapping)
        
        mock_get.assert_called_once()

    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_reputation_missing_agent_id(self, mock_exit, mock_logger):
        """Test reputation query with missing agent ID"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.agent_id = None
        
        def output_format(args):
            return "json"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_reputation(args, "http://localhost:8006", output_format, render_mapping)
        
        mock_exit.assert_called_with(1)


class TestHandleMessagingModerate:
    """Test handle_messaging_moderate function"""

    @patch('handlers.messaging.requests.post')
    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_moderate_success(self, mock_exit, mock_logger, mock_post):
        """Test successful moderation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message_id": 1, "action": "approve"}
        mock_post.return_value = mock_response
        
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.message_id = 1
        args.action = "approve"
        args.wallet = None
        args.password_file = None
        
        def read_password(args):
            return "password"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_moderate(args, "http://localhost:8006", read_password, render_mapping)
        
        mock_post.assert_called_once()

    @patch('handlers.messaging.logger')
    @patch('sys.exit')
    def test_handle_messaging_moderate_missing_params(self, mock_exit, mock_logger):
        """Test moderation with missing parameters"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.message_id = None
        args.action = None
        args.wallet = None
        args.password_file = None
        
        def read_password(args):
            return "password"
        
        def render_mapping(title, data):
            pass
        
        handle_messaging_moderate(args, "http://localhost:8006", read_password, render_mapping)
        
        mock_exit.assert_called_with(1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
