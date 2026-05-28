"""
Broker Credential Manager

Manages broker credential encryption and secure storage.
Supports OAuth, API Key, and Session Token authentication flows.

Requirements: 10.10, 16.6, 20.10
"""

import os
import base64
import hashlib
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import logging

logger = logging.getLogger(__name__)


class CredentialManager:
    """
    Manages encryption and decryption of broker credentials.
    
    Uses AES-256 encryption via Fernet (which uses AES-256 in CBC mode).
    """
    
    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize credential manager.
        
        Args:
            master_key: Master encryption key. If not provided, uses environment variable.
        """
        self.master_key = master_key or os.getenv('BROKER_CREDENTIAL_MASTER_KEY')
        if not self.master_key:
            logger.warning("No master key provided - using development key")
            self.master_key = "dev-key-not-for-production"
        
        self._fernet = self._initialize_cipher()
    
    def _initialize_cipher(self) -> Fernet:
        """Initialize Fernet cipher from master key."""
        # Derive a 32-byte key from the master key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._get_salt(),
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key.encode()))
        return Fernet(key)
    
    def _get_salt(self) -> bytes:
        """Get or generate salt for key derivation."""
        salt_env = os.getenv('BROKER_CREDENTIAL_SALT')
        if salt_env:
            return base64.urlsafe_b64decode(salt_env)
        # Use a fixed salt for development (in production, this should be securely stored)
        return hashlib.sha256(b"signalixai-broker-salt-v1").digest()[:16]
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext credential.
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            Base64-encoded encrypted string
        """
        if not plaintext:
            return ""
        
        try:
            encrypted = self._fernet.encrypt(plaintext.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError(f"Failed to encrypt credential: {e}")
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt encrypted credential.
        
        Args:
            ciphertext: Base64-encoded encrypted string
            
        Returns:
            Decrypted plaintext string
        """
        if not ciphertext:
            return ""
        
        try:
            encrypted = base64.urlsafe_b64decode(ciphertext.encode())
            decrypted = self._fernet.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Failed to decrypt credential: {e}")
    
    def encrypt_credentials(self, credentials: Dict[str, str]) -> Dict[str, str]:
        """
        Encrypt multiple credentials.
        
        Args:
            credentials: Dictionary of credential fields
            
        Returns:
            Dictionary with encrypted values
        """
        encrypted = {}
        for key, value in credentials.items():
            if value and self._is_sensitive_field(key):
                encrypted[key] = self.encrypt(value)
            else:
                encrypted[key] = value
        return encrypted
    
    def decrypt_credentials(self, credentials: Dict[str, str]) -> Dict[str, str]:
        """
        Decrypt multiple credentials.
        
        Args:
            credentials: Dictionary of encrypted credential fields
            
        Returns:
            Dictionary with decrypted values
        """
        decrypted = {}
        for key, value in credentials.items():
            if value and self._is_sensitive_field(key):
                try:
                    decrypted[key] = self.decrypt(value)
                except Exception as e:
                    logger.error(f"Failed to decrypt {key}: {e}")
                    decrypted[key] = value  # Keep original if decryption fails
            else:
                decrypted[key] = value
        return decrypted
    
    def _is_sensitive_field(self, field_name: str) -> bool:
        """
        Check if a field contains sensitive data that should be encrypted.
        
        Args:
            field_name: Name of the credential field
            
        Returns:
            True if field should be encrypted
        """
        sensitive_fields = [
            'api_key', 'api_secret', 'access_token', 'refresh_token',
            'client_id', 'password', 'pin', 'totp_secret', 'api_token',
            'session_token', 'auth_token', 'consumer_key', 'consumer_secret'
        ]
        return any(sensitive in field_name.lower() for sensitive in sensitive_fields)
    
    def validate_credentials(
        self,
        auth_type: str,
        credentials: Dict[str, str]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate credential format before encryption.
        
        Args:
            auth_type: Authentication type (api_key, oauth, etc.)
            credentials: Credential fields
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = self._get_required_fields(auth_type)
        
        for field in required_fields:
            if field not in credentials or not credentials[field]:
                return False, f"Missing required credential field: {field}"
        
        # Type-specific validation
        if auth_type == "api_key":
            if len(credentials.get('api_key', '')) < 8:
                return False, "API key too short"
        
        elif auth_type == "oauth":
            if 'access_token' not in credentials:
                return False, "Missing access token for OAuth"
        
        return True, None
    
    def _get_required_fields(self, auth_type: str) -> list:
        """Get required credential fields for each auth type."""
        fields = {
            "api_key": ["api_key"],
            "oauth": ["access_token"],
            "session_token": ["session_token"],
            "two_factor": ["api_key", "api_secret"]
        }
        return fields.get(auth_type, ["api_key"])
    
    def rotate_key(self, new_master_key: str) -> bool:
        """
        Rotate encryption key (for key rotation scenarios).
        
        Note: This requires re-encrypting all existing credentials.
        
        Args:
            new_master_key: New master key
            
        Returns:
            True if rotation successful
        """
        try:
            # Store old cipher
            old_fernet = self._fernet
            
            # Update master key and create new cipher
            self.master_key = new_master_key
            self._fernet = self._initialize_cipher()
            
            logger.info("Encryption key rotated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Key rotation failed: {e}")
            return False
    
    def generate_secure_token(self, length: int = 32) -> str:
        """
        Generate a secure random token.
        
        Args:
            length: Token length
            
        Returns:
            Secure random token
        """
        import secrets
        return secrets.token_urlsafe(length)
    
    def hash_identifier(self, identifier: str) -> str:
        """
        Create a one-way hash of an identifier (for searching without exposing value).
        
        Args:
            identifier: String to hash
            
        Returns:
            Hash string
        """
        return hashlib.sha256(identifier.encode()).hexdigest()[:16]


class SecureCredentialStorage:
    """
    Secure storage wrapper for broker credentials.
    
    Provides high-level interface for credential operations.
    """
    
    def __init__(self, credential_manager: CredentialManager, db_session=None):
        """
        Initialize secure storage.
        
        Args:
            credential_manager: CredentialManager instance
            db_session: Database session for persistence
        """
        self.cm = credential_manager
        self.db = db_session
    
    async def store_credentials(
        self,
        connection_id: str,
        auth_type: str,
        credentials: Dict[str, str]
    ) -> tuple[bool, Optional[str]]:
        """
        Store encrypted credentials for a broker connection.
        
        Args:
            connection_id: Broker connection ID
            auth_type: Authentication type
            credentials: Credential fields
            
        Returns:
            Tuple of (success, error_message)
        """
        # Validate credentials
        is_valid, error = self.cm.validate_credentials(auth_type, credentials)
        if not is_valid:
            return False, error
        
        # Encrypt sensitive fields
        encrypted = self.cm.encrypt_credentials(credentials)
        
        # Store in database
        if self.db:
            try:
                from ..models import BrokerConnection, AuthType
                
                connection = self.db.query(BrokerConnection).filter(
                    BrokerConnection.id == connection_id
                ).first()
                
                if not connection:
                    return False, "Connection not found"
                
                # Update fields
                connection.auth_type = AuthType(auth_type)
                connection.api_key = encrypted.get('api_key', '')
                connection.api_secret = encrypted.get('api_secret', '')
                connection.access_token = encrypted.get('access_token', '')
                connection.refresh_token = encrypted.get('refresh_token', '')
                connection.client_id = encrypted.get('client_id', '')
                
                self.db.commit()
                
                logger.info(f"Stored encrypted credentials for connection {connection_id}")
                return True, None
                
            except Exception as e:
                logger.error(f"Failed to store credentials: {e}")
                return False, str(e)
        
        return True, None
    
    async def retrieve_credentials(
        self,
        connection_id: str
    ) -> tuple[Optional[Dict[str, str]], Optional[str]]:
        """
        Retrieve and decrypt credentials for a broker connection.
        
        Args:
            connection_id: Broker connection ID
            
        Returns:
            Tuple of (credentials_dict, error_message)
        """
        if not self.db:
            return None, "No database session available"
        
        try:
            from ..models import BrokerConnection
            
            connection = self.db.query(BrokerConnection).filter(
                BrokerConnection.id == connection_id
            ).first()
            
            if not connection:
                return None, "Connection not found"
            
            # Get encrypted fields
            encrypted = {
                'api_key': connection.api_key,
                'api_secret': connection.api_secret,
                'access_token': connection.access_token,
                'refresh_token': connection.refresh_token,
                'client_id': connection.client_id
            }
            
            # Decrypt
            credentials = self.cm.decrypt_credentials(encrypted)
            
            return credentials, None
            
        except Exception as e:
            logger.error(f"Failed to retrieve credentials: {e}")
            return None, str(e)
    
    async def update_access_token(
        self,
        connection_id: str,
        access_token: str,
        refresh_token: Optional[str] = None
    ) -> bool:
        """
        Update OAuth access token (for token refresh scenarios).
        
        Args:
            connection_id: Broker connection ID
            access_token: New access token
            refresh_token: Optional new refresh token
            
        Returns:
            True if update successful
        """
        if not self.db:
            return False
        
        try:
            from ..models import BrokerConnection
            
            connection = self.db.query(BrokerConnection).filter(
                BrokerConnection.id == connection_id
            ).first()
            
            if not connection:
                return False
            
            # Encrypt and store
            connection.access_token = self.cm.encrypt(access_token)
            if refresh_token:
                connection.refresh_token = self.cm.encrypt(refresh_token)
            
            self.db.commit()
            
            logger.info(f"Updated access token for connection {connection_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update access token: {e}")
            return False
