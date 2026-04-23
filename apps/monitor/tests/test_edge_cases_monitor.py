"""Edge case and error handling tests for monitor service"""

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
def test_json_decode_error_handling():
    """Test JSON decode error is handled correctly"""
    with patch('monitor.logging') as mock_logging, \
         patch('monitor.time.sleep', side_effect=[None, KeyboardInterrupt]), \
         patch('monitor.Path') as mock_path, \
         patch('builtins.open', mock_open(read_data='invalid json{')):
        
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
        
        # Verify error was logged
        error_calls = [call for call in logger.error.call_args_list if 'JSONDecodeError' in str(call)]
        assert len(error_calls) > 0


@pytest.mark.unit
def test_file_not_found_error_handling():
    """Test FileNotFoundError is handled correctly"""
    with patch('monitor.logging') as mock_logging, \
         patch('monitor.time.sleep', side_effect=[None, KeyboardInterrupt]), \
         patch('monitor.Path') as mock_path, \
         patch('builtins.open', side_effect=FileNotFoundError("File not found")):
        
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
        
        # Verify error was logged
        error_calls = [call for call in logger.error.call_args_list if 'FileNotFoundError' in str(call)]
        assert len(error_calls) > 0


@pytest.mark.unit
def test_permission_error_handling():
    """Test PermissionError is handled correctly"""
    with patch('monitor.logging') as mock_logging, \
         patch('monitor.time.sleep', side_effect=[None, KeyboardInterrupt]), \
         patch('monitor.Path') as mock_path, \
         patch('builtins.open', side_effect=PermissionError("Permission denied")):
        
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
        
        # Verify error was logged
        error_calls = [call for call in logger.error.call_args_list if 'PermissionError' in str(call)]
        assert len(error_calls) > 0


@pytest.mark.unit
def test_io_error_handling():
    """Test IOError is handled correctly"""
    with patch('monitor.logging') as mock_logging, \
         patch('monitor.time.sleep', side_effect=[None, KeyboardInterrupt]), \
         patch('monitor.Path') as mock_path, \
         patch('builtins.open', side_effect=IOError("I/O error")):
        
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
        
        # Verify error was logged
        error_calls = [call for call in logger.error.call_args_list if 'IOError' in str(call) or 'OSError' in str(call)]
        assert len(error_calls) > 0


@pytest.mark.unit
def test_psutil_error_handling():
    """Test psutil.Error is handled correctly"""
    with patch('monitor.logging') as mock_logging, \
         patch('monitor.time.sleep', side_effect=[None, KeyboardInterrupt]), \
         patch('monitor.psutil.cpu_percent', side_effect=PsutilError("psutil error")):
        
        logger = mock_logging.getLogger.return_value
        mock_logging.basicConfig.return_value = None
        
        try:
            monitor.main()
        except KeyboardInterrupt:
            pass
        
        # Verify error was logged
        error_calls = [call for call in logger.error.call_args_list if 'psutil error' in str(call)]
        assert len(error_calls) > 0


@pytest.mark.unit
def test_empty_blocks_array():
    """Test handling of empty blocks array in blockchain data"""
    with patch('monitor.logging') as mock_logging, \
         patch('monitor.time.sleep', side_effect=KeyboardInterrupt), \
         patch('monitor.Path') as mock_path, \
         patch('builtins.open', mock_open(read_data='{"blocks": []}')):
        
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
        
        # Verify blockchain stats were logged with 0 blocks
        blockchain_calls = [call for call in logger.info.call_args_list if 'Blockchain' in str(call)]
        assert len(blockchain_calls) > 0
        assert '0 blocks' in str(blockchain_calls[0])


@pytest.mark.unit
def test_missing_blocks_key():
    """Test handling of missing blocks key in blockchain data"""
    with patch('monitor.logging') as mock_logging, \
         patch('monitor.time.sleep', side_effect=KeyboardInterrupt), \
         patch('monitor.Path') as mock_path, \
         patch('builtins.open', mock_open(read_data='{"height": 100}')):
        
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
        
        # Verify blockchain stats were logged with 0 blocks (default)
        blockchain_calls = [call for call in logger.info.call_args_list if 'Blockchain' in str(call)]
        assert len(blockchain_calls) > 0
        assert '0 blocks' in str(blockchain_calls[0])
