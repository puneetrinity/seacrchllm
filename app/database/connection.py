# app/database/connection.py - Database Connection Manager
"""
Comprehensive database connection management with async support,
connection pooling, health monitoring, and migration management.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json

# SQLAlchemy imports
from sqlalchemy import create_engine, text, MetaData, inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError
from sqlalchemy.sql import func

# Database models and migrations
try:
    from alembic import command
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    ALEMBIC_AVAILABLE = True
except ImportError:
    ALEMBIC_AVAILABLE = False

# Health monitoring
from prometheus_client import Counter, Histogram, Gauge
import psutil

logger = logging.getLogger(__name__)

# Metrics
DB_CONNECTIONS_TOTAL = Counter('db_connections_total', 'Total database connections', ['status'])
DB_QUERY_DURATION = Histogram('db_query_duration_seconds', 'Database query duration')
DB_ACTIVE_CONNECTIONS = Gauge('db_active_connections', 'Active database connections')
DB_POOL_SIZE = Gauge('db_pool_size', 'Database connection pool size')
DB_CHECKED_OUT_CONNECTIONS = Gauge('db_checked_out_connections', 'Checked out connections')

class DatabaseError(Exception):
    """Custom database exception"""
    pass

class ConnectionHealthMonitor:
    """Monitors database connection health and performance"""
    
    def __init__(self):
        self.connection_stats = {
            'total_connections': 0,
            'failed_connections': 0,
            'average_query_time': 0.0,
            'last_health_check': None,
            'pool_status': {}
        }
    
    def record_connection_attempt(self, success: bool):
        """Record a connection attempt"""
        self.connection_stats['total_connections'] += 1
        if not success:
            self.connection_stats['failed_connections'] += 1
        
        DB_CONNECTIONS_TOTAL.labels(status='success' if success else 'failure').inc()
    
    def record_query_time(self, duration: float):
        """Record query execution time"""
        DB_QUERY_DURATION.observe(duration)
        
        # Update rolling average
        current_avg = self.connection_stats['average_query_time']
        total_queries = max(1, self.connection_stats['total_connections'])
        self.connection_stats['average_query_time'] = (
            (current_avg * (total_queries - 1) + duration) / total_queries
        )
    
    def update_pool_metrics(self, pool):
        """Update connection pool metrics"""
        if hasattr(pool, 'size'):
            DB_POOL_SIZE.set(pool.size())
        if hasattr(pool, 'checked_in'):
            DB_ACTIVE_CONNECTIONS.set(pool.checkedout())
        if hasattr(pool, 'checked_out'):
            DB_CHECKED_OUT_CONNECTIONS.set(pool.checkedout())
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status"""
        total = self.connection_stats['total_connections']
        failed = self.connection_stats['failed_connections']
        success_rate = (total - failed) / max(1, total)
        
        return {
            'healthy': success_rate > 0.95 and total > 0,
            'success_rate': success_rate,
            'total_connections': total,
            'failed_connections': failed,
            'average_query_time': self.connection_stats['average_query_time'],
            'last_health_check': self.connection_stats['last_health_check']
        }

class DatabaseManager:
    """Comprehensive database connection and session management"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.engine = None
        self.async_engine = None
        self.session_factory = None
        self.async_session_factory = None
        self.health_monitor = ConnectionHealthMonitor()
        self._initialized = False
        self._migration_lock = asyncio.Lock()
        
        # Connection pool configuration
        self.pool_config = {
            'pool_size': config.get('pool_size', 20),
            'max_overflow': config.get('max_overflow', 30),
            'pool_timeout': config.get('pool_timeout', 30),
            'pool_recycle': config.get('pool_recycle', 3600),
            'pool_pre_ping': True,
            'poolclass': QueuePool
        }
    
    async def initialize(self):
        """Initialize database connections and session factories"""
        if self._initialized:
            return
        
        try:
            logger.info("Initializing database connections...")
            
            # Create database URL
            db_url = self.config.get('url')
            if not db_url:
                raise DatabaseError("Database URL not configured")
            
            # Create async engine
            async_url = db_url.replace('postgresql://', 'postgresql+asyncpg://')
            self.async_engine = create_async_engine(
                async_url,
                echo=self.config.get('echo', False),
                **self.pool_config
            )
            
            # Create sync engine (for migrations and admin tasks)
            self.engine = create_engine(
                db_url,
                echo=self.config.get('echo', False),
                **self.pool_config
            )
            
            # Create session factories
            self.async_session_factory = async_sessionmaker(
                self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            self.session_factory = sessionmaker(
                self.engine,
                expire_on_commit=False
            )
            
            # Test connections
            await self._test_connections()
            
            # Run migrations if needed
            await self._check_and_run_migrations()
            
            self._initialized = True
            self.health_monitor.record_connection_attempt(True)
            
            logger.info("Database initialization completed successfully")
            
        except Exception as e:
            self.health_monitor.record_connection_attempt(False)
            logger.error(f"Database initialization failed: {e}")
            raise DatabaseError(f"Failed to initialize database: {e}")
    
    async def _test_connections(self):
        """Test database connections"""
        try:
            # Test async connection
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
            
            # Test sync connection
            with self.engine.begin() as conn:
                result = conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
            
            logger.info("Database connection tests passed")
            
        except Exception as e:
            raise DatabaseError(f"Database connection test failed: {e}")
    
    async def _check_and_run_migrations(self):
        """Check and run database migrations if needed"""
        if not ALEMBIC_AVAILABLE:
            logger.warning("Alembic not available, skipping migrations")
            return
        
        try:
            async with self._migration_lock:
                # Check current migration state
                with self.engine.begin() as conn:
                    context = MigrationContext.configure(conn)
                    current_rev = context.get_current_revision()
                    
                    # Load Alembic configuration
                    alembic_cfg = Config("alembic.ini")
                    
                    # Check if migrations are needed
                    script_dir = alembic_cfg.get_main_option("script_location")
                    if script_dir and current_rev is None:
                        logger.info("Running initial database migrations...")
                        command.upgrade(alembic_cfg, "head")
                        logger.info("Database migrations completed")
                    
        except Exception as e:
            logger.error(f"Migration check failed: {e}")
            # Don't fail initialization for migration issues
    
    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session with automatic cleanup"""
        if not self._initialized:
            await self.initialize()
        
        session = self.async_session_factory()
        start_time = datetime.now()
        
        try:
            yield session
            await session.commit()
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        
        finally:
            duration = (datetime.now() - start_time).total_seconds()
            self.health_monitor.record_query_time(duration)
            await session.close()
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[Session, None]:
        """Get sync database session with automatic cleanup"""
        if not self._initialized:
            await self.initialize()
        
        session = self.session_factory()
        start_time = datetime.now()
        
        try:
            yield session
            session.commit()
            
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        
        finally:
            duration = (datetime.now() - start_time).total_seconds()
            self.health_monitor.record_query_time(duration)
            session.close()
    
    async def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Execute a raw SQL query and return results"""
        async with self.get_async_session() as session:
            result = await session.execute(text(query), params or {})
            return [dict(row._mapping) for row in result]
    
    async def execute_command(self, command: str, params: Optional[Dict] = None) -> int:
        """Execute a SQL command and return affected row count"""
        async with self.get_async_session() as session:
            result = await session.execute(text(command), params or {})
            return result.rowcount
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        start_time = datetime.now()
        health_status = {
            'healthy': False,
            'timestamp': start_time.isoformat(),
            'checks': {},
            'metrics': {},
            'errors': []
        }
        
        try:
            # Test basic connectivity
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text("SELECT 1 as test"))
                assert result.scalar() == 1
            
            health_status['checks']['connectivity'] = True
            
            # Test query performance
            query_start = datetime.now()
            async with self.async_engine.begin() as conn:
                await conn.execute(text("SELECT COUNT(*) FROM information_schema.tables"))
            query_duration = (datetime.now() - query_start).total_seconds()
            
            health_status['checks']['query_performance'] = query_duration < 1.0
            health_status['metrics']['query_duration'] = query_duration
            
            # Check connection pool status
            pool = self.async_engine.pool
            health_status['metrics']['pool_size'] = pool.size()
            health_status['metrics']['checked_out_connections'] = pool.checkedout()
            health_status['metrics']['overflow_connections'] = pool.overflow()
            health_status['metrics']['invalid_connections'] = pool.invalidated()
            
            # Update pool metrics
            self.health_monitor.update_pool_metrics(pool)
            
            # Check system resources
            memory_usage = psutil.virtual_memory().percent
            health_status['metrics']['system_memory_usage'] = memory_usage
            health_status['checks']['system_resources'] = memory_usage < 90
            
            # Get overall health status
            monitor_status = self.health_monitor.get_health_status()
            health_status['metrics'].update(monitor_status)
            
            # Determine overall health
            all_checks_passed = all(health_status['checks'].values())
            health_status['healthy'] = all_checks_passed and monitor_status['healthy']
            
            # Update health monitor
            self.health_monitor.connection_stats['last_health_check'] = start_time.isoformat()
            
        except Exception as e:
            health_status['healthy'] = False
            health_status['errors'].append(str(e))
            logger.error(f"Database health check failed: {e}")
        
        total_duration = (datetime.now() - start_time).total_seconds()
        health_status['metrics']['health_check_duration'] = total_duration
        
        return health_status
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database statistics"""
        try:
            stats = {}
            
            async with self.get_async_session() as session:
                # Database size
                result = await session.execute(text("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as size,
                           pg_database_size(current_database()) as size_bytes
                """))
                row = result.first()
                stats['database_size'] = row.size
                stats['database_size_bytes'] = row.size_bytes
                
                # Connection count
                result = await session.execute(text("""
                    SELECT count(*) as active_connections
                    FROM pg_stat_activity
                    WHERE state = 'active'
                """))
                stats['active_connections'] = result.scalar()
                
                # Table statistics
                result = await session.execute(text("""
                    SELECT schemaname, tablename, n_tup_ins as inserts,
                           n_tup_upd as updates, n_tup_del as deletes,
                           n_live_tup as live_rows, n_dead_tup as dead_rows
                    FROM pg_stat_user_tables
                    ORDER BY n_live_tup DESC
                    LIMIT 10
                """))
                stats['table_stats'] = [dict(row._mapping) for row in result]
                
                # Index usage
                result = await session.execute(text("""
                    SELECT schemaname, tablename, indexname, idx_tup_read, idx_tup_fetch
                    FROM pg_stat_user_indexes
                    ORDER BY idx_tup_read DESC
                    LIMIT 10
                """))
                stats['index_stats'] = [dict(row._mapping) for row in result]
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {'error': str(e)}
    
    async def backup_database(self, backup_path: str) -> Dict[str, Any]:
        """Create database backup (requires pg_dump)"""
        try:
            import subprocess
            import os
            
            # Extract connection details from URL
            url = self.config.get('url')
            # This is a simplified implementation
            # In production, use proper URL parsing and security
            
            backup_command = [
                'pg_dump',
                '--verbose',
                '--format=custom',
                '--file', backup_path,
                url
            ]
            
            start_time = datetime.now()
            result = subprocess.run(backup_command, capture_output=True, text=True)
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                backup_size = os.path.getsize(backup_path) if os.path.exists(backup_path) else 0
                return {
                    'success': True,
                    'backup_path': backup_path,
                    'backup_size_bytes': backup_size,
                    'duration_seconds': duration,
                    'timestamp': start_time.isoformat()
                }
            else:
                return {
                    'success': False,
                    'error': result.stderr,
                    'duration_seconds': duration
                }
                
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def cleanup_old_data(self, days_to_keep: int = 30) -> Dict[str, Any]:
        """Clean up old data based on retention policy"""
        try:
            cleanup_stats = {
                'tables_processed': 0,
                'rows_deleted': 0,
                'errors': []
            }
            
            # Define tables with timestamp columns for cleanup
            # This should be configured based on your schema
            cleanup_tables = [
                ('search_logs', 'created_at'),
                ('user_sessions', 'created_at'),
                ('analytics_events', 'timestamp'),
                ('audit_logs', 'created_at')
            ]
            
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            async with self.get_async_session() as session:
                for table_name, timestamp_column in cleanup_tables:
                    try:
                        # Check if table exists
                        result = await session.execute(text(f"""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_name = '{table_name}'
                            )
                        """))
                        
                        if not result.scalar():
                            continue
                        
                        # Delete old records
                        delete_result = await session.execute(text(f"""
                            DELETE FROM {table_name} 
                            WHERE {timestamp_column} < :cutoff_date
                        """), {'cutoff_date': cutoff_date})
                        
                        rows_deleted = delete_result.rowcount
                        cleanup_stats['rows_deleted'] += rows_deleted
                        cleanup_stats['tables_processed'] += 1
                        
                        logger.info(f"Cleaned up {rows_deleted} rows from {table_name}")
                        
                    except Exception as e:
                        error_msg = f"Failed to cleanup {table_name}: {e}"
                        cleanup_stats['errors'].append(error_msg)
                        logger.error(error_msg)
            
            return cleanup_stats
            
        except Exception as e:
            logger.error(f"Data cleanup failed: {e}")
            return {'error': str(e)}
    
    async def close(self):
        """Close database connections and cleanup"""
        try:
            if self.async_engine:
                await self.async_engine.dispose()
            
            if self.engine:
                self.engine.dispose()
            
            self._initialized = False
            logger.info("Database connections closed")
            
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")

# Utility functions
async def get_database_manager() -> DatabaseManager:
    """Get database manager instance (dependency injection)"""
    # This will be injected by the main application
    raise NotImplementedError("Database manager must be injected by application")

# Migration utilities
def create_migration(message: str, autogenerate: bool = True):
    """Create a new Alembic migration"""
    if not ALEMBIC_AVAILABLE:
        raise DatabaseError("Alembic not available for migrations")
    
    try:
        alembic_cfg = Config("alembic.ini")
        if autogenerate:
            command.revision(alembic_cfg, message=message, autogenerate=True)
        else:
            command.revision(alembic_cfg, message=message)
        logger.info(f"Created migration: {message}")
    except Exception as e:
        logger.error(f"Failed to create migration: {e}")
        raise DatabaseError(f"Migration creation failed: {e}")

def run_migrations():
    """Run pending migrations"""
    if not ALEMBIC_AVAILABLE:
        raise DatabaseError("Alembic not available for migrations")
    
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise DatabaseError(f"Migration failed: {e}")

# Export main classes and functions
__all__ = [
    'DatabaseManager',
    'DatabaseError',
    'ConnectionHealthMonitor',
    'get_database_manager',
    'create_migration',
    'run_migrations'
]
