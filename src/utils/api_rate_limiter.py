# ==================== NEW FILE: src/utils/api_rate_limiter.py ====================
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Any, List
import aiohttp

class APIRateLimiter:
    """
    Handle Upstox API rate limiting to prevent 429 errors
    
    Upstox limits: ~100 requests per minute
    This implements conservative limiting with exponential backoff
    """
    
    def __init__(self, max_requests_per_minute: int = 50):
        self.max_requests_per_minute = max_requests_per_minute
        self.request_timestamps: List[datetime] = []
        self.current_backoff = 1.0
        self.max_backoff = 32.0
        self.logger = logging.getLogger(__name__)
        
        # Track consecutive failures for backoff
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
        
    async def execute_with_rate_limit(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with rate limiting and backoff
        
        Args:
            func: Async function to execute
            *args, **kwargs: Arguments for the function
            
        Returns:
            Function result or None if rate limited
        """
        try:
            # Clean old request timestamps
            await self._cleanup_old_requests()
            
            # Check if we're at the rate limit
            if len(self.request_timestamps) >= self.max_requests_per_minute:
                wait_time = self._calculate_wait_time()
                self.logger.warning(f"Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
            
            # Execute with exponential backoff on failures
            for attempt in range(3):
                try:
                    # Record request attempt
                    self.request_timestamps.append(datetime.now())
                    
                    # Execute the function
                    result = await func(*args, **kwargs)
                    
                    # Success - reset backoff
                    self.consecutive_failures = 0
                    self.current_backoff = 1.0
                    self.last_success_time = datetime.now()
                    
                    return result
                    
                except Exception as e:
                    # Check if it's a rate limit error
                    if "429" in str(e) or "rate limit" in str(e).lower():
                        self.consecutive_failures += 1
                        backoff_time = min(self.current_backoff * (2 ** attempt), self.max_backoff)
                        
                        self.logger.warning(
                            f"Rate limit hit (attempt {attempt + 1}/3), "
                            f"backing off {backoff_time:.1f}s"
                        )
                        
                        await asyncio.sleep(backoff_time)
                        continue
                    else:
                        # Non-rate-limit error, propagate immediately
                        raise e
            
            # All attempts failed
            self.logger.error("All API attempts failed due to rate limiting")
            return None
            
        except Exception as e:
            self.logger.error(f"Error in rate-limited execution: {e}")
            return None
    
    async def _cleanup_old_requests(self):
        """Remove request timestamps older than 1 minute"""
        cutoff_time = datetime.now() - timedelta(minutes=1)
        original_count = len(self.request_timestamps)
        
        self.request_timestamps = [
            ts for ts in self.request_timestamps 
            if ts > cutoff_time
        ]
        
        cleaned_count = original_count - len(self.request_timestamps)
        if cleaned_count > 0:
            self.logger.debug(f"Cleaned {cleaned_count} old request timestamps")
    
    def _calculate_wait_time(self) -> float:
        """Calculate how long to wait before next request"""
        if not self.request_timestamps:
            return 0.0
        
        # Wait until the oldest request is more than 1 minute old
        oldest_request = min(self.request_timestamps)
        time_since_oldest = (datetime.now() - oldest_request).total_seconds()
        
        # Need to wait until 60 seconds have passed since oldest request
        wait_time = max(0, 60.0 - time_since_oldest + 1.0)  # +1 second buffer
        
        return wait_time
    
    def get_rate_limit_status(self) -> dict:
        """Get current rate limiting status"""
        current_requests = len(self.request_timestamps)
        time_since_last_success = (datetime.now() - self.last_success_time).total_seconds()
        
        return {
            'current_requests_per_minute': current_requests,
            'max_requests_per_minute': self.max_requests_per_minute,
            'consecutive_failures': self.consecutive_failures,
            'current_backoff': self.current_backoff,
            'time_since_last_success': time_since_last_success,
            'requests_remaining': max(0, self.max_requests_per_minute - current_requests)
        }
