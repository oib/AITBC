"""Utility functions for AITBC CLI"""

import time
import logging
import sys
import os
from pathlib import Path
from typing import Tuple, List, Dict, Optional, Any
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
    """Tamper-evident audit logging for CLI operations"""
    
    def __init__(self, log_dir: Optional[Path] = None):
        # Import secure audit logger
        from .secure_audit import SecureAuditLogger
        self._secure_logger = SecureAuditLogger(log_dir)
    
    def log(self, action: str, details: dict = None, user: str = None):
        """Log an audit event with cryptographic integrity"""
        self._secure_logger.log(action, details, user)
    
    def get_logs(self, limit: int = 50, action_filter: str = None) -> list:
        """Read audit log entries with integrity verification"""
        return self._secure_logger.get_logs(limit, action_filter)
    
    def verify_integrity(self) -> Tuple[bool, List[str]]:
        """Verify audit log integrity"""
        return self._secure_logger.verify_integrity()
    
    def export_report(self, output_file: Optional[Path] = None) -> Dict:
        """Export comprehensive audit report"""
        return self._secure_logger.export_audit_report(output_file)
    
    def search_logs(self, query: str, limit: int = 50) -> List[Dict]:
        """Search audit logs"""
        return self._secure_logger.search_logs(query, limit)


def _get_fernet_key(key: str = None) -> bytes:
    """Derive a Fernet key from a password using Argon2 KDF"""
    from cryptography.fernet import Fernet
    import base64
    import secrets
    import getpass
    
    if key is None:
        # CRITICAL SECURITY FIX: Never use hardcoded keys
        # Always require user to provide a password or generate a secure random key
        error("❌ CRITICAL: No encryption key provided. This is a security vulnerability.")
        error("Please provide a password for encryption.")
        key = getpass.getpass("Enter encryption password: ")
        
        if not key:
            error("❌ Password cannot be empty for encryption operations.")
            raise ValueError("Encryption password is required")
    
    # Use Argon2 for secure key derivation (replaces insecure SHA-256)
    try:
        from argon2 import PasswordHasher
        from argon2.exceptions import VerifyMismatchError
        
        # Generate a secure salt
        salt = secrets.token_bytes(16)
        
        # Derive key using Argon2
        ph = PasswordHasher(
            time_cost=3,      # Number of iterations
            memory_cost=65536,  # Memory usage in KB
            parallelism=4,   # Number of parallel threads
            hash_len=32,     # Output hash length
            salt_len=16      # Salt length
        )
        
        # Hash the password to get a 32-byte key
        hashed_key = ph.hash(key + salt.decode('utf-8'))
        
        # Extract the hash part and convert to bytes suitable for Fernet
        key_bytes = hashed_key.encode('utf-8')[:32]
        
        # Ensure we have exactly 32 bytes for Fernet
        if len(key_bytes) < 32:
            key_bytes += secrets.token_bytes(32 - len(key_bytes))
        elif len(key_bytes) > 32:
            key_bytes = key_bytes[:32]
        
        return base64.urlsafe_b64encode(key_bytes)
        
    except ImportError:
        # Fallback to PBKDF2 if Argon2 is not available
        import hashlib
        import hmac
        
        warning("⚠️ Argon2 not available, falling back to PBKDF2 (less secure)")
        
        # Generate a secure salt
        salt = secrets.token_bytes(16)
        
        # Use PBKDF2 with SHA-256 (better than plain SHA-256)
        key_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            key.encode('utf-8'),
            salt,
            100000,  # 100k iterations
            32       # 32-byte key
        )
        
        return base64.urlsafe_b64encode(key_bytes)


def encrypt_value(value: str, key: str = None) -> str:
    """Encrypt a value using Fernet symmetric encryption"""
    from cryptography.fernet import Fernet
    import base64
    
    fernet_key = _get_fernet_key(key)
    f = Fernet(fernet_key)
    encrypted = f.encrypt(value.encode())
    return base64.b64encode(encrypted).decode()


def decrypt_value(encrypted: str, key: str = None) -> str:
    """Decrypt a Fernet-encrypted value"""
    from cryptography.fernet import Fernet
    import base64
    
    fernet_key = _get_fernet_key(key)
    f = Fernet(fernet_key)
    data = base64.b64decode(encrypted)
    return f.decrypt(data).decode()


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


def render(data: Any, format_type: str = "table", title: str = None):
    """Format and output data"""
    if format_type == "json":
        console.print(json.dumps(data, indent=2, default=str))
    elif format_type == "yaml":
        console.print(yaml.dump(data, default_flow_style=False, sort_keys=False))
    elif format_type == "table":
        if isinstance(data, dict) and not isinstance(data, list):
            # Simple key-value table
            table = Table(show_header=False, box=None, title=title)
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


# Backward compatibility alias
def output(data: Any, format_type: str = "table", title: str = None):
    """Deprecated: use render() instead - kept for backward compatibility"""
    return render(data, format_type, title)


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
                    response = super().handle_request(request)
                    
                    # Check for retryable HTTP status codes
                    if hasattr(response, 'status_code'):
                        retryable_codes = {429, 502, 503, 504}
                        if response.status_code in retryable_codes:
                            last_exception = httpx.HTTPStatusError(
                                f"Retryable status code {response.status_code}",
                                request=request,
                                response=response
                            )
                            
                            if attempt == self.max_retries:
                                break
                            
                            delay = min(
                                self.base_delay * (self.backoff_factor ** attempt),
                                self.max_delay
                            )
                            time.sleep(delay)
                            continue
                    
                    return response
                    
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
