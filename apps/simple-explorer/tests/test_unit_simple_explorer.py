"""Unit tests for simple explorer service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime


# Mock httpx before importing
sys.modules['httpx'] = Mock()

from main import app, BLOCKCHAIN_RPC_URL, HTML_TEMPLATE


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "Simple AITBC Explorer"
    assert app.version == "0.1.0"


@pytest.mark.unit
def test_blockchain_rpc_url():
    """Test that the blockchain RPC URL is configured"""
    assert BLOCKCHAIN_RPC_URL == "http://localhost:8025"


@pytest.mark.unit
def test_html_template_exists():
    """Test that the HTML template is defined"""
    assert HTML_TEMPLATE is not None
    assert "<!DOCTYPE html>" in HTML_TEMPLATE
    assert "AITBC Blockchain Explorer" in HTML_TEMPLATE


@pytest.mark.unit
def test_html_template_has_search():
    """Test that the HTML template has search functionality"""
    assert "search-input" in HTML_TEMPLATE
    assert "performSearch()" in HTML_TEMPLATE


@pytest.mark.unit
def test_html_template_has_blocks_section():
    """Test that the HTML template has blocks section"""
    assert "Latest Blocks" in HTML_TEMPLATE
    assert "blocks-list" in HTML_TEMPLATE


@pytest.mark.unit
def test_html_template_has_results_section():
    """Test that the HTML template has results section"""
    assert "Transaction Details" in HTML_TEMPLATE
    assert "tx-details" in HTML_TEMPLATE


@pytest.mark.unit
def test_html_template_has_tailwind():
    """Test that the HTML template includes Tailwind CSS"""
    assert "tailwindcss" in HTML_TEMPLATE


@pytest.mark.unit
def test_html_template_format_timestamp_function():
    """Test that the HTML template has formatTimestamp function"""
    assert "formatTimestamp" in HTML_TEMPLATE
    assert "toLocaleString" in HTML_TEMPLATE
