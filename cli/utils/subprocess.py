import subprocess
import sys
from typing import List, Optional, Union, Any
from . import error, output

def run_subprocess(cmd: List[str], check: bool = True, capture_output: bool = True, shell: bool = False, **kwargs: Any) -> Optional[Union[str, subprocess.CompletedProcess]]:
    """Run a subprocess command safely with logging"""
    try:
        # Always use shell=False for security
        result = subprocess.run(cmd, check=check, capture_output=capture_output, text=True, shell=False, **kwargs)
        
        if capture_output:
            return result.stdout.strip()
        return result
        
    except subprocess.CalledProcessError as e:
        error(f"Command failed with exit code {e.returncode}")
        if capture_output and getattr(e, 'stderr', None):
            print(e.stderr, file=sys.stderr)
        if check:
            sys.exit(e.returncode)
        return getattr(e, 'stdout', None) if capture_output else None
    except Exception as e:
        error(f"Failed to execute command: {e}")
        if check:
            sys.exit(1)
        return None
