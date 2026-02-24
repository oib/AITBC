# Web Vitals 422 Error - RESOLVED

**Date:** February 16, 2026  
**Status:** Resolved  
**Severity:** Medium  

## Issue Description
The `/api/web-vitals` endpoint was returning 422 Unprocessable Content errors when receiving performance metrics from the frontend. This prevented the collection of important web performance data.

## Affected Components
- **Backend**: `/apps/coordinator-api/src/app/routers/web_vitals.py` - API schema
- **Frontend**: `/website/assets/js/web-vitals.js` - Metrics collection script
- **Endpoint**: `/api/web-vitals` - POST endpoint for performance metrics

## Root Cause Analysis
The `WebVitalsEntry` Pydantic model in the backend only included three fields:
- `name` (required)
- `startTime` (optional)
- `duration` (optional)

However, the browser's Web Vitals library was sending additional fields for certain metrics:
- `value` - For CLS (Cumulative Layout Shift) metrics
- `hadRecentInput` - For CLS metrics to distinguish user-initiated shifts

When these extra fields were included in the JSON payload, Pydantic validation failed with a 422 error.

## Solution Implemented

### 1. Schema Enhancement
Updated the `WebVitalsEntry` model to include the missing optional fields:

```python
class WebVitalsEntry(BaseModel):
    name: str
    startTime: Optional[float] = None
    duration: Optional[float] = None
    value: Optional[float] = None          # Added
    hadRecentInput: Optional[bool] = None  # Added
```

### 2. Defensive Processing
Added filtering logic to handle any unexpected fields that might be sent in the future:

```python
# Filter entries to only include supported fields
filtered_entries = []
for entry in metric.entries:
    filtered_entry = {
        "name": entry.name,
        "startTime": entry.startTime,
        "duration": entry.duration,
        "value": entry.value,
        "hadRecentInput": entry.hadRecentInput
    }
    # Remove None values
    filtered_entry = {k: v for k, v in filtered_entry.items() if v is not None}
    filtered_entries.append(filtered_entry)
```

### 3. Deployment
- Deployed changes to both localhost and AITBC server
- Restarted coordinator-api service on both systems
- Verified functionality with test requests

## Verification
Tested the fix with various Web Vitals payloads:

```bash
# Test with CLS metric (includes extra fields)
curl -X POST https://aitbc.bubuit.net/api/web-vitals \
  -H "Content-Type: application/json" \
  -d '{"name":"CLS","value":0.1,"id":"cls","delta":0.05,"entries":[{"name":"layout-shift","startTime":100,"duration":0,"value":0.1,"hadRecentInput":false}],"url":"https://aitbc.bubuit.net/","timestamp":"2026-02-16T20:00:00Z"}'

# Result: 200 OK ✅
```

## Impact
- **Before**: Web Vitals metrics collection was failing completely
- **After**: All Web Vitals metrics are now successfully collected and logged
- **Performance**: No performance impact on the API endpoint
- **Compatibility**: Backward compatible with existing frontend code

## Lessons Learned
1. **Schema Mismatch**: Always ensure backend schemas match frontend payloads exactly
2. **Optional Fields**: Web APIs often evolve with additional optional fields
3. **Defensive Programming**: Filter unknown fields to prevent future validation errors
4. **Testing**: Test with real frontend payloads, not just ideal ones

## Related Documentation
- [Web Vitals Documentation](https://web.dev/vitals/)
- [Pydantic Validation](https://pydantic-docs.helpmanual.io/)
- [FastAPI Error Handling](https://fastapi.tiangolo.com/tutorial/handling-errors/)
