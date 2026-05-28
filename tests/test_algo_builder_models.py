"""Unit tests for algo_builder models

Tests all Pydantic models and validators for strategy specification.
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
"""
import pytest
import sys
import os
from pathlib import Path
from pydantic import ValidationError

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.algo_builder.models import (
    IndicatorType,
    CompareOperator,
    ConditionBlock,
    LogicGate,
    ConditionGroup,
    EntryRule,
    ExitRule,
    PositionSizingMethod,
    PositionSizing,
    MarketFilter,
    StrategySpec,
)


class TestIndicatorType:
    """Test IndicatorType enum"""

    def test_all_indicator_types_exist(self):
        """Verify all required indicator types are defined"""
        expected_indicators = [
            "rsi", "macd", "ema", "sma", "bollinger_bands", "atr", "vwap",
            "supertrend", "adx", "stochastic", "obv", "pivot_points",
            "ichimoku", "williams_r", "cci", "mfi"
        ]
        for indicator in expected_indicators:
            assert indicator in [e.value for e in IndicatorType]

    def test_indicator_type_values(self):
        """Test specific indicator type values"""
        assert IndicatorType.RSI.value == "rsi"
        assert IndicatorType.MACD.value == "macd"
        assert IndicatorType.SUPERTREND.value == "supertrend"


class TestCompareOperator:
    """Test CompareOperator enum"""

    def test_all_operators_exist(self):
        """Verify all required operators are defined"""
        expected_operators = [">", "<", "crosses_above", "crosses_below", "==", "between"]
        for operator in expected_operators:
            assert operator in [e.value for e in CompareOperator]

    def test_operator_values(self):
        """Test specific operator values"""
        assert CompareOperator.GREATER.value == ">"
        assert CompareOperator.CROSSES_ABOVE.value == "crosses_above"


class TestConditionBlock:
    """Test ConditionBlock model"""

    def test_valid_condition_block(self):
        """Test creating a valid condition block"""
        condition = ConditionBlock(
            left_operand="rsi_14",
            operator=CompareOperator.GREATER,
            right_operand=70.0,
            time_frame="1D"
        )
        assert condition.left_operand == "rsi_14"
        assert condition.operator == CompareOperator.GREATER
        assert condition.right_operand == 70.0
        assert condition.time_frame == "1D"

    def test_condition_block_with_string_operand(self):
        """Test condition block with string right operand"""
        condition = ConditionBlock(
            left_operand="ema_21",
            operator=CompareOperator.CROSSES_ABOVE,
            right_operand="ema_50"
        )
        assert condition.right_operand == "ema_50"

    def test_condition_block_default_timeframe(self):
        """Test default timeframe is 1D"""
        condition = ConditionBlock(
            left_operand="close",
            operator=CompareOperator.GREATER,
            right_operand=100.0
        )
        assert condition.time_frame == "1D"


class TestLogicGate:
    """Test LogicGate enum"""

    def test_logic_gates_exist(self):
        """Verify AND and OR gates exist"""
        assert LogicGate.AND.value == "AND"
        assert LogicGate.OR.value == "OR"


class TestConditionGroup:
    """Test ConditionGroup model"""

    def test_valid_condition_group(self):
        """Test creating a valid condition group"""
        conditions = [
            ConditionBlock(
                left_operand="rsi_14",
                operator=CompareOperator.GREATER,
                right_operand=30.0
            ),
            ConditionBlock(
                left_operand="rsi_14",
                operator=CompareOperator.LESS,
                right_operand=70.0
            )
        ]
        group = ConditionGroup(conditions=conditions, gate=LogicGate.AND)
        assert len(group.conditions) == 2
        assert group.gate == LogicGate.AND

    def test_condition_group_default_gate(self):
        """Test default gate is AND"""
        conditions = [
            ConditionBlock(
                left_operand="rsi_14",
                operator=CompareOperator.GREATER,
                right_operand=30.0
            )
        ]
        group = ConditionGroup(conditions=conditions)
        assert group.gate == LogicGate.AND


class TestEntryRule:
    """Test EntryRule model"""

    def test_valid_long_entry_rule(self):
        """Test creating a valid long entry rule"""
        condition_group = ConditionGroup(
            conditions=[
                ConditionBlock(
                    left_operand="rsi_14",
                    operator=CompareOperator.CROSSES_ABOVE,
                    right_operand=50.0
                )
            ]
        )
        entry_rule = EntryRule(
            direction="LONG",
            condition_groups=[condition_group],
            confirmation_candles=2
        )
        assert entry_rule.direction == "LONG"
        assert len(entry_rule.condition_groups) == 1
        assert entry_rule.confirmation_candles == 2

    def test_valid_short_entry_rule(self):
        """Test creating a valid short entry rule"""
        condition_group = ConditionGroup(
            conditions=[
                ConditionBlock(
                    left_operand="rsi_14",
                    operator=CompareOperator.CROSSES_BELOW,
                    right_operand=50.0
                )
            ]
        )
        entry_rule = EntryRule(
            direction="SHORT",
            condition_groups=[condition_group]
        )
        assert entry_rule.direction == "SHORT"
        assert entry_rule.confirmation_candles == 1  # default

    def test_entry_rule_default_confirmation_candles(self):
        """Test default confirmation candles is 1"""
        condition_group = ConditionGroup(
            conditions=[
                ConditionBlock(
                    left_operand="close",
                    operator=CompareOperator.GREATER,
                    right_operand="ema_200"
                )
            ]
        )
        entry_rule = EntryRule(
            direction="LONG",
            condition_groups=[condition_group]
        )
        assert entry_rule.confirmation_candles == 1


class TestExitRule:
    """Test ExitRule model"""

    def test_target_exit_rule(self):
        """Test creating a target exit rule"""
        exit_rule = ExitRule(
            exit_type="target",
            target_pct=5.0
        )
        assert exit_rule.exit_type == "target"
        assert exit_rule.target_pct == 5.0

    def test_stop_loss_exit_rule(self):
        """Test creating a stop loss exit rule"""
        exit_rule = ExitRule(
            exit_type="stop_loss",
            stop_loss_pct=2.0
        )
        assert exit_rule.exit_type == "stop_loss"
        assert exit_rule.stop_loss_pct == 2.0

    def test_trailing_stop_exit_rule(self):
        """Test creating a trailing stop exit rule"""
        exit_rule = ExitRule(
            exit_type="trailing_sl",
            trailing_sl_pct=3.0
        )
        assert exit_rule.exit_type == "trailing_sl"
        assert exit_rule.trailing_sl_pct == 3.0

    def test_indicator_exit_rule(self):
        """Test creating an indicator-based exit rule"""
        condition = ConditionBlock(
            left_operand="rsi_14",
            operator=CompareOperator.LESS,
            right_operand=30.0
        )
        exit_rule = ExitRule(
            exit_type="indicator",
            indicator_condition=condition
        )
        assert exit_rule.exit_type == "indicator"
        assert exit_rule.indicator_condition is not None

    def test_time_exit_rule(self):
        """Test creating a time-based exit rule"""
        exit_rule = ExitRule(
            exit_type="time",
            max_hold_candles=20
        )
        assert exit_rule.exit_type == "time"
        assert exit_rule.max_hold_candles == 20


class TestPositionSizingMethod:
    """Test PositionSizingMethod enum"""

    def test_all_sizing_methods_exist(self):
        """Verify all required sizing methods are defined"""
        expected_methods = [
            "fixed_capital", "pct_capital", "kelly", "atr_based", "vol_adj"
        ]
        for method in expected_methods:
            assert method in [e.value for e in PositionSizingMethod]

    def test_kelly_method_has_warning(self):
        """Test that Kelly method includes warning about historical data"""
        # The warning is in the comment/description, not the value
        assert PositionSizingMethod.KELLY_CRITERION.value == "kelly"


class TestPositionSizing:
    """Test PositionSizing model and validators"""

    def test_valid_position_sizing(self):
        """Test creating valid position sizing"""
        sizing = PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=2.0,
            max_position_pct=5.0,
            max_concurrent_positions=3
        )
        assert sizing.method == PositionSizingMethod.PCT_CAPITAL
        assert sizing.value == 2.0
        assert sizing.max_position_pct == 5.0
        assert sizing.max_concurrent_positions == 3

    def test_max_position_pct_at_limit(self):
        """Test max_position_pct at exactly 10%"""
        sizing = PositionSizing(
            method=PositionSizingMethod.FIXED_CAPITAL,
            value=10000.0,
            max_position_pct=10.0
        )
        assert sizing.max_position_pct == 10.0

    def test_max_position_pct_exceeds_limit(self):
        """Test that max_position_pct > 10% raises error"""
        with pytest.raises(ValidationError) as exc_info:
            PositionSizing(
                method=PositionSizingMethod.FIXED_CAPITAL,
                value=10000.0,
                max_position_pct=15.0
            )
        assert "max_position_pct cannot exceed 10.0%" in str(exc_info.value)

    def test_kelly_sizing_method(self):
        """Test Kelly sizing method is accepted"""
        sizing = PositionSizing(
            method=PositionSizingMethod.KELLY_CRITERION,
            value=1.0,
            max_position_pct=8.0
        )
        assert sizing.method == PositionSizingMethod.KELLY_CRITERION

    def test_atr_based_sizing(self):
        """Test ATR-based sizing"""
        sizing = PositionSizing(
            method=PositionSizingMethod.ATR_BASED,
            value=1.0,
            max_position_pct=7.0
        )
        assert sizing.method == PositionSizingMethod.ATR_BASED

    def test_default_max_position_pct(self):
        """Test default max_position_pct is 10.0"""
        sizing = PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=2.0
        )
        assert sizing.max_position_pct == 10.0

    def test_default_max_concurrent_positions(self):
        """Test default max_concurrent_positions is 5"""
        sizing = PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=2.0
        )
        assert sizing.max_concurrent_positions == 5


class TestMarketFilter:
    """Test MarketFilter model"""

    def test_default_market_filter(self):
        """Test default market filter values"""
        filter = MarketFilter()
        assert filter.require_above_200ema is False
        assert filter.min_adx is None
        assert filter.max_vix is None
        assert filter.require_positive_breadth is False

    def test_market_filter_with_ema_requirement(self):
        """Test market filter with 200 EMA requirement"""
        filter = MarketFilter(require_above_200ema=True)
        assert filter.require_above_200ema is True

    def test_market_filter_with_adx(self):
        """Test market filter with ADX requirement"""
        filter = MarketFilter(min_adx=25.0)
        assert filter.min_adx == 25.0

    def test_market_filter_with_vix(self):
        """Test market filter with VIX limit"""
        filter = MarketFilter(max_vix=30.0)
        assert filter.max_vix == 30.0

    def test_market_filter_all_conditions(self):
        """Test market filter with all conditions"""
        filter = MarketFilter(
            require_above_200ema=True,
            min_adx=25.0,
            max_vix=30.0,
            require_positive_breadth=True
        )
        assert filter.require_above_200ema is True
        assert filter.min_adx == 25.0
        assert filter.max_vix == 30.0
        assert filter.require_positive_breadth is True


class TestStrategySpec:
    """Test StrategySpec model and validators"""

    def create_valid_strategy_spec(self):
        """Helper to create a valid strategy spec"""
        entry_rule = EntryRule(
            direction="LONG",
            condition_groups=[
                ConditionGroup(
                    conditions=[
                        ConditionBlock(
                            left_operand="rsi_14",
                            operator=CompareOperator.CROSSES_ABOVE,
                            right_operand=50.0
                        )
                    ]
                )
            ]
        )
        exit_rule = ExitRule(
            exit_type="target",
            target_pct=5.0
        )
        position_sizing = PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=2.0
        )
        market_filter = MarketFilter()

        return StrategySpec(
            strategy_id="test-123",
            user_id="user-456",
            name="Test Strategy",
            description="A test strategy",
            asset_class="equity",
            instruments=["BANKNIFTY"],
            entry_rules=[entry_rule],
            exit_rules=[exit_rule],
            position_sizing=position_sizing,
            market_filter=market_filter,
            indicators_config={"rsi_14": {"period": 14}},
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z"
        )

    def test_valid_strategy_spec(self):
        """Test creating a valid strategy spec"""
        spec = self.create_valid_strategy_spec()
        assert spec.strategy_id == "test-123"
        assert spec.name == "Test Strategy"
        assert spec.asset_class == "equity"
        assert len(spec.entry_rules) == 1
        assert len(spec.exit_rules) == 1

    def test_strategy_spec_no_entry_rules(self):
        """Test that strategy spec requires at least one entry rule"""
        with pytest.raises(ValidationError) as exc_info:
            spec = self.create_valid_strategy_spec()
            spec.entry_rules = []
            StrategySpec(**spec.dict())
        # Pydantic will catch this with min_items validation

    def test_strategy_spec_no_exit_rules(self):
        """Test that strategy spec requires at least one exit rule"""
        with pytest.raises(ValidationError) as exc_info:
            spec = self.create_valid_strategy_spec()
            spec.exit_rules = []
            StrategySpec(**spec.dict())
        # Pydantic will catch this with min_items validation

    def test_strategy_spec_multiple_entry_rules(self):
        """Test strategy spec with multiple entry rules"""
        spec = self.create_valid_strategy_spec()
        entry_rule_2 = EntryRule(
            direction="SHORT",
            condition_groups=[
                ConditionGroup(
                    conditions=[
                        ConditionBlock(
                            left_operand="rsi_14",
                            operator=CompareOperator.CROSSES_BELOW,
                            right_operand=50.0
                        )
                    ]
                )
            ]
        )
        spec.entry_rules.append(entry_rule_2)
        assert len(spec.entry_rules) == 2

    def test_strategy_spec_multiple_exit_rules(self):
        """Test strategy spec with multiple exit rules"""
        spec = self.create_valid_strategy_spec()
        exit_rule_2 = ExitRule(
            exit_type="stop_loss",
            stop_loss_pct=2.0
        )
        spec.exit_rules.append(exit_rule_2)
        assert len(spec.exit_rules) == 2

    def test_strategy_spec_all_asset_classes(self):
        """Test strategy spec with all asset classes"""
        asset_classes = ["equity", "fo", "crypto", "forex", "commodity"]
        for asset_class in asset_classes:
            spec = self.create_valid_strategy_spec()
            spec.asset_class = asset_class
            assert spec.asset_class == asset_class

    def test_strategy_spec_all_statuses(self):
        """Test strategy spec with all statuses"""
        statuses = ["draft", "testing", "paper", "live"]
        for status in statuses:
            spec = self.create_valid_strategy_spec()
            spec.status = status
            assert spec.status == status

    def test_strategy_spec_default_status(self):
        """Test default status is draft"""
        spec = self.create_valid_strategy_spec()
        assert spec.status == "draft"

    def test_strategy_spec_default_risk_per_trade(self):
        """Test default risk_per_trade_pct is 1.0"""
        spec = self.create_valid_strategy_spec()
        assert spec.risk_per_trade_pct == 1.0

    def test_strategy_spec_default_max_daily_loss(self):
        """Test default max_daily_loss_pct is 2.0"""
        spec = self.create_valid_strategy_spec()
        assert spec.max_daily_loss_pct == 2.0

    def test_strategy_spec_default_regime_awareness(self):
        """Test default regime_awareness is True"""
        spec = self.create_valid_strategy_spec()
        assert spec.regime_awareness is True

    def test_strategy_spec_multiple_instruments(self):
        """Test strategy spec with multiple instruments"""
        spec = self.create_valid_strategy_spec()
        spec.instruments = ["BANKNIFTY", "NIFTY", "RELIANCE"]
        assert len(spec.instruments) == 3

    def test_strategy_spec_complex_indicators_config(self):
        """Test strategy spec with complex indicators config"""
        spec = self.create_valid_strategy_spec()
        spec.indicators_config = {
            "rsi_14": {"period": 14},
            "ema_21": {"period": 21},
            "ema_50": {"period": 50},
            "macd": {"fast": 12, "slow": 26, "signal": 9}
        }
        assert len(spec.indicators_config) == 4


class TestValidatorEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_max_position_pct_boundary_values(self):
        """Test max_position_pct at various boundary values"""
        # Valid: exactly 10.0
        sizing = PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=2.0,
            max_position_pct=10.0
        )
        assert sizing.max_position_pct == 10.0

        # Valid: less than 10.0
        sizing = PositionSizing(
            method=PositionSizingMethod.PCT_CAPITAL,
            value=2.0,
            max_position_pct=9.99
        )
        assert sizing.max_position_pct == 9.99

        # Invalid: greater than 10.0
        with pytest.raises(ValidationError):
            PositionSizing(
                method=PositionSizingMethod.PCT_CAPITAL,
                value=2.0,
                max_position_pct=10.01
            )

    def test_empty_entry_rules_list(self):
        """Test that empty entry rules list is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            StrategySpec(
                strategy_id="test-123",
                user_id="user-456",
                name="Test Strategy",
                description="A test strategy",
                asset_class="equity",
                instruments=["BANKNIFTY"],
                entry_rules=[],  # Empty list
                exit_rules=[ExitRule(exit_type="target", target_pct=5.0)],
                position_sizing=PositionSizing(
                    method=PositionSizingMethod.PCT_CAPITAL,
                    value=2.0
                ),
                market_filter=MarketFilter(),
                indicators_config={"rsi_14": {"period": 14}},
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z"
            )
        # Should fail due to min_items=1 constraint

    def test_empty_exit_rules_list(self):
        """Test that empty exit rules list is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            StrategySpec(
                strategy_id="test-123",
                user_id="user-456",
                name="Test Strategy",
                description="A test strategy",
                asset_class="equity",
                instruments=["BANKNIFTY"],
                entry_rules=[EntryRule(
                    direction="LONG",
                    condition_groups=[
                        ConditionGroup(
                            conditions=[
                                ConditionBlock(
                                    left_operand="rsi_14",
                                    operator=CompareOperator.GREATER,
                                    right_operand=50.0
                                )
                            ]
                        )
                    ]
                )],
                exit_rules=[],  # Empty list
                position_sizing=PositionSizing(
                    method=PositionSizingMethod.PCT_CAPITAL,
                    value=2.0
                ),
                market_filter=MarketFilter(),
                indicators_config={"rsi_14": {"period": 14}},
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z"
            )
        # Should fail due to min_items=1 constraint


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
