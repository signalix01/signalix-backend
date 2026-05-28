"""
Webhook Handler

Validates webhook signatures, timestamps, and sanitizes payloads.
Requirements: 1.1, 17.1, 17.2, 17.4, 17.5, 17.6, 17.7
"""

import hmac
import hashlib
import json
import re
import html
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of webhook validation"""
    valid: bool
    error_message: Optional[str] = None
    signature_valid: bool = False
    timestamp_valid: bool = False
    rate_limit_allowed: bool = True
    sanitized_payload: Optional[Dict[str, Any]] = None
    
    
class WebhookHandler:
    """
    Handles webhook security validation
    
    Features:
    - HMAC-SHA256 signature validation
    - Timestamp validation for replay attack prevention
    - Payload sanitization
    """
    
    # Constants
    MAX_TIMESTAMP_AGE_SECONDS = 300  # 5 minutes for replay protection
    MAX_PAYLOAD_SIZE = 1024 * 1024  # 1MB max payload
    
    # Patterns for sanitization
    DANGEROUS_PATTERNS = [
        (re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL), '[SCRIPT_REMOVED]'),
        (re.compile(r'javascript:', re.IGNORECASE), '[JS_REMOVED]'),
        (re.compile(r'on\w+\s*=', re.IGNORECASE), '[EVENT_REMOVED]'),
        (re.compile(r'<iframe[^>]*>.*?</iframe>', re.IGNORECASE | re.DOTALL), '[IFRAME_REMOVED]'),
        (re.compile(r'<object[^>]*>.*?</object>', re.IGNORECASE | re.DOTALL), '[OBJECT_REMOVED]'),
        (re.compile(r'<embed[^>]*>.*?</embed>', re.IGNORECASE | re.DOTALL), '[EMBED_REMOVED]'),
    ]
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def validate_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str,
        algorithm: str = "sha256"
    ) -> bool:
        """
        Validate HMAC-SHA256 signature
        
        Args:
            payload: Raw request body bytes
            signature: Provided signature (hex string)
            secret: Webhook secret key
            algorithm: Hash algorithm (default: sha256)
            
        Returns:
            bool: True if signature is valid
            
        Requirements: 1.1, 17.1, 17.2
        """
        try:
            if not signature or not secret:
                self.logger.warning("Missing signature or secret")
                return False
            
            # Normalize signature (remove 'sha256=' prefix if present)
            if signature.startswith("sha256="):
                signature = signature[7:]
            
            # Compute expected signature
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            # Use constant-time comparison to prevent timing attacks
            is_valid = hmac.compare_digest(
                signature.lower().encode(),
                expected_signature.lower().encode()
            )
            
            if not is_valid:
                self.logger.warning(f"Signature mismatch. Expected: {expected_signature[:16]}...")
            
            return is_valid
            
        except Exception as e:
            self.logger.error(f"Signature validation error: {str(e)}")
            return False
    
    def validate_timestamp(
        self,
        timestamp: int,
        max_age_seconds: Optional[int] = None
    ) -> bool:
        """
        Validate timestamp for replay attack prevention
        
        Args:
            timestamp: Unix timestamp (seconds since epoch)
            max_age_seconds: Maximum age allowed (default: 300 seconds)
            
        Returns:
            bool: True if timestamp is within acceptable range
            
        Requirements: 17.4, 17.5
        """
        try:
            max_age = max_age_seconds or self.MAX_TIMESTAMP_AGE_SECONDS
            
            # Convert timestamp to datetime
            timestamp_dt = datetime.utcfromtimestamp(timestamp)
            now = datetime.utcnow()
            
            # Check if timestamp is in the future (more than 30 seconds)
            if timestamp_dt > now + timedelta(seconds=30):
                self.logger.warning(f"Timestamp is in the future: {timestamp}")
                return False
            
            # Check if timestamp is too old
            age = now - timestamp_dt
            if age.total_seconds() > max_age:
                self.logger.warning(f"Timestamp too old: {age.total_seconds()}s > {max_age}s")
                return False
            
            return True
            
        except (ValueError, OSError) as e:
            self.logger.error(f"Timestamp validation error: {str(e)}")
            return False
    
    def validate_timestamp_header(
        self,
        timestamp_header: str,
        max_age_seconds: Optional[int] = None
    ) -> Tuple[bool, Optional[int]]:
        """
        Validate timestamp from HTTP header string
        
        Args:
            timestamp_header: Timestamp value from header (seconds or milliseconds)
            max_age_seconds: Maximum age allowed
            
        Returns:
            Tuple of (is_valid, timestamp_value)
        """
        try:
            timestamp = int(timestamp_header)
            
            # Handle millisecond timestamps (convert to seconds)
            if timestamp > 1_000_000_000_000:
                timestamp = timestamp // 1000
            
            is_valid = self.validate_timestamp(timestamp, max_age_seconds)
            return is_valid, timestamp
            
        except (ValueError, TypeError) as e:
            self.logger.error(f"Invalid timestamp header format: {str(e)}")
            return False, None
    
    def sanitize_payload(self, payload: Any) -> Dict[str, Any]:
        """
        Sanitize payload to prevent injection attacks
        
        Args:
            payload: Raw payload (dict, string, or bytes)
            
        Returns:
            Sanitized payload dict
            
        Requirements: 17.7
        """
        try:
            # Convert to dict if needed
            if isinstance(payload, bytes):
                payload = json.loads(payload.decode('utf-8'))
            elif isinstance(payload, str):
                payload = json.loads(payload)
            
            if not isinstance(payload, dict):
                payload = {"data": payload}
            
            return self._sanitize_dict(payload)
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {str(e)}")
            return {"error": "Invalid JSON", "raw_size": len(str(payload))}
        except Exception as e:
            self.logger.error(f"Sanitization error: {str(e)}")
            return {"error": "Sanitization failed"}
    
    def _sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize dictionary values"""
        sanitized = {}
        
        for key, value in data.items():
            # Sanitize key (alphanumeric and underscores only)
            safe_key = re.sub(r'[^a-zA-Z0-9_]', '_', str(key))[:100]
            
            if isinstance(value, str):
                sanitized[safe_key] = self._sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[safe_key] = self._sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[safe_key] = self._sanitize_list(value)
            elif isinstance(value, (int, float, bool)):
                sanitized[safe_key] = value
            elif value is None:
                sanitized[safe_key] = None
            else:
                # Convert other types to string and sanitize
                sanitized[safe_key] = self._sanitize_string(str(value))
        
        return sanitized
    
    def _sanitize_list(self, data: list) -> list:
        """Recursively sanitize list items"""
        sanitized = []
        
        for item in data:
            if isinstance(item, str):
                sanitized.append(self._sanitize_string(item))
            elif isinstance(item, dict):
                sanitized.append(self._sanitize_dict(item))
            elif isinstance(item, list):
                sanitized.append(self._sanitize_list(item))
            elif isinstance(item, (int, float, bool)):
                sanitized.append(item)
            elif item is None:
                sanitized.append(None)
            else:
                sanitized.append(self._sanitize_string(str(item)))
        
        return sanitized
    
    def _sanitize_string(self, value: str) -> str:
        """Sanitize string value"""
        if not isinstance(value, str):
            return str(value)
        
        # Limit string length
        if len(value) > 10000:
            value = value[:10000] + "...[TRUNCATED]"
        
        # Remove dangerous patterns
        for pattern, replacement in self.DANGEROUS_PATTERNS:
            value = pattern.sub(replacement, value)
        
        # HTML escape
        value = html.escape(value)
        
        return value
    
    def validate_webhook(
        self,
        payload: bytes,
        signature: Optional[str],
        secret: str,
        timestamp: Optional[int] = None,
        max_age_seconds: Optional[int] = None
    ) -> ValidationResult:
        """
        Perform complete webhook validation
        
        Args:
            payload: Raw request body
            signature: Provided signature
            secret: Webhook secret
            timestamp: Unix timestamp for replay protection
            max_age_seconds: Maximum timestamp age
            
        Returns:
            ValidationResult with validation status and details
        """
        result = ValidationResult(valid=False)
        errors = []
        
        # Check payload size
        if len(payload) > self.MAX_PAYLOAD_SIZE:
            errors.append(f"Payload exceeds max size: {len(payload)} > {self.MAX_PAYLOAD_SIZE}")
            return ValidationResult(
                valid=False,
                error_message="; ".join(errors)
            )
        
        # Validate signature
        if signature:
            result.signature_valid = self.validate_signature(payload, signature, secret)
            if not result.signature_valid:
                errors.append("Invalid signature")
        else:
            errors.append("Missing signature")
        
        # Validate timestamp
        if timestamp:
            result.timestamp_valid = self.validate_timestamp(timestamp, max_age_seconds)
            if not result.timestamp_valid:
                errors.append("Invalid or expired timestamp")
        else:
            # Timestamp is optional for some integrations
            result.timestamp_valid = True
        
        # Sanitize payload
        result.sanitized_payload = self.sanitize_payload(payload)
        if "error" in result.sanitized_payload:
            errors.append(f"Payload sanitization error: {result.sanitized_payload['error']}")
        
        # Determine overall validity
        result.valid = result.signature_valid and result.timestamp_valid and len(errors) == 0
        
        if errors:
            result.error_message = "; ".join(errors)
        
        return result
    
    def extract_signature_from_headers(
        self,
        headers: Dict[str, str],
        header_names: list = None
    ) -> Optional[str]:
        """
        Extract signature from various header formats
        
        Args:
            headers: HTTP headers dict
            header_names: List of header names to check (case-insensitive)
            
        Returns:
            Signature string or None
        """
        if header_names is None:
            header_names = [
                "X-Signature",
                "X-Webhook-Signature",
                "X-TradingView-Signature",
                "Signature",
                "X-Signature-Sha256",
            ]
        
        headers_lower = {k.lower(): v for k, v in headers.items()}
        
        for name in header_names:
            if name.lower() in headers_lower:
                return headers_lower[name.lower()]
        
        return None
    
    def extract_timestamp_from_headers(
        self,
        headers: Dict[str, str]
    ) -> Optional[int]:
        """
        Extract timestamp from various header formats
        
        Args:
            headers: HTTP headers dict
            
        Returns:
            Unix timestamp or None
        """
        timestamp_headers = [
            "x-timestamp",
            "x-webhook-timestamp",
            "x-request-timestamp",
            "timestamp",
        ]
        
        headers_lower = {k.lower(): v for k, v in headers.items()}
        
        for name in timestamp_headers:
            if name in headers_lower:
                try:
                    timestamp = int(headers_lower[name])
                    # Convert milliseconds to seconds if needed
                    if timestamp > 1_000_000_000_000:
                        timestamp = timestamp // 1000
                    return timestamp
                except (ValueError, TypeError):
                    continue
        
        return None
