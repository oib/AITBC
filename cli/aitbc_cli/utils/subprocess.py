import subprocess
import sys
from typing import List, Optional, Union
from . import error, output

def run_subprocess(cmd: List[str], check: bool = True, capture_output: bool = True, shell: bool = False) -> Optional[str]:
    """Run a subprocess command safely with logging"""
    try:
        if shell:
            # When shell=True, cmd should be a string
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            result = subprocess.run(cmd_str, shell=True, check=check, capture_output=capture_output, text=True)
        else:
            result = subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
            
        if capture_output:
            return result.stdout.strip()
        return None
        
    except subprocess.CalledProcessError as e:
        error(f"Command failed with exit code {e.returncode}")
        if capture_output and e.stderr:
            print(e.stderr, file=sys.stderr)
        if check:
            sys.exit(e.returncode)
        return None
    except Exception as e:
        error(f"Failed to execute command: {e}")
        if check:
            sys.exit(1)
        return None
