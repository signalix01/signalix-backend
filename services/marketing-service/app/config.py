"""
Configuration for Marketing Service
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Marketing service configuration"""
    
    # Service
    SERVICE_NAME: str = "marketing-service"
    SERVICE_PORT: int = 8010
    DEBUG: bool = False
    
    # SendGrid
    SENDGRID_API_KEY: str
    FROM_EMAIL: str = "noreply@signalixai.com"
    FROM_NAME: str = "SignalixAI AI"
    REPLY_TO_EMAIL: Optional[str] = "support@signalixai.com"
    
    # Email Templates (SendGrid Dynamic Template IDs)
    TEMPLATE_WELCOME: str = "d-welcome-001"
    TEMPLATE_VERIFY_EMAIL: str = "d-verify-email-001"
    TEMPLATE_PASSWORD_RESET: str = "d-password-reset-001"
    TEMPLATE_SUBSCRIPTION_CONFIRMATION: str = "d-subscription-confirmation-001"
    TEMPLATE_PAYMENT_RECEIPT: str = "d-payment-receipt-001"
    
    # Onboarding Sequence Templates
    TEMPLATE_GETTING_STARTED: str = "d-getting-started-001"
    TEMPLATE_FIRST_ANALYSIS_TIPS: str = "d-first-analysis-tips-001"
    TEMPLATE_FEATURE_DISCOVERY: str = "d-feature-discovery-001"
    TEMPLATE_SUCCESS_STORIES: str = "d-success-stories-001"
    TEMPLATE_TRIAL_ENDING: str = "d-trial-ending-001"
    
    # Behavioral Trigger Templates
    TEMPLATE_INCOMPLETE_ONBOARDING: str = "d-incomplete-onboarding-001"
    TEMPLATE_INACTIVE_USER: str = "d-inactive-user-001"
    TEMPLATE_FEATURE_UNUSED: str = "d-feature-unused-001"
    TEMPLATE_UPGRADE_PROMPT: str = "d-upgrade-prompt-001"
    
    # Lead Magnet Nurture Sequence Templates
    TEMPLATE_LEAD_MAGNET_DELIVERY: str = "d-lead-magnet-delivery-001"
    TEMPLATE_RELATED_CONTENT: str = "d-related-content-001"
    TEMPLATE_CASE_STUDY: str = "d-case-study-001"
    TEMPLATE_TRIAL_INVITATION: str = "d-trial-invitation-001"
    
    # Redis (for rq task queue)
    REDIS_URL: str
    
    # Database
    DATABASE_URL: str
    
    # URLs
    DASHBOARD_URL: str = "https://signalixai.com/dashboard"
    HELP_URL: str = "https://signalixai.com/help"
    UNSUBSCRIBE_BASE_URL: str = "https://signalixai.com/unsubscribe"
    PREFERENCES_BASE_URL: str = "https://signalixai.com/email-preferences"
    FRONTEND_URL: str = "https://signalixai.com"
    
    # Service URLs
    SUBSCRIPTION_SERVICE_URL: Optional[str] = "http://localhost:8006"
    
    # Company Info
    COMPANY_NAME: str = "SignalixAI AI"
    COMPANY_ADDRESS: str = "Mumbai, India"
    
    # Retry Configuration
    EMAIL_MAX_RETRIES: int = 3
    EMAIL_RETRY_DELAY_SECONDS: int = 60
    
    # Analytics (for server-side tracking)
    GA4_MEASUREMENT_ID: Optional[str] = None
    GA4_API_SECRET: Optional[str] = None
    MIXPANEL_TOKEN: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
