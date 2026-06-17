# aitbc.api

API utilities for AITBC applications.

## Exports

### Response Helpers
- `success_response`, `error_response`, `not_found_response`
- `unauthorized_response`, `forbidden_response`
- `validation_error_response`, `conflict_response`, `internal_error_response`

### Pagination
- `APIResponse`, `PaginatedResponse`, `PaginationParams`
- `paginate_items`, `build_paginated_response`

### Headers
- `RateLimitHeaders`, `build_cors_headers`, `build_standard_headers`

### Utilities
- `validate_sort_field`, `build_sort_params`, `filter_fields`
- `get_client_ip`, `get_user_agent`, `build_request_metadata`

## Usage

```python
from aitbc.api import success_response, paginate_items
```
