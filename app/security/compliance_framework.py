# app/security/compliance_framework.py - Enterprise Security & Compliance

import asyncio
import hashlib
import json
import secrets
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import uuid
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import re

logger = logging.getLogger(__name__)

class ComplianceFramework(str, Enum):
    GDPR = "gdpr"                    # General Data Protection Regulation
    CCPA = "ccpa"                    # California Consumer Privacy Act
    SOC2 = "soc2"                    # SOC 2 Type II
    HIPAA = "hipaa"                  # Health Insurance Portability and Accountability Act
    PCI_DSS = "pci_dss"             # Payment Card Industry Data Security Standard
    ISO27001 = "iso27001"            # ISO/IEC 27001

class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    TOP_SECRET = "top_secret"

class SecurityLevel(str, Enum):
    BASIC = "basic"
    STANDARD = "standard"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityPolicy:
    policy_id: str
    name: str
    description: str
    compliance_frameworks: List[ComplianceFramework]
    data_classifications: List[DataClassification]
    security_level: SecurityLevel
    rules: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    active: bool

@dataclass
class AuditLogEntry:
    log_id: str
    timestamp: datetime
    user_id: Optional[str]
    tenant_id: Optional[str]
    action: str
    resource: str
    result: str  # success, failure, denied
    details: Dict[str, Any]
    ip_address: Optional[str]
    user_agent: Optional[str]
    session_id: Optional[str]
    compliance_frameworks: List[ComplianceFramework]

class SecurityComplianceEngine:
    """Enterprise security and compliance engine"""
    
    def __init__(self):
        self.encryption_key = self._generate_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)
        
        # Security policies
        self.security_policies: Dict[str, SecurityPolicy] = {}
        self.compliance_rules: Dict[ComplianceFramework, Dict[str, Any]] = {}
        
        # Audit and logging
        self.audit_logs: List[AuditLogEntry] = []
        self.security_events: List[Dict[str, Any]] = []
        
        # Data protection
        self.pii_patterns: Dict[str, str] = {}
        self.sensitive_data_rules: Dict[str, Any] = {}
        
        # Access control
        self.rbac_policies: Dict[str, Any] = {}
        self.permission_matrix: Dict[str, Dict[str, Set[str]]] = {}
        
        # Initialize security framework
        self._initialize_security_framework()
    
    def _generate_encryption_key(self) -> bytes:
        """Generate secure encryption key"""
        password = secrets.token_bytes(32)
        salt = secrets.token_bytes(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key
    
    def _initialize_security_framework(self):
        """Initialize security framework with compliance rules"""
        
        # Initialize PII detection patterns
        self.pii_patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
            "credit_card": r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
            "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
        }
        
        # Initialize compliance rules
        self._setup_compliance_rules()
        
        # Initialize RBAC policies
        self._setup_rbac_policies()
        
        # Initialize security policies
        self._create_default_security_policies()
    
    def _setup_compliance_rules(self):
        """Setup compliance framework rules"""
        
        self.compliance_rules = {
            ComplianceFramework.GDPR: {
                "data_retention_days": 365,
                "right_to_be_forgotten": True,
                "consent_required": True,
                "data_portability": True,
                "privacy_by_design": True,
                "dpo_required": True,
                "breach_notification_hours": 72,
                "lawful_basis_required": True
            },
            ComplianceFramework.CCPA: {
                "data_retention_days": 365,
                "right_to_delete": True,
                "right_to_know": True,
                "opt_out_right": True,
                "non_discrimination": True,
                "authorized_agent_support": True
            },
            ComplianceFramework.SOC2: {
                "security_principle": True,
                "availability_principle": True,
                "processing_integrity": True,
                "confidentiality_principle": True,
                "privacy_principle": True,
                "annual_audit_required": True,
                "control_documentation": True
            },
            ComplianceFramework.HIPAA: {
                "administrative_safeguards": True,
                "physical_safeguards": True,
                "technical_safeguards": True,
                "encryption_required": True,
                "access_controls": True,
                "audit_logs_required": True,
                "business_associate_agreements": True
            }
        }
    
    def _setup_rbac_policies(self):
        """Setup Role-Based Access Control policies"""
        
        # Define roles and permissions
        self.rbac_policies = {
            "roles": {
                "admin": {
                    "permissions": [
                        "search:execute", "search:manage", "analytics:view", 
                        "analytics:manage", "user:manage", "tenant:manage",
                        "security:manage", "compliance:manage"
                    ],
                    "data_access": ["public", "internal", "confidential", "restricted"]
                },
                "tenant_admin": {
                    "permissions": [
                        "search:execute", "search:manage", "analytics:view",
                        "user:manage_tenant", "billing:view"
                    ],
                    "data_access": ["public", "internal", "confidential"]
                },
                "user": {
                    "permissions": ["search:execute", "analytics:view_own"],
                    "data_access": ["public", "internal"]
                },
                "analyst": {
                    "permissions": [
                        "search:execute", "analytics:view", "analytics:export"
                    ],
                    "data_access": ["public", "internal", "confidential"]
                },
                "auditor": {
                    "permissions": [
                        "audit:view", "compliance:view", "security:view"
                    ],
                    "data_access": ["audit_logs", "compliance_reports"]
                }
            },
            "permission_inheritance": {
                "admin": ["tenant_admin", "analyst", "auditor"],
                "tenant_admin": ["user"],
                "analyst": ["user"]
            }
        }
    
    def _create_default_security_policies(self):
        """Create default security policies"""
        
        # GDPR Compliance Policy
        gdpr_policy = SecurityPolicy(
            policy_id="gdpr_001",
            name="GDPR Data Protection Policy",
            description="Ensures GDPR compliance for EU data subjects",
            compliance_frameworks=[ComplianceFramework.GDPR],
            data_classifications=[DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED],
            security_level=SecurityLevel.HIGH,
            rules=[
                {
                    "type": "data_retention",
                    "action": "auto_delete",
                    "condition": "age > 365 days AND consent_withdrawn = true"
                },
                {
                    "type": "pii_detection",
                    "action": "encrypt",
                    "condition": "contains_pii = true"
                },
                {
                    "type": "data_export",
                    "action": "require_consent",
                    "condition": "subject_request = true"
                }
            ],
            created_at=datetime.now(),
            updated_at=datetime.now(),
            active=True
        )
        
        self.security_policies["gdpr_001"] = gdpr_policy
        
        # Data Classification Policy
        classification_policy = SecurityPolicy(
            policy_id="class_001",
            name="Data Classification Policy",
            description="Automatic data classification and protection",
            compliance_frameworks=[ComplianceFramework.SOC2, ComplianceFramework.ISO27001],
            data_classifications=[
                DataClassification.PUBLIC, DataClassification.INTERNAL,
                DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED
            ],
            security_level=SecurityLevel.STANDARD,
            rules=[
                {
                    "type": "auto_classification",
                    "action": "classify",
                    "condition": "content_analysis = true"
                },
                {
                    "type": "access_control",
                    "action": "restrict_access",
                    "condition": "classification >= confidential"
                }
            ],
            created_at=datetime.now(),
            updated_at=datetime.now(),
            active=True
        )
        
        self.security_policies["class_001"] = classification_policy
    
    async def validate_compliance(self, 
                                action: str,
                                data: Dict[str, Any],
                                user_context: Dict[str, Any],
                                frameworks: List[ComplianceFramework] = None) -> Dict[str, Any]:
        """Validate action against compliance requirements"""
        
        frameworks = frameworks or [ComplianceFramework.GDPR, ComplianceFramework.SOC2]
        
        validation_result = {
            "compliant": True,
            "violations": [],
            "warnings": [],
            "required_actions": [],
            "frameworks_checked": frameworks
        }
        
        for framework in frameworks:
            framework_result = await self._validate_framework_compliance(
                framework, action, data, user_context
            )
            
            if not framework_result["compliant"]:
                validation_result["compliant"] = False
                validation_result["violations"].extend(framework_result["violations"])
            
            validation_result["warnings"].extend(framework_result["warnings"])
            validation_result["required_actions"].extend(framework_result["required_actions"])
        
        # Log compliance check
        await self._log_compliance_check(action, data, user_context, validation_result)
        
        return validation_result
    
    async def _validate_framework_compliance(self,
                                           framework: ComplianceFramework,
                                           action: str,
                                           data: Dict[str, Any],
                                           user_context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate compliance for specific framework"""
        
        result = {
            "compliant": True,
            "violations": [],
            "warnings": [],
            "required_actions": []
        }
        
        if framework == ComplianceFramework.GDPR:
            result = await self._validate_gdpr_compliance(action, data, user_context)
        elif framework == ComplianceFramework.CCPA:
            result = await self._validate_ccpa_compliance(action, data, user_context)
        elif framework == ComplianceFramework.SOC2:
            result = await self._validate_soc2_compliance(action, data, user_context)
        elif framework == ComplianceFramework.HIPAA:
            result = await self._validate_hipaa_compliance(action, data, user_context)
        
        return result
    
    async def _validate_gdpr_compliance(self,
                                      action: str,
                                      data: Dict[str, Any],
                                      user_context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate GDPR compliance"""
        
        result = {
            "compliant": True,
            "violations": [],
            "warnings": [],
            "required_actions": []
        }
        
        # Check for PII in query
        query = data.get("query", "")
        pii_detected = await self._detect_pii(query)
        
        if pii_detected["has_pii"]:
            # Check if processing is lawful
            lawful_basis = user_context.get("lawful_basis")
            if not lawful_basis:
                result["compliant"] = False
                result["violations"].append({
                    "rule": "Article 6 - Lawful basis",
                    "description": "No lawful basis provided for processing personal data",
                    "severity": "high"
                })
                result["required_actions"].append("Obtain valid lawful basis for processing")
            
            # Check consent if required
            if lawful_basis == "consent":
                consent = user_context.get("consent_given", False)
                if not consent:
                    result["compliant"] = False
                    result["violations"].append({
                        "rule": "Article 7 - Consent",
                        "description": "Consent required but not provided",
                        "severity": "high"
                    })
                    result["required_actions"].append("Obtain explicit consent")
        
        # Check data subject rights
        if action == "data_export":
            # Right to portability
            if not user_context.get("data_subject_verified", False):
                result["violations"].append({
                    "rule": "Article 20 - Right to data portability",
                    "description": "Data subject identity not verified",
                    "severity": "medium"
                })
        
        elif action == "data_deletion":
            # Right to erasure
            result["required_actions"].append("Verify erasure across all systems")
        
        return result
    
    async def detect_and_protect_pii(self, content: str) -> Dict[str, Any]:
        """Detect and protect PII in content"""
        
        pii_detection = await self._detect_pii(content)
        
        if pii_detection["has_pii"]:
            # Apply protection based on policies
            protected_content = await self._apply_pii_protection(content, pii_detection)
            
            return {
                "original_content": content,
                "protected_content": protected_content["content"],
                "pii_detected": pii_detection["detected_types"],
                "protection_applied": protected_content["protections"],
                "compliance_status": "protected"
            }
        
        return {
            "original_content": content,
            "protected_content": content,
            "pii_detected": [],
            "protection_applied": [],
            "compliance_status": "clean"
        }
    
    async def _detect_pii(self, content: str) -> Dict[str, Any]:
        """Detect PII in content using patterns"""
        
        detected_pii = {
            "has_pii": False,
            "detected_types": [],
            "locations": []
        }
        
        for pii_type, pattern in self.pii_patterns.items():
            matches = re.finditer(pattern, content)
            for match in matches:
                detected_pii["has_pii"] = True
                detected_pii["detected_types"].append(pii_type)
                detected_pii["locations"].append({
                    "type": pii_type,
                    "start": match.start(),
                    "end": match.end(),
                    "text": match.group()
                })
        
        return detected_pii
    
    async def _apply_pii_protection(self, content: str, pii_detection: Dict[str, Any]) -> Dict[str, Any]:
        """Apply PII protection strategies"""
        
        protected_content = content
        protections_applied = []
        
        # Sort locations by position (reverse order to maintain indices)
        locations = sorted(pii_detection["locations"], key=lambda x: x["start"], reverse=True)
        
        for location in locations:
            pii_type = location["type"]
            start = location["start"]
            end = location["end"]
            original_text = location["text"]
            
            # Apply appropriate protection strategy
            if pii_type == "email":
                # Redact domain but keep structure
                protected_text = self._redact_email(original_text)
                protections_applied.append(f"{pii_type}: redacted")
                
            elif pii_type == "phone":
                # Mask middle digits
                protected_text = self._mask_phone(original_text)
                protections_applied.append(f"{pii_type}: masked")
                
            elif pii_type == "ssn":
                # Full redaction for SSN
                protected_text = "***-**-****"
                protections_applied.append(f"{pii_type}: redacted")
                
            elif pii_type == "credit_card":
                # Mask all but last 4 digits
                protected_text = self._mask_credit_card(original_text)
                protections_applied.append(f"{pii_type}: masked")
                
            else:
                # Default: full redaction
                protected_text = "[REDACTED]"
                protections_applied.append(f"{pii_type}: redacted")
            
            # Replace in content
            protected_content = protected_content[:start] + protected_text + protected_content[end:]
        
        return {
            "content": protected_content,
            "protections": protections_applied
        }
    
    def _redact_email(self, email: str) -> str:
        """Redact email while preserving structure"""
        parts = email.split("@")
        if len(parts) == 2:
            username = parts[0]
            domain = parts[1]
            masked_username = username[0] + "*" * (len(username) - 2) + username[-1] if len(username) > 2 else "***"
            return f"{masked_username}@{domain}"
        return "[EMAIL_REDACTED]"
    
    def _mask_phone(self, phone: str) -> str:
        """Mask phone number"""
        # Remove non-digits
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 10:
            return f"{digits[:3]}-***-{digits[-4:]}"
        return "[PHONE_REDACTED]"
    
    def _mask_credit_card(self, card: str) -> str:
        """Mask credit card number"""
        digits = re.sub(r'\D', '', card)
        if len(digits) >= 13:
            return f"****-****-****-{digits[-4:]}"
        return "[CARD_REDACTED]"
    
    async def audit_log(self,
                      action: str,
                      resource: str,
                      result: str,
                      user_id: Optional[str] = None,
                      tenant_id: Optional[str] = None,
                      details: Dict[str, Any] = None,
                      ip_address: Optional[str] = None,
                      user_agent: Optional[str] = None,
                      session_id: Optional[str] = None) -> str:
        """Create audit log entry"""
        
        log_entry = AuditLogEntry(
            log_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource=resource,
            result=result,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            compliance_frameworks=await self._determine_applicable_frameworks(action, details)
        )
        
        # Store audit log
        self.audit_logs.append(log_entry)
        
        # Check if this is a security-relevant event
        if await self._is_security_event(action, result, details):
            await self._handle_security_event(log_entry)
        
        logger.info(f"Audit log created: {log_entry.log_id} - {action} on {resource}")
        
        return log_entry.log_id
    
    async def encrypt_sensitive_data(self, data: Any, classification: DataClassification) -> Dict[str, Any]:
        """Encrypt sensitive data based on classification"""
        
        if classification in [DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED, DataClassification.TOP_SECRET]:
            # Serialize data
            data_str = json.dumps(data) if not isinstance(data, str) else data
            
            # Encrypt
            encrypted_data = self.cipher_suite.encrypt(data_str.encode())
            
            return {
                "encrypted": True,
                "data": base64.b64encode(encrypted_data).decode(),
                "classification": classification.value,
                "encryption_timestamp": datetime.now().isoformat()
            }
        
        return {
            "encrypted": False,
            "data": data,
            "classification": classification.value,
            "encryption_timestamp": datetime.now().isoformat()
        }
    
    async def decrypt_sensitive_data(self, encrypted_data: Dict[str, Any]) -> Any:
        """Decrypt sensitive data"""
        
        if not encrypted_data.get("encrypted", False):
            return encrypted_data["data"]
        
        try:
            # Decode and decrypt
            encrypted_bytes = base64.b64decode(encrypted_data["data"])
            decrypted_bytes = self.cipher_suite.decrypt(encrypted_bytes)
            decrypted_str = decrypted_bytes.decode()
            
            # Try to parse as JSON, fall back to string
            try:
                return json.loads(decrypted_str)
            except json.JSONDecodeError:
                return decrypted_str
                
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise SecurityException("Data decryption failed")
    
    async def check_user_permissions(self,
                                   user_id: str,
                                   action: str,
                                   resource: str,
                                   tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Check user permissions for action"""
        
        # Get user roles
        user_roles = await self._get_user_roles(user_id, tenant_id)
        
        # Get required permissions for action
        required_permissions = await self._get_required_permissions(action, resource)
        
        # Check permissions
        has_permission = False
        granted_by = []
        
        for role in user_roles:
            role_permissions = self.rbac_policies["roles"].get(role, {}).get("permissions", [])
            
            for required_perm in required_permissions:
                if required_perm in role_permissions:
                    has_permission = True
                    granted_by.append(f"{role}:{required_perm}")
        
        # Log permission check
        await self.audit_log(
            action="permission_check",
            resource=f"{action}:{resource}",
            result="granted" if has_permission else "denied",
            user_id=user_id,
            tenant_id=tenant_id,
            details={
                "user_roles": user_roles,
                "required_permissions": required_permissions,
                "granted_by": granted_by
            }
        )
        
        return {
            "allowed": has_permission,
            "user_roles": user_roles,
            "required_permissions": required_permissions,
            "granted_by": granted_by,
            "denial_reason": "Insufficient permissions" if not has_permission else None
        }
    
    async def generate_compliance_report(self,
                                       framework: ComplianceFramework,
                                       tenant_id: Optional[str] = None,
                                       start_date: Optional[datetime] = None,
                                       end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Generate compliance report"""
        
        end_date = end_date or datetime.now()
        start_date = start_date or (end_date - timedelta(days=30))
        
        # Filter audit logs for period and tenant
        relevant_logs = [
            log for log in self.audit_logs
            if (
                start_date <= log.timestamp <= end_date and
                (not tenant_id or log.tenant_id == tenant_id) and
                framework in log.compliance_frameworks
            )
        ]
        
        # Analyze compliance status
        compliance_analysis = await self._analyze_compliance_status(framework, relevant_logs)
        
        # Generate recommendations
        recommendations = await self._generate_compliance_recommendations(framework, compliance_analysis)
        
        report = {
            "framework": framework.value,
            "report_period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "tenant_id": tenant_id,
            "compliance_status": compliance_analysis["status"],
            "compliance_score": compliance_analysis["score"],
            "key_metrics": compliance_analysis["metrics"],
            "violations": compliance_analysis["violations"],
            "remediation_actions": recommendations["remediation"],
            "improvement_opportunities": recommendations["improvements"],
            "audit_trail": {
                "total_events": len(relevant_logs),
                "by_action": self._group_logs_by_action(relevant_logs),
                "by_result": self._group_logs_by_result(relevant_logs)
            },
            "generated_at": datetime.now().isoformat(),
            "report_id": str(uuid.uuid4())
        }
        
        return report

class SecurityException(Exception):
    """Security-related exception"""
    pass

class DataGovernanceEngine:
    """Data governance and lifecycle management"""
    
    def __init__(self, security_engine: SecurityComplianceEngine):
        self.security = security_engine
        self.data_catalog: Dict[str, Dict[str, Any]] = {}
        self.retention_policies: Dict[str, Dict[str, Any]] = {}
        self.data_lineage: Dict[str, List[str]] = {}
        
    async def register_data_asset(self,
                                asset_id: str,
                                asset_type: str,
                                classification: DataClassification,
                                metadata: Dict[str, Any],
                                owner: str,
                                tenant_id: Optional[str] = None) -> str:
        """Register data asset in governance catalog"""
        
        data_asset = {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "classification": classification,
            "metadata": metadata,
            "owner": owner,
            "tenant_id": tenant_id,
            "created_at": datetime.now(),
            "last_accessed": datetime.now(),
            "access_count": 0,
            "retention_policy": await self._determine_retention_policy(classification, asset_type),
            "compliance_tags": await self._determine_compliance_tags(classification, metadata)
        }
        
        self.data_catalog[asset_id] = data_asset
        
        # Log registration
        await self.security.audit_log(
            action="data_asset_registration",
            resource=asset_id,
            result="success",
            tenant_id=tenant_id,
            details={
                "asset_type": asset_type,
                "classification": classification.value,
                "owner": owner
            }
        )
        
        return asset_id
    
    async def apply_retention_policy(self, asset_id: str) -> Dict[str, Any]:
        """Apply data retention policy to asset"""
        
        if asset_id not in self.data_catalog:
            raise ValueError(f"Data asset {asset_id} not found")
        
        asset = self.data_catalog[asset_id]
        retention_policy = asset["retention_policy"]
        
        # Check if retention period exceeded
        retention_days = retention_policy["retention_days"]
        created_date = asset["created_at"]
        
        if datetime.now() - created_date > timedelta(days=retention_days):
            # Apply retention action
            action = retention_policy["action"]
            
            if action == "delete":
                result = await self._delete_data_asset(asset_id)
            elif action == "archive":
                result = await self._archive_data_asset(asset_id)
            elif action == "anonymize":
                result = await self._anonymize_data_asset(asset_id)
            else:
                result = {"action": "none", "reason": "unknown_action"}
            
            # Log retention action
            await self.security.audit_log(
                action="data_retention_applied",
                resource=asset_id,
                result="success",
                tenant_id=asset["tenant_id"],
                details={
                    "retention_action": action,
                    "retention_days": retention_days,
                    "result": result
                }
            )
            
            return result
        
        return {"action": "none", "reason": "retention_period_not_exceeded"}
