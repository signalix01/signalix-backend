"""
Lead Magnet Nurture Sequence Configuration
4-email nurture sequence for lead magnet downloads
"""
from typing import List, Dict, Any


class EmailStep:
    """Single email step in a sequence"""
    
    def __init__(
        self,
        day: int,
        template_name: str,
        subject: str,
        delay_hours: int,
        description: str = ""
    ):
        self.day = day
        self.template_name = template_name
        self.subject = subject
        self.delay_hours = delay_hours
        self.description = description
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "day": self.day,
            "template_name": self.template_name,
            "subject": self.subject,
            "delay_hours": self.delay_hours,
            "description": self.description
        }


# Lead magnet nurture sequence: 4 emails over 7 days
LEAD_MAGNET_SEQUENCE: List[EmailStep] = [
    EmailStep(
        day=0,
        template_name="lead_magnet_delivery",
        subject="Your {{lead_magnet_title}} is ready",
        delay_hours=0,
        description="Immediate delivery email with download link"
    ),
    EmailStep(
        day=2,
        template_name="related_content",
        subject="3 more resources for {{topic}}",
        delay_hours=48,
        description="Related content and additional resources"
    ),
    EmailStep(
        day=4,
        template_name="case_study",
        subject="How traders are using AI to improve returns",
        delay_hours=96,
        description="Case study showing real trader results"
    ),
    EmailStep(
        day=7,
        template_name="trial_invitation",
        subject="Ready to try AI-powered trading signals?",
        delay_hours=168,
        description="Trial invitation with signup CTA"
    ),
]


def get_lead_magnet_sequence() -> List[EmailStep]:
    """Get the complete lead magnet nurture sequence"""
    return LEAD_MAGNET_SEQUENCE


def get_sequence_step(day: int) -> EmailStep:
    """Get a specific step from the sequence by day"""
    for step in LEAD_MAGNET_SEQUENCE:
        if step.day == day:
            return step
    raise ValueError(f"No sequence step found for day {day}")


def get_sequence_metadata() -> Dict[str, Any]:
    """Get metadata about the lead magnet sequence"""
    return {
        "name": "lead_magnet",
        "description": "4-email nurture sequence for lead magnet downloads",
        "total_emails": len(LEAD_MAGNET_SEQUENCE),
        "duration_days": 7,
        "steps": [step.to_dict() for step in LEAD_MAGNET_SEQUENCE]
    }


# Lead magnet content mapping for personalization
LEAD_MAGNET_CONTENT: Dict[str, Dict[str, Any]] = {
    "fo-trading-checklist": {
        "title": "F&O Trading Checklist",
        "topic": "F&O trading",
        "category": "futures_options",
        "related_resources": [
            "Options Greeks Cheat Sheet",
            "Position Sizing Calculator",
            "Risk Management Guide"
        ]
    },
    "options-greeks-cheat-sheet": {
        "title": "Options Greeks Cheat Sheet",
        "topic": "options trading",
        "category": "options",
        "related_resources": [
            "F&O Trading Checklist",
            "Options Strategy Guide",
            "IV Analysis Template"
        ]
    },
    "position-sizing-calculator": {
        "title": "Position Sizing Calculator",
        "topic": "risk management",
        "category": "risk_management",
        "related_resources": [
            "Risk Management Guide",
            "Trading Journal Template",
            "Stop Loss Calculator"
        ]
    },
    "backtesting-template": {
        "title": "Backtesting Template",
        "topic": "strategy testing",
        "category": "backtesting",
        "related_resources": [
            "Strategy Development Guide",
            "Performance Metrics Tracker",
            "Trade Analysis Spreadsheet"
        ]
    },
    "ai-trading-signals-guide": {
        "title": "AI Trading Signals Guide",
        "topic": "AI trading",
        "category": "ai_signals",
        "related_resources": [
            "Signal Interpretation Guide",
            "AI Strategy Examples",
            "Getting Started with AI Trading"
        ]
    }
}


def get_lead_magnet_content(lead_magnet_id: str) -> Dict[str, Any]:
    """Get content metadata for a lead magnet"""
    return LEAD_MAGNET_CONTENT.get(
        lead_magnet_id,
        {
            "title": "Trading Resource",
            "topic": "trading",
            "category": "general",
            "related_resources": []
        }
    )
