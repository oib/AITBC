"""Utility functions for AITBC CLI"""

import time
import logging
import sys
import os
from pathlib import Path
from typing import Any, Optional, Callable, Iterator
from contextlib import contextmanager
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
import json
import yaml
from tabulate import tabulate


console = Console()


@contextmanager
def progress_bar(description: str = "Working...", total: Optional[int] = None):
    """Context manager for progress bar display"""
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(description, total=total)
        yield progress, task


def progress_spinner(description: str = "Working..."):
    """Simple spinner for indeterminate operations"""
    return console.status(f"[bold blue]{description}")


class AuditLogger:
    """Audit logging for CLI operations"""
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or Path.home() / ".aitbc" / "audit"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "audit.jsonl"
    
    def log(self, action: str, details: dict = None, user: str = None):
        """Log an audit event"""
        import datetime
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "action": action,
            "user": user or os.environ.get("USER", "unknown"),
            "details": details or {}
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def get_logs(self, limit: int = 50, action_filter: str = None) -> list:
        """Read audit log entries"""
        if not self.log_file.exists():
            return []
        entries = []
        with open(self.log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    if action_filter and entry.get("action") != action_filter:
                        continue
                    entries.append(entry)
        return entries[-limit:]


def encrypt_value(value: str, key: str = None) -> str:
    """Simple XOR-based obfuscation for config values (not cryptographic security)"""
    import base64
    key = key or "aitbc_config_key_2026"
    encrypted = bytes([ord(c) ^ ord(key[i % len(key)]) for i, c in enumerate(value)])
    return base64.b64encode(encrypted).decode()


def decrypt_value(encrypted: str, key: str = None) -> str:
    """Decrypt an XOR-obfuscated config value"""
    import base64
    key = key or "aitbc_config_key_2026"
    data = base64.b64decode(encrypted)
    return ''.join(chr(b ^ ord(key[i % len(key)])) for i, b in enumerate(data))


def setup_logging(verbosity: int, debug: bool = False) -> str:
    """Setup logging with Rich"""
    log_level = "WARNING"
    
    if verbosity >= 3 or debug:
        log_level = "DEBUG"
    elif verbosity == 2:
        log_level = "INFO"
    elif verbosity == 1:
        log_level = "WARNING"
    
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )
    
    return log_level


def output(data: Any, format_type: str = "table"):
    """Format and output data"""
    if format_type == "json":
        console.print(json.dumps(data, indent=2, default=str))
    elif format_type == "yaml":
        console.print(yaml.dump(data, default_flow_style=False, sort_keys=False))
    elif format_type == "table":
        if isinstance(data, dict) and not isinstance(data, list):
            # Simple key-value table
            table = Table(show_header=False, box=None)
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="green")
            
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, default=str)
                table.add_row(str(key), str(value))
            
            console.print(table)
        elif isinstance(data, list) and data:
            if all(isinstance(item, dict) for item in data):
                # Table from list of dicts
                headers = list(data[0].keys())
                table = Table()
                
                for header in headers:
                    table.add_column(header, style="cyan")
                
                for item in data:
                    row = [str(item.get(h, "")) for h in headers]
                    table.add_row(*row)
                
                console.print(table)
            else:
                # Simple list
                for item in data:
                    console.print(f"• {item}")
        else:
            console.print(data)
    else:
        console.print(data)


def error(message: str):
    """Print error message"""
    console.print(Panel(f"[red]Error: {message}[/red]", title="❌"))


def success(message: str):
    """Print success message"""
    console.print(Panel(f"[green]{message}[/green]", title="✅"))


def warning(message: str):
    """Print warning message"""
    console.print(Panel(f"[yellow]{message}[/yellow]", title="⚠️"))


def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Retry function with exponential backoff
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retries
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch and retry on
    
    Returns:
        Result of function call
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                error(f"Max retries ({max_retries}) exceeded. Last error: {e}")
                raise
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            
            warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s...")
            time.sleep(delay)
    
    raise last_exception


def create_http_client_with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    timeout: float = 30.0
):
    """
    Create an HTTP client with retry capabilities
    
    Args:
        max_retries: Maximum number of retries
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        timeout: Request timeout in seconds
    
    Returns:
        httpx.Client with retry transport
    """
    import httpx
    
    class RetryTransport(httpx.Transport):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.max_retries = max_retries
            self.base_delay = base_delay
            self.max_delay = max_delay
            self.backoff_factor = 2.0
        
        def handle_request(self, request):
            last_exception = None
            
            for attempt in range(self.max_retries + 1):
                try:
                    return super().handle_request(request)
                except (httpx.NetworkError, httpx.TimeoutException) as e:
                    last_exception = e
                    
                    if attempt == self.max_retries:
                        break
                    
                    delay = min(
                        self.base_delay * (self.backoff_factor ** attempt),
                        self.max_delay
                    )
                    time.sleep(delay)
            
            raise last_exception
    
    return httpx.Client(
        transport=RetryTransport(),
        timeout=timeout
    )
