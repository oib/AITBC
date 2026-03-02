"""Tests for wallet commands using AITBC CLI"""

import pytest
import json
import re
import tempfile
import os
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.main import cli


def extract_json_from_output(output):
   