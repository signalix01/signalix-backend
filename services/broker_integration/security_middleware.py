"""
Security Middleware for Broker Integration Service

CSRF protection and rate limiting for enhanced security.
Part of Phase 4.3 security hardening.

Requirements: CSRF protection and rate limiting
"""

import time
import hashlib
import secrets
from typing import Optional, Dict, Any, Callable
from functools import wraps
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

logger = logging.getLogger(__name__)


class CSRFProtection:
    """
    CSRF (Cross-Site Request Forgery) Protection.
    
    Implements double-submit cookie pattern for state-changing operations.
    """
    
    def __init__(
        self,
        token_length: int = 32,
        cookie_name: str = "csrf_token",
        header_name: str = "X-CSRF-Token",
        max_age: int = 3600
    ):
        """
        Initialize CSRF protection.
        
        Args:
            token_length: Length of CSRF token
            cookie_name: Name of the CSRF cookie
            header_name: Name of the CSRF header
            max_age: Token max age in seconds
        """
        self.token_length = token_length
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.max_age = max_age
        self._tokens: Dict[str, tuple[str, datetime]] = {}  # user_id -> (token, expiry)
    
    def generate_token(self, user_id: str) -> str:
        """Generate a new CSRF token for a user."""
        token = secrets.token_urlsafe(self.token_length)
        expiry = datetime.utcnow() + timedelta(seconds=self.max_age)
        self._tokens[user_id] = (token, expiry)
        return token
    
    def validate_token(self, user_id: str, token: str) -> bool:
        """Validate a CSRF token for a user."""
        if user_id not in self._tokens:
            return False
        
        stored_token, expiry = self._tokens[user_id]
        
        if datetime.utcnow() > expiry:
            del self._tokens[user_id]
            return False
        
        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(stored_token, token)
    
    def clear_token(self, user_id: str):
        """Clear a user's CSRF token."""
        self._tokens.pop(user_id, None)
    
    async def protect(self, request: Request) -> None:
        """
        Middleware to protect state-changing requests.
        
        Args:
            request: FastAPI request object
            
        Raises:
            HTTPException: If CSRF validation fails
        """
        # Only check state-changing methods
        if request.method not in ["POST", "PUT", "PATCH", "DELETE"]:
            return
        
        # Skip CSRF for certain paths (e.g., webhooks)
        path = request.url.path
        if any(skip in path for skip in ["/webhook", "/callback", "/health"]):
            return
        
        # Get user ID from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(
                status_code=403,
                detail="CSRF protection: User not authenticated"
            )
        
        # Get CSRF token from header
        csrf_token = request.headers.get(self.header_name)
        if not csrf_token:
            raise HTTPException(
                status_code=403,
                detail=f"CSRF protection: Missing {self.header_name} header"
            )
        
        # Validate token
        if not self.validate_token(user_id, csrf_token):
            raise HTTPException(
                status_code=403,
                detail="CSRF protection: Invalid or expired token"
            )
    
    def get_csrf_cookie(self, user_id: str) -> Dict[str, Any]:
        """Get CSRF token as cookie settings."""
        token = self.generate_token(user_id)
        return {
            "key": self.cookie_name,
            "value": token,
            "max_age": self.max_age,
            "httponly": False,  # Must be accessible by JS for double-submit
            "secure": True,
            "samesite": "strict"
        }


class RateLimiter:
    """
    Rate Limiter using sliding window algorithm.
    
    Protects against brute force and DoS attacks.
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        block_duration: int = 300
    ):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests per minute
            burst_size: Maximum burst requests
            block_duration: Block duration in seconds after exceeding limit
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.block_duration = block_duration
        
        # In-memory storage (use Redis in production)
        self._requests: Dict[str, list] = {}  # key -> list of timestamps
        self._blocked: Dict[str, datetime] = {}  # key -> block expiry
        
    def _get_key(self, request: Request, identifier: Optional[str] = None) -> str:
        """Generate rate limit key from request."""
        if identifier:
            return identifier
        
        # Use IP + path hash
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        return hashlib.sha256(f"{client_ip}:{path}".encode()).hexdigest()[:16]
    
    def is_allowed(self, key: str) -> tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed under rate limit.
        
        Returns:
            Tuple of (allowed, rate_limit_info)
        """
        now = datetime.utcnow()
        
        # Check if blocked
        if key in self._blocked:
            block_expiry = self._blocked[key]
            if now < block_expiry:
                remaining = int((block_expiry - now).total_seconds())
                return False, {
                    "blocked": True,
                    "retry_after": remaining,
                    "limit": self.requests_per_minute,
                    "window": 60
                }
            else:
                del self._blocked[key]
        
        # Clean old requests
        cutoff = now - timedelta(minutes=1)
        if key in self._requests:
            self._requests[key] = [
                ts for ts in self._requests[key] if ts > cutoff
            ]
        else:
            self._requests[key] = []
        
        # Check burst limit
        if len(self._requests[key]) >= self.burst_size:
            # Block for duration
            self._blocked[key] = now + timedelta(seconds=self.block_duration)
            return False, {
                "blocked": True,
                "retry_after": self.block_duration,
                "limit": self.requests_per_minute,
                "window": 60,
                "burst_exceeded": True
            }
        
        # Check rate limit
        if len(self._requests[key]) >= self.requests_per_minute:
            oldest = self._requests[key][0]
            retry_after = int(60 - (now - oldest).total_seconds())
            return False, {
                "blocked": False,
                "retry_after": max(0, retry_after),
                "limit": self.requests_per_minute,
                "window": 60,
                "remaining": 0
            }
        
        # Record request
        self._requests[key].append(now)
        
        remaining = self.requests_per_minute - len(self._requests[key])
        
        return True, {
            "blocked": False,
            "limit": self.requests_per_minute,
            "remaining": remaining,
            "window": 60,
            "reset_after": 60
        }
    
    async def check_rate_limit(
        self,
        request: Request,
        identifier: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check rate limit and raise exception if exceeded.
        
        Args:
            request: FastAPI request object
            identifier: Optional custom identifier
            
        Returns:
            Rate limit info if allowed
            
        Raises:
            HTTPException: If rate limit exceeded
        """
        key = self._get_key(request, identifier)
        allowed, info = self.is_allowed(key)
        
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "retry_after": info.get("retry_after", 60),
                    "message": f"Too many requests. Please retry after {info.get('retry_after', 60)} seconds."
                },
                headers={
                    "Retry-After": str(info.get("retry_after", 60)),
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(info.get("reset_after", 60))
                }
            )
        
        return info


class SecurityHeaders:
    """Security headers middleware configuration."""
    
    DEFAULT_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        ),
        "Cache-Control": "no-store, max-age=0",
    }
    
    def __init__(self, additional_headers: Optional[Dict[str, str]] = None):
        self.headers = {**self.DEFAULT_HEADERS, **(additional_headers or {})}
    
    async def add_security_headers(self, request: Request, call_next: Callable):
        """Add security headers to response."""
        response = await call_next(request)
        
        for header, value in self.headers.items():
            response.headers[header] = value
        
        return response


def create_security_middleware(app, 
                                 enable_csrf: bool = True,
                                 enable_rate_limit: bool = True,
                                 rate_limit_per_minute: int = 60):
    """
    Create and configure security middleware for FastAPI app.
    
    Args:
        app: FastAPI application
        enable_csrf: Enable CSRF protection
        enable_rate_limit: Enable rate limiting
        rate_limit_per_minute: Rate limit per minute
    """
    csrf = CSRFProtection() if enable_csrf else None
    rate_limiter = RateLimiter(requests_per_minute=rate_limit_per_minute) if enable_rate_limit else None
    security_headers = SecurityHeaders()
    
    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        """Apply security middleware."""
        try:
            # Rate limiting
            if rate_limiter:
                rate_info = await rate_limiter.check_rate_limit(request)
                request.state.rate_limit_info = rate_info
            
            # CSRF protection
            if csrf:
                await csrf.protect(request)
            
            # Process request
            response = await call_next(request)
            
            # Add security headers
            response = await security_headers.add_security_headers(request, lambda: response)
            
            # Add rate limit headers
            if rate_limiter and hasattr(request.state, "rate_limit_info"):
                info = request.state.rate_limit_info
                response.headers["X-RateLimit-Limit"] = str(info.get("limit", 60))
                response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 0))
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Security middleware error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
    
    return {
        "csrf": csrf,
        "rate_limiter": rate_limiter,
        "security_headers": security_headers
    }


# Dependency for endpoints that need rate limit info
depends_rate_limit_info = HTTPBearer(auto_error=False)

async def get_rate_limit_info(request: Request) -> Optional[Dict[str, Any]]:
    """Get rate limit info from request state."""
    return getattr(request.state, "rate_limit_info", None)
