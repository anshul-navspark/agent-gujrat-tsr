"""
LLM API Call Logger for Gujarat TSR Agent.

Provides structured logging for all LLM API calls with support for:
- JSON format for machine parsing and monitoring
- Plain text format for human-readable debugging
- Configurable log levels and output destinations
"""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Union
from functools import wraps
from dataclasses import dataclass, field, asdict


# =============================================================================
# CONFIGURATION
# =============================================================================

# Environment variables for configuration
LLM_LOG_FORMAT = os.getenv('LLM_LOG_FORMAT', 'text')  # 'text' only (json removed)
LLM_LOG_LEVEL = os.getenv('LLM_LOG_LEVEL', 'INFO')
LLM_LOG_DIR = os.getenv('LLM_LOG_DIR', 'logs/llm')
LLM_LOG_PROMPTS = os.getenv('LLM_LOG_PROMPTS', 'false').lower() == 'true'  # Log full prompts (can be large)
LLM_LOG_RESPONSES = os.getenv('LLM_LOG_RESPONSES', 'false').lower() == 'true'  # Log full responses
LLM_LOG_MAX_CONTENT_LENGTH = int(os.getenv('LLM_LOG_MAX_CONTENT_LENGTH', '500'))  # Truncate content


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class LLMCallLog:
    """Structured log entry for an LLM API call."""
    
    # Request metadata
    call_id: str = ""
    timestamp: str = ""
    model_name: str = ""
    
    # Request details
    prompt_length: int = 0
    prompt_preview: str = ""  # First N chars of prompt
    estimated_input_tokens: int = 0
    
    # Response details
    response_length: int = 0
    response_preview: str = ""  # First N chars of response
    estimated_output_tokens: int = 0
    
    # Performance
    duration_ms: int = 0
    retry_count: int = 0
    
    # Status
    success: bool = True
    error_type: str = ""
    error_message: str = ""
    
    # Context
    caller_function: str = ""
    caller_file: str = ""
    
    # Optional: full content (if enabled)
    full_prompt: str = ""
    full_response: str = ""
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)
    
    def to_text(self) -> str:
        """Convert to human-readable text format."""
        lines = [
            "=" * 80,
            f"LLM API CALL: {self.call_id}",
            "=" * 80,
            f"Timestamp:      {self.timestamp}",
            f"Model:          {self.model_name}",
            f"Caller:         {self.caller_function} ({self.caller_file})",
            "-" * 40,
            f"PROMPT:",
            f"  Length:       {self.prompt_length} chars (~{self.estimated_input_tokens} tokens)",
        ]
        
        if self.prompt_preview:
            preview = self.prompt_preview.replace('\n', '\n                ')
            lines.append(f"  Preview:      {preview}...")
        
        lines.extend([
            "-" * 40,
            f"RESPONSE:",
            f"  Success:      {self.success}",
            f"  Duration:     {self.duration_ms} ms",
            f"  Retries:      {self.retry_count}",
        ])
        
        if self.success:
            lines.extend([
                f"  Length:       {self.response_length} chars (~{self.estimated_output_tokens} tokens)",
            ])
            if self.response_preview:
                preview = self.response_preview.replace('\n', '\n                ')
                lines.append(f"  Preview:      {preview}...")
        else:
            lines.extend([
                f"  Error Type:   {self.error_type}",
                f"  Error:        {self.error_message}",
            ])
        
        lines.append("=" * 80)
        return '\n'.join(lines)


# =============================================================================
# LOGGER SETUP
# =============================================================================

class LLMLogger:
    """Logger for LLM API calls with support for JSON and plain text output."""
    
    _instance: Optional['LLMLogger'] = None
    
    def __new__(cls):
        """Singleton pattern - only one logger instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._call_counter = 0
        
        # Create log directory
        self.log_dir = Path(LLM_LOG_DIR)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create date-based log files
        date_str = datetime.now().strftime('%Y%m%d')
        
        # JSON logger remove as per instruction
        # self.json_logger = logging.getLogger('llm.json') ...
        
        # Plain text logger
        self.text_logger = logging.getLogger('llm.text')
        self.text_logger.setLevel(logging.DEBUG)
        self.text_logger.handlers.clear()
        
        text_handler = logging.FileHandler(
            self.log_dir / f'llm_calls_{date_str}.log',
            encoding='utf-8'
        )
        text_handler.setFormatter(logging.Formatter('%(message)s'))
        self.text_logger.addHandler(text_handler)
        self.text_logger.propagate = False
        
        # Console logger for important events
        self.console_logger = logging.getLogger('llm.console')
        self.console_logger.setLevel(getattr(logging, LLM_LOG_LEVEL.upper(), logging.INFO))
        if not self.console_logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(
                '%(asctime)s - LLM - %(levelname)s - %(message)s'
            ))
            self.console_logger.addHandler(console_handler)
    
    def _generate_call_id(self) -> str:
        """Generate a unique call ID."""
        self._call_counter += 1
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{timestamp}_{self._call_counter:04d}"
    
    def log_call(self, log_entry: LLMCallLog):
        """Log an LLM API call entry."""
        log_format = LLM_LOG_FORMAT.lower()
        
        # JSON logging removed
        # if log_format in ('json', 'both'):
        #     pass
        
        if log_format in ('text', 'both'):
            self.text_logger.info(log_entry.to_text())
        
        # Console summary
        if log_entry.success:
            self.console_logger.info(
                f"[{log_entry.call_id}] {log_entry.model_name} - "
                f"{log_entry.duration_ms}ms - "
                f"~{log_entry.estimated_input_tokens + log_entry.estimated_output_tokens} tokens"
            )
        else:
            self.console_logger.error(
                f"[{log_entry.call_id}] {log_entry.model_name} FAILED - "
                f"{log_entry.error_type}: {log_entry.error_message[:100]}"
            )
    
    def create_log_entry(
        self,
        model_name: str,
        prompt: str,
        caller_function: str = "",
        caller_file: str = ""
    ) -> LLMCallLog:
        """Create a new log entry for an LLM call (before making the call)."""
        log_entry = LLMCallLog()
        log_entry.call_id = self._generate_call_id()
        log_entry.timestamp = datetime.now().isoformat()
        log_entry.model_name = model_name
        log_entry.prompt_length = len(prompt)
        log_entry.estimated_input_tokens = len(prompt) // 4
        log_entry.caller_function = caller_function
        log_entry.caller_file = caller_file
        
        # Preview (truncated)
        max_len = LLM_LOG_MAX_CONTENT_LENGTH
        log_entry.prompt_preview = prompt[:max_len] if len(prompt) > max_len else prompt
        
        # Full content if enabled
        if LLM_LOG_PROMPTS:
            log_entry.full_prompt = prompt
        
        return log_entry
    
    def finalize_log_entry(
        self,
        log_entry: LLMCallLog,
        response: Optional[str] = None,
        duration_ms: int = 0,
        retry_count: int = 0,
        error: Optional[Exception] = None
    ):
        """Finalize and log the entry after the LLM call completes."""
        log_entry.duration_ms = duration_ms
        log_entry.retry_count = retry_count
        
        if error:
            log_entry.success = False
            log_entry.error_type = type(error).__name__
            log_entry.error_message = str(error)
        elif response is not None:
            log_entry.success = True
            log_entry.response_length = len(response)
            log_entry.estimated_output_tokens = len(response) // 4
            
            # Preview (truncated)
            max_len = LLM_LOG_MAX_CONTENT_LENGTH
            log_entry.response_preview = response[:max_len] if len(response) > max_len else response
            
            # Full content if enabled
            if LLM_LOG_RESPONSES:
                log_entry.full_response = response
        
        self.log_call(log_entry)


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_llm_logger: Optional[LLMLogger] = None

def get_llm_logger() -> LLMLogger:
    """Get the singleton LLM logger instance."""
    global _llm_logger
    if _llm_logger is None:
        _llm_logger = LLMLogger()
    return _llm_logger


# =============================================================================
# DECORATOR FOR AUTOMATIC LOGGING
# =============================================================================

def log_llm_call(model_name_attr: str = "model", prompt_arg: str = "prompt"):
    """
    Decorator to automatically log LLM API calls.
    
    Args:
        model_name_attr: Attribute name on self that contains model name, or a literal string
        prompt_arg: Argument name that contains the prompt
    
    Example:
        @log_llm_call(model_name_attr="model_name", prompt_arg="prompt")
        def invoke(self, prompt: str):
            return self.llm.invoke(prompt)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            llm_logger = get_llm_logger()
            
            # Extract model name
            if args and hasattr(args[0], model_name_attr):
                model_name = getattr(args[0], model_name_attr)
            else:
                model_name = model_name_attr  # Use as literal if not found
            
            # Extract prompt from args or kwargs
            prompt = kwargs.get(prompt_arg, "")
            if not prompt and len(args) > 1:
                prompt = args[1] if isinstance(args[1], str) else str(args[1])
            
            # Create log entry
            log_entry = llm_logger.create_log_entry(
                model_name=model_name,
                prompt=prompt,
                caller_function=func.__name__,
                caller_file=func.__module__
            )
            
            start_time = time.time()
            error = None
            response_text = None
            
            try:
                result = func(*args, **kwargs)
                
                # Extract response text
                if hasattr(result, 'content'):
                    content = result.content
                    if isinstance(content, list):
                        response_text = ''.join(
                            part.get('text', str(part)) if isinstance(part, dict) else str(part)
                            for part in content
                        )
                    else:
                        response_text = str(content)
                else:
                    response_text = str(result)
                
                return result
            except Exception as e:
                error = e
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)
                llm_logger.finalize_log_entry(
                    log_entry=log_entry,
                    response=response_text,
                    duration_ms=duration_ms,
                    error=error
                )
        
        return wrapper
    return decorator


# =============================================================================
# HELPER FUNCTIONS FOR MANUAL LOGGING
# =============================================================================

def log_llm_request(model_name: str, prompt: str, caller: str = "") -> LLMCallLog:
    """
    Log the start of an LLM request.
    
    Returns a log entry that should be passed to log_llm_response() after the call.
    
    Example:
        log_entry = log_llm_request("gemini-3-pro", prompt, "extract_all_unified")
        try:
            response = llm.invoke(prompt)
            log_llm_response(log_entry, response=response.content)
        except Exception as e:
            log_llm_response(log_entry, error=e)
    """
    logger = get_llm_logger()
    return logger.create_log_entry(
        model_name=model_name,
        prompt=prompt,
        caller_function=caller,
        caller_file=""
    )


def log_llm_response(
    log_entry: LLMCallLog,
    response: Optional[str] = None,
    duration_ms: Optional[int] = None,
    retry_count: int = 0,
    error: Optional[Exception] = None,
    start_time: Optional[float] = None
):
    """
    Log the completion of an LLM request.
    
    Args:
        log_entry: The log entry returned by log_llm_request()
        response: The response text (if successful)
        duration_ms: Duration in milliseconds (or use start_time)
        retry_count: Number of retries performed
        error: Exception if the call failed
        start_time: Start timestamp (alternative to duration_ms)
    """
    if duration_ms is None and start_time is not None:
        duration_ms = int((time.time() - start_time) * 1000)
    elif duration_ms is None:
        duration_ms = 0
    
    logger = get_llm_logger()
    logger.finalize_log_entry(
        log_entry=log_entry,
        response=response,
        duration_ms=duration_ms,
        retry_count=retry_count,
        error=error
    )


# =============================================================================
# SUMMARY AND STATISTICS
# =============================================================================

def get_recent_calls_summary(limit: int = 10) -> Dict[str, Any]:
    """
    Get a summary of recent LLM calls from the log file.
    
    Returns:
        Dict with call statistics and recent entries
    """
    logger = get_llm_logger()
    date_str = datetime.now().strftime('%Y%m%d')
    json_log_path = logger.log_dir / f'llm_calls_{date_str}.json'
    
    if not json_log_path.exists():
        return {"error": "No log file found for today", "calls": []}
    
    calls = []
    total_duration = 0
    total_tokens = 0
    errors = 0
    
    try:
        with open(json_log_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        calls.append(entry)
                        total_duration += entry.get('duration_ms', 0)
                        total_tokens += entry.get('estimated_input_tokens', 0)
                        total_tokens += entry.get('estimated_output_tokens', 0)
                        if not entry.get('success', True):
                            errors += 1
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        return {"error": f"Failed to read log file: {e}", "calls": []}
    
    return {
        "total_calls": len(calls),
        "total_errors": errors,
        "error_rate": f"{(errors/len(calls)*100):.1f}%" if calls else "N/A",
        "total_duration_ms": total_duration,
        "avg_duration_ms": total_duration // len(calls) if calls else 0,
        "total_estimated_tokens": total_tokens,
        "recent_calls": calls[-limit:] if limit else calls
    }
