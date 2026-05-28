#!/usr/bin/env python3
"""
Production Setup Script
Validates environment and prepares for deployment
"""

import os
import sys
import json
from typing import Dict, List, Tuple

# Color codes for terminal output
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_header(text: str):
    """Print section header"""
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}{text.center(70)}{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")


def print_success(text: str):
    """Print success message"""
    print(f"{GREEN}✓ {text}{RESET}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{YELLOW}⚠ {text}{RESET}")


def print_error(text: str):
    """Print error message"""
    print(f"{RED}✗ {text}{RESET}")


def check_required_env_vars() -> Tuple[List[str], List[str]]:
    """
    Check if all required environment variables are set
    
    Returns:
        Tuple of (present_vars, missing_vars)
    """
    required_vars = [
        "DATABASE_URL",
        "REDIS_URL",
        "JWT_SECRET_KEY",
        "ANTHROPIC_API_KEY",
    ]
    
    optional_vars = [
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "MISTRAL_API_KEY",
        "SENTRY_DSN",
        "SENDGRID_API_KEY",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "RAZORPAY_KEY_ID",
        "RAZORPAY_KEY_SECRET",
        "STRIPE_API_KEY",
    ]
    
    present = []
    missing = []
    
    print_header("Environment Variables Check")
    
    print("Required Variables:")
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print_success(f"{var}: Set")
            present.append(var)
        else:
            print_error(f"{var}: Missing")
            missing.append(var)
    
    print("\nOptional Variables:")
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print_success(f"{var}: Set")
        else:
            print_warning(f"{var}: Not set (optional)")
    
    return present, missing


def validate_database_url() -> bool:
    """Validate database URL format"""
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        return False
    
    # Check if it's async format
    if not db_url.startswith("postgresql+asyncpg://"):
        print_warning("DATABASE_URL should use asyncpg driver: postgresql+asyncpg://...")
        return False
    
    return True


def validate_redis_url() -> bool:
    """Validate Redis URL format"""
    redis_url = os.getenv("REDIS_URL")
    
    if not redis_url:
        return False
    
    if not redis_url.startswith("redis://"):
        print_warning("REDIS_URL should start with redis://")
        return False
    
    return True


def validate_jwt_secret() -> bool:
    """Validate JWT secret strength"""
    jwt_secret = os.getenv("JWT_SECRET_KEY")
    
    if not jwt_secret:
        return False
    
    if len(jwt_secret) < 32:
        print_warning("JWT_SECRET_KEY should be at least 32 characters long")
        return False
    
    if jwt_secret == "your-secret-key-change-this-in-production":
        print_error("JWT_SECRET_KEY is using default value - INSECURE!")
        return False
    
    return True


def check_python_version() -> bool:
    """Check Python version"""
    print_header("Python Version Check")
    
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    
    if version.major == 3 and version.minor >= 11:
        print_success(f"Python {version_str} (✓ 3.11+ required)")
        return True
    else:
        print_error(f"Python {version_str} (✗ 3.11+ required)")
        return False


def check_dependencies() -> bool:
    """Check if all dependencies are installed"""
    print_header("Dependencies Check")
    
    required_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "alembic",
        "redis",
        "langchain",
        "langgraph",
        "sentry_sdk",
        "slowapi",
    ]
    
    all_installed = True
    
    for package in required_packages:
        try:
            __import__(package)
            print_success(f"{package}: Installed")
        except ImportError:
            print_error(f"{package}: Not installed")
            all_installed = False
    
    if not all_installed:
        print("\nInstall missing dependencies:")
        print("  pip install -r requirements.txt")
    
    return all_installed


def check_database_connection() -> bool:
    """Test database connection"""
    print_header("Database Connection Check")
    
    try:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print_error("DATABASE_URL not set")
            return False
        
        async def test_connection():
            engine = create_async_engine(db_url, echo=False)
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                result.scalar()
            await engine.dispose()
        
        asyncio.run(test_connection())
        print_success("Database connection successful")
        return True
        
    except Exception as e:
        print_error(f"Database connection failed: {str(e)}")
        return False


def check_redis_connection() -> bool:
    """Test Redis connection"""
    print_header("Redis Connection Check")
    
    try:
        import asyncio
        import redis.asyncio as redis
        
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            print_error("REDIS_URL not set")
            return False
        
        async def test_connection():
            client = redis.from_url(redis_url, decode_responses=True)
            await client.ping()
            await client.close()
        
        asyncio.run(test_connection())
        print_success("Redis connection successful")
        return True
        
    except Exception as e:
        print_error(f"Redis connection failed: {str(e)}")
        return False


def generate_deployment_summary(checks: Dict[str, bool]) -> str:
    """Generate deployment readiness summary"""
    total = len(checks)
    passed = sum(1 for v in checks.values() if v)
    percentage = (passed / total) * 100
    
    summary = f"\n{BLUE}{'=' * 70}{RESET}\n"
    summary += f"{BLUE}{'DEPLOYMENT READINESS SUMMARY'.center(70)}{RESET}\n"
    summary += f"{BLUE}{'=' * 70}{RESET}\n\n"
    
    for check, result in checks.items():
        status = f"{GREEN}✓ PASS{RESET}" if result else f"{RED}✗ FAIL{RESET}"
        summary += f"  {check.ljust(40)} {status}\n"
    
    summary += f"\n{BLUE}{'=' * 70}{RESET}\n"
    summary += f"  Overall: {passed}/{total} checks passed ({percentage:.0f}%)\n"
    summary += f"{BLUE}{'=' * 70}{RESET}\n"
    
    if percentage == 100:
        summary += f"\n{GREEN}✓ READY FOR DEPLOYMENT{RESET}\n"
    elif percentage >= 80:
        summary += f"\n{YELLOW}⚠ MOSTLY READY - Fix remaining issues{RESET}\n"
    else:
        summary += f"\n{RED}✗ NOT READY - Critical issues must be fixed{RESET}\n"
    
    return summary


def main():
    """Main setup validation"""
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}{'SignalixAI Backend - Production Setup Validation'.center(70)}{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}")
    
    checks = {}
    
    # Check Python version
    checks["Python 3.11+"] = check_python_version()
    
    # Check dependencies
    checks["Dependencies installed"] = check_dependencies()
    
    # Check environment variables
    present, missing = check_required_env_vars()
    checks["Required env vars"] = len(missing) == 0
    
    # Validate configurations
    if "DATABASE_URL" in present:
        checks["Database URL format"] = validate_database_url()
        checks["Database connection"] = check_database_connection()
    else:
        checks["Database URL format"] = False
        checks["Database connection"] = False
    
    if "REDIS_URL" in present:
        checks["Redis URL format"] = validate_redis_url()
        checks["Redis connection"] = check_redis_connection()
    else:
        checks["Redis URL format"] = False
        checks["Redis connection"] = False
    
    if "JWT_SECRET_KEY" in present:
        checks["JWT secret strength"] = validate_jwt_secret()
    else:
        checks["JWT secret strength"] = False
    
    # Print summary
    summary = generate_deployment_summary(checks)
    print(summary)
    
    # Exit with appropriate code
    if all(checks.values()):
        print(f"\n{GREEN}Next steps:{RESET}")
        print("  1. Run database migrations: alembic upgrade head")
        print("  2. Seed initial data: python scripts/init_database.py")
        print("  3. Deploy to Railway: bash scripts/deploy_railway.sh")
        sys.exit(0)
    else:
        print(f"\n{RED}Fix the issues above before deploying.{RESET}")
        print("\nFor help, see:")
        print("  - DEPLOYMENT_GUIDE.md")
        print("  - PRODUCTION_READINESS_AUDIT.md")
        sys.exit(1)


if __name__ == "__main__":
    main()
