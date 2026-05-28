"""Unit tests for StrategyCompiler

Tests compilation of all 8 strategy templates and validates generated Python syntax.

Requirements: 3.1, 3.2
"""
import pytest
import ast
import sys
import importlib.util
from pathlib import Path
from datetime import datetime

# Import the compiler
from services.algo_builder.compiler import StrategyCompiler
from services.algo_builder.models import StrategySpec

# Import strategy templates
migration_path = Path(__file__).parent.parent.parent / "alembic" / "versions" / "006_strategy_templates.py"
spec = importlib.util.spec_from_file_location("templates_module", migration_path)
templates_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(templates_module)

STRATEGY_TEMPLATES = templates_module.STRATEGY_TEMPLATES


class TestStrategyCompiler:
    """Test suite for StrategyCompiler"""

    def setup_method(self):
        """Set up test fixtures"""
        self.compiler = StrategyCompiler()

    def test_compiler_initialization(self):
        """Test that compiler can be instantiated"""
        assert self.compiler is not None
        assert isinstance(self.compiler, StrategyCompiler)

    def test_compile_returns_string(self):
        """Test that compile() returns a string"""
        # Use the first template
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        result = self.compiler.compile(spec)
        
        assert isinstance(result, str)
        assert len(result) > 0

    def test_compile_generates_valid_python(self):
        """Test that compiled code is valid Python syntax"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        result = self.compiler.compile(spec)
        
        # Should not raise SyntaxError
        try:
            ast.parse(result)
        except SyntaxError as e:
            pytest.fail(f"Generated code has syntax errors: {e}")

    def test_compile_includes_class_definition(self):
        """Test that compiled code includes a class definition"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        result = self.compiler.compile(spec)
        
        assert "class CompiledStrategy_" in result
        assert "BaseStrategy" in result

    def test_compile_includes_required_methods(self):
        """Test that compiled code includes all required methods"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        result = self.compiler.compile(spec)
        
        required_methods = [
            "def compute_indicators",
            "def market_filter_pass",
            "def should_enter_long",
            "def should_enter_short",
            "def should_exit",
            "def position_size"
        ]
        
        for method in required_methods:
            assert method in result, f"Missing required method: {method}"

    def test_compile_includes_imports(self):
        """Test that compiled code includes necessary imports"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        result = self.compiler.compile(spec)
        
        required_imports = [
            "import pandas as pd",
            "import numpy as np",
            "import talib",
            "from services.algo_builder.base_strategy import BaseStrategy"
        ]
        
        for imp in required_imports:
            assert imp in result, f"Missing required import: {imp}"

    def test_compile_turtle_breakout_template(self):
        """Test compilation of Turtle Breakout template"""
        turtle = next((t for t in STRATEGY_TEMPLATES if "Turtle Breakout" in t["name"]), None)
        assert turtle is not None, "Turtle Breakout template not found"
        
        spec = StrategySpec(**turtle["spec"])
        result = self.compiler.compile(spec)
        
        # Validate syntax
        ast.parse(result)
        
        # Check for specific Turtle strategy elements
        assert "crosses_above" in result
        assert "highest_high_20" in result
        assert "lowest_low_10" in result
        assert "atr_based" in result.lower() or "atr" in result.lower()

    def test_compile_thorp_volatility_template(self):
        """Test compilation of Thorp Volatility template"""
        thorp = next((t for t in STRATEGY_TEMPLATES if "Thorp" in t["name"]), None)
        assert thorp is not None, "Thorp template not found"
        
        spec = StrategySpec(**thorp["spec"])
        result = self.compiler.compile(spec)
        
        # Validate syntax
        ast.parse(result)
        
        # Check for specific Thorp strategy elements
        assert "iv_rank" in result
        assert "rsi_14" in result
        assert "between" in result
        assert "kelly" in result.lower()

    def test_compile_jones_momentum_template(self):
        """Test compilation of Paul Tudor Jones Momentum template"""
        jones = next((t for t in STRATEGY_TEMPLATES if "Paul Tudor Jones" in t["name"]), None)
        assert jones is not None, "Jones template not found"
        
        spec = StrategySpec(**jones["spec"])
        result = self.compiler.compile(spec)
        
        # Validate syntax
        ast.parse(result)
        
        # Check for specific Jones strategy elements
        assert "ema_200" in result
        assert "rsi_14" in result
        assert "crosses_above" in result

    def test_compile_supertrend_ema_template(self):
        """Test compilation of SuperTrend + EMA Cross template"""
        supertrend = next((t for t in STRATEGY_TEMPLATES if "SuperTrend" in t["name"]), None)
        assert supertrend is not None, "SuperTrend template not found"
        
        spec = StrategySpec(**supertrend["spec"])
        result = self.compiler.compile(spec)
        
        # Validate syntax
        ast.parse(result)
        
        # Check for specific SuperTrend strategy elements
        assert "supertrend" in result.lower()
        assert "ema" in result.lower()

    def test_compile_banknifty_iron_condor_template(self):
        """Test compilation of BankNifty Iron Condor template"""
        iron_condor = next((t for t in STRATEGY_TEMPLATES if "Iron Condor" in t["name"]), None)
        assert iron_condor is not None, "Iron Condor template not found"
        
        spec = StrategySpec(**iron_condor["spec"])
        result = self.compiler.compile(spec)
        
        # Validate syntax
        ast.parse(result)
        
        # Check for specific Iron Condor strategy elements
        assert "iv_rank" in result or "iv" in result.lower()

    def test_compile_druckenmiller_trend_template(self):
        """Test compilation of Druckenmiller Concentrated Trend template"""
        druckenmiller = next((t for t in STRATEGY_TEMPLATES if "Druckenmiller" in t["name"]), None)
        assert druckenmiller is not None, "Druckenmiller template not found"
        
        spec = StrategySpec(**druckenmiller["spec"])
        result = self.compiler.compile(spec)
        
        # Validate syntax
        ast.parse(result)
        
        # Check for specific Druckenmiller strategy elements
        assert "adx" in result.lower()

    def test_compile_value_momentum_template(self):
        """Test compilation of Rakesh Jhunjhunwala Value Momentum template"""
        value_momentum = next((t for t in STRATEGY_TEMPLATES if "Jhunjhunwala" in t["name"]), None)
        assert value_momentum is not None, "Value Momentum template not found"
        
        spec = StrategySpec(**value_momentum["spec"])
        result = self.compiler.compile(spec)
        
        # Validate syntax
        ast.parse(result)

    def test_compile_crypto_accumulation_template(self):
        """Test compilation of Crypto Accumulation template"""
        crypto = next((t for t in STRATEGY_TEMPLATES if "Crypto" in t["name"]), None)
        assert crypto is not None, "Crypto template not found"
        
        spec = StrategySpec(**crypto["spec"])
        result = self.compiler.compile(spec)
        
        # Validate syntax
        ast.parse(result)

    def test_compile_all_templates(self):
        """Test that all 8 templates compile successfully"""
        assert len(STRATEGY_TEMPLATES) == 8, f"Expected 8 templates, found {len(STRATEGY_TEMPLATES)}"
        
        for template in STRATEGY_TEMPLATES:
            spec = StrategySpec(**template["spec"])
            result = self.compiler.compile(spec)
            
            # Validate syntax
            try:
                ast.parse(result)
            except SyntaxError as e:
                pytest.fail(f"Template '{template['name']}' generated invalid Python: {e}")
            
            # Validate structure
            assert "class CompiledStrategy_" in result
            assert "def compute_indicators" in result
            assert "def should_enter_long" in result
            assert "def should_exit" in result

    def test_compile_condition_greater_than(self):
        """Test compilation of > operator"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        # Modify to use > operator
        spec.entry_rules[0].condition_groups[0].conditions[0].operator = ">"
        spec.entry_rules[0].condition_groups[0].conditions[0].right_operand = 50.0
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert ">" in result

    def test_compile_condition_less_than(self):
        """Test compilation of < operator"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        # Modify to use < operator
        spec.entry_rules[0].condition_groups[0].conditions[0].operator = "<"
        spec.entry_rules[0].condition_groups[0].conditions[0].right_operand = 30.0
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "<" in result

    def test_compile_condition_crosses_above(self):
        """Test compilation of crosses_above operator"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "crosses_above" in result

    def test_compile_condition_crosses_below(self):
        """Test compilation of crosses_below operator"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        # Modify to use crosses_below
        spec.entry_rules[0].condition_groups[0].conditions[0].operator = "crosses_below"
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "crosses_below" in result

    def test_compile_condition_between(self):
        """Test compilation of between operator"""
        thorp = next((t for t in STRATEGY_TEMPLATES if "Thorp" in t["name"]), None)
        spec = StrategySpec(**thorp["spec"])
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "between" in result

    def test_compile_position_sizing_fixed_capital(self):
        """Test compilation of fixed_capital position sizing"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        spec.position_sizing.method = "fixed_capital"
        spec.position_sizing.value = 10000.0
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "Fixed capital" in result or "fixed" in result.lower()

    def test_compile_position_sizing_pct_capital(self):
        """Test compilation of pct_capital position sizing"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        spec.position_sizing.method = "pct_capital"
        spec.position_sizing.value = 5.0
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "Percentage" in result or "pct" in result.lower() or "%" in result

    def test_compile_position_sizing_atr_based(self):
        """Test compilation of atr_based position sizing"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        spec.position_sizing.method = "atr_based"
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "atr" in result.lower()

    def test_compile_position_sizing_kelly(self):
        """Test compilation of kelly position sizing"""
        thorp = next((t for t in STRATEGY_TEMPLATES if "Thorp" in t["name"]), None)
        spec = StrategySpec(**thorp["spec"])
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "kelly" in result.lower()

    def test_compile_position_sizing_volatility_adjusted(self):
        """Test compilation of vol_adj position sizing"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        spec.position_sizing.method = "vol_adj"
        spec.position_sizing.value = 10.0
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "volatility" in result.lower() or "vol" in result.lower()

    def test_compile_market_filter_above_200ema(self):
        """Test compilation of require_above_200ema market filter"""
        jones = next((t for t in STRATEGY_TEMPLATES if "Paul Tudor Jones" in t["name"]), None)
        spec = StrategySpec(**jones["spec"])
        spec.market_filter.require_above_200ema = True
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "ema_200" in result

    def test_compile_market_filter_min_adx(self):
        """Test compilation of min_adx market filter"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        spec.market_filter.min_adx = 25.0
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "adx" in result.lower()
        assert "25" in result

    def test_compile_market_filter_max_vix(self):
        """Test compilation of max_vix market filter"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        spec.market_filter.max_vix = 30.0
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "vix" in result.lower()
        assert "30" in result

    def test_compile_exit_rule_target(self):
        """Test compilation of target exit rule"""
        thorp = next((t for t in STRATEGY_TEMPLATES if "Thorp" in t["name"]), None)
        spec = StrategySpec(**thorp["spec"])
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "target" in result.lower()

    def test_compile_exit_rule_stop_loss(self):
        """Test compilation of stop_loss exit rule"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        # Add stop loss exit rule
        from services.algo_builder.models import ExitRule
        spec.exit_rules.append(ExitRule(exit_type="stop_loss", stop_loss_pct=2.0))
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "stop_loss" in result.lower() or "stop" in result.lower()

    def test_compile_exit_rule_trailing_sl(self):
        """Test compilation of trailing_sl exit rule"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        # Add trailing stop loss exit rule
        from services.algo_builder.models import ExitRule
        spec.exit_rules.append(ExitRule(exit_type="trailing_sl", trailing_sl_pct=3.0))
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "trailing" in result.lower()

    def test_compile_exit_rule_indicator(self):
        """Test compilation of indicator exit rule"""
        turtle = next((t for t in STRATEGY_TEMPLATES if "Turtle Breakout" in t["name"]), None)
        spec = StrategySpec(**turtle["spec"])
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "indicator" in result.lower()

    def test_compile_exit_rule_time(self):
        """Test compilation of time exit rule"""
        thorp = next((t for t in STRATEGY_TEMPLATES if "Thorp" in t["name"]), None)
        spec = StrategySpec(**thorp["spec"])
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert "time" in result.lower() or "max_hold" in result.lower()

    def test_compile_uses_only_safe_libraries(self):
        """Test that compiled code only uses safe libraries (no network/filesystem)"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        result = self.compiler.compile(spec)
        
        # Should NOT contain dangerous imports
        dangerous_imports = [
            "import os",
            "import sys",
            "import subprocess",
            "import socket",
            "import requests",
            "import urllib",
            "import http",
            "from os import",
            "from sys import",
        ]
        
        for dangerous in dangerous_imports:
            assert dangerous not in result, f"Compiled code contains dangerous import: {dangerous}"
        
        # Should ONLY contain safe imports
        safe_imports = ["pandas", "numpy", "talib", "datetime", "math", "BaseStrategy"]
        for line in result.split("\n"):
            if line.strip().startswith("import ") or line.strip().startswith("from "):
                assert any(safe in line for safe in safe_imports), f"Unexpected import: {line}"

    def test_compile_max_position_cap_enforced(self):
        """Test that max_position_pct cap is enforced in compiled code"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        # Should contain max position cap logic
        assert "max_size" in result or "max_position" in result.lower()
        assert "min(size, max_size)" in result or "min(" in result

    def test_compile_handles_multiple_entry_rules(self):
        """Test compilation with multiple entry rules"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        # Add another entry rule
        from services.algo_builder.models import EntryRule, ConditionGroup, ConditionBlock
        new_rule = EntryRule(
            direction="LONG",
            condition_groups=[
                ConditionGroup(
                    conditions=[
                        ConditionBlock(
                            left_operand="rsi_14",
                            operator=">",
                            right_operand=50.0
                        )
                    ]
                )
            ]
        )
        spec.entry_rules.append(new_rule)
        
        result = self.compiler.compile(spec)
        ast.parse(result)

    def test_compile_handles_multiple_exit_rules(self):
        """Test compilation with multiple exit rules"""
        thorp = next((t for t in STRATEGY_TEMPLATES if "Thorp" in t["name"]), None)
        spec = StrategySpec(**thorp["spec"])
        
        # Thorp template already has multiple exit rules
        assert len(spec.exit_rules) >= 2
        
        result = self.compiler.compile(spec)
        ast.parse(result)

    def test_compile_handles_and_logic_gate(self):
        """Test compilation with AND logic gate"""
        jones = next((t for t in STRATEGY_TEMPLATES if "Paul Tudor Jones" in t["name"]), None)
        spec = StrategySpec(**jones["spec"])
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert " and " in result

    def test_compile_handles_or_logic_gate(self):
        """Test compilation with OR logic gate"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        # Modify to use OR gate
        spec.entry_rules[0].condition_groups[0].gate = "OR"
        
        result = self.compiler.compile(spec)
        ast.parse(result)
        
        assert " or " in result

    def test_compile_preserves_strategy_metadata(self):
        """Test that compiled code preserves strategy metadata"""
        template = STRATEGY_TEMPLATES[0]
        spec = StrategySpec(**template["spec"])
        
        result = self.compiler.compile(spec)
        
        assert spec.name in result
        assert spec.asset_class in result
        assert spec.strategy_id.replace("-", "_") in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
