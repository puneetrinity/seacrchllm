# app/cache/redis_manager.py - Redis Cache Manager
"""
Comprehensive Redis cache management with async support, clustering,
health monitoring, and advanced caching strategies.
"""

import logging
import asyncio
import json
import pickle
import hashlib
from typing import Dict, Any, Optional, Union, List, Set
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import time

# Redis imports
import redis.asyncio as redis
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError, ConnectionError, TimeoutError

# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

# Serialization
try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False

logger = logging.getLogger(__name__)

# Metrics
CACHE_OPERATIONS = Counter('cache_operations_total', 'Total cache operations', ['operation', 'status'])
CACHE_HIT_RATE = Gauge('cache_hit_rate', 'Cache hit rate')
CACHE_LATENCY = Histogram('cache_operation_duration_seconds', 'Cache operation duration')
REDIS_CONNECTIONS = Gauge('redis_connections_active', 'Active Redis connections')
CACHE_MEMORY_USAGE = Gauge('cache_memory_usage_bytes', 'Cache memory usage')

class CacheError(Exception):
    """Custom cache exception"""
    pass

class CacheSerializer:
    """Handles serialization/deserialization for cache values"""
    
    @staticmethod
    def serialize(value: Any, method: str = 'json') -> bytes:
        """Serialize value to bytes"""
        try:
            if method == 'json':
                return json.dumps(value, default=str).encode('utf-8')
            elif method == 'pickle':
                return pickle.dumps(value)
            elif method == 'msgpack' and MSGPACK_AVAILABLE:
                return msgpack.packb(value, default=str)
            else:
                # Fallback to JSON
                return json.dumps(value, default=str).encode('utf-8')
        except Exception as e:
            logger.error(f"Serialization failed: {e}")
            raise CacheError(f"Failed to serialize value: {e}")
    
    @staticmethod
    def deserialize(data: bytes, method: str = 'json') -> Any:
        """Deserialize bytes to value"""
        try:
            if method == 'json':
                return json.loads(data.decode('utf-8'))
            elif method == 'pickle':
                return pickle.loads(data)
            elif method == 'msgpack' and MSGPACK_AVAILABLE:
                return msgpack.unpackb(data, raw=False)
            else:
                # Fallback to JSON
                return json.loads(data.decode('utf-8'))
        except Exception as e:
            logger.error(f"Deserialization failed: {e}")
            raise CacheError(f"Failed to deserialize value: {e}")

class CacheStats:
    """Cache statistics tracking"""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.errors = 0
        self.total_operations = 0
        self.start_time = datetime.now()
    
    def record_hit(self):
        self.hits += 1
        self.total_operations += 1
        self._update_metrics()
    
    def record_miss(self):
        self.misses += 1
        self.total_operations += 1
        self._update_metrics()
    
    def record_set(self):
        self.sets += 1
        self.total_operations += 1
    
    def record_delete(self):
        self.deletes += 1
        self.total_operations += 1
    
    def record_error(self):
        self.errors += 1
        self.total_operations += 1
    
    def _update_metrics(self):
        """Update Prometheus metrics"""
        total_requests = self.hits + self.misses
        if total_requests > 0:
            hit_rate = self.hits / total_requests
            CACHE_HIT_RATE.set(hit_rate)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current cache statistics"""
        total_requests = self.hits + self.misses
        hit_rate = self.hits / max(1, total_requests)
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            'hits': self.hits,
            'misses': self.misses,
            'sets': self.sets,
            'deletes': self.deletes,
            'errors': self.errors,
            'total_operations': self.total_operations,
            'hit_rate': hit_rate,
            'uptime_seconds': uptime,
            'operations_per_second': self.total_operations / max(1, uptime)
        }

class RedisManager:
    """Comprehensive Redis cache management"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.redis_client: Optional[Redis] = None
        self.connection_pool: Optional[ConnectionPool] = None
        self.stats = CacheStats()
        self._initialized = False
        self.serializer = CacheSerializer()
        
        # Configuration
        self.default_ttl = config.get('default_ttl', 3600)  # 1 hour
        self.serialization_method = config.get('serialization', 'json')
        self.key_prefix = config.get('key_prefix', 'langgraph:')
        self.max_connections = config.get('pool_size', 20)
        
        # Connection settings
        self.connection_config = {
            'socket_timeout': config.get('socket_timeout', 30),
            'socket_connect_timeout': config.get('socket_connect_timeout', 30),
            'retry_on_timeout': config.get('retry_on_timeout', True),
            'decode_responses': config.get('decode_responses', False),  # We handle bytes
            'max_connections': self.max_connections
        }
    
    async def initialize(self):
        """Initialize Redis connection and pool"""
        if self._initialized:
            return
        
        try:
            logger.info("Initializing Redis connection...")
            
            redis_url = self.config.get('url')
            if not redis_url:
                raise CacheError("Redis URL not configured")
            
            # Create connection pool
            self.connection_pool = ConnectionPool.from_url(
                redis_url,
                **self.connection_config
            )
            
            # Create Redis client
            self.redis_client = Redis(connection_pool=self.connection_pool)
            
            # Test connection
            await self._test_connection()
            
            self._initialized = True
            logger.info("Redis initialization completed successfully")
            
        except Exception as e:
            logger.error(f"Redis initialization failed: {e}")
            raise CacheError(f"Failed to initialize Redis: {e}")
    
    async def _test_connection(self):
        """Test Redis connection"""
        try:
            await self.redis_client.ping()
            info = await self.redis_client.info()
            logger.info(f"Redis connection test passed. Version: {info.get('redis_version')}")
        except Exception as e:
            raise CacheError(f"Redis connection test failed: {e}")
    
    def _build_key(self, key: str, namespace: Optional[str] = None) -> str:
        """Build full cache key with prefix and namespace"""
        if namespace:
            return f"{self.key_prefix}{namespace}:{key}"
        return f"{self.key_prefix}{key}"
    
    def _hash_key(self, key: str) -> str:
        """Hash long keys to ensure Redis key length limits"""
        if len(key) > 250:  # Redis key length limit is ~512MB but practical limit
            return hashlib.sha256(key.encode()).hexdigest()
        return key
    
    async def get(self, key: str, namespace: Optional[str] = None, 
                  default: Any = None) -> Any:
        """Get value from cache"""
        if not self._initialized:
            await self.initialize()
        
        start_time = time.time()
        full_key = self._build_key(self._hash_key(key), namespace)
        
        try:
            data = await self.redis_client.get(full_key)
            
            if data is None:
                self.stats.record_miss()
                CACHE_OPERATIONS.labels(operation='get', status='miss').inc()
                return default
            
            value = self.serializer.deserialize(data, self.serialization_method)
            self.stats.record_hit()
            CACHE_OPERATIONS.labels(operation='get', status='hit').inc()
            
            return value
            
        except Exception as e:
            self.stats.record_error()
            CACHE_OPERATIONS.labels(operation='get', status='error').inc()
            logger.error(f"Cache get failed for key {key}: {e}")
            return default
        
        finally:
            duration = time.time() - start_time
            CACHE_LATENCY.observe(duration)
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None,
                  namespace: Optional[str] = None, 
                  if_not_exists: bool = False) -> bool:
        """Set value in cache"""
        if not self._initialized:
            await self.initialize()
        
        start_time = time.time()
        full_key = self._build_key(self._hash_key(key), namespace)
        ttl = ttl or self.default_ttl
        
        try:
            data = self.serializer.serialize(value, self.serialization_method)
            
            if if_not_exists:
                result = await self.redis_client.set(full_key, data, ex=ttl, nx=True)
                success = result is not None
            else:
                await self.redis_client.set(full_key, data, ex=ttl)
                success = True
            
            if success:
                self.stats.record_set()
                CACHE_OPERATIONS.labels(operation='set', status='success').inc()
            else:
                CACHE_OPERATIONS.labels(operation='set', status='failed').inc()
            
            return success
            
        except Exception as e:
            self.stats.record_error()
            CACHE_OPERATIONS.labels(operation='set', status='error').inc()
            logger.error(f"Cache set failed for key {key}: {e}")
            return False
        
        finally:
            duration = time.time() - start_time
            CACHE_LATENCY.observe(duration)
    
    async def delete(self, key: str, namespace: Optional[str] = None) -> bool:
        """Delete key from cache"""
        if not self._initialized:
            await self.initialize()
        
        start_time = time.time()
        full_key = self._build_key(self._hash_key(key), namespace)
        
        try:
            result = await self.redis_client.delete(full_key)
            success = result > 0
            
            if success:
                self.stats.record_delete()
                CACHE_OPERATIONS.labels(operation='delete', status='success').inc()
            else:
                CACHE_OPERATIONS.labels(operation='delete', status='not_found').inc()
            
            return success
            
        except Exception as e:
            self.stats.record_error()
            CACHE_OPERATIONS.labels(operation='delete', status='error').inc()
            logger.error(f"Cache delete failed for key {key}: {e}")
            return False
        
        finally:
            duration = time.time() - start_time
            CACHE_LATENCY.observe(duration)
    
    async def exists(self, key: str, namespace: Optional[str] = None) -> bool:
        """Check if key exists in cache"""
        if not self._initialized:
            await self.initialize()
        
        full_key = self._build_key(self._hash_key(key), namespace)
        
        try:
            result = await self.redis_client.exists(full_key)
            return result > 0
        except Exception as e:
            logger.error(f"Cache exists check failed for key {key}: {e}")
            return False
    
    async def expire(self, key: str, ttl: int, namespace: Optional[str] = None) -> bool:
        """Set expiration time for key"""
        if not self._initialized:
            await self.initialize()
        
        full_key = self._build_key(self._hash_key(key), namespace)
        
        try:
            result = await self.redis_client.expire(full_key, ttl)
            return result
        except Exception as e:
            logger.error(f"Cache expire failed for key {key}: {e}")
            return False
    
    async def get_ttl(self, key: str, namespace: Optional[str] = None) -> Optional[int]:
        """Get remaining TTL for key"""
        if not self._initialized:
            await self.initialize()
        
        full_key = self._build_key(self._hash_key(key), namespace)
        
        try:
            ttl = await self.redis_client.ttl(full_key)
            return ttl if ttl >= 0 else None
        except Exception as e:
            logger.error(f"Cache TTL check failed for key {key}: {e}")
            return None
    
    async def clear_namespace(self, namespace: str) -> int:
        """Clear all keys in a namespace"""
        if not self._initialized:
            await self.initialize()
        
        pattern = self._build_key("*", namespace)
        
        try:
            keys = []
            async for key in self.redis_client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                deleted = await self.redis_client.delete(*keys)
                logger.info(f"Cleared {deleted} keys from namespace {namespace}")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to clear namespace {namespace}: {e}")
            return 0
    
    async def get_many(self, keys: List[str], namespace: Optional[str] = None) -> Dict[str, Any]:
        """Get multiple values from cache"""
        if not self._initialized:
            await self.initialize()
        
        if not keys:
            return {}
        
        full_keys = [self._build_key(self._hash_key(key), namespace) for key in keys]
        
        try:
            values = await self.redis_client.mget(full_keys)
            result = {}
            
            for i, (original_key, value) in enumerate(zip(keys, values)):
                if value is not None:
                    try:
                        result[original_key] = self.serializer.deserialize(
                            value, self.serialization_method
                        )
                        self.stats.record_hit()
                    except Exception as e:
                        logger.error(f"Failed to deserialize value for key {original_key}: {e}")
                        self.stats.record_error()
                else:
                    self.stats.record_miss()
            
            return result
            
        except Exception as e:
            logger.error(f"Cache get_many failed: {e}")
            return {}
    
    async def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None,
                       namespace: Optional[str] = None) -> int:
        """Set multiple values in cache"""
        if not self._initialized:
            await self.initialize()
        
        if not mapping:
            return 0
        
        ttl = ttl or self.default_ttl
        success_count = 0
        
        try:
            # Use pipeline for efficiency
            async with self.redis_client.pipeline() as pipe:
                for key, value in mapping.items():
                    try:
                        full_key = self._build_key(self._hash_key(key), namespace)
                        data = self.serializer.serialize(value, self.serialization_method)
                        pipe.set(full_key, data, ex=ttl)
                    except Exception as e:
                        logger.error(f"Failed to prepare set for key {key}: {e}")
                        continue
                
                results = await pipe.execute()
                success_count = sum(1 for result in results if result)
            
            return success_count
            
        except Exception as e:
            logger.error(f"Cache set_many failed: {e}")
            return 0
    
    async def increment(self, key: str, amount: int = 1, 
                       namespace: Optional[str] = None, ttl: Optional[int] = None) -> Optional[int]:
        """Increment a numeric value"""
        if not self._initialized:
            await self.initialize()
        
        full_key = self._build_key(self._hash_key(key), namespace)
        
        try:
            async with self.redis_client.pipeline() as pipe:
                result = await pipe.incr(full_key, amount).execute()
                
                if ttl:
                    await pipe.expire(full_key, ttl).execute()
                
                return result[0]
                
        except Exception as e:
            logger.error(f"Cache increment failed for key {key}: {e}")
            return None
    
    async def add_to_set(self, key: str, *values, namespace: Optional[str] = None,
                        ttl: Optional[int] = None) -> int:
        """Add values to a set"""
        if not self._initialized:
            await self.initialize()
        
        full_key = self._build_key(self._hash_key(key), namespace)
        
        try:
            # Serialize values
            serialized_values = [
                self.serializer.serialize(value, self.serialization_method)
                for value in values
            ]
            
            async with self.redis_client.pipeline() as pipe:
                pipe.sadd(full_key, *serialized_values)
                if ttl:
                    pipe.expire(full_key, ttl)
                
                results = await pipe.execute()
                return results[0]
                
        except Exception as e:
            logger.error(f"Cache add_to_set failed for key {key}: {e}")
            return 0
    
    async def get_set_members(self, key: str, namespace: Optional[str] = None) -> Set[Any]:
        """Get all members of a set"""
        if not self._initialized:
            await self.initialize()
        
        full_key = self._build_key(self._hash_key(key), namespace)
        
        try:
            members = await self.redis_client.smembers(full_key)
            return {
                self.serializer.deserialize(member, self.serialization_method)
                for member in members
            }
        except Exception as e:
            logger.error(f"Cache get_set_members failed for key {key}: {e}")
            return set()
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        health_status = {
            'healthy': False,
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'metrics': {},
            'errors': []
        }
        
        try:
            if not self._initialized:
                await self.initialize()
            
            # Test basic connectivity
            start_time = time.time()
            await self.redis_client.ping()
            ping_duration = time.time() - start_time
            
            health_status['checks']['connectivity'] = True
            health_status['metrics']['ping_duration'] = ping_duration
            
            # Get Redis info
            info = await self.redis_client.info()
            health_status['metrics']['redis_version'] = info.get('redis_version')
            health_status['metrics']['connected_clients'] = info.get('connected_clients')
            health_status['metrics']['used_memory'] = info.get('used_memory')
            health_status['metrics']['used_memory_human'] = info.get('used_memory_human')
            health_status['metrics']['total_commands_processed'] = info.get('total_commands_processed')
            
            # Update memory usage metric
            CACHE_MEMORY_USAGE.set(info.get('used_memory', 0))
            
            # Test read/write operations
            test_key = f"health_check_{int(time.time())}"
            test_value = {'test': True, 'timestamp': time.time()}
            
            await self.set(test_key, test_value, ttl=60, namespace='health')
            retrieved_value = await self.get(test_key, namespace='health')
            
            health_status['checks']['read_write'] = retrieved_value == test_value
            
            # Clean up test key
            await self.delete(test_key, namespace='health')
            
            # Get cache statistics
            cache_stats = self.stats.get_stats()
            health_status['metrics']['cache_stats'] = cache_stats
            
            # Update connection metrics
            REDIS_CONNECTIONS.set(info.get('connected_clients', 0))
            
            # Determine overall health
            all_checks_passed = all(health_status['checks'].values())
            health_status['healthy'] = all_checks_passed and ping_duration < 1.0
            
        except Exception as e:
            health_status['healthy'] = False
            health_status['errors'].append(str(e))
            logger.error(f"Redis health check failed: {e}")
        
        return health_status
    
    async def get_cache_info(self) -> Dict[str, Any]:
        """Get detailed cache information"""
        try:
            info = await self.redis_client.info()
            config_info = await self.redis_client.config_get('*')
            
            return {
                'redis_info': {
                    'version': info.get('redis_version'),
                    'mode': info.get('redis_mode'),
                    'connected_clients': info.get('connected_clients'),
                    'used_memory': info.get('used_memory'),
                    'used_memory_human': info.get('used_memory_human'),
                    'used_memory_peak': info.get('used_memory_peak'),
                    'used_memory_peak_human': info.get('used_memory_peak_human'),
                    'total_system_memory': info.get('total_system_memory'),
                    'total_commands_processed': info.get('total_commands_processed'),
                    'instantaneous_ops_per_sec': info.get('instantaneous_ops_per_sec'),
                    'keyspace_hits': info.get('keyspace_hits'),
                    'keyspace_misses': info.get('keyspace_misses'),
                    'expired_keys': info.get('expired_keys'),
                    'evicted_keys': info.get('evicted_keys')
                },
                'cache_stats': self.stats.get_stats(),
                'configuration': {
                    'default_ttl': self.default_ttl,
                    'serialization_method': self.serialization_method,
                    'key_prefix': self.key_prefix,
                    'max_connections': self.max_connections
                }
            }
        except Exception as e:
            logger.error(f"Failed to get cache info: {e}")
            return {'error': str(e)}
    
    async def flush_cache(self, namespace: Optional[str] = None) -> bool:
        """Flush cache (use with caution!)"""
        try:
            if namespace:
                deleted = await self.clear_namespace(namespace)
                logger.warning(f"Flushed namespace {namespace}, deleted {deleted} keys")
                return True
            else:
                await self.redis_client.flushdb()
                logger.warning("Flushed entire cache database")
                return True
        except Exception as e:
            logger.error(f"Cache flush failed: {e}")
            return False
    
    async def close(self):
        """Close Redis connections"""
        try:
            if self.redis_client:
                await self.redis_client.close()
            
            if self.connection_pool:
                await self.connection_pool.disconnect()
            
            self._initialized = False
            logger.info("Redis connections closed")
            
        except Exception as e:
            logger.error(f"Error closing Redis connections: {e}")

# Utility functions and decorators
def cache_key_from_args(*args, **kwargs) -> str:
    """Generate cache key from function arguments"""
    key_parts = [str(arg) for arg in args]
    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
    key_string = ":".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()

def cached(ttl: int = 3600, namespace: str = 'default', 
          key_func: Optional[callable] = None):
    """Decorator for caching function results"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # This would need to be injected with actual cache manager
            # Simplified implementation for now
            cache_key = key_func(*args, **kwargs) if key_func else cache_key_from_args(*args, **kwargs)
            
            # Get from cache
            # result = await cache_manager.get(cache_key, namespace)
            # if result is not None:
            #     return result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            # await cache_manager.set(cache_key, result, ttl, namespace)
            
            return result
        return wrapper
    return decorator

# Export main classes and functions
__all__ = [
    'RedisManager',
    'CacheError',
    'CacheSerializer',
    'CacheStats',
    'cached',
    'cache_key_from_args'
]
