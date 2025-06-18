# app/security/auth.py - Authentication & Security System
"""
Comprehensive authentication and authorization system with JWT,
role-based access control, and security monitoring.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
import hashlib
import hmac
from enum import Enum

# FastAPI and security imports
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.requests import Request

# JWT and crypto
import jwt
from passlib.context import CryptContext
from passlib.hash import bcrypt

# Pydantic models
from pydantic import BaseModel, Field, validator
from pydantic import EmailStr

# Database and cache
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, Text

logger = logging.getLogger(__name__)

# Security configuration
security_scheme = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserRole(str, Enum):
    """User roles for RBAC"""
    ADMIN = "admin"
    USER = "user"
    PREMIUM = "premium"
    API_USER = "api_user"
    READONLY = "readonly"

class TokenType(str, Enum):
    """JWT token types"""
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"
    PASSWORD_RESET = "password_reset"

class SecurityException(Exception):
    """Custom security exception"""
    pass

# Pydantic models
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    role: UserRole = UserRole.USER
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain lowercase letter')  
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain digit')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

class TokenData(BaseModel):
    user_id: int
    email: str
    role: UserRole
    token_type: TokenType
    exp: datetime
    iat: datetime
    jti: str  # JWT ID for token revocation

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]

class User(BaseModel):
    """User model for API responses"""
    id: int
    email: str
    full_name: Optional[str]
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True

class PasswordHasher:
    """Password hashing utilities"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def generate_salt() -> str:
        """Generate a random salt"""
        return secrets.token_hex(32)

class JWTManager:
    """JWT token management"""
    
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire = timedelta(hours=1)
        self.refresh_token_expire = timedelta(days=30)
        
        # Token blacklist (in production, use Redis)
        self.blacklisted_tokens: set = set()
    
    def create_access_token(self, user_data: Dict[str, Any]) -> str:
        """Create JWT access token"""
        now = datetime.utcnow()
        expire = now + self.access_token_expire
        
        payload = {
            "user_id": user_data["id"],
            "email": user_data["email"],
            "role": user_data["role"],
            "token_type": TokenType.ACCESS.value,
            "exp": expire,
            "iat": now,
            "jti": secrets.token_hex(16)
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, user_data: Dict[str, Any]) -> str:
        """Create JWT refresh token"""
        now = datetime.utcnow()
        expire = now + self.refresh_token_expire
        
        payload = {
            "user_id": user_data["id"],
            "email": user_data["email"],
            "role": user_data["role"],
            "token_type": TokenType.REFRESH.value,
            "exp": expire,
            "iat": now,
            "jti": secrets.token_hex(16)
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_api_key(self, user_data: Dict[str, Any], expires_days: int = 365) -> str:
        """Create long-lived API key"""
        now = datetime.utcnow()
        expire = now + timedelta(days=expires_days)
        
        payload = {
            "user_id": user_data["id"],
            "email": user_data["email"],
            "role": user_data["role"],
            "token_type": TokenType.API_KEY.value,
            "exp": expire,
            "iat": now,
            "jti": secrets.token_hex(16)
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> TokenData:
        """Verify and decode JWT token"""
        try:
            # Check if token is blacklisted
            if token in self.blacklisted_tokens:
                raise SecurityException("Token has been revoked")
            
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Validate required fields
            required_fields = ["user_id", "email", "role", "token_type", "exp", "iat", "jti"]
            for field in required_fields:
                if field not in payload:
                    raise SecurityException(f"Token missing required field: {field}")
            
            # Check expiration
            exp_timestamp = payload["exp"]
            if isinstance(exp_timestamp, int):
                exp_datetime = datetime.utcfromtimestamp(exp_timestamp)
            else:
                exp_datetime = datetime.fromisoformat(exp_timestamp)
            
            if datetime.utcnow() > exp_datetime:
                raise SecurityException("Token has expired")
            
            return TokenData(
                user_id=payload["user_id"],
                email=payload["email"],
                role=UserRole(payload["role"]),
                token_type=TokenType(payload["token_type"]),
                exp=exp_datetime,
                iat=datetime.utcfromtimestamp(payload["iat"]),
                jti=payload["jti"]
            )
            
        except jwt.ExpiredSignatureError:
            raise SecurityException("Token has expired")
        except jwt.InvalidTokenError as e:
            raise SecurityException(f"Invalid token: {str(e)}")
        except Exception as e:
            raise SecurityException(f"Token verification failed: {str(e)}")
    
    def revoke_token(self, token: str):
        """Revoke a token (add to blacklist)"""
        self.blacklisted_tokens.add(token)
    
    def refresh_access_token(self, refresh_token: str) -> str:
        """Create new access token from refresh token"""
        token_data = self.verify_token(refresh_token)
        
        if token_data.token_type != TokenType.REFRESH:
            raise SecurityException("Invalid token type for refresh")
        
        # Create new access token
        user_data = {
            "id": token_data.user_id,
            "email": token_data.email,
            "role": token_data.role.value
        }
        
        return self.create_access_token(user_data)

class RoleBasedAccessControl:
    """Role-based access control system"""
    
    # Define role hierarchy (higher number = more permissions)
    ROLE_HIERARCHY = {
        UserRole.READONLY: 1,
        UserRole.USER: 2,
        UserRole.API_USER: 3,
        UserRole.PREMIUM: 4,
        UserRole.ADMIN: 5
    }
    
    # Define permission mappings
    PERMISSIONS = {
        "search:basic": [UserRole.USER, UserRole.API_USER, UserRole.PREMIUM, UserRole.ADMIN],
        "search:advanced": [UserRole.PREMIUM, UserRole.ADMIN],
        "search:unlimited": [UserRole.ADMIN],
        "analytics:view": [UserRole.USER, UserRole.PREMIUM, UserRole.ADMIN],
        "analytics:export": [UserRole.PREMIUM, UserRole.ADMIN],
        "admin:users": [UserRole.ADMIN],
        "admin:system": [UserRole.ADMIN],
        "api:unlimited": [UserRole.API_USER, UserRole.ADMIN]
    }
    
    @classmethod
    def has_permission(cls, user_role: UserRole, permission: str) -> bool:
        """Check if user role has specific permission"""
        allowed_roles = cls.PERMISSIONS.get(permission, [])
        return user_role in allowed_roles
    
    @classmethod
    def has_role_level(cls, user_role: UserRole, required_level: int) -> bool:
        """Check if user role meets minimum level requirement"""
        user_level = cls.ROLE_HIERARCHY.get(user_role, 0)
        return user_level >= required_level
    
    @classmethod
    def can_access_resource(cls, user_role: UserRole, resource_owner_id: int, 
                          user_id: int, admin_override: bool = True) -> bool:
        """Check if user can access a resource"""
        # Users can access their own resources
        if user_id == resource_owner_id:
            return True
        
        # Admins can access any resource (if admin_override is True)
        if admin_override and user_role == UserRole.ADMIN:
            return True
        
        return False

class AuthenticationService:
    """Main authentication service"""
    
    def __init__(self, jwt_manager: JWTManager, db_session_factory):
        self.jwt_manager = jwt_manager
        self.db_session_factory = db_session_factory
        self.rbac = RoleBasedAccessControl()
        self.password_hasher = PasswordHasher()
    
    async def register_user(self, user_data: UserCreate) -> User:
        """Register a new user"""
        # In a real implementation, this would interact with the database
        # For now, returning a mock user
        hashed_password = self.password_hasher.hash_password(user_data.password)
        
        # Mock user creation (replace with actual database logic)
        user = {
            "id": 1,
            "email": user_data.email,
            "full_name": user_data.full_name,
            "role": user_data.role.value,
            "hashed_password": hashed_password,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "last_login": None
        }
        
        logger.info(f"User registered: {user_data.email}")
        return User(**user)
    
    async def authenticate_user(self, login_data: UserLogin) -> Optional[User]:
        """Authenticate user with email and password"""
        # Mock user lookup (replace with actual database query)
        # In real implementation: user = db.query(UserModel).filter(email=login_data.email).first()
        
        mock_user = {
            "id": 1,
            "email": login_data.email,
            "full_name": "Test User",
            "role": UserRole.USER.value,
            "hashed_password": self.password_hasher.hash_password("password123"),
            "is_active": True,
            "created_at": datetime.utcnow(),
            "last_login": datetime.utcnow()
        }
        
        # Verify password
        if not self.password_hasher.verify_password(login_data.password, mock_user["hashed_password"]):
            return None
        
        if not mock_user["is_active"]:
            return None
        
        logger.info(f"User authenticated: {login_data.email}")
        return User(**mock_user)
    
    async def create_auth_tokens(self, user: User) -> AuthResponse:
        """Create authentication tokens for user"""
        user_data = {
            "id": user.id,
            "email": user.email,
            "role": user.role.value
        }
        
        access_token = self.jwt_manager.create_access_token(user_data)
        refresh_token = self.jwt_manager.create_refresh_token(user_data)
        
        return AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(self.jwt_manager.access_token_expire.total_seconds()),
            user=user.dict()
        )
    
    async def get_current_user_from_token(self, token: str) -> User:
        """Get current user from JWT token"""
        try:
            token_data = self.jwt_manager.verify_token(token)
            
            # Mock user lookup (replace with actual database query)
            user = {
                "id": token_data.user_id,
                "email": token_data.email,
                "full_name": "Test User",
                "role": token_data.role.value,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "last_login": datetime.utcnow()
            }
            
            return User(**user)
            
        except SecurityException as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": "Bearer"}
            )
    
    def require_permission(self, permission: str):
        """Decorator to require specific permission"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Extract user from request context
                # This is a simplified implementation
                user = kwargs.get('current_user')
                if not user or not self.rbac.has_permission(user.role, permission):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Insufficient permissions. Required: {permission}"
                    )
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def require_role(self, required_role: UserRole):
        """Decorator to require specific role or higher"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                user = kwargs.get('current_user')
                if not user or not self.rbac.has_role_level(user.role, 
                                                          self.rbac.ROLE_HIERARCHY[required_role]):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Insufficient role level. Required: {required_role.value}"
                    )
                return await func(*args, **kwargs)
            return wrapper
        return decorator

# Global authentication service instance (will be injected)
auth_service: Optional[AuthenticationService] = None

def setup_security(config: Dict[str, Any]) -> AuthenticationService:
    """Setup authentication service"""
    global auth_service
    
    jwt_secret = config.get('jwt_secret_key')
    if not jwt_secret or len(jwt_secret) < 32:
        raise SecurityException("JWT secret key must be at least 32 characters long")
    
    jwt_manager = JWTManager(jwt_secret)
    
    # Mock database session factory (replace with actual implementation)
    db_session_factory = None
    
    auth_service = AuthenticationService(jwt_manager, db_session_factory)
    
    logger.info("Authentication service initialized")
    return auth_service

# Dependency functions for FastAPI
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> User:
    """FastAPI dependency to get current authenticated user"""
    if not auth_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service not initialized"
        )
    
    token = credentials.credentials
    return await auth_service.get_current_user_from_token(token)

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency to get current active user"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency to get current admin user"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def require_permission(permission: str):
    """Dependency to require specific permission"""
    async def permission_dependency(current_user: User = Depends(get_current_user)):
        if not RoleBasedAccessControl.has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission}"
            )
        return current_user
    return permission_dependency

def require_role(required_role: UserRole):
    """Dependency to require specific role"""
    async def role_dependency(current_user: User = Depends(get_current_user)):
        rbac = RoleBasedAccessControl()
        user_level = rbac.ROLE_HIERARCHY.get(current_user.role, 0)
        required_level = rbac.ROLE_HIERARCHY.get(required_role, 999)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role level. Required: {required_role.value}"
            )
        return current_user
    return role_dependency

# Utility functions
def generate_api_key() -> str:
    """Generate a secure API key"""
    return f"lgs_{secrets.token_urlsafe(32)}"

def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage"""
    return hashlib.sha256(api_key.encode()).hexdigest()

def verify_api_key(api_key: str, hashed_api_key: str) -> bool:
    """Verify an API key against its hash"""
    return hmac.compare_digest(hash_api_key(api_key), hashed_api_key)

# Export main classes and functions
__all__ = [
    'AuthenticationService',
    'JWTManager',
    'RoleBasedAccessControl',
    'PasswordHasher',
    'UserRole',
    'TokenType',
    'User',
    'UserCreate',
    'UserLogin',
    'UserUpdate',
    'AuthResponse',
    'TokenData',
    'SecurityException',
    'setup_security',
    'get_current_user',
    'get_current_active_user',
    'get_current_admin_user',
    'require_permission',
    'require_role',
    'generate_api_key',
    'hash_api_key',
    'verify_api_key'
]
