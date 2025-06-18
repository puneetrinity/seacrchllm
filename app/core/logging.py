# app/core/logging.py - Comprehensive Logging System
"""
Advanced logging configuration with structured logging, metrics, and observability.
Supports multiple outputs, log levels, and integration with monitoring systems.
"""

import logging
import logging.config
import sys
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import traceback

# Third-party imports
try:
    import structlog
    from pythonjsonlogger import jsonlogger
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

try:
    from elastic_transport import Transport
    from elasticsearch import Elasticsearch
    ELASTICSEARCH_AVAILABLE = True
except ImportError:
    ELASTICSEARCH_AVAILABLE = False

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'process_id': os.getpid(),
            'thread_id': record.thread,
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields from the record
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                          'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                          'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                          'thread', 'threadName', 'processName', 'process', 'message']:
                log_entry[key] = value
        
        return json.dumps(log_entry)

class ElasticsearchHandler(logging.Handler):
    """Custom handler to send logs to Elasticsearch"""
    
    def __init__(self, hosts, index_pattern="langgraph-logs-%Y.%m.%d"):
        super().__init__()
        self.hosts = hosts
        self.index_pattern = index_pattern
        self.es_client = None
        
        if ELASTICSEARCH_AVAILABLE:
            try:
                self.es_client = Elasticsearch(hosts)
            except Exception as e:
                print(f"Failed to initialize Elasticsearch client: {e}")
    
    def emit(self, record):
        if not self.es_client:
            return
        
        try:
            # Format the log record as JSON
            log_entry = json.loads(JSONFormatter().format(record))
            
            # Generate index name with current date
            index_name = datetime.now().strftime(self.index_pattern)
            
            # Send to Elasticsearch
            self.es_client.index(index=index_name, body=log_entry)
            
        except Exception as e:
            # Don't let logging errors break the application
            print(f"Failed to send log to Elasticsearch: {e}")

class PerformanceLogger:
    """Performance and metrics logger"""
    
    def __init__(self, logger_name: str = "performance"):
        self.logger = logging.getLogger(logger_name)
    
    def log_search_performance(self, query: str, duration: float, 
                             result_count: int, confidence: float,
                             workflow_path: str, **kwargs):
        """Log search performance metrics"""
        self.logger.info(
            "Search performance metrics",
            extra={
                'event_type': 'search_performance',
                'query': query,
                'duration_seconds': duration,
                'result_count': result_count,
                'confidence_score': confidence,
                'workflow_path': workflow_path,
                **kwargs
            }
        )
    
    def log_api_performance(self, endpoint: str, method: str, 
                          duration: float, status_code: int,
                          user_id: Optional[str] = None, **kwargs):
        """Log API performance metrics"""
        self.logger.info(
            "API performance metrics",
            extra={
                'event_type': 'api_performance',
                'endpoint': endpoint,
                'method': method,
                'duration_seconds': duration,
                'status_code': status_code,
                'user_id': user_id,
                **kwargs
            }
        )
    
    def log_workflow_performance(self, workflow_id: str, stage: str,
                               duration: float, success: bool, **kwargs):
        """Log LangGraph workflow performance"""
        self.logger.info(
            "Workflow performance metrics",
            extra={
                'event_type': 'workflow_performance',
                'workflow_id': workflow_id,
                'stage': stage,
                'duration_seconds': duration,
                'success': success,
                **kwargs
            }
        )

class SecurityLogger:
    """Security event logger"""
    
    def __init__(self, logger_name: str = "security"):
        self.logger = logging.getLogger(logger_name)
    
    def log_auth_event(self, event_type: str, user_id: Optional[str],
                      ip_address: str, user_agent: str, 
                      success: bool, **kwargs):
        """Log authentication events"""
        self.logger.warning(
            f"Authentication event: {event_type}",
            extra={
                'event_type': 'auth_event',
                'auth_event_type': event_type,
                'user_id': user_id,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'success': success,
                **kwargs
            }
        )
    
    def log_rate_limit_event(self, user_id: Optional[str], ip_address: str,
                           endpoint: str, limit_type: str, **kwargs):
        """Log rate limiting events"""
        self.logger.warning(
            f"Rate limit exceeded: {limit_type}",
            extra={
                'event_type': 'rate_limit',
                'user_id': user_id,
                'ip_address': ip_address,
                'endpoint': endpoint,
                'limit_type': limit_type,
                **kwargs
            }
        )
    
    def log_security_violation(self, violation_type: str, severity: str,
                             user_id: Optional[str], ip_address: str,
                             details: Dict[str, Any], **kwargs):
        """Log security violations"""
        self.logger.error(
            f"Security violation: {violation_type}",
            extra={
                'event_type': 'security_violation',
                'violation_type': violation_type,
                'severity': severity,
                'user_id': user_id,
                'ip_address': ip_address,
                'details': details,
                **kwargs
            }
        )

class AuditLogger:
    """Audit trail logger for compliance"""
    
    def __init__(self, logger_name: str = "audit"):
        self.logger = logging.getLogger(logger_name)
    
    def log_data_access(self, user_id: str, data_type: str, 
                       action: str, resource_id: str,
                       sensitive: bool = False, **kwargs):
        """Log data access events"""
        self.logger.info(
            f"Data access: {action} on {data_type}",
            extra={
                'event_type': 'data_access',
                'user_id': user_id,
                'data_type': data_type,
                'action': action,
                'resource_id': resource_id,
                'sensitive': sensitive,
                **kwargs
            }
        )
    
    def log_admin_action(self, admin_user_id: str, action: str,
                        target_user_id: Optional[str], 
                        details: Dict[str, Any], **kwargs):
        """Log administrative actions"""
        self.logger.warning(
            f"Admin action: {action}",
            extra={
                'event_type': 'admin_action',
                'admin_user_id': admin_user_id,
                'action': action,
                'target_user_id': target_user_id,
                'details': details,
                **kwargs
            }
        )

def setup_logging(log_level: str = "INFO", 
                 log_format: str = "json",
                 log_file: Optional[str] = None,
                 elasticsearch_hosts: Optional[list] = None,
                 enable_performance_logging: bool = True,
                 enable_security_logging: bool = True,
                 enable_audit_logging: bool = True):
    """
    Setup comprehensive logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format type ('json', 'text', 'structured')
        log_file: Optional file path for file logging
        elasticsearch_hosts: List of Elasticsearch hosts for centralized logging
        enable_performance_logging: Enable performance metrics logging
        enable_security_logging: Enable security event logging
        enable_audit_logging: Enable audit trail logging
    """
    
    # Ensure logs directory exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    
    if log_format.lower() == "json":
        console_handler.setFormatter(JSONFormatter())
    elif log_format.lower() == "structured" and STRUCTLOG_AVAILABLE:
        # Configure structlog if available
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.dev.ConsoleRenderer()
            ],
            context_class=structlog.threadlocal.wrap_dict(dict),
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    else:
        # Standard text format
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        ))
    
    root_logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=100*1024*1024, backupCount=5
        )
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)
    
    # Elasticsearch handler (if configured)
    if elasticsearch_hosts and ELASTICSEARCH_AVAILABLE:
        try:
            es_handler = ElasticsearchHandler(elasticsearch_hosts)
            es_handler.setFormatter(JSONFormatter())
            root_logger.addHandler(es_handler)
        except Exception as e:
            print(f"Failed to setup Elasticsearch logging: {e}")
    
    # Setup specialized loggers
    if enable_performance_logging:
        perf_logger = logging.getLogger("performance")
        perf_handler = logging.handlers.RotatingFileHandler(
            log_dir / "performance.log", maxBytes=50*1024*1024, backupCount=3
        )
        perf_handler.setFormatter(JSONFormatter())
        perf_logger.addHandler(perf_handler)
        perf_logger.propagate = False
    
    if enable_security_logging:
        security_logger = logging.getLogger("security")
        security_handler = logging.handlers.RotatingFileHandler(
            log_dir / "security.log", maxBytes=50*1024*1024, backupCount=10
        )
        security_handler.setFormatter(JSONFormatter())
        security_logger.addHandler(security_handler)
        security_logger.propagate = False
    
    if enable_audit_logging:
        audit_logger = logging.getLogger("audit")
        audit_handler = logging.handlers.RotatingFileHandler(
            log_dir / "audit.log", maxBytes=50*1024*1024, backupCount=20
        )
        audit_handler.setFormatter(JSONFormatter())
        audit_logger.addHandler(audit_handler)
        audit_logger.propagate = False
    
    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # Create specialized logger instances
    root_logger.info("Logging system initialized", extra={
        'log_level': log_level,
        'log_format': log_format,
        'performance_logging': enable_performance_logging,
        'security_logging': enable_security_logging,
        'audit_logging': enable_audit_logging,
        'elasticsearch_enabled': elasticsearch_hosts is not None
    })

# Convenience functions for getting specialized loggers
def get_performance_logger() -> PerformanceLogger:
    """Get performance logger instance"""
    return PerformanceLogger()

def get_security_logger() -> SecurityLogger:
    """Get security logger instance"""
    return SecurityLogger()

def get_audit_logger() -> AuditLogger:
    """Get audit logger instance"""
    return AuditLogger()

# Context managers for automatic performance logging
class LogExecutionTime:
    """Context manager to automatically log execution time"""
    
    def __init__(self, operation_name: str, logger: Optional[logging.Logger] = None,
                 **extra_fields):
        self.operation_name = operation_name
        self.logger = logger or logging.getLogger(__name__)
        self.extra_fields = extra_fields
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.info(f"Starting {self.operation_name}", extra=self.extra_fields)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        success = exc_type is None
        
        log_data = {
            'operation': self.operation_name,
            'duration_seconds': duration,
            'success': success,
            **self.extra_fields
        }
        
        if success:
            self.logger.info(f"Completed {self.operation_name}", extra=log_data)
        else:
            log_data['error_type'] = exc_type.__name__ if exc_type else None
            log_data['error_message'] = str(exc_val) if exc_val else None
            self.logger.error(f"Failed {self.operation_name}", extra=log_data)

# Export main functions and classes
__all__ = [
    'setup_logging',
    'PerformanceLogger',
    'SecurityLogger', 
    'AuditLogger',
    'get_performance_logger',
    'get_security_logger',
    'get_audit_logger',
    'LogExecutionTime',
    'JSONFormatter'
]
