# Connection Pooling Implementation

## Overview
Added HTTP connection pooling to the `TSRAPIClient` for significantly improved performance when making multiple API requests.

## What Changed

### Before (Without Connection Pooling)
- Each API request created a new TCP connection
- Connection overhead (DNS lookup, TCP handshake, TLS handshake) for every request
- Slower batch processing
- Higher resource usage

### After (With Connection Pooling)
- Reuses existing HTTP connections across multiple requests
- Maintains a pool of persistent connections
- Significantly faster batch processing
- Lower resource usage and latency

## Technical Implementation

### Key Features

1. **Session-based Requests**
   - Uses `requests.Session()` instead of direct `requests.get/post()`
   - Maintains connection pool across multiple requests

2. **HTTPAdapter Configuration**
   ```python
   pool_connections=10   # Number of connection pools to cache
   pool_maxsize=20       # Max connections per pool
   ```

3. **Keep-Alive Headers**
   - Automatically sets `Connection: keep-alive`
   - Reuses TCP connections when possible

4. **Proper Resource Cleanup**
   - Context manager support (`with` statement)
   - Automatic cleanup on object destruction
   - Manual `close()` method

## Performance Benefits

### Expected Improvements
- **Batch Processing**: 30-50% faster for processing multiple records
- **Latency Reduction**: Eliminates connection overhead for subsequent requests
- **Resource Efficiency**: Fewer TCP connections = less memory and CPU usage

### Benchmarks (Estimated)
- **Without pooling**: ~500ms connection overhead per request
- **With pooling**: ~50ms for first request, ~10ms for subsequent requests

## Usage Examples

### Basic Usage (Automatic Cleanup)
```python
from app.api_client import TSRAPIClient

# Client automatically manages connection pool
client = TSRAPIClient(
    api_url="https://your-api.run.app",
    pool_maxsize=20  # Adjust based on concurrency needs
)

# Make multiple requests - connections are reused
for record in records:
    response = client.process_record(
        district=record['district'],
        taluka=record['taluka'],
        village=record['village'],
        survey_number=record['survey']
    )
```

### Context Manager (Recommended for Batch Processing)
```python
# Ensures proper cleanup even if errors occur
with TSRAPIClient(api_url="https://your-api.run.app") as client:
    for record in records:
        response = client.process_record(...)
# Session automatically closed when exiting context
```

### Manual Cleanup
```python
client = TSRAPIClient(api_url="https://your-api.run.app")
try:
    # Process records...
    response = client.process_record(...)
finally:
    client.close()  # Explicitly close session
```

## Configuration Parameters

### `pool_connections` (default: 10)
- Number of connection pools to cache
- One pool per unique host
- Increase if connecting to multiple different hosts

### `pool_maxsize` (default: 20)
- Maximum number of connections to save in each pool
- Should match or exceed your max concurrent requests
- For batch processing with 40 workers, consider setting to 40-50

### Recommended Settings by Use Case

**Single Record Processing**
```python
client = TSRAPIClient(
    api_url="...",
    pool_connections=1,
    pool_maxsize=5
)
```

**Batch Processing (Low Concurrency)**
```python
client = TSRAPIClient(
    api_url="...",
    pool_connections=5,
    pool_maxsize=10
)
```

**Batch Processing (High Concurrency - 40 workers)**
```python
client = TSRAPIClient(
    api_url="...",
    pool_connections=10,
    pool_maxsize=50  # Higher than worker count
)
```

## Integration with Streamlit Cloud App

The Streamlit Cloud app (`streamlit_app_cloud.py`) already uses `TSRAPIClient`. The connection pooling is automatically enabled with sensible defaults.

### Current Usage
```python
# In streamlit_app_cloud.py
st.session_state.api_client = TSRAPIClient(
    api_url=api_url,
    timeout=api_timeout,
    max_retries=max_retries
)
```

### Optimized for Batch Processing
```python
# For high-concurrency batch processing
st.session_state.api_client = TSRAPIClient(
    api_url=api_url,
    timeout=api_timeout,
    max_retries=max_retries,
    pool_connections=10,
    pool_maxsize=50  # Match or exceed max_workers
)
```

## Monitoring Connection Pool

### Logging
The client logs when the connection pool is initialized:
```
INFO: Initialized API client with connection pooling (pool_size=20)
```

### Debugging
To see connection reuse in action, enable debug logging:
```python
import logging
logging.getLogger('urllib3.connectionpool').setLevel(logging.DEBUG)
```

## Best Practices

1. **Reuse Client Instances**
   - Create one client instance and reuse it for multiple requests
   - Don't create a new client for each request

2. **Use Context Managers**
   - Ensures proper cleanup even if errors occur
   - Recommended for batch processing

3. **Tune Pool Size**
   - Set `pool_maxsize` based on your concurrency needs
   - Too small = connection creation overhead
   - Too large = wasted resources

4. **Close When Done**
   - Always close the client when finished
   - Use context manager or explicit `close()` call

## Troubleshooting

### Issue: "Connection pool is full"
**Solution**: Increase `pool_maxsize` to match your concurrency level

### Issue: "Too many open files"
**Solution**: Ensure you're closing clients properly. Use context managers.

### Issue: Slow first request
**Expected**: First request establishes connection. Subsequent requests are faster.

## Migration Guide

### Existing Code
No changes required! The connection pooling is backward compatible.

### To Optimize
1. Reuse client instances instead of creating new ones
2. Use context managers for batch processing
3. Tune pool size based on your workload

## References
- [Requests Session Documentation](https://requests.readthedocs.io/en/latest/user/advanced/#session-objects)
- [urllib3 Connection Pooling](https://urllib3.readthedocs.io/en/stable/advanced-usage.html#connection-pooling)
