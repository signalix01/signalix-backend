"""Strategy Compiler - Converts StrategySpec to executable Python code

This module compiles StrategySpec JSON into executable Python class strings that inherit
from BaseStrategy. The compiled code is safe for sandboxed execution with no filesystem
or network access.

Requirements: 3.1, 3.2
"""
from typing import List, Union
import ast
from services.algo_builder.models import (
    StrategySpec,
    EntryRule,
    ExitRule,
    ConditionBlock,
    PositionSizing,
    MarketFilter,
    CompareOperator,
    PositionSizingMethod,
)


class StrategyCompiler:
    """
    Compiles StrategySpec into a Python class string.
    
    The compiled class inherits from BaseStrategy and is safe to exec().
    Security: all compiled code runs in a sandboxed subprocess with:
    - No filesystem access
    - No network access  
    - 30-second execution timeout
    - Memory limit 512MB
    
    Requirements: 3.1, 3.2
    """

    def compile(self, spec: StrategySpec) -> str:
        """
        Returns a Python class string ready for sandboxed execution.
        
        Args:
            spec: StrategySpec object containing the complete strategy definition
            
        Returns:
            Python class string that inherits from BaseStrategy
            
        Raises:
            ValueError: If the spec is invalid or compilation fails
            SyntaxError: If the generated code has syntax errors
        """
        # Compile each section
        indicators_setup = self._compile_indicators(spec.indicators_config)
        entry_logic_long = self._compile_entry_rules(spec.entry_rules, "LONG")
        entry_logic_short = self._compile_entry_rules(spec.entry_rules, "SHORT")
        exit_logic = self._compile_exit_rules(spec.exit_rules)
        sizing_logic = self._compile_position_sizing(spec.position_sizing)
        filter_logic = self._compile_market_filter(spec.market_filter)

        # Generate the complete class
        class_code = f'''import pandas as pd
import numpy as np
from datetime import datetime
import math

class CompiledStrategy_{spec.strategy_id.replace("-", "_")}(BaseStrategy):
    """Compiled strategy: {spec.name}"""
    name = "{spec.name}"
    asset_class = "{spec.asset_class}"
    strategy_id = "{spec.strategy_id}"

    def __init__(self, data: pd.DataFrame, capital: float):
        super().__init__(data, capital)
        self.risk_per_trade = {spec.risk_per_trade_pct} / 100
        self.max_daily_loss = {spec.max_daily_loss_pct} / 100
{indicators_setup}

    def compute_indicators(self):
        """Compute all technical indicators required by the strategy"""
{self._render_indicators(spec.indicators_config)}

    def market_filter_pass(self, bar_idx: int) -> bool:
        """Check if market filter conditions are met"""
{filter_logic}

    def should_enter_long(self, bar_idx: int) -> bool:
        """Check if long entry conditions are met"""
        if not self.market_filter_pass(bar_idx):
            return False
{entry_logic_long}

    def should_enter_short(self, bar_idx: int) -> bool:
        """Check if short entry conditions are met"""
        if not self.market_filter_pass(bar_idx):
            return False
{entry_logic_short}

    def should_exit(self, position, bar_idx: int) -> tuple:
        """Check if exit conditions are met for the given position"""
{exit_logic}

    def position_size(self, capital: float, price: float, atr: float) -> float:
        """Calculate position size based on strategy's sizing method"""
{sizing_logic}
'''

        # Validate the generated code by parsing it
        try:
            ast.parse(class_code)
        except SyntaxError as e:
            raise SyntaxError(f"Generated code has syntax errors: {e}")

        return class_code

    def _compile_indicators(self, indicators_config: dict) -> str:
        """Generate indicator initialization code"""
        if not indicators_config:
            return "        pass  # No indicators configured"
        
        lines = []
        for indicator_id, params in indicators_config.items():
            lines.append(f"        self.indicator_{indicator_id} = {params}")
        
        return "\n".join(lines) if lines else "        pass  # No indicators configured"

    def _render_indicators(self, indicators_config: dict) -> str:
        """Generate indicator computation code"""
        if not indicators_config:
            return "        pass  # No indicators to compute"
        
        lines = []
        lines.append("        # Indicators are pre-computed in the data pipeline")
        lines.append("        # This method is called during initialization")
        lines.append("        pass")
        
        return "\n".join(lines)

    def _compile_entry_rules(self, rules: List[EntryRule], direction: str) -> str:
        """
        Converts condition groups to Python boolean expressions for entry rules.
        
        Args:
            rules: List of EntryRule objects
            direction: "LONG" or "SHORT" to filter rules by direction
            
        Returns:
            Python code string for entry logic
        """
        # Filter rules by direction
        filtered_rules = [r for r in rules if r.direction == direction]
        
        if not filtered_rules:
            return "        return False  # No entry rules for this direction"
        
        code_lines = []
        for rule in filtered_rules:
            group_exprs = []
            for group in rule.condition_groups:
                cond_exprs = [self._compile_condition(c) for c in group.conditions]
                group_expr = f" {group.gate.value.lower()} ".join(cond_exprs)
                group_exprs.append(f"({group_expr})")
            
            final_expr = " and ".join(group_exprs)
            code_lines.append(f"        if {final_expr}:")
            code_lines.append(f"            return True")
        
        code_lines.append("        return False")
        return "\n".join(code_lines)

    def _compile_condition(self, cond: ConditionBlock) -> str:
        """
        Maps each ConditionBlock operator to its Python expression.
        
        Args:
            cond: ConditionBlock object
            
        Returns:
            Python expression string
        """
        left = cond.left_operand
        right = cond.right_operand
        op = cond.operator
        
        # Handle special operators that use helper methods
        if op == CompareOperator.CROSSES_ABOVE:
            # Handle numeric right operand
            if isinstance(right, (int, float)):
                return f"self.crosses_above('{left}', {right}, bar_idx)"
            else:
                return f"self.crosses_above('{left}', '{right}', bar_idx)"
        
        elif op == CompareOperator.CROSSES_BELOW:
            # Handle numeric right operand
            if isinstance(right, (int, float)):
                return f"self.crosses_below('{left}', {right}, bar_idx)"
            else:
                return f"self.crosses_below('{left}', '{right}', bar_idx)"
        
        elif op == CompareOperator.BETWEEN:
            # Parse the bounds from the right operand
            # Expected format: "40,70" or [40, 70]
            if isinstance(right, str):
                bounds = right.split(',')
                lower = float(bounds[0].strip())
                upper = float(bounds[1].strip())
            elif isinstance(right, (list, tuple)):
                lower, upper = float(right[0]), float(right[1])
            else:
                raise ValueError(f"Invalid bounds format for BETWEEN operator: {right}")
            
            return f"self.between('{left}', ({lower}, {upper}), bar_idx)"
        
        # Handle standard comparison operators
        else:
            # Map operator enum to Python operator
            op_map = {
                CompareOperator.GREATER: ">",
                CompareOperator.LESS: "<",
                CompareOperator.EQUALS: "==",
            }
            
            python_op = op_map.get(op, op.value)
            
            # Handle numeric vs indicator right operand
            if isinstance(right, (int, float)):
                return f"self.get_value('{left}', bar_idx) {python_op} {right}"
            else:
                return f"self.get_value('{left}', bar_idx) {python_op} self.get_value('{right}', bar_idx)"

    def _compile_exit_rules(self, rules: List[ExitRule]) -> str:
        """
        Converts exit rules to Python code.
        
        Args:
            rules: List of ExitRule objects
            
        Returns:
            Python code string for exit logic
        """
        if not rules:
            return "        return False, 'no_exit_rules'"
        
        code_lines = []
        code_lines.append("        # Check each exit rule")
        
        for idx, rule in enumerate(rules):
            if rule.exit_type == "target":
                code_lines.append(f"        # Exit rule {idx + 1}: Target profit")
                code_lines.append(f"        if hasattr(position, 'entry_price') and hasattr(position, 'direction'):")
                code_lines.append(f"            current_price = self.get_value('close', bar_idx)")
                code_lines.append(f"            if current_price is not None:")
                code_lines.append(f"                if position.direction == 'LONG':")
                code_lines.append(f"                    pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100")
                code_lines.append(f"                else:")
                code_lines.append(f"                    pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100")
                code_lines.append(f"                if pnl_pct >= {rule.target_pct}:")
                code_lines.append(f"                    return True, 'target_hit'")
            
            elif rule.exit_type == "stop_loss":
                code_lines.append(f"        # Exit rule {idx + 1}: Stop loss")
                code_lines.append(f"        if hasattr(position, 'entry_price') and hasattr(position, 'direction'):")
                code_lines.append(f"            current_price = self.get_value('close', bar_idx)")
                code_lines.append(f"            if current_price is not None:")
                code_lines.append(f"                if position.direction == 'LONG':")
                code_lines.append(f"                    pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100")
                code_lines.append(f"                else:")
                code_lines.append(f"                    pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100")
                code_lines.append(f"                if pnl_pct <= -{rule.stop_loss_pct}:")
                code_lines.append(f"                    return True, 'stop_loss_hit'")
            
            elif rule.exit_type == "trailing_sl":
                code_lines.append(f"        # Exit rule {idx + 1}: Trailing stop loss")
                code_lines.append(f"        if hasattr(position, 'entry_price') and hasattr(position, 'highest_price'):")
                code_lines.append(f"            current_price = self.get_value('close', bar_idx)")
                code_lines.append(f"            if current_price is not None:")
                code_lines.append(f"                trailing_stop = position.highest_price * (1 - {rule.trailing_sl_pct} / 100)")
                code_lines.append(f"                if current_price <= trailing_stop:")
                code_lines.append(f"                    return True, 'trailing_stop_hit'")
            
            elif rule.exit_type == "indicator":
                if rule.indicator_condition:
                    code_lines.append(f"        # Exit rule {idx + 1}: Indicator condition")
                    condition_expr = self._compile_condition(rule.indicator_condition)
                    code_lines.append(f"        if {condition_expr}:")
                    code_lines.append(f"            return True, 'indicator_exit'")
            
            elif rule.exit_type == "time":
                code_lines.append(f"        # Exit rule {idx + 1}: Time-based exit")
                code_lines.append(f"        if hasattr(position, 'entry_bar_idx'):")
                code_lines.append(f"            bars_held = bar_idx - position.entry_bar_idx")
                code_lines.append(f"            if bars_held >= {rule.max_hold_candles}:")
                code_lines.append(f"                return True, 'time_exit'")
        
        code_lines.append("        return False, 'no_exit'")
        return "\n".join(code_lines)

    def _compile_position_sizing(self, sizing: PositionSizing) -> str:
        """
        Converts position sizing configuration to Python code.
        
        Args:
            sizing: PositionSizing object
            
        Returns:
            Python code string for position sizing logic
        """
        code_lines = []
        
        if sizing.method == PositionSizingMethod.FIXED_CAPITAL:
            code_lines.append(f"        # Fixed capital per trade")
            code_lines.append(f"        size = {sizing.value}")
        
        elif sizing.method == PositionSizingMethod.PCT_CAPITAL:
            code_lines.append(f"        # Percentage of capital")
            code_lines.append(f"        size = capital * ({sizing.value} / 100)")
        
        elif sizing.method == PositionSizingMethod.KELLY_CRITERION:
            code_lines.append(f"        # Kelly Criterion (simplified - requires historical win rate)")
            code_lines.append(f"        # Using half-Kelly for safety")
            code_lines.append(f"        kelly_fraction = {sizing.value}")
            code_lines.append(f"        size = capital * kelly_fraction")
        
        elif sizing.method == PositionSizingMethod.ATR_BASED:
            code_lines.append(f"        # ATR-based position sizing")
            code_lines.append(f"        # Risk 1% of capital per trade, position size = risk / ATR")
            code_lines.append(f"        risk_amount = capital * self.risk_per_trade")
            code_lines.append(f"        if atr > 0:")
            code_lines.append(f"            size = risk_amount / atr")
            code_lines.append(f"        else:")
            code_lines.append(f"            size = capital * 0.01  # Fallback to 1% if ATR is 0")
        
        elif sizing.method == PositionSizingMethod.VOLATILITY_ADJUSTED:
            code_lines.append(f"        # Volatility-adjusted position sizing")
            code_lines.append(f"        # Scale inversely with volatility (ATR)")
            code_lines.append(f"        base_size = capital * ({sizing.value} / 100)")
            code_lines.append(f"        if atr > 0:")
            code_lines.append(f"            avg_atr = price * 0.02  # Assume 2% average volatility")
            code_lines.append(f"            vol_adjustment = avg_atr / atr")
            code_lines.append(f"            size = base_size * vol_adjustment")
            code_lines.append(f"        else:")
            code_lines.append(f"            size = base_size")
        
        else:
            code_lines.append(f"        # Default: 1% of capital")
            code_lines.append(f"        size = capital * 0.01")
        
        # Apply maximum position cap
        code_lines.append(f"        # Apply maximum position cap")
        code_lines.append(f"        max_size = capital * ({sizing.max_position_pct} / 100)")
        code_lines.append(f"        size = min(size, max_size)")
        code_lines.append(f"        return size")
        
        return "\n".join(code_lines)

    def _compile_market_filter(self, filter_config: MarketFilter) -> str:
        """
        Converts market filter configuration to Python code.
        
        Args:
            filter_config: MarketFilter object
            
        Returns:
            Python code string for market filter logic
        """
        code_lines = []
        
        # If no filters are active, always pass
        if not any([
            filter_config.require_above_200ema,
            filter_config.min_adx is not None,
            filter_config.max_vix is not None,
            filter_config.require_positive_breadth
        ]):
            code_lines.append("        return True  # No market filters configured")
            return "\n".join(code_lines)
        
        code_lines.append("        # Check market filter conditions")
        
        if filter_config.require_above_200ema:
            code_lines.append("        # Require price above 200 EMA")
            code_lines.append("        close = self.get_value('close', bar_idx)")
            code_lines.append("        ema_200 = self.get_value('ema_200', bar_idx)")
            code_lines.append("        if close is None or ema_200 is None or close <= ema_200:")
            code_lines.append("            return False")
        
        if filter_config.min_adx is not None:
            code_lines.append(f"        # Require ADX > {filter_config.min_adx}")
            code_lines.append("        adx = self.get_value('adx_14', bar_idx)")
            code_lines.append(f"        if adx is None or adx < {filter_config.min_adx}:")
            code_lines.append("            return False")
        
        if filter_config.max_vix is not None:
            code_lines.append(f"        # Require VIX < {filter_config.max_vix}")
            code_lines.append("        vix = self.get_value('vix', bar_idx)")
            code_lines.append(f"        if vix is not None and vix > {filter_config.max_vix}:")
            code_lines.append("            return False")
        
        if filter_config.require_positive_breadth:
            code_lines.append("        # Require positive market breadth")
            code_lines.append("        breadth = self.get_value('market_breadth', bar_idx)")
            code_lines.append("        if breadth is None or breadth <= 50:")
            code_lines.append("            return False")
        
        code_lines.append("        return True")
        return "\n".join(code_lines)
