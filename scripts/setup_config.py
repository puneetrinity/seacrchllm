#!/usr/bin/env python3
"""
Configuration Setup Script for LangGraph Search System

This script helps set up the configuration management system:
- Creates necessary directories
- Copies example files
- Validates configuration
- Generates environment-specific configs
- Sets up secrets management
"""

import os
import sys
import argparse
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import yaml
import secrets
import string
from datetime import datetime

# Add the project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

class ConfigSetup:
    """Configuration setup and validation utility"""
    
    def __init__(self):
        self.project_root = PROJECT_ROOT
        self.config_dir = self.project_root / "config"
        self.scripts_dir = self.project_root / "scripts"
        
    def setup_directories(self):
        """Create necessary directories"""
        directories = [
            self.config_dir,
            self.project_root / "logs",
            self.project_root / "data",
            self.project_root / "data" / "uploads",
            self.project_root / "data" / "cache",
            self.project_root / "data" / "exports",
            self.project_root / "checkpoints",
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            print(f"✅ Created directory: {directory}")
    
    def generate_secret_key(self, length: int = 64) -> str:
        """Generate a secure random secret key"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def create_env_file(self, environment: str = "development"):
        """Create environment-specific .env file"""
        env_file = self.project_root / f".env.{environment}"
        
        if env_file.exists():
            response = input(f"⚠️  {env_file} already exists. Overwrite? (y/N): ")
            if response.lower() != 'y':
                print(f"⏭️  Skipped {env_file}")
                return
        
        # Generate secure keys
        jwt_secret = self.generate_secret_key(64)
        data_encryption_key = self.generate_secret_key(32)
        
        env_content = f"""# Environment Configuration for {environment.title()}
# Generated on {datetime.now().isoformat()}

# Environment
ENVIRONMENT={environment}
DEBUG={'true' if environment == 'development' else 'false'}
LOG_LEVEL={'DEBUG' if environment == 'development' else 'INFO'}

# Database Configuration
DATABASE_URL=postgresql://langgraph_user:langgraph_pass@localhost:5432/langgraph_search_{environment}

# Redis Configuration  
REDIS_URL=redis://localhost:6379/0

# Security Keys (CHANGE THESE!)
JWT_SECRET_KEY={jwt_secret}
DATA_ENCRYPTION_KEY={data_encryption_key}

# Search Engine API Keys (REPLACE WITH YOUR KEYS)
BRAVE_SEARCH_API_KEY=your_brave_search_api_key_here
SERPAPI_API_KEY=your_serpapi_key_here
ZENROWS_API_KEY=your_zenrows_api_key_here

# LLM Provider API Keys (REPLACE WITH YOUR KEYS)
OPENAI_API_KEY=sk-your_openai_api_key_here
ANTHROPIC_API_KEY=sk-ant-your_anthropic_api_key_here

# Monitoring (Optional)
PROMETHEUS_GATEWAY_URL=http://localhost:9091
ELASTICSEARCH_HOSTS=http://localhost:9200
GRAFANA_URL=http://localhost:3000

# Notifications (Optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
SMTP_SERVER=smtp.gmail.com
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_email_password

# Storage (Production)
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_S3_BUCKET=langgraph-search-{environment}
AWS_REGION=us-east-1

# Additional configuration for {environment}
"""
        
        if environment == "development":
            env_content += """
# Development-specific settings
ENABLE_PROFILING=true
ENABLE_TRACING=true
MOCK_EXTERNAL_APIS=false
"""
        elif environment == "production":
            env_content += """
# Production-specific settings
ENABLE_METRICS=true
ENABLE_AUDIT_LOGGING=true
REQUIRE_HTTPS=true
ENABLE_RATE_LIMITING=true
"""
        
        with open(env_file, 'w') as f:
            f.write(env_content)
        
        print(f"✅ Created {env_file}")
        print(f"⚠️  Please update the API keys in {env_file}")
    
    def validate_configuration(self, environment: str = "development") -> bool:
        """Validate configuration for an environment"""
        print(f"\n🔍 Validating configuration for {environment}...")
        
        try:
            # Try to load the configuration
            os.environ['ENVIRONMENT'] = environment
            from app.core.config import get_config
            
            config = get_config()
            
            # Validation checks
            checks = [
                ("App configuration", lambda: config.app.name is not None),
                ("Database configuration", lambda: config.database.url is not None),
                ("Redis configuration", lambda: config.redis.url is not None),
                ("Search engines", lambda: len([e for e in config.search.engines.values() if e.get('enabled')]) > 0),
                ("LLM providers", lambda: len([p for p in config.llm.providers.values() if p.get('enabled')]) > 0),
                ("Security settings", lambda: len(config.security.jwt_secret_key) >= 32),
                ("Feature flags", lambda: isinstance(config.features, dict)),
                ("Monitoring settings", lambda: hasattr(config.monitoring, 'health_checks_enabled')),
            ]
            
            all_passed = True
            for check_name, check_func in checks:
                try:
                    if check_func():
                        print(f"  ✅ {check_name}")
                    else:
                        print(f"  ❌ {check_name}")
                        all_passed = False
                except Exception as e:
                    print(f"  ❌ {check_name}: {e}")
                    all_passed = False
            
            if all_passed:
                print(f"✅ Configuration validation passed for {environment}")
                return True
            else:
                print(f"❌ Configuration validation failed for {environment}")
                return False
                
        except Exception as e:
            print(f"❌ Configuration validation error: {e}")
            return False
    
    def create_docker_env_file(self):
        """Create Docker environment file"""
        docker_env_file = self.project_root / ".env.docker"
        
        content = """# Docker Environment Configuration
# This file is used by docker-compose.yml

# Database
POSTGRES_DB=langgraph_search
POSTGRES_USER=langgraph_user
POSTGRES_PASSWORD=langgraph_pass
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=

# Application
APP_PORT=8000
APP_HOST=0.0.0.0

# Volumes
DATA_VOLUME=./data
LOGS_VOLUME=./logs
CONFIG_VOLUME=./config

# Network
NETWORK_NAME=langgraph_network
"""
        
        with open(docker_env_file, 'w') as f:
            f.write(content)
        
        print(f"✅ Created {docker_env_file}")
    
    def create_kubernetes_secrets_template(self):
        """Create Kubernetes secrets template"""
        k8s_dir = self.project_root / "k8s"
        k8s_dir.mkdir(exist_ok=True)
        
        secrets_template = k8s_dir / "secrets-template.yaml"
        
        content = """# Kubernetes Secrets Template
# Base64 encode your values before applying
apiVersion: v1
kind: Secret
metadata:
  name: langgraph-secrets
  namespace: langgraph-search
type: Opaque
data:
  # Database
  database-url: <base64-encoded-database-url>
  
  # Redis
  redis-url: <base64-encoded-redis-url>
  
  # Security
  jwt-secret-key: <base64-encoded-jwt-secret>
  data-encryption-key: <base64-encoded-encryption-key>
  
  # Search APIs
  brave-api-key: <base64-encoded-brave-key>
  serpapi-key: <base64-encoded-serpapi-key>
  zenrows-api-key: <base64-encoded-zenrows-key>
  
  # LLM APIs
  openai-api-key: <base64-encoded-openai-key>
  anthropic-api-key: <base64-encoded-anthropic-key>
  
  # Storage
  aws-access-key-id: <base64-encoded-aws-access-key>
  aws-secret-access-key: <base64-encoded-aws-secret-key>

---
# ConfigMap for non-sensitive configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: langgraph-config
  namespace: langgraph-search
data:
  environment: "production"
  log-level: "INFO"
  debug: "false"
  # Add other non-sensitive config here
"""
        
        with open(secrets_template, 'w') as f:
            f.write(content)
        
        print(f"✅ Created {secrets_template}")
    
    def generate_config_docs(self):
        """Generate configuration documentation"""
        docs_dir = self.project_root / "docs"
        docs_dir.mkdir(exist_ok=True)
        
        config_docs = docs_dir / "configuration.md"
        
        content = """# Configuration Guide

## Overview

The LangGraph Search System uses a hierarchical configuration system with:
- Base configuration (`config/base.yml`)
- Environment-specific overrides (`config/{environment}.yml`)
- Secret management via environment variables
- Validation and type checking

## Configuration Files

### Base Configuration
- `config/base.yml` - Common settings for all environments
- Contains defaults and shared configuration

### Environment Configurations
- `config/development.yml` - Development overrides
- `config/staging.yml` - Staging overrides  
- `config/production.yml` - Production overrides

### Secrets
- `config/secrets.yml.example` - Template for sensitive values
- Never commit actual secrets to version control
- Use environment variables or secret management systems

## Environment Variables

### Required
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `JWT_SECRET_KEY` - JWT signing key (min 32 chars)

### Search APIs
- `BRAVE_SEARCH_API_KEY` - Brave Search API key
- `SERPAPI_API_KEY` - SerpAPI key
- `ZENROWS_API_KEY` - ZenRows API key

### LLM Providers
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key

### Optional
- `SLACK_WEBHOOK_URL` - Slack notifications
- `AWS_ACCESS_KEY_ID` - AWS credentials
- `AWS_SECRET_ACCESS_KEY` - AWS credentials
- `ELASTICSEARCH_HOSTS` - Elasticsearch for logging

## Configuration Access

```python
from app.core.config import get_config

config = get_config()

# Access different sections
print(config.app.name)
print(config.database.pool_size)
print(config.is_feature_enabled('vector_search'))
```

## Validation

The configuration system includes validation for:
- Required fields
- Type checking
- Range validation
- Secret presence
- External service availability

## Environment Setup

1. Copy the appropriate environment file:
   ```bash
   cp .env.example .env.development
   ```

2. Update API keys and credentials

3. Validate configuration:
   ```bash
   python scripts/setup_config.py --validate --environment development
   ```

## Production Deployment

For production, use:
- Kubernetes secrets for sensitive values
- External secret management (AWS Secrets Manager, etc.)
- Environment-specific configuration files
- Proper RBAC and access controls

## Troubleshooting

Common issues:
- Missing environment variables
- Invalid configuration values
- Network connectivity to external services
- Permission issues with secret files

Check logs and use the validation script to identify issues.
"""
        
        with open(config_docs, 'w') as f:
            f.write(content)
        
        print(f"✅ Created {config_docs}")
    
    def run_interactive_setup(self):
        """Run interactive configuration setup"""
        print("🚀 LangGraph Search Configuration Setup")
        print("=" * 50)
        
        # Get environment
        while True:
            env = input("Enter environment (development/staging/production) [development]: ").strip()
            if not env:
                env = "development"
            if env in ["development", "staging", "production"]:
                break
            print("❌ Please enter 'development', 'staging', or 'production'")
        
        print(f"\n📁 Setting up configuration for {env} environment...")
        
        # Setup directories
        self.setup_directories()
        
        # Create environment file
        print(f"\n🔑 Creating environment file...")
        self.create_env_file(env)
        
        # Create Docker files
        print(f"\n🐳 Creating Docker configuration...")
        self.create_docker_env_file()
        
        # Create Kubernetes templates
        print(f"\n☸️  Creating Kubernetes templates...")
        self.create_kubernetes_secrets_template()
        
        # Generate documentation
        print(f"\n📚 Creating documentation...")
        self.generate_config_docs()
        
        # Validate configuration
        print(f"\n🔍 Validating configuration...")
        if self.validate_configuration(env):
            print(f"\n✅ Configuration setup completed successfully!")
            print(f"\n📝 Next steps:")
            print(f"   1. Update API keys in .env.{env}")
            print(f"   2. Review configuration in config/{env}.yml") 
            print(f"   3. Run validation: python scripts/setup_config.py --validate --environment {env}")
            print(f"   4. Start the application: uvicorn app.main:app --reload")
        else:
            print(f"\n❌ Configuration validation failed. Please check the errors above.")
    
    def print_config_summary(self, environment: str):
        """Print configuration summary"""
        try:
            os.environ['ENVIRONMENT'] = environment
            from app.core.config import get_config
            
            config = get_config()
            summary = config.export_config_summary()
            
            print(f"\n📊 Configuration Summary for {environment}:")
            print("=" * 50)
            print(f"App: {summary['app']['name']} v{summary['app']['version']}")
            print(f"Environment: {summary['environment']}")
            print(f"Features enabled: {', '.join(summary['features_enabled'])}")
            print(f"Search engines: {', '.join(summary['search_engines_enabled'])}")
            print(f"LLM providers: {', '.join(summary['llm_providers_enabled'])}")
            print(f"Compliance: {', '.join(summary['compliance_frameworks'])}")
            print(f"Multi-tenancy: {'Enabled' if summary['multitenancy_enabled'] else 'Disabled'}")
            print(f"Monitoring: {'Enabled' if summary['monitoring_enabled'] else 'Disabled'}")
            
        except Exception as e:
            print(f"❌ Failed to get configuration summary: {e}")

def main():
    parser = argparse.ArgumentParser(description="LangGraph Search Configuration Setup")
    parser.add_argument("--environment", "-e", default="development", 
                       choices=["development", "staging", "production"],
                       help="Environment to configure")
    parser.add_argument("--validate", "-v", action="store_true",
                       help="Validate configuration")
    parser.add_argument("--interactive", "-i", action="store_true",
                       help="Run interactive setup")
    parser.add_argument("--summary", "-s", action="store_true",
                       help="Print configuration summary")
    parser.add_argument("--create-env", action="store_true",
                       help="Create environment file")
    
    args = parser.parse_args()
    
    setup = ConfigSetup()
    
    if args.interactive:
        setup.run_interactive_setup()
    elif args.validate:
        setup.validate_configuration(args.environment)
    elif args.summary:
        setup.print_config_summary(args.environment)
    elif args.create_env:
        setup.create_env_file(args.environment)
    else:
        # Default: run full setup
        print("🚀 Running configuration setup...")
        setup.setup_directories()
        setup.create_env_file(args.environment)
        setup.create_docker_env_file()
        setup.create_kubernetes_secrets_template()
        setup.generate_config_docs()
        
        if setup.validate_configuration(args.environment):
            print("✅ Configuration setup completed successfully!")
        else:
            print("❌ Configuration setup completed with validation errors.")
            sys.exit(1)

if __name__ == "__main__":
    main()
