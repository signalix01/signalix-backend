"""
Telegram Authentication Handler

Handles Telegram user authentication and session management.
Requirements: 24.1, 24.2, 24.3, 24.5, 24.9
"""

import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from services.telegram_service.models.telegram_models import (
    TelegramConnection, TelegramAuthToken, ConnectionStatus
)

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    """Authentication result"""
    success: bool
    message: str
    connection: Optional[TelegramConnection] = None
    user_id: Optional[str] = None


class TelegramAuthHandler:
    """Handle Telegram authentication"""
    
    # Configuration
    TOKEN_VALIDITY_MINUTES = 10
    SESSION_VALIDITY_HOURS = 24
    MAX_AUTH_ATTEMPTS = 3
    BLOCK_DURATION_MINUTES = 30
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        
    async def generate_auth_token(self, db: AsyncSession, user_id: str) -> TelegramAuthToken:
        """
        Generate one-time authentication token for Telegram linking.
        Requirements: 24.1, 24.2
        """
        # Generate secure random token
        token = secrets.token_urlsafe(32)
        
        # Set expiry
        expires_at = datetime.utcnow() + timedelta(minutes=self.TOKEN_VALIDITY_MINUTES)
        
        # Create auth token record
        auth_token = TelegramAuthToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at
        )
        
        db.add(auth_token)
        await db.commit()
        await db.refresh(auth_token)
        
        # Cache in Redis for quick lookup
        if self.redis:
            cache_key = f"telegram:auth_token:{token}"
            await self.redis.setex(
                cache_key,
                self.TOKEN_VALIDITY_MINUTES * 60,
                user_id
            )
        
        logger.info(f"Generated auth token for user {user_id}, expires at {expires_at}")
        
        return auth_token
    
    async def validate_auth_token(
        self, 
        db: AsyncSession, 
        token: str, 
        telegram_user_id: str,
        telegram_username: Optional[str] = None,
        telegram_first_name: Optional[str] = None,
        telegram_last_name: Optional[str] = None
    ) -> AuthResult:
        """
        Validate authentication token and link Telegram account.
        Requirements: 24.1, 24.3, 24.5
        """
        try:
            # Check Redis cache first
            user_id = None
            if self.redis:
                cache_key = f"telegram:auth_token:{token}"
                user_id = await self.redis.get(cache_key)
            
            # Query database if not in cache
            if not user_id:
                query = select(TelegramAuthToken).where(
                    and_(
                        TelegramAuthToken.token == token,
                        TelegramAuthToken.expires_at > datetime.utcnow(),
                        TelegramAuthToken.used_at.is_(None)
                    )
                )
                result = await db.execute(query)
                auth_token = result.scalar_one_or_none()
                
                if not auth_token:
                    logger.warning(f"Invalid or expired auth token: {token[:10]}...")
                    return AuthResult(
                        success=False,
                        message="Invalid or expired authentication token. Please generate a new token from the web interface."
                    )
                
                user_id = auth_token.user_id
            
            # Mark token as used
            query = select(TelegramAuthToken).where(TelegramAuthToken.token == token)
            result = await db.execute(query)
            auth_token = result.scalar_one_or_none()
            
            if auth_token and not auth_token.used_at:
                auth_token.used_at = datetime.utcnow()
                auth_token.used_by_telegram_user_id = telegram_user_id
            
            # Check if connection already exists
            query = select(TelegramConnection).where(
                TelegramConnection.telegram_user_id == telegram_user_id
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing connection
                existing.user_id = user_id
                existing.status = ConnectionStatus.CONNECTED
                existing.connected_at = datetime.utcnow()
                existing.telegram_username = telegram_username
                existing.telegram_first_name = telegram_first_name
                existing.telegram_last_name = telegram_last_name
                existing.last_activity_at = datetime.utcnow()
                existing.session_expires_at = datetime.utcnow() + timedelta(hours=self.SESSION_VALIDITY_HOURS)
                existing.auth_attempts = 0
                existing.auth_blocked_until = None
                
                await db.commit()
                await db.refresh(existing)
                
                logger.info(f"Reconnected Telegram user {telegram_user_id} to user {user_id}")
                
                return AuthResult(
                    success=True,
                    message="✅ Your Telegram account has been reconnected successfully! You can now receive alerts and execute commands.",
                    connection=existing,
                    user_id=user_id
                )
            
            # Create new connection
            connection = TelegramConnection(
                user_id=user_id,
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
                telegram_first_name=telegram_first_name,
                telegram_last_name=telegram_last_name,
                status=ConnectionStatus.CONNECTED,
                connected_at=datetime.utcnow(),
                last_activity_at=datetime.utcnow(),
                session_expires_at=datetime.utcnow() + timedelta(hours=self.SESSION_VALIDITY_HOURS)
            )
            
            db.add(connection)
            await db.commit()
            await db.refresh(connection)
            
            logger.info(f"Linked Telegram user {telegram_user_id} to user {user_id}")
            
            return AuthResult(
                success=True,
                message="✅ Authentication successful! Your Telegram account is now linked to SignalixAI.\n\nYou can now:\n• Receive order alerts\n• View positions and orders\n• Execute trading commands\n\nType /help to see available commands.",
                connection=connection,
                user_id=user_id
            )
            
        except Exception as e:
            logger.error(f"Error validating auth token: {e}")
            return AuthResult(
                success=False,
                message="❌ An error occurred during authentication. Please try again or contact support."
            )
    
    async def check_authentication(
        self, 
        db: AsyncSession, 
        telegram_user_id: str
    ) -> AuthResult:
        """
        Check if Telegram user is authenticated and session is valid.
        Requirements: 24.3, 24.5
        """
        try:
            query = select(TelegramConnection).where(
                TelegramConnection.telegram_user_id == telegram_user_id
            )
            result = await db.execute(query)
            connection = result.scalar_one_or_none()
            
            if not connection:
                return AuthResult(
                    success=False,
                    message="🔐 You need to authenticate first. Please visit the SignalixAI web app to get your authentication token, then use /auth <token>"
                )
            
            # Check if blocked
            if connection.auth_blocked_until and connection.auth_blocked_until > datetime.utcnow():
                remaining = int((connection.auth_blocked_until - datetime.utcnow()).total_seconds() / 60)
                return AuthResult(
                    success=False,
                    message=f"⛔ Your account is temporarily blocked due to too many failed attempts. Please try again in {remaining} minutes."
                )
            
            # Check session expiry
            if connection.session_expires_at and connection.session_expires_at < datetime.utcnow():
                connection.status = ConnectionStatus.DISCONNECTED
                await db.commit()
                
                return AuthResult(
                    success=False,
                    message="🔐 Your session has expired. Please re-authenticate using /auth <token> or visit the web app."
                )
            
            # Check if connected
            if connection.status != ConnectionStatus.CONNECTED:
                return AuthResult(
                    success=False,
                    message="🔐 Your account is not connected. Please authenticate using /auth <token>"
                )
            
            # Update last activity
            connection.last_activity_at = datetime.utcnow()
            await db.commit()
            
            return AuthResult(
                success=True,
                message="Authenticated",
                connection=connection,
                user_id=str(connection.user_id)
            )
            
        except Exception as e:
            logger.error(f"Error checking authentication: {e}")
            return AuthResult(
                success=False,
                message="❌ An error occurred. Please try again."
            )
    
    async def record_auth_attempt(
        self, 
        db: AsyncSession, 
        telegram_user_id: str, 
        success: bool
    ) -> None:
        """
        Record authentication attempt for rate limiting.
        Requirements: 24.9
        """
        try:
            query = select(TelegramConnection).where(
                TelegramConnection.telegram_user_id == telegram_user_id
            )
            result = await db.execute(query)
            connection = result.scalar_one_or_none()
            
            if connection:
                if success:
                    connection.auth_attempts = 0
                    connection.auth_blocked_until = None
                else:
                    connection.auth_attempts += 1
                    
                    # Block after max attempts
                    if connection.auth_attempts >= self.MAX_AUTH_ATTEMPTS:
                        connection.auth_blocked_until = datetime.utcnow() + timedelta(minutes=self.BLOCK_DURATION_MINUTES)
                        logger.warning(f"Blocked Telegram user {telegram_user_id} after {connection.auth_attempts} failed attempts")
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error recording auth attempt: {e}")
    
    async def revoke_connection(
        self, 
        db: AsyncSession, 
        user_id: str,
        telegram_user_id: Optional[str] = None
    ) -> bool:
        """
        Revoke Telegram connection from web interface.
        Requirements: 24.6
        """
        try:
            query = select(TelegramConnection).where(
                TelegramConnection.user_id == user_id
            )
            
            if telegram_user_id:
                query = query.where(TelegramConnection.telegram_user_id == telegram_user_id)
            
            result = await db.execute(query)
            connections = result.scalars().all()
            
            for connection in connections:
                connection.status = ConnectionStatus.REVOKED
                connection.disconnected_at = datetime.utcnow()
            
            await db.commit()
            
            logger.info(f"Revoked {len(connections)} Telegram connection(s) for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error revoking connection: {e}")
            return False
    
    async def get_connection_by_user(
        self, 
        db: AsyncSession, 
        user_id: str
    ) -> Optional[TelegramConnection]:
        """Get Telegram connection by SignalixAI user ID"""
        try:
            query = select(TelegramConnection).where(
                and_(
                    TelegramConnection.user_id == user_id,
                    TelegramConnection.status == ConnectionStatus.CONNECTED
                )
            )
            result = await db.execute(query)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Error getting connection: {e}")
            return None
    
    async def refresh_session(
        self, 
        db: AsyncSession, 
        telegram_user_id: str
    ) -> bool:
        """Refresh user session"""
        try:
            query = select(TelegramConnection).where(
                TelegramConnection.telegram_user_id == telegram_user_id
            )
            result = await db.execute(query)
            connection = result.scalar_one_or_none()
            
            if connection:
                connection.session_expires_at = datetime.utcnow() + timedelta(hours=self.SESSION_VALIDITY_HOURS)
                connection.last_activity_at = datetime.utcnow()
                await db.commit()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error refreshing session: {e}")
            return False
