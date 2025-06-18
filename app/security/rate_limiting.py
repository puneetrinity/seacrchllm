# app/security/rate_limiting.py - Rate Limiting System
"""
Comprehensive rate limiting system with multiple algorithms,
tiered limits, and Redis-based distributed rate limiting.
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json

# FastAPI imports
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

# Redis for distributed rate limiting
from redis.asyncio import Redis

# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)

# Metrics
RATE_LIMIT_HITS = Counter('rate_limit_hits_total', 'Rate limit hits', ['limit_type', 'user_tier'])
RATE_LIMIT_BLOCKED = Counter('rate_limit_blocked_total', 'Rate limit blocks', ['limit_type', 'user_tier'])
RATE_LIMIT_LATENCY = Histogram('rate_limit_check_duration_seconds', 'Rate limit check duration')

class RateLimitAlgorithm(str, Enum):
    """Rate limiting algorithms"""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"
    LEAKY_BUCKET = "leaky_bucket"

class UserTier(str, Enum):
    """User subscription tiers"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    ADMIN = "admin"

class RateLimitType(str, Enum):
    """Types of rate limits"""
    REQUESTS_PER_MINUTE = "requests_per_minute"
    REQUESTS_PER_HOUR = "requests_per_hour"
    REQUESTS_PER_DAY = "requests_per_day"
    SEARCH_QUERIES_PER_MINUTE = "search_queries_per_minute"
    API_CALLS_PER_MINUTE = "api_calls_per_minute"
    CONCURRENT_REQUESTS = "concurrent_requests"

class RateLimitException(Exception):
    """Rate limit exceeded exception"""
    pass

class RateLimitConfig:
    """Rate limit configuration for different tiers"""
    
    TIER_LIMITS = {
        UserTier.FREE: {
            RateLimitType.REQUESTS_PER_MINUTE: 60,
            RateLimitType.REQUESTS_PER_HOUR: 1000,
            RateLimitType.REQUESTS_PER_DAY: 10000,
            RateLimitType.SEARCH_QUERIES_PER_MINUTE: 10,
            RateLimitType.CONCURRENT_REQUESTS: 5
        },
        UserTier.PRO: {
            RateLimitType.REQUESTS_PER_MINUTE: 600,
            RateLimitType.REQUESTS_PER_HOUR: 10000,
            RateLimitType.REQUESTS_PER_DAY: 100000,
            RateLimitType.SEARCH_QUERIES_PER_MINUTE: 100,
            RateLimitType.CONCURRENT_REQUESTS: 20
        },
        UserTier.ENTERPRISE: {
            RateLimitType.REQUESTS_PER_MINUTE: -1,  # Unlimited
            RateLimitType.REQUESTS_PER_HOUR: -1,
            RateLimitType.REQUESTS_PER_DAY: -1,
            RateLimitType.SEARCH_QUERIES_PER_MINUTE: 1000,
            RateLimitType.CONCURRENT_REQUESTS: 100
        },
        UserTier.ADMIN: {
            RateLimitType.REQUESTS_PER_MINUTE: -1,  # Unlimited
            RateLimitType.REQUESTS_PER_HOUR: -1,
            RateLimitType.REQUESTS_PER_DAY: -1,
            RateLimitType.SEARCH_QUERIES_PER_MINUTE: -1,
            RateLimitType.CONCURRENT_REQUESTS: -1
        }
    }
    
    # Window durations in seconds
    WINDOW_DURATIONS = {
        RateLimitType.REQUESTS_PER_MINUTE: 60,
        RateLimitType.REQUESTS_PER_HOUR: 3600,
        RateLimitType.REQUESTS_PER_DAY: 86400,
        RateLimitType.SEARCH_QUERIES_PER_MINUTE: 60,
        RateLimitType.API_CALLS_PER_MINUTE: 60
    }
    
    @classmethod
    def get_limit(cls, tier: UserTier, limit_type: RateLimitType) -> int:
        """Get rate limit for tier and type"""
        return cls.TIER_LIMITS.get(tier, {}).get(limit_type, 100)
    
    @classmethod
    def get_window_duration(cls, limit_type: RateLimitType) -> int:
        """Get window duration for limit type"""
        return cls.WINDOW_DURATIONS.get(limit_type, 60)

class TokenBucket:
    """Token bucket rate limiting algorithm"""
    
    def __init__(self, capacity: int, refill_rate: float, initial_tokens: Optional[int] = None):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_refill = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from bucket"""
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def _refill(self):
        """Refill tokens based on time elapsed"""
        now = time.time()
        elapsed = now - self.last_refill
        
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def get_wait_time(self, tokens: int = 1) -> float:
        """Get time to wait before tokens are available"""
        self._refill()
        
        if self.tokens >= tokens:
            return 0.0
        
        tokens_needed = tokens - self.tokens
        return tokens_needed / self.refill_rate

class SlidingWindowCounter:
    """Sliding window rate limiting algorithm"""
    
    def __init__(self, window_size: int, max_requests: int):
        self.window_size = window_size  # seconds
        self.max_requests = max_requests
        self.requests = []  # List of (timestamp, count) tuples
    
    def is_allowed(self, current_time: Optional[float] = None) -> bool:
        """Check if request is allowed"""
        if current_time is None:
            current_time = time.time()
        
        # Remove old requests outside the window
        cutoff_time = current_time - self.window_size
        self.requests = [(ts, count) for ts, count in self.requests if ts > cutoff_time]
        
        # Count total requests in window
        total_requests = sum(count for _, count in self.requests)
        
        if total_requests < self.max_requests:
            # Add current request
            self.requests.append((current_time, 1))
            return True
        
        return False
    
    def get_remaining_requests(self, current_time: Optional[float] = None) -> int:
        """Get remaining requests in current window"""
        if current_time is None:
            current_time = time.time()
        
        cutoff_time = current_time - self.window_size
        self.requests = [(ts, count) for ts, count in self.requests if ts > cutoff_time]
        
        total_requests = sum(count for _, count in self.requests)
        return max(0, self.max_requests - total_requests)

class RedisRateLimiter:
    """Redis-based distributed rate limiter"""
    
    def __init__(self, redis_client: Redis, key_prefix: str = "rate_limit:"):
        self.redis = redis_client
        self.key_prefix = key_prefix
    
    async def is_allowed_sliding_window(self, key: str, window_size: int, 
                                      max_requests: int, current_time: Optional[float] = None) -> Tuple[bool, Dict[str, Any]]:
        """Sliding window rate limiting with Redis"""
        if current_time is None:
            current_time = time.time()
        
        redis_key = f"{self.key_prefix}{key}"
        
        # Use Redis sorted set for sliding window
        # Score is timestamp, value is unique identifier
        pipeline = self.redis.pipeline()
        
        # Remove old entries outside the window
        cutoff_time = current_time - window_size
        pipeline.zremrangebyscore(redis_key, 0, cutoff_time)
        
        # Count current entries
        pipeline.zcard(redis_key)
        
        # Add current request
        request_id = f"{current_time}:{hash(key)}:{time.time()}"
        pipeline.zadd(redis_key, {request_id: current_time})
        
        # Set expiration
        pipeline.expire(redis_key, window_size + 1)
        
        results = await pipeline.execute()
        current_count = results[1]  # Count after cleanup, before adding new request
        
        allowed = current_count < max_requests
        remaining = max(0, max_requests - current_count - (1 if allowed else 0))
        
        # If not allowed, remove the request we just added
        if not allowed:
            await self.redis.zrem(redis_key, request_id)
        
        return allowed, {
            'current_count': current_count + (1 if allowed else 0),
            'remaining': remaining,
            'reset_time': current_time + window_size,
            'window_size': window_size
        }
    
    async def is_allowed_token_bucket(self, key: str, capacity: int, refill_rate: float, 
                                    tokens_requested: int = 1) -> Tuple[bool, Dict[str, Any]]:
        """Token bucket rate limiting with Redis"""
        redis_key = f"{self.key_prefix}bucket:{key}"
        current_time = time.time()
        
        # Lua script for atomic token bucket operations
        lua_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local tokens_requested = tonumber(ARGV[3])
        local current_time = tonumber(ARGV[4])
        
        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(bucket[1]) or capacity
        local last_refill = tonumber(bucket[2]) or current_time
        
        -- Refill tokens
        local elapsed = current_time - last_refill
        local tokens_to_add = elapsed * refill_rate
        tokens = math.min(capacity, tokens + tokens_to_add)
        
        -- Try to consume tokens
        local allowed = false
        if tokens >= tokens_requested then
            tokens = tokens - tokens_requested
            allowed = true
        end
        
        -- Update bucket state
        redis.call('HMSET', key, 'tokens', tokens, 'last_refill', current_time)
        redis.call('EXPIRE', key, 3600)  -- Expire after 1 hour of inactivity
        
        return {allowed and 1 or 0, tokens, capacity}
        """
        
        result = await self.redis.eval(
            lua_script, 1, redis_key, 
            capacity, refill_rate, tokens_requested, current_time
        )
        
        allowed = bool(result[0])
        remaining_tokens = result[1]
        
        return allowed, {
            'remaining_tokens': remaining_tokens,
            'capacity': capacity,
            'refill_rate': refill_rate
        }
    
    async def get_rate_limit_info(self, key: str, limit_type: RateLimitType) -> Dict[str, Any]:
        """Get current rate limit status"""
        redis_key = f"{self.key_prefix}{key}"
        
        if limit_type in [RateLimitType.REQUESTS_PER_MINUTE, RateLimitType.SEARCH_QUERIES_PER_MINUTE]:
            # For sliding window limits
            window_size = RateLimitConfig.get_window_duration(limit_type)
            current_time = time.time()
            cutoff_time = current_time - window_size
            
            # Count requests in current window
            count = await self.redis.zcount(redis_key, cutoff_time, current_time)
            
            return {
                'current_count': count,
                'window_size': window_size,
                'reset_time': current_time + window_size
            }
        
        return {}

class RateLimiter:
    """Main rate limiting service"""
    
    def __init__(self, redis_manager=None):
        self.redis_manager = redis_manager
        self.local_buckets: Dict[str, TokenBucket] = {}
        self.local_windows: Dict[str, SlidingWindowCounter] = {}
        self.config = RateLimitConfig()
        
        # Use Redis if available, otherwise fall back to local rate limiting
        self.use_redis = redis_manager is not None
        if self.use_redis:
            self.redis_limiter = RedisRateLimiter(redis_manager.redis_client)
    
    def _get_client_key(self, request: Request, user_id: Optional[str] = None) -> str:
        """Generate unique key for client identification"""
        if user_id:
            return f"user:{user_id}"
        
        # Use IP address as fallback
        client_ip = self._get_client_ip(request)
        return f"ip:{client_ip}"
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request"""
        # Check for forwarded headers (from load balancers/proxies)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        if hasattr(request.client, 'host'):
            return request.client.host
        
        return "unknown"
    
    def _get_user_tier(self, user_id: Optional[str], user_role: Optional[str] = None) -> UserTier:
        """Determine user tier based on user info"""
        if user_role == "admin":
            return UserTier.ADMIN
        elif user_role == "premium":
            return UserTier.PRO
        elif user_id:
            return UserTier.FREE  # Authenticated user
        else:
            return UserTier.FREE  # Anonymous user
    
    async def check_rate_limit(self, request: Request, limit_type: RateLimitType,
                             user_id: Optional[str] = None, user_role: Optional[str] = None,
                             tokens: int = 1) -> Dict[str, Any]:
        """Check if request is within rate limits"""
        start_time = time.time()
        
        try:
            client_key = self._get_client_key(request, user_id)
            user_tier = self._get_user_tier(user_id, user_role)
            
            # Get rate limit for this tier
            limit = self.config.get_limit(user_tier, limit_type)
            
            # If limit is -1 (unlimited), allow the request
            if limit == -1:
                return {
                    'allowed': True,
                    'tier': user_tier.value,
                    'limit': 'unlimited',
                    'remaining': 'unlimited',
                    'reset_time': None
                }
            
            # Create rate limit key
            rate_limit_key = f"{limit_type.value}:{client_key}"
            
            # Check rate limit
            if self.use_redis:
                allowed, info = await self._check_redis_rate_limit(
                    rate_limit_key, limit_type, limit, tokens
                )
            else:
                allowed, info = await self._check_local_rate_limit(
                    rate_limit_key, limit_type, limit, tokens
                )
            
            # Record metrics
            if allowed:
                RATE_LIMIT_HITS.labels(
                    limit_type=limit_type.value, 
                    user_tier=user_tier.value
                ).inc()
            else:
                RATE_LIMIT_BLOCKED.labels(
                    limit_type=limit_type.value,
                    user_tier=user_tier.value
                ).inc()
            
            # Add tier information to response
            info.update({
                'allowed': allowed,
                'tier': user_tier.value,
                'limit': limit,
                'client_key': client_key
            })
            
            return info
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # On error, allow the request (fail open)
            return {
                'allowed': True,
                'error': str(e),
                'fallback': True
            }
        
        finally:
            duration = time.time() - start_time
            RATE_LIMIT_LATENCY.observe(duration)
    
    async def _check_redis_rate_limit(self, key: str, limit_type: RateLimitType, 
                                    limit: int, tokens: int) -> Tuple[bool, Dict[str, Any]]:
        """Check rate limit using Redis"""
        if limit_type == RateLimitType.CONCURRENT_REQUESTS:
            # Handle concurrent requests differently
            return await self._check_concurrent_limit_redis(key, limit)
        
        # Use sliding window for time-based limits
        window_size = self.config.get_window_duration(limit_type)
        return await self.redis_limiter.is_allowed_sliding_window(
            key, window_size, limit
        )
    
    async def _check_local_rate_limit(self, key: str, limit_type: RateLimitType,
                                    limit: int, tokens: int) -> Tuple[bool, Dict[str, Any]]:
        """Check rate limit using local algorithms"""
        if limit_type == RateLimitType.CONCURRENT_REQUESTS:
            # Handle concurrent requests
            return await self._check_concurrent_limit_local(key, limit)
        
        # Use sliding window for local rate limiting
        if key not in self.local_windows:
            window_size = self.config.get_window_duration(limit_type)
            self.local_windows[key] = SlidingWindowCounter(window_size, limit)
        
        window = self.local_windows[key]
        allowed = window.is_allowed()
        
        return allowed, {
            'remaining': window.get_remaining_requests(),
            'window_size': window.window_size,
            'reset_time': time.time() + window.window_size
        }
    
    async def _check_concurrent_limit_redis(self, key: str, limit: int) -> Tuple[bool, Dict[str, Any]]:
        """Check concurrent request limit using Redis"""
        redis_key = f"concurrent:{key}"
        
        # Increment counter
        current_count = await self.redis_manager.redis_client.incr(redis_key)
        
        # Set expiration for cleanup (in case of connection issues)
        await self.redis_manager.redis_client.expire(redis_key, 300)  # 5 minutes
        
        allowed = current_count <= limit
        
        if not allowed:
            # Decrement if not allowed
            await self.redis_manager.redis_client.decr(redis_key)
        
        return allowed, {
            'current_concurrent': current_count if allowed else current_count - 1,
            'max_concurrent': limit
        }
    
    async def _check_concurrent_limit_local(self, key: str, limit: int) -> Tuple[bool, Dict[str, Any]]:
        """Check concurrent request limit locally"""
        # This is simplified - in practice, you'd track active requests
        # For now, always allow (concurrent limiting is better with Redis)
        return True, {
            'current_concurrent': 0,
            'max_concurrent': limit,
            'note': 'Local concurrent limiting not fully implemented'
        }
    
    async def release_concurrent_slot(self, request: Request, user_id: Optional[str] = None):
        """Release a concurrent request slot"""
        if not self.use_redis:
            return
        
        client_key = self._get_client_key(request, user_id)
        rate_limit_key = f"concurrent:concurrent_requests:{client_key}"
        
        try:
            await self.redis_manager.redis_client.decr(rate_limit_key)
        except Exception as e:
            logger.error(f"Failed to release concurrent slot: {e}")
    
    def create_rate_limit_middleware(self):
        """Create FastAPI middleware for automatic rate limiting"""
        async def rate_limit_middleware(request: Request, call_next):
            # Skip rate limiting for health checks and internal endpoints
            if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json"]:
                return await call_next(request)
            
            # Determine limit type based on endpoint
            limit_type = RateLimitType.REQUESTS_PER_MINUTE
            if "/search" in request.url.path:
                limit_type = RateLimitType.SEARCH_QUERIES_PER_MINUTE
            elif "/api/" in request.url.path:
                limit_type = RateLimitType.API_CALLS_PER_MINUTE
            
            # Extract user info from request (this would be set by auth middleware)
            user_id = getattr(request.state, 'user_id', None)
            user_role = getattr(request.state, 'user_role', None)
            
            # Check rate limit
            rate_limit_info = await self.check_rate_limit(
                request, limit_type, user_id, user_role
            )
            
            if not rate_limit_info.get('allowed', True):
                # Return rate limit exceeded response
                headers = {
                    "X-RateLimit-Limit": str(rate_limit_info.get('limit', 0)),
                    "X-RateLimit-Remaining": str(rate_limit_info.get('remaining', 0)),
                    "X-RateLimit-Reset": str(int(rate_limit_info.get('reset_time', 0))),
                    "Retry-After": str(60)  # Retry after 60 seconds
                }
                
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Rate limit exceeded",
                        "message": f"Too many requests. Limit: {rate_limit_info.get('limit', 0)} per minute",
                        "tier": rate_limit_info.get('tier', 'unknown'),
                        "retry_after": 60
                    },
                    headers=headers
                )
            
            # Add rate limit headers to response
            response = await call_next(request)
            
            if hasattr(response, 'headers'):
                response.headers["X-RateLimit-Limit"] = str(rate_limit_info.get('limit', 0))
                response.headers["X-RateLimit-Remaining"] = str(rate_limit_info.get('remaining', 0))
                response.headers["X-RateLimit-Reset"] = str(int(rate_limit_info.get('reset_time', 0)))
                response.headers["X-RateLimit-Tier"] = rate_limit_info.get('tier', 'unknown')
            
            return response
        
        return rate_limit_middleware

# Export main classes and functions
__all__ = [
    'RateLimiter',
    'RateLimitConfig',
    'RateLimitAlgorithm',
    'RateLimitType',
    'UserTier',
    'RateLimitException',
    'TokenBucket',
    'SlidingWindowCounter',
    'RedisRateLimiter'
]
