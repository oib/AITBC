# Output Encoding

This guide covers output encoding, JSON serialization, and file download security.

## Encode Output

```python
import html

def encode_output(output: str) -> str:
    """Encode output to prevent XSS"""
    return html.escape(output)
```

## JSON Encoding

```python
import json

def safe_json_serialize(data: dict) -> str:
    """Safely serialize to JSON"""
    return json.dumps(data, default=str)
```

## File Download Security

```python
from pathlib import Path

def safe_file_download(file_path: Path) -> bool:
    """Validate file download request"""
    # Prevent directory traversal
    resolved_path = file_path.resolve()
    base_dir = Path("/safe/directory").resolve()

    if not str(resolved_path).startswith(str(base_dir)):
        return False

    # Check file extension
    allowed_extensions = {'.txt', '.json', '.csv'}
    if file_path.suffix not in allowed_extensions:
        return False

    return True
```

## See Also

- [Input Validation](input-validation.md) - Input sanitization
- [Web Security](web-security.md) - XSS prevention
- [Database Security](database-security.md) - Database protection
