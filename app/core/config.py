# app/core/config.py - Configuration Management System
"""
Comprehensive configuration management for LangGraph Search System.
Supports environment-specific configs, secret management, and validation.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import lru_cache
from dynaconf import Dynaconf, Validator
from pydantic import BaseSettings, Field, validator
import yaml

# Configure logging
logger = logging.getLogger(__name__)

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent

class ConfigurationError(Exception):
    """Custom exception for configuration errors"""
    pass

class DatabaseConfig(BaseSettings):
    """Database configuration with validation"""
    url: str = Field(..., description="Database connection URL")
    pool_size: int = Field(default=20, ge=1, le=100)
    max_overflow: int = Field(default=30, ge=0, le=100)
    pool_timeout: int = Field(default=30, ge=1, le=300)
    pool_recycle: int = Field(default=3600, ge=300, le=86400)
    echo: bool = Field(default=False)
    
    @validator('url')
    def validate_database_url(cls, v):
        if not v.startswith(('postgresql://', 'postgres://', 'sqlite://')):
            raise ValueError('Database URL must start with postgresql://, postgres://, or sqlite://')
        return v

class RedisConfig(BaseSettings):
    """Redis configuration with validation"""
    url: str = Field(..., description="Redis connection URL")
    pool_size: int = Field(default=20, ge=1, le=100)
    socket_timeout: int = Field(default=30, ge=1, le=300)
    socket_connect_timeout: int = Field(default=30, ge=1, le=300)
    retry_on_timeout: bool = Field(default=True)
    decode_responses: bool = Field(default=True)
    
    @validator('url')
    def validate_redis_url(cls, v):
        if not v.startswith('redis://'):
            raise ValueError('Redis URL must start with redis://')
        return v

class SearchEngineConfig(BaseSettings):
    """Search engine configuration"""
    enabled: bool = Field(default=True)
    weight: float = Field(default=0.33, ge=0.0, le=1.0)
    timeout: int = Field(default=10, ge=1, le=60)
    max_results: int = Field(default=20, ge=1, le=100)
    retry_attempts: int = Field(default=3, ge=1, le=10)
    retry_delay: int = Field(default=1, ge=0, le=10)

class LLMProviderConfig(BaseSettings):
    """LLM provider configuration"""
    enabled: bool = Field(default=True)
    model: str = Field(default="gpt-4")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    timeout: int = Field(default=30, ge=1, le=300)
    retry_attempts: int = Field(default=3, ge=1, le=10)

class SecurityConfig(BaseSettings):
    """Security configuration"""
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30)
    
    @validator('jwt_secret_key')
    def validate_jwt_secret(cls, v):
        if len(v) < 32:
            raise ValueError('JWT secret key must be at least 32 characters long')
        return v

class ComplianceConfig(BaseSettings):
    """Compliance configuration"""
    enabled_frameworks: List[str] = Field(default=["GDPR"])
    data_retention_days: int = Field(default=365, ge=30, le=2555)  # 30 days to 7 years
    pii_detection_enabled: bool = Field(default=True)
    audit_logging_enabled: bool = Field(default=True)
    
    @validator('enabled_frameworks')
    def validate_frameworks(cls, v):
        valid_frameworks = {"GDPR", "CCPA", "SOC2", "HIPAA"}
        for framework in v:
            if framework not in valid_frameworks:
                raise ValueError(f'Invalid compliance framework: {framework}. Valid options: {valid_frameworks}')
        return v

class MonitoringConfig(BaseSettings):
    """Monitoring configuration"""
    health_checks_enabled: bool = Field(default=True)
    metrics_enabled: bool = Field(default=True)
    tracing_enabled: bool = Field(default=False)
    sampling_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    error_rate_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    response_time_threshold: float = Field(default=5.0, ge=0.1, le=60.0)

class ConfigManager:
    """
    Centralized configuration management system.
    
    Features:
    - Environment-specific configuration loading
    - Secret management integration
    - Configuration validation
    - Hot-reload support (development)
    - Structured access to configuration sections
    """
    
    def __init__(self, environment: Optional[str] = None):
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.config_dir = PROJECT_ROOT / "config"
        self._settings = None
        self._load_configuration()
        self._validate_configuration()
        
    def _load_configuration(self):
        """Load configuration from YAML files"""
        try:
            # Configure Dynaconf
            self._settings = Dynaconf(
                # Base configuration
                settings_files=[
                    str(self.config_dir / "base.yml"),
                    str(self.config_dir / f"{self.environment}.yml"),
                ],
                
                # Environment variables
                envvar_prefix="LANGGRAPH",
                environments=True,
                load_dotenv=True,
                
                # Merge strategies
                merge_enabled=True,
                
                # Validation
                validators=[
                    # Core validation
                    Validator('app.name', must_exist=True),
                    Validator('api.rate_limit.default.requests_per_minute', gte=1, lte=10000),
                    
                    # LangGraph validation
                    Validator('langgraph.workflows.timeout_seconds', gte=1, lte=300),
                    Validator('langgraph.workflows.max_iterations', gte=1, lte=20),
                    
                    # Search validation
                    Validator('search.max_total_results', gte=1, lte=1000),
                    
                    # Database validation
                    Validator('database.pool_size', gte=1, lte=100),
                    
                    # Security validation
                    Validator('security.jwt.access_token_expire_minutes', gte=1, lte=1440),
                    
                    # Performance validation
                    Validator('performance.timeouts.database_query', gte=1, lte=300),
                ]
            )
            
            logger.info(f"Configuration loaded for environment: {self.environment}")
            
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}")
    
    def _validate_configuration(self):
        """Validate the loaded configuration"""
        try:
            # Validate required sections exist
            required_sections = [
                'app', 'api', 'langgraph', 'search', 'database', 
                'redis', 'security', 'monitoring'
            ]
            
            for section in required_sections:
                if not hasattr(self._settings, section):
                    raise ConfigurationError(f"Missing required configuration section: {section}")
            
            # Validate critical settings
            self._validate_secrets()
            self._validate_external_dependencies()
            
            logger.info("Configuration validation completed successfully")
            
        except Exception as e:
            raise ConfigurationError(f"Configuration validation failed: {e}")
    
    def _validate_secrets(self):
        """Validate that required secrets are present"""
        required_secrets = [
            'DATABASE_URL',
            'REDIS_URL', 
            'JWT_SECRET_KEY'
        ]
        
        missing_secrets = []
        for secret in required_secrets:
            if not os.getenv(secret):
                missing_secrets.append(secret)
        
        if missing_secrets:
            raise ConfigurationError(
                f"Missing required environment variables: {', '.join(missing_secrets)}"
            )
    
    def _validate_external_dependencies(self):
        """Validate external service configurations"""
        # Check search engine configurations
        search_engines = self._settings.search.engines
        enabled_engines = [name for name, config in search_engines.items() if config.get('enabled', False)]
        
        if not enabled_engines:
            raise ConfigurationError("At least one search engine must be enabled")
        
        # Check LLM provider configurations
        llm_providers = self._settings.llm.providers
        enabled_providers = [name for name, config in llm_providers.items() if config.get('enabled', False)]
        
        if not enabled_providers:
            raise ConfigurationError("At least one LLM provider must be enabled")
    
    @property
    def app(self) -> Dict[str, Any]:
        """Application configuration"""
        return self._settings.app
    
    @property
    def api(self) -> Dict[str, Any]:
        """API configuration"""
        return self._settings.api
    
    @property
    def langgraph(self) -> Dict[str, Any]:
        """LangGraph workflow configuration"""
        return self._settings.langgraph
    
    @property
    def search(self) -> Dict[str, Any]:
        """Search engine configuration"""
        return self._settings.search
    
    @property
    def database(self) -> DatabaseConfig:
        """Database configuration with validation"""
        db_config = self._settings.database
        db_config['url'] = os.getenv('DATABASE_URL', db_config.get('url'))
        return DatabaseConfig(**db_config)
    
    @property
    def redis(self) -> RedisConfig:
        """Redis configuration with validation"""
        redis_config = self._settings.redis
        redis_config['url'] = os.getenv('REDIS_URL', redis_config.get('url'))
        return RedisConfig(**redis_config)
    
    @property
    def llm(self) -> Dict[str, Any]:
        """LLM provider configuration"""
        return self._settings.llm
    
    @property
    def security(self) -> SecurityConfig:
        """Security configuration with validation"""
        sec_config = self._settings.security
        sec_config['jwt_secret_key'] = os.getenv('JWT_SECRET_KEY', '')
        return SecurityConfig(**sec_config.jwt)
    
    @property
    def compliance(self) -> ComplianceConfig:
        """Compliance configuration with validation"""
        comp_config = self._settings.compliance
        return ComplianceConfig(
            enabled_frameworks=comp_config.frameworks.enabled,
            data_retention_days=comp_config.gdpr.data_retention_days,
            pii_detection_enabled=comp_config.pii_detection.enabled,
            audit_logging_enabled=comp_config.audit.enabled
        )
    
    @property
    def monitoring(self) -> MonitoringConfig:
        """Monitoring configuration with validation"""
        mon_config = self._settings.monitoring
        return MonitoringConfig(**mon_config.alerts)
    
    @property
    def cache(self) -> Dict[str, Any]:
        """Cache configuration"""
        return self._settings.cache
    
    @property
    def analytics(self) -> Dict[str, Any]:
        """Analytics configuration"""
        return self._settings.analytics
    
    @property
    def multitenancy(self) -> Dict[str, Any]:
        """Multi-tenancy configuration"""
        return self._settings.multitenancy
    
    @property
    def features(self) -> Dict[str, bool]:
        """Feature flags"""
        return self._settings.features
    
    @property
    def performance(self) -> Dict[str, Any]:
        """Performance configuration"""
        return self._settings.performance
    
    @property
    def logging_config(self) -> Dict[str, Any]:
        """Logging configuration"""
        return self._settings.logging
    
    def get_search_engine_config(self, engine_name: str) -> SearchEngineConfig:
        """Get configuration for a specific search engine"""
        engine_config = self._settings.search.engines.get(engine_name)
        if not engine_config:
            raise ConfigurationError(f"Unknown search engine: {engine_name}")
        
        return SearchEngineConfig(**engine_config)
    
    def get_llm_provider_config(self, provider_name: str) -> LLMProviderConfig:
        """Get configuration for a specific LLM provider"""
        provider_config = self._settings.llm.providers.get(provider_name)
        if not provider_config:
            raise ConfigurationError(f"Unknown LLM provider: {provider_name}")
        
        return LLMProviderConfig(**provider_config)
    
    def get_api_key(self, service: str) -> str:
        """Get API key for external service"""
        api_key_map = {
            'brave': 'BRAVE_SEARCH_API_KEY',
            'serpapi': 'SERPAPI_API_KEY', 
            'zenrows': 'ZENROWS_API_KEY',
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
        }
        
        env_var = api_key_map.get(service)
        if not env_var:
            raise ConfigurationError(f"Unknown service for API key: {service}")
        
        api_key = os.getenv(env_var)
        if not api_key:
            raise ConfigurationError(f"Missing API key for {service}: {env_var}")
        
        return api_key
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature flag is enabled"""
        return self._settings.features.get(feature, False)
    
    def get_environment_info(self) -> Dict[str, Any]:
        """Get information about the current environment"""
        return {
            'environment': self.environment,
            'app_name': self._settings.app.name,
            'app_version': self._settings.app.version,
            'debug_mode': getattr(self._settings, 'development', {}).get('debug', False),
            'config_dir': str(self.config_dir),
            'loaded_files': [
                str(self.config_dir / "base.yml"),
                str(self.config_dir / f"{self.environment}.yml")
            ]
        }
    
    def reload_configuration(self):
        """Reload configuration (useful for development)"""
        if self.environment == 'production':
            logger.warning("Configuration reload attempted in production - ignored")
            return
            
        logger.info("Reloading configuration...")
        self._load_configuration()
        self._validate_configuration()
        logger.info("Configuration reloaded successfully")
    
    def export_config_summary(self) -> Dict[str, Any]:
        """Export a summary of current configuration (without secrets)"""
        return {
            'environment': self.environment,
            'app': {
                'name': self._settings.app.name,
                'version': self._settings.app.version,
            },
            'features_enabled': [k for k, v in self._settings.features.items() if v],
            'search_engines_enabled': [
                k for k, v in self._settings.search.engines.items() 
                if v.get('enabled', False)
            ],
            'llm_providers_enabled': [
                k for k, v in self._settings.llm.providers.items()
                if v.get('enabled', False)
            ],
            'compliance_frameworks': self._settings.compliance.frameworks.enabled,
            'multitenancy_enabled': self._settings.multitenancy.enabled,
            'monitoring_enabled': self._settings.monitoring.health_checks.enabled,
        }

# Global configuration instance
@lru_cache()
def get_config() -> ConfigManager:
    """Get the global configuration instance (cached)"""
    return ConfigManager()

# Convenience functions for quick access
def get_database_url() -> str:
    """Get database URL"""
    return get_config().database.url

def get_redis_url() -> str:
    """Get Redis URL"""
    return get_config().redis.url

def get_api_key(service: str) -> str:
    """Get API key for service"""
    return get_config().get_api_key(service)

def is_development() -> bool:
    """Check if running in development mode"""
    return get_config().environment == 'development'

def is_production() -> bool:
    """Check if running in production mode"""
    return get_config().environment == 'production'

def is_feature_enabled(feature: str) -> bool:
    """Check if feature is enabled"""
    return get_config().is_feature_enabled(feature)

# Configuration validation decorator
def require_config_section(section: str):
    """Decorator to ensure a configuration section exists"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            config = get_config()
            if not hasattr(config._settings, section):
                raise ConfigurationError(f"Required configuration section missing: {section}")
            return func(*args, **kwargs)
        return wrapper
    return decorator

# Environment variable helpers
def require_env_var(var_name: str, default: Optional[str] = None) -> str:
    """Require an environment variable to be set"""
    value = os.getenv(var_name, default)
    if value is None:
        raise ConfigurationError(f"Required environment variable not set: {var_name}")
    return value

def get_env_bool(var_name: str, default: bool = False) -> bool:
    """Get boolean value from environment variable"""
    value = os.getenv(var_name, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')

def get_env_int(var_name: str, default: int = 0) -> int:
    """Get integer value from environment variable"""
    try:
        return int(os.getenv(var_name, str(default)))
    except ValueError:
        logger.warning(f"Invalid integer value for {var_name}, using default: {default}")
        return default

def get_env_float(var_name: str, default: float = 0.0) -> float:
    """Get float value from environment variable"""
    try:
        return float(os.getenv(var_name, str(default)))
    except ValueError:
        logger.warning(f"Invalid float value for {var_name}, using default: {default}")
        return default

def get_env_list(var_name: str, default: Optional[List[str]] = None, separator: str = ',') -> List[str]:
    """Get list value from environment variable"""
    value = os.getenv(var_name)
    if value is None:
        return default or []
    return [item.strip() for item in value.split(separator) if item.strip()]

if __name__ == "__main__":
    # Example usage and testing
    try:
        config = get_config()
        print("Configuration loaded successfully!")
        print(f"Environment: {config.environment}")
        print(f"App: {config.app.name} v{config.app.version}")
        print(f"Features enabled: {[k for k, v in config.features.items() if v]}")
        
        # Test configuration access
        print(f"Database pool size: {config.database.pool_size}")
        print(f"Redis pool size: {config.redis.pool_size}")
        print(f"Monitoring enabled: {config.monitoring.health_checks_enabled}")
        
    except ConfigurationError as e:
        print(f"Configuration error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
