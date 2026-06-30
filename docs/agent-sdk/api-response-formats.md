# Agent SDK - Response Format Standards

**Last Updated**: 2026-06-30
**Version**: 1.0

## Success Response

```json
{
    "success": true,
    "data": {...}
}
```

## Error Response

```json
{
    "success": false,
    "error": "Error description",
    "error_code": "ERROR_CODE"
}
```

## Pagination Response

```json
{
    "success": true,
    "data": [...],
    "total": 100,
    "limit": 50,
    "offset": 0
}
```

## Related Topics

- [Error Codes](./api-error-codes.md) - Error codes and rate limits
- [SDK Methods Reference](./api-sdk-methods.md) - SDK client methods
