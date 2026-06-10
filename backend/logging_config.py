"""
Logging configuration with JSON formatting
Structured logging for better observability
"""

import logging
import json
import sys
from datetime import datetime, timezone
from pythonjsonlogger import jsonlogger
from config import config

# ── Custom JSON Formatter ────────────────────────────────
class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields"""
    
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        
        # Add standard fields
        log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        
        # Add request ID if available
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
        
        # Remove duplicate fields
        if "message" in log_record:
            log_record["msg"] = log_record.pop("message")


# ── Root Logger Configuration ────────────────────────────────
def configure_logging():
    """Configure logging for the application"""
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(config.LOG_LEVEL)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler with JSON formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(logger)s %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Log initial message
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "mode": "PRODUCTION" if config.is_production() else "DEVELOPMENT",
            "log_level": config.LOG_LEVEL,
        }
    )
    
    return root_logger


# ── Logger Utilities ────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(name)


def log_with_context(logger: logging.Logger, level: str, msg: str, **context):
    """
    Log with additional context
    
    Args:
        logger: Logger instance
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        msg: Log message
        **context: Additional context fields
    """
    log_func = getattr(logger, level.lower())
    log_func(msg, extra=context)


# ── Request Logger ────────────────────────────────────
class RequestLogger:
    """Utility for logging HTTP requests and responses"""
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or get_logger(__name__)
    
    def log_request(self, method: str, path: str, request_id: str = None, **extra):
        """Log incoming request"""
        self.logger.info(
            f"Request started: {method} {path}",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                **extra
            }
        )
    
    def log_response(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        request_id: str = None,
        **extra
    ):
        """Log outgoing response"""
        level = "ERROR" if status_code >= 500 else "WARNING" if status_code >= 400 else "INFO"
        
        self.logger.log(
            getattr(logging, level),
            f"Request completed: {method} {path} {status_code}",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                **extra
            }
        )
    
    def log_error(self, msg: str, error: Exception, request_id: str = None, **extra):
        """Log error with full exception context"""
        self.logger.exception(
            msg,
            extra={
                "request_id": request_id,
                "error_type": type(error).__name__,
                "error_message": str(error),
                **extra
            }
        )