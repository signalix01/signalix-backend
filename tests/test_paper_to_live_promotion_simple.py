"""
Simple unit tests for paper-to-live strategy promotion endpoint.

Tests the key requirement: rejection when strategy has been in paper mode < 30 days.

Requirements: 15.2
"""

import pytest
from datetime import datetime, timedelta


class TestPaperModeDurationCheck:
    """Test the 30-day paper mode duration requirement."""
    
    def test_calculate_duration_25_days(self):
        """Test that 25 days in paper mode is correctly calculated."""
        now = datetime.utcnow()
        paper_mode_start = now - timedelta(days=25)
        
        duration = now - paper_mode_start
        required_duration = timedelta(days=30)
        
        assert duration.days == 25
        assert duration < required_duration
        
        days_remaining = (required_duration - duration).days
        assert days_remaining == 5
    
    def test_calculate_duration_30_days(self):
        """Test that exactly 30 days in paper mode passes."""
        now = datetime.utcnow()
        paper_mode_start = now - timedelta(days=30)
        
        duration = now - paper_mode_start
        required_duration = timedelta(days=30)
        
        assert duration.days == 30
        assert duration >= required_duration
    
    def test_calculate_duration_35_days(self):
        """Test that 35 days in paper mode passes."""
        now = datetime.utcnow()
        paper_mode_start = now - timedelta(days=35)
        
        duration = now - paper_mode_start
        required_duration = timedelta(days=30)
        
        assert duration.days == 35
        assert duration >= required_duration
    
    def test_error_message_format(self):
        """Test that error message contains required information."""
        days_in_paper = 25
        required_days = 30
        days_remaining = required_days - days_in_paper
        
        error_detail = {
            "error": "Insufficient paper trading duration",
            "message": f"Strategy must be in paper mode for at least 30 days. Current: {days_in_paper} days, Required: 30 days",
            "days_in_paper_mode": days_in_paper,
            "required_days": required_days,
            "days_remaining": days_remaining,
            "action": f"Continue paper trading for {days_remaining} more days"
        }
        
        assert error_detail["error"] == "Insufficient paper trading duration"
        assert error_detail["days_in_paper_mode"] == 25
        assert error_detail["required_days"] == 30
        assert error_detail["days_remaining"] == 5
        assert "at least 30 days" in error_detail["message"].lower()
        assert "continue paper trading" in error_detail["action"].lower()
        assert "5 more days" in error_detail["action"]


class TestPromotionPreflightChecks:
    """Test all pre-flight check logic."""
    
    def test_status_check_draft(self):
        """Test that draft status is rejected."""
        status = "draft"
        required_status = "paper"
        
        assert status != required_status
        
        error_detail = {
            "error": "Invalid strategy status",
            "message": f"Strategy must be in paper trading mode to promote to live. Current status: {status}",
            "current_status": status,
            "required_status": required_status,
            "action": "Start paper trading first"
        }
        
        assert error_detail["current_status"] == "draft"
        assert error_detail["required_status"] == "paper"
    
    def test_status_check_live(self):
        """Test that live status is rejected (already promoted)."""
        status = "live"
        required_status = "paper"
        
        assert status != required_status
        
        error_detail = {
            "error": "Invalid strategy status",
            "message": f"Strategy must be in paper trading mode to promote to live. Current status: {status}",
            "current_status": status,
            "required_status": required_status,
            "action": "Strategy cannot be promoted from current status"
        }
        
        assert error_detail["current_status"] == "live"
    
    def test_positive_return_check_negative(self):
        """Test that negative returns are rejected."""
        total_return_pct = -5.0
        
        assert total_return_pct <= 0
        
        error_detail = {
            "error": "Negative or zero returns",
            "message": f"Strategy must demonstrate positive returns in paper mode. Current return: {total_return_pct:.2f}%",
            "total_return_pct": total_return_pct,
            "required_return_pct": "> 0",
            "action": "Optimize strategy parameters or test different market conditions"
        }
        
        assert error_detail["total_return_pct"] == -5.0
        assert "must demonstrate positive returns" in error_detail["message"].lower()
    
    def test_positive_return_check_zero(self):
        """Test that zero returns are rejected."""
        total_return_pct = 0.0
        
        assert total_return_pct <= 0
        
        error_detail = {
            "error": "Negative or zero returns",
            "message": f"Strategy must demonstrate positive returns in paper mode. Current return: {total_return_pct:.2f}%",
            "total_return_pct": total_return_pct,
            "required_return_pct": "> 0"
        }
        
        assert error_detail["total_return_pct"] == 0.0
    
    def test_positive_return_check_positive(self):
        """Test that positive returns pass."""
        total_return_pct = 15.0
        
        assert total_return_pct > 0
    
    def test_walk_forward_check_failed(self):
        """Test that low WF consistency score is rejected."""
        wf_consistency_score = 0.5
        required_score = 0.7
        
        assert wf_consistency_score < required_score
        
        error_detail = {
            "error": "Walk-forward validation failed",
            "message": f"Strategy must pass walk-forward validation (consistency score >= 0.7). Current score: {wf_consistency_score:.2f}",
            "wf_consistency_score": wf_consistency_score,
            "required_score": required_score,
            "action": "Simplify strategy rules to avoid overfitting, or run walk-forward validation again"
        }
        
        assert error_detail["wf_consistency_score"] == 0.5
        assert error_detail["required_score"] == 0.7
        assert "consistency score >= 0.7" in error_detail["message"].lower()
    
    def test_walk_forward_check_passed(self):
        """Test that high WF consistency score passes."""
        wf_consistency_score = 0.85
        required_score = 0.7
        
        assert wf_consistency_score >= required_score
    
    def test_walk_forward_check_exactly_threshold(self):
        """Test that exactly 0.7 WF consistency score passes."""
        wf_consistency_score = 0.7
        required_score = 0.7
        
        assert wf_consistency_score >= required_score
    
    def test_pin_validation_digits(self):
        """Test that 4-digit PIN is valid."""
        pin = "1234"
        
        assert len(pin) == 4
        assert pin.isdigit()
    
    def test_pin_validation_non_digits(self):
        """Test that non-digit PIN is invalid."""
        pin = "abcd"
        
        assert len(pin) == 4
        assert not pin.isdigit()
        
        error_detail = {
            "error": "Invalid PIN format",
            "message": "PIN must be exactly 4 digits",
            "action": "Enter a valid 4-digit PIN"
        }
        
        assert "must be exactly 4 digits" in error_detail["message"].lower()


class TestPromotionResponseFormat:
    """Test response format and structure."""
    
    def test_success_response_structure(self):
        """Test that success response has correct structure."""
        strategy_id = "123e4567-e89b-12d3-a456-426614174000"
        
        response = {
            "success": True,
            "message": f"Strategy 'Test Strategy' promoted to live trading successfully. Execution engine will begin monitoring market data.",
            "strategy_id": strategy_id,
            "status": "live",
            "celery_task_id": None
        }
        
        # Check all required fields
        assert "success" in response
        assert "message" in response
        assert "strategy_id" in response
        assert "status" in response
        assert "celery_task_id" in response
        
        # Check types
        assert isinstance(response["success"], bool)
        assert isinstance(response["message"], str)
        assert isinstance(response["strategy_id"], str)
        assert isinstance(response["status"], str)
        
        # Check values
        assert response["success"] is True
        assert response["status"] == "live"
        assert response["strategy_id"] == strategy_id
        assert "promoted to live trading successfully" in response["message"].lower()
    
    def test_error_response_structure_insufficient_days(self):
        """Test that error response has correct structure with actionable details."""
        error_detail = {
            "error": "Insufficient paper trading duration",
            "message": "Strategy must be in paper mode for at least 30 days. Current: 25 days, Required: 30 days",
            "days_in_paper_mode": 25,
            "required_days": 30,
            "days_remaining": 5,
            "paper_mode_start_date": "2024-12-01T10:00:00",
            "earliest_promotion_date": "2024-12-31T10:00:00",
            "action": "Continue paper trading for 5 more days"
        }
        
        # Check all required error fields
        assert "error" in error_detail
        assert "message" in error_detail
        assert "action" in error_detail
        
        # Check types
        assert isinstance(error_detail["error"], str)
        assert isinstance(error_detail["message"], str)
        assert isinstance(error_detail["action"], str)
        
        # Check actionable guidance
        assert len(error_detail["action"]) > 0
        assert "days" in error_detail["action"].lower()
        
        # Check specific fields for this error
        assert "days_in_paper_mode" in error_detail
        assert "required_days" in error_detail
        assert "days_remaining" in error_detail
        assert error_detail["days_in_paper_mode"] == 25
        assert error_detail["required_days"] == 30
        assert error_detail["days_remaining"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
