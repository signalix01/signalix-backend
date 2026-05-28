"""Unit tests for strategy templates

Tests that all 8 strategy templates:
1. Load successfully from the database
2. Pass StrategySpec Pydantic validation

Requirements: 2.1, 2.2, 2.3
"""
import pytest
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.algo_builder.models import StrategySpec

# Import the templates directly from the migration file
import importlib.util
spec = importlib.util.spec_from_file_location(
    "templates_module",
    Path(__file__).parent.parent / "alembic" / "versions" / "006_strategy_templates.py"
)
templates_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(templates_module)


class TestStrategyTemplates:
    """Test suite for strategy templates"""

    def test_all_templates_defined(self):
        """Verify all 8 templates are defined in the migration"""
        templates = templates_module.STRATEGY_TEMPLATES
        assert len(templates) == 8, f"Expected 8 templates, found {len(templates)}"

    def test_template_names(self):
        """Verify all expected template names are present"""
        templates = templates_module.STRATEGY_TEMPLATES
        template_names = [t["name"] for t in templates]
        
        expected_names = [
            "Turtle Breakout (Richard Dennis)",
            "Volatility Mean Reversion (Edward Thorp)",
            "Macro Momentum (Paul Tudor Jones)",
            "SuperTrend + EMA Cross",
            "BankNifty Iron Condor (PR Sundar)",
            "Concentrated Trend (Stanley Druckenmiller)",
            "Value Momentum (Rakesh Jhunjhunwala)",
            "Crypto Accumulation"
        ]
        
        for expected_name in expected_names:
            assert expected_name in template_names, f"Template '{expected_name}' not found"

    def test_template_structure(self):
        """Verify each template has required fields"""
        templates = templates_module.STRATEGY_TEMPLATES
        
        required_fields = ["id", "name", "description", "methodology_attribution", "use_cases", "spec"]
        
        for template in templates:
            for field in required_fields:
                assert field in template, f"Template '{template.get('name', 'unknown')}' missing field '{field}'"

    def test_template_spec_validation(self):
        """Verify each template's spec passes StrategySpec Pydantic validation"""
        templates = templates_module.STRATEGY_TEMPLATES
        
        for template in templates:
            template_name = template["name"]
            spec_data = template["spec"]
            
            try:
                # Attempt to validate the spec with Pydantic
                strategy_spec = StrategySpec(**spec_data)
                
                # Verify the validated object has required attributes
                assert strategy_spec.strategy_id is not None
                assert strategy_spec.name is not None
                assert strategy_spec.asset_class in ["equity", "fo", "crypto", "forex", "commodity"]
                assert len(strategy_spec.entry_rules) >= 1, f"{template_name}: Must have at least 1 entry rule"
                assert len(strategy_spec.exit_rules) >= 1, f"{template_name}: Must have at least 1 exit rule"
                assert strategy_spec.position_sizing is not None
                assert strategy_spec.market_filter is not None
                assert strategy_spec.indicators_config is not None
                
            except Exception as e:
                pytest.fail(f"Template '{template_name}' failed validation: {str(e)}")

    def test_turtle_breakout_template(self):
        """Test Turtle Breakout template specifically"""
        templates = templates_module.STRATEGY_TEMPLATES
        turtle = next((t for t in templates if "Turtle Breakout" in t["name"]), None)
        
        assert turtle is not None, "Turtle Breakout template not found"
        
        spec = StrategySpec(**turtle["spec"])
        assert spec.asset_class == "equity"
        assert spec.position_sizing.method == "atr_based"
        assert spec.risk_per_trade_pct == 1.0
        assert "highest_high_20" in spec.indicators_config
        assert "lowest_low_10" in spec.indicators_config

    def test_thorp_volatility_template(self):
        """Test Thorp Volatility template specifically"""
        templates = templates_module.STRATEGY_TEMPLATES
        thorp = next((t for t in templates if "Thorp" in t["name"]), None)
        
        assert thorp is not None, "Thorp Volatility template not found"
        
        spec = StrategySpec(**thorp["spec"])
        assert spec.asset_class == "fo"
        assert spec.position_sizing.method == "kelly"
        assert "iv_rank" in spec.indicators_config

    def test_jones_momentum_template(self):
        """Test Paul Tudor Jones Momentum template specifically"""
        templates = templates_module.STRATEGY_TEMPLATES
        jones = next((t for t in templates if "Paul Tudor Jones" in t["name"]), None)
        
        assert jones is not None, "Jones Momentum template not found"
        
        spec = StrategySpec(**jones["spec"])
        assert spec.asset_class == "equity"
        assert spec.market_filter.require_above_200ema == True
        assert "ema_200" in spec.indicators_config
        assert "rsi_14" in spec.indicators_config

    def test_supertrend_ema_template(self):
        """Test SuperTrend + EMA Cross template specifically"""
        templates = templates_module.STRATEGY_TEMPLATES
        supertrend = next((t for t in templates if "SuperTrend" in t["name"]), None)
        
        assert supertrend is not None, "SuperTrend template not found"
        
        spec = StrategySpec(**supertrend["spec"])
        assert spec.asset_class == "equity"
        assert "supertrend" in spec.indicators_config
        assert "ema_9" in spec.indicators_config
        assert "ema_21" in spec.indicators_config

    def test_banknifty_iron_condor_template(self):
        """Test BankNifty Iron Condor template specifically"""
        templates = templates_module.STRATEGY_TEMPLATES
        iron_condor = next((t for t in templates if "Iron Condor" in t["name"]), None)
        
        assert iron_condor is not None, "Iron Condor template not found"
        
        spec = StrategySpec(**iron_condor["spec"])
        assert spec.asset_class == "fo"
        assert "BANKNIFTY" in spec.instruments
        assert "iv_rank" in spec.indicators_config
        assert "pcr" in spec.indicators_config

    def test_druckenmiller_trend_template(self):
        """Test Druckenmiller Concentrated Trend template specifically"""
        templates = templates_module.STRATEGY_TEMPLATES
        druckenmiller = next((t for t in templates if "Druckenmiller" in t["name"]), None)
        
        assert druckenmiller is not None, "Druckenmiller template not found"
        
        spec = StrategySpec(**druckenmiller["spec"])
        assert spec.asset_class == "equity"
        assert spec.market_filter.min_adx == 30.0
        assert spec.position_sizing.max_concurrent_positions == 1
        assert "adx_14" in spec.indicators_config

    def test_value_momentum_template(self):
        """Test Rakesh Jhunjhunwala Value Momentum template specifically"""
        templates = templates_module.STRATEGY_TEMPLATES
        value_momentum = next((t for t in templates if "Jhunjhunwala" in t["name"]), None)
        
        assert value_momentum is not None, "Value Momentum template not found"
        
        spec = StrategySpec(**value_momentum["spec"])
        assert spec.asset_class == "equity"
        assert spec.market_filter.require_above_200ema == True
        assert spec.market_filter.require_positive_breadth == True
        assert "ema_50" in spec.indicators_config

    def test_crypto_accumulation_template(self):
        """Test Crypto Accumulation template specifically"""
        templates = templates_module.STRATEGY_TEMPLATES
        crypto = next((t for t in templates if "Crypto" in t["name"]), None)
        
        assert crypto is not None, "Crypto Accumulation template not found"
        
        spec = StrategySpec(**crypto["spec"])
        assert spec.asset_class == "crypto"
        assert "BTCUSDT" in spec.instruments or "ETHUSDT" in spec.instruments
        assert spec.market_filter.require_above_200ema == True
        assert "ema_200" in spec.indicators_config

    def test_position_sizing_validation(self):
        """Test that all templates respect the 10% max position cap"""
        templates = templates_module.STRATEGY_TEMPLATES
        
        for template in templates:
            spec = StrategySpec(**template["spec"])
            assert spec.position_sizing.max_position_pct <= 10.0, \
                f"Template '{template['name']}' exceeds 10% max position cap"

    def test_entry_exit_rules_present(self):
        """Test that all templates have at least one entry and exit rule"""
        templates = templates_module.STRATEGY_TEMPLATES
        
        for template in templates:
            spec = StrategySpec(**template["spec"])
            assert len(spec.entry_rules) >= 1, \
                f"Template '{template['name']}' has no entry rules"
            assert len(spec.exit_rules) >= 1, \
                f"Template '{template['name']}' has no exit rules"

    def test_indicators_config_not_empty(self):
        """Test that all templates have indicator configurations"""
        templates = templates_module.STRATEGY_TEMPLATES
        
        for template in templates:
            spec = StrategySpec(**template["spec"])
            assert len(spec.indicators_config) > 0, \
                f"Template '{template['name']}' has no indicators configured"

    def test_methodology_attribution_present(self):
        """Test that all templates have methodology attribution"""
        templates = templates_module.STRATEGY_TEMPLATES
        
        for template in templates:
            assert template["methodology_attribution"], \
                f"Template '{template['name']}' missing methodology attribution"
            assert len(template["methodology_attribution"]) > 0

    def test_use_cases_present(self):
        """Test that all templates have use cases documented"""
        templates = templates_module.STRATEGY_TEMPLATES
        
        for template in templates:
            assert template["use_cases"], \
                f"Template '{template['name']}' missing use cases"
            assert len(template["use_cases"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
