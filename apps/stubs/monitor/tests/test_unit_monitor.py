"""Unit tests for monitor service"""

import sys
import pytest
import sys
from unittest.mock import Mock, patch, MagicMock, mock_open
from pathlib import Path
import json

# Create a proper psutil mock with Error exception class
class PsutilError(Exception):
    pass

mock_psutil = MagicMock()
mock_psutil.cpu_percent = Mock(return_value=45.5)
mock_psutil.virtual_memory = Mock(return_value=MagicMock(percent=60.2))
mock_psutil.Error = PsutilError
sys.modules['psutil'] = mock_psutil

import monitor


@pytest.mark.unit
def test_main_system_stats_logging():
    """Test that system stats are logged correctly"""
    with patch('monitor.logging') as mock_logging, \
         patch('monitor.time.sleep', side_effect=KeyboardInterrupt), \
         patch('monitor.Path') as mock_path:
        
        mock_path.return_value.exists.return_value = False
        
        logger = mock_logging.getLogger.return_value
        mock_logging.basicConfig.return_value = None
        
        try:
            monitor.main()
        except KeyboardInterrupt:
            pass
        
        # Verify system stats were logged
        assert logger.info.call_count >= 1
        system_call = logger.info.call_args_list[0]
        assert 'CPU 45.5%' in str(system_call)
        assert 'Memory 60.2%' in str(system_call)


@pytest.mark.unit
def test_main_blockchain_stats_logging():
    """Test that blockchain stats are logged when file exists"""
    with patch('monitor.logging') as mock_logging, \
         patch('monitor.time.sleep', side_effect=KeyboardInterrupt), \
         patch('monitor.Path') as mock_path, \
         patch('builtins.open', mock_open(read_data='{"blocks": [{"height": 1}, {"height": 2}]}')):
        
        # Mock blockchain file exists
        blockchain_path = Mock()
        blockchain_path.exists.return_value = True
        marketplace_path = Mock()
        marketplace_path.exists.return_value = False
        
        mock_path.side_effect = lambda x: blockchain_path if 'blockchain' in str(x) else marketplace_path
        
        logger = mock_logging.getLogger.return_value
        mock_logging.basicConfig.return_value = None
        
        try:
            monitor.main()
        except KeyboardInterrupt:
            pass
        
        # Verify blockchain stats were logged
        blockchain_calls = [call for call in logger.info.call_args_list if 'Blockchain' in str(call)]
        assert len(blockchain_calls) > 0
        assert '2 blocks' in str(blockchain_calls[0])


@pytest.mark.unit
def test_main_marketplace_stats_logging():
    """Test that marketplace stats are logged when file exists"""
    with patch('monitor.logging') as mock_logging, \
         patch('monitor.time.sleep', side_effect=KeyboardInterrupt), \
         patch('monitor.Path') as mock_path, \
         patch('builtins.open', mock_open(read_data='[{"id": 1, "gpu": "rtx3080"}, {"id": 2, "gpu": "rtx3090"}]')):
        
        # Mock blockchain file doesn't exist, marketplace does
        blockchain_path = Mock()
        blockchain_path.exists.return_value = False
        marketplace_path = Mock()
        marketplace_path.exists.return_value = True
        listings_file = Mock()
        listings_file.exists.return_value = True
        listings_file.__truediv__ = Mock(return_value=listings_file)
        marketplace_path.__truediv__ = Mock(return_value=listings_file)
        
        mock_path.side_effect = lambda x: listings_file if 'gpu_listings' in str(x) else (marketplace_path if 'marketplace' in str(x) else blockchain_path)
        
        logger = mock_logging.getLogger.return_value
        mock_logging.basicConfig.return_value = None
        
        try:
            monitor.main()
        except KeyboardInterrupt:
            pass
        
        # Verify marketplace stats were logged
        marketplace_calls = [call for call in logger.info.call_args_list if 'Marketplace' in str(call)]
        assert len(marketplace_calls) > 0
        assert '2 GPU listings' in str(marketplace_calls[0])
