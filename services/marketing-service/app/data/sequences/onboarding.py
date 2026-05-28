"""
Onboarding Email Sequence Configuration
Day 0-7 welcome sequence for new trial users
"""
from typing import List, Dict, Any
from datetime import timedelta


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


# Onboarding sequence: 6 emails over 7 days
ONBOARDING_SEQUENCE: List[EmailStep] = [
    EmailStep(
        day=0,
        template_name="welcome",
        subject="Welcome to SignalixAI AI - Let's get started",
        delay_hours=0,
        description="Welcome email sent immediately after signup"
    ),
    EmailStep(
        day=1,
        template_name="getting_started",
        subject="Your first AI analysis in 3 steps",
        delay_hours=24,
        description="Getting started guide with quick-start steps"
    ),
    EmailStep(
        day=2,
        template_name="first_analysis_tips",
        subject="Pro tips for your first market analysis",
        delay_hours=48,
        description="Tips for running first analysis and interpreting signals"
    ),
    EmailStep(
        day=3,
        template_name="feature_discovery",
        subject="Discover: Options Intelligence & Risk Manager",
        delay_hours=72,
        description="Feature discovery highlighting key platform capabilities"
    ),
    EmailStep(
        day=5,
        template_name="success_stories",
        subject="How traders avoid bad trades with AI",
        delay_hours=120,
        description="Success stories and testimonials from active traders"
    ),
    EmailStep(
        day=6,
        template_name="trial_ending",
        subject="Your trial ends tomorrow - Upgrade to keep your signals",
        delay_hours=144,
        description="Trial ending reminder with upgrade CTA"
    ),
]


def get_onboarding_sequence() -> List[EmailStep]:
    """Get the complete onboarding sequence"""
    return ONBOARDING_SEQUENCE


def get_sequence_step(day: int) -> EmailStep:
    """Get a specific step from the sequence by day"""
    for step in ONBOARDING_SEQUENCE:
        if step.day == day:
            return step
    raise ValueError(f"No sequence step found for day {day}")


def get_sequence_metadata() -> Dict[str, Any]:
    """Get metadata about the onboarding sequence"""
    return {
        "name": "onboarding",
        "description": "Day 0-7 welcome sequence for new trial users",
        "total_emails": len(ONBOARDING_SEQUENCE),
        "duration_days": 7,
        "steps": [step.to_dict() for step in ONBOARDING_SEQUENCE]
    }
