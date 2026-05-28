"""
Alert Rule Pydantic Models
Request/Response models for alert rule CRUD operations

Requirements: 13.1, 13.8
"""
from pydantic import BaseModel, Field, UUID4, validator
from typing import List, Optional, Literal
from datetime import datetime
from shared.database.models import AnomalySeverity


class CreateAlertRuleRequest(BaseModel):
    """Request to create a new alert rule"""
    name: str = Field(..., min_length=1, max_length=255, description="Rule name")
    description: Optional[str] = Field(None, description="Rule description")
    
    # Filters
    instruments: List[str] = Field(..., min_items=1, description="List of instrument symbols or ['ALL'] for all watchlisted")
    asset_classes: List[str] = Field(..., min_items=1, description="Asset classes: equity, fo, crypto, forex, commodity")
    anomaly_types: List[str] = Field(..., min_items=1, description="Anomaly types to monitor")
    min_severity: AnomalySeverity = Field(default=AnomalySeverity.MEDIUM, description="Minimum severity threshold")
    
    # Delivery channels
    channels: List[str] = Field(..., min_items=1, description="Delivery channels: in_app, push, email, whatsapp, sms, telegram, webhook")
    
    # Rate limiting
    max_alerts_per_hour: int = Field(default=10, ge=1, le=100, description="Maximum alerts per hour")
    
    # Quiet hours (IST timezone)
    quiet_hours_start: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$", description="Quiet hours start time (HH:MM)")
    quiet_hours_end: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$", description="Quiet hours end time (HH:MM)")
    
    # Webhook configuration
    webhook_url: Optional[str] = Field(None, max_length=500, description="Webhook URL for delivery")
    webhook_secret: Optional[str] = Field(None, max_length=100, description="Webhook HMAC secret")
    
    enabled: bool = Field(default=True, description="Whether rule is enabled")
    
    @validator('asset_classes')
    def validate_asset_classes(cls, v):
        """Validate asset classes"""
        valid_classes = {'equity', 'fo', 'crypto', 'forex', 'commodity'}
        for ac in v:
            if ac not in valid_classes:
                raise ValueError(f"Invalid asset class: {ac}. Must be one of {valid_classes}")
        return v
    
    @validator('anomaly_types')
    def validate_anomaly_types(cls, v):
        """Validate anomaly types"""
        valid_types = {
            'price_spike', 'volume_surge', 'volatility_explosion',
            'gap_up', 'gap_down', 'flash_crash', 'flash_rally',
            'unusual_pattern', 'whale_movement', 'institutional_flow',
            'options_unusual', 'correlation_break', 'regime_change'
        }
        for at in v:
            if at not in valid_types:
                raise ValueError(f"Invalid anomaly type: {at}. Must be one of {valid_types}")
        return v
    
    @validator('channels')
    def validate_channels(cls, v):
        """Validate delivery channels"""
        valid_channels = {'in_app', 'push', 'email', 'whatsapp', 'sms', 'telegram', 'webhook'}
        for ch in v:
            if ch not in valid_channels:
                raise ValueError(f"Invalid channel: {ch}. Must be one of {valid_channels}")
        
        # If webhook channel is selected, webhook_url must be provided
        # This will be validated in the endpoint
        return v
    
    @validator('quiet_hours_end')
    def validate_quiet_hours(cls, v, values):
        """Validate quiet hours consistency"""
        if v and not values.get('quiet_hours_start'):
            raise ValueError("quiet_hours_start must be provided if quiet_hours_end is set")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "BankNifty Critical Alerts",
                "description": "Critical alerts for BankNifty movements",
                "instruments": ["BANKNIFTY"],
                "asset_classes": ["fo"],
                "anomaly_types": ["flash_crash", "flash_rally", "whale_movement"],
                "min_severity": "high",
                "channels": ["in_app", "push", "telegram"],
                "max_alerts_per_hour": 10,
                "quiet_hours_start": "22:00",
                "quiet_hours_end": "08:00",
                "webhook_url": None,
                "webhook_secret": None,
                "enabled": True
            }
        }


class UpdateAlertRuleRequest(BaseModel):
    """Request to update an existing alert rule"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Rule name")
    description: Optional[str] = Field(None, description="Rule description")
    
    # Filters
    instruments: Optional[List[str]] = Field(None, min_items=1, description="List of instrument symbols or ['ALL']")
    asset_classes: Optional[List[str]] = Field(None, min_items=1, description="Asset classes")
    anomaly_types: Optional[List[str]] = Field(None, min_items=1, description="Anomaly types to monitor")
    min_severity: Optional[AnomalySeverity] = Field(None, description="Minimum severity threshold")
    
    # Delivery channels
    channels: Optional[List[str]] = Field(None, min_items=1, description="Delivery channels")
    
    # Rate limiting
    max_alerts_per_hour: Optional[int] = Field(None, ge=1, le=100, description="Maximum alerts per hour")
    
    # Quiet hours
    quiet_hours_start: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$", description="Quiet hours start")
    quiet_hours_end: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$", description="Quiet hours end")
    
    # Webhook configuration
    webhook_url: Optional[str] = Field(None, max_length=500, description="Webhook URL")
    webhook_secret: Optional[str] = Field(None, max_length=100, description="Webhook secret")
    
    enabled: Optional[bool] = Field(None, description="Whether rule is enabled")
    
    @validator('asset_classes')
    def validate_asset_classes(cls, v):
        """Validate asset classes"""
        if v is None:
            return v
        valid_classes = {'equity', 'fo', 'crypto', 'forex', 'commodity'}
        for ac in v:
            if ac not in valid_classes:
                raise ValueError(f"Invalid asset class: {ac}. Must be one of {valid_classes}")
        return v
    
    @validator('anomaly_types')
    def validate_anomaly_types(cls, v):
        """Validate anomaly types"""
        if v is None:
            return v
        valid_types = {
            'price_spike', 'volume_surge', 'volatility_explosion',
            'gap_up', 'gap_down', 'flash_crash', 'flash_rally',
            'unusual_pattern', 'whale_movement', 'institutional_flow',
            'options_unusual', 'correlation_break', 'regime_change'
        }
        for at in v:
            if at not in valid_types:
                raise ValueError(f"Invalid anomaly type: {at}. Must be one of {valid_types}")
        return v
    
    @validator('channels')
    def validate_channels(cls, v):
        """Validate delivery channels"""
        if v is None:
            return v
        valid_channels = {'in_app', 'push', 'email', 'whatsapp', 'sms', 'telegram', 'webhook'}
        for ch in v:
            if ch not in valid_channels:
                raise ValueError(f"Invalid channel: {ch}. Must be one of {valid_channels}")
        return v


class AlertRuleResponse(BaseModel):
    """Response containing alert rule details"""
    id: str
    user_id: str
    name: str
    description: Optional[str]
    
    # Filters
    instruments: List[str]
    asset_classes: List[str]
    anomaly_types: List[str]
    min_severity: str
    
    # Delivery channels
    channels: List[str]
    
    # Rate limiting
    max_alerts_per_hour: int
    
    # Quiet hours
    quiet_hours_start: Optional[str]
    quiet_hours_end: Optional[str]
    
    # Webhook configuration
    webhook_url: Optional[str]
    webhook_secret: Optional[str]
    
    enabled: bool
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AlertRuleListResponse(BaseModel):
    """Paginated list of alert rules"""
    rules: List[AlertRuleResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class TestAlertRequest(BaseModel):
    """Request to send a test alert"""
    message: Optional[str] = Field(
        default="This is a test alert from Signalix",
        description="Custom test message"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Testing alert delivery for BankNifty rule"
            }
        }


class TestAlertResponse(BaseModel):
    """Response after sending test alert"""
    success: bool
    message: str
    rule_id: str
    delivery_statuses: dict
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Test alert sent to all configured channels",
                "rule_id": "550e8400-e29b-41d4-a716-446655440000",
                "delivery_statuses": {
                    "in_app": "sent",
                    "push": "sent",
                    "telegram": "sent"
                }
            }
        }
