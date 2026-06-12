"""
Resilience patterns: exponential backoff, retry logic, and circuit breaker
for external API calls (Groq, Typesense).

Used by: search.py, sync_manage.py, main.py
"""

import logging
import time
from functools import wraps
from typing import Callable, Any, Type, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states (Pure Enumeration)"""
    CLOSED = "CLOSED"           # Normal operation
    OPEN = "OPEN"               # Failing, reject requests
    HALF_OPEN = "HALF_OPEN"     # Testing if service recovered


class CircuitBreaker:
    """Manages circuit breaker lifecycle and state transitions."""
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Type[Exception] = Exception
    ):
        self.breaker_name = name  # Avoids conflict with Python internals
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with circuit breaker protection."""
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout elapsed
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info(f"🔄 {self.breaker_name}: Attempting recovery (HALF_OPEN)")
                self.state = CircuitState.HALF_OPEN
            else:
                raise Exception(f"Circuit breaker OPEN for {self.breaker_name} — service unavailable")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Called after successful execution."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info(f"✅ {self.breaker_name}: Recovery successful (CLOSED)")
        self.failure_count = 0
        self.state = CircuitState.CLOSED
    
    def _on_failure(self):
        """Called after a failure."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            logger.error(f"🔌 {self.breaker_name}: Circuit breaker OPEN (failures: {self.failure_count})")
            self.state = CircuitState.OPEN


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 32.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Decorator for exponential backoff with jitter.
    
    Retries a function on failure with exponential delays:
    - Attempt 1: ~1s (base_delay)
    - Attempt 2: ~2s (base_delay * exponential_base)
    - Attempt 3: ~4s (base_delay * exponential_base^2)
    - ...
    - Jitter: ±20% random variation to prevent thundering herd
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(
                            f"❌ {func.__name__}: Failed after {max_retries} attempts. "
                            f"Error: {str(e)[:100]}"
                        )
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay
                    )
                    
                    # Add jitter: ±20% of delay
                    if jitter:
                        import random
                        jitter_amount = delay * 0.2 * (2 * random.random() - 1)
                        delay += jitter_amount
                    
                    delay = max(0, delay)  # Ensure non-negative
                    
                    logger.warning(
                        f"⚠️  {func.__name__}: Attempt {attempt}/{max_retries} failed. "
                        f"Retrying in {delay:.2f}s... ({str(e)[:50]})"
                    )
                    time.sleep(delay)
            
            raise last_exception
        return wrapper
    return decorator