# LLM Logging System

This system provides comprehensive logging for all LLM API calls made by the Gujarat TSR Agent.

## Features
- **JSON Logs**: Machine-readable logs for parsing and monitoring (`logs/llm/llm_calls_YYYYMMDD.json`)
- **Text Logs**: Human-readable logs for debugging (`logs/llm/llm_calls_YYYYMMDD.log`)
- **Console Output**: Live activity summary in the console

## Log Location
Logs are stored in `logs/llm/` by default. Files are rotated daily.

## Configuration
You can configure the logger using environment variables in your `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_LOG_DIR` | `logs/llm` | Directory where logs are stored |
| `LLM_LOG_FORMAT` | `both` | Output format: `json`, `text`, or `both` |
| `LLM_LOG_LEVEL` | `INFO` | Logging level |
| `LLM_LOG_PROMPTS` | `false` | Set to `true` to log the full prompt content |
| `LLM_LOG_RESPONSES` | `false` | Set to `true` to log the full response content |
| `LLM_LOG_MAX_CONTENT_LENGTH` | `500` | Max characters to show in preview/text logs |

## Usage in Code

To log LLM calls in new modules:

```python
from utils.llm_logger import log_llm_request, log_llm_response

# 1. Log Request (Before call)
log_entry = log_llm_request(
    model_name="gemini-1.5-pro", 
    prompt="Extract land details...",
    caller="my_function_name"
)

try:
    # 2. Make Call
    response = llm.invoke(prompt)
    
    # 3. Log Response (After success)
    log_llm_response(log_entry, response=response.content)
    
except Exception as e:
    # 4. Log Error (After failure)
    log_llm_response(log_entry, error=e)
```
