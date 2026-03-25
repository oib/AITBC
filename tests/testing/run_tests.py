#!/usr/bin/env python3
"""
Wrapper script to run pytest with proper Python path configuration
"""

import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Add package source directories
sys.path.insert(0, str(project_root / "packages" / "py" / "aitbc-core" / "src"))
sys.path.insert(0, str(project_root / "packages" / "py" / "aitbc-crypto" / "src"))
sys.path.insert(0, str(project_root / "packages" / "py" / "aitbc-p2p" / "src"))
sys.path.insert(0, str(project_root / "packages" / "py" / "aitbc-sdk" / "src"))

# Add app source directories
sys.path.insert(0, str(project_root / "apps" / "coordinator-api" / "src"))
sys.path.insert(0, str(project_root / "apps" / "wallet-daemon" / "src"))
sys.path.insert(0, str(project_root / "apps" / "blockchain-node" / "src"))

# Run pytest with the original arguments
import pytest
sys.exit(pytest.main())
