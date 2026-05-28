"""Create algo builder, backtesting, screening and alert engine schema

Revision ID: 004
Revises: 003
Create Date: 2025-01-15 10:00:00.000000

Requirements: 1.8, 11.7, 16.2, 16.3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create tables for:
    - Algo Builder (strategies)
    - Backtesting (backtest_results)
    - AI Screening (screening_criteria, screening_results)
    - Anomaly Detection & Alerts (anomaly_events, alert_rules, alert_delivery_log)
    
    TimescaleDB hypertables:
    - anomaly_events (partitioned by detected_at)
    - screening_results (partitioned by run_at)
    
    Retention policies:
    - anomaly_events: 90 days (Pro tier), 30 days (free tier) - handled at application level
    """
    
    # ============================================================================
    # 1. STRATEGIES TABLE
    # ============================================================================
    op.create_table(
        'strategies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('spec', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('compiled_hash', sa.String(64), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Indexes for strategies
    op.create_index('idx_strategies_user_id', 'strategies', ['user_id'])
    op.create_index('idx_strategies_compiled_hash', 'strategies', ['compiled_hash'])
    op.create_index('idx_strategies_status', 'strategies', ['status'])
    op.create_index('idx_strategies_user_status', 'strategies', ['user_id', 'status'])
    
    # ============================================================================
    # 2. BACKTEST_RESULTS TABLE
    # ============================================================================
    op.create_table(
        'backtest_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('instrument', sa.String(50), nullable=False),
        sa.Column('asset_class', sa.String(20), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column('mode', sa.String(20), nullable=False),
        
        # Core performance metrics
        sa.Column('total_return_pct', sa.Float(), nullable=True),
        sa.Column('cagr_pct', sa.Float(), nullable=True),
        sa.Column('sharpe_ratio', sa.Float(), nullable=True),
        sa.Column('sortino_ratio', sa.Float(), nullable=True),
        sa.Column('calmar_ratio', sa.Float(), nullable=True),
        sa.Column('max_drawdown_pct', sa.Float(), nullable=True),
        sa.Column('avg_drawdown_pct', sa.Float(), nullable=True),
        sa.Column('max_drawdown_duration_days', sa.Integer(), nullable=True),
        
        # Trade statistics
        sa.Column('total_trades', sa.Integer(), nullable=True),
        sa.Column('win_rate_pct', sa.Float(), nullable=True),
        sa.Column('avg_win_pct', sa.Float(), nullable=True),
        sa.Column('avg_loss_pct', sa.Float(), nullable=True),
        sa.Column('profit_factor', sa.Float(), nullable=True),
        sa.Column('expectancy_per_trade', sa.Float(), nullable=True),
        sa.Column('avg_hold_days', sa.Float(), nullable=True),
        sa.Column('max_consecutive_losses', sa.Integer(), nullable=True),
        
        # Risk metrics
        sa.Column('kelly_fraction', sa.Float(), nullable=True),
        sa.Column('half_kelly', sa.Float(), nullable=True),
        
        # Walk-forward results
        sa.Column('wf_train_return', sa.Float(), nullable=True),
        sa.Column('wf_validate_return', sa.Float(), nullable=True),
        sa.Column('wf_test_return', sa.Float(), nullable=True),
        sa.Column('wf_consistency_score', sa.Float(), nullable=True),
        
        # Regime analysis
        sa.Column('trending_bull_return', sa.Float(), nullable=True),
        sa.Column('trending_bear_return', sa.Float(), nullable=True),
        sa.Column('ranging_return', sa.Float(), nullable=True),
        sa.Column('volatile_return', sa.Float(), nullable=True),
        
        # Monte Carlo
        sa.Column('mc_median_return', sa.Float(), nullable=True),
        sa.Column('mc_5th_percentile_return', sa.Float(), nullable=True),
        sa.Column('mc_95th_percentile_return', sa.Float(), nullable=True),
        sa.Column('mc_ruin_probability', sa.Float(), nullable=True),
        
        # Full result data
        sa.Column('result_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='CASCADE'),
    )
    
    # Indexes for backtest_results
    op.create_index('idx_backtest_strategy_id', 'backtest_results', ['strategy_id'])
    op.create_index('idx_backtest_user_id', 'backtest_results', ['user_id'])
    op.create_index('idx_backtest_created_at', 'backtest_results', ['created_at'])
    op.create_index('idx_backtest_user_created', 'backtest_results', ['user_id', 'created_at'])
    op.create_index('idx_backtest_strategy_created', 'backtest_results', ['strategy_id', 'created_at'])
    
    # ============================================================================
    # 3. SCREENING_CRITERIA TABLE
    # ============================================================================
    op.create_table(
        'screening_criteria',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('criteria_spec', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('schedule_cron', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Indexes for screening_criteria
    op.create_index('idx_screening_criteria_user_id', 'screening_criteria', ['user_id'])
    op.create_index('idx_screening_criteria_is_active', 'screening_criteria', ['is_active'])
    op.create_index('idx_screening_criteria_user_active', 'screening_criteria', ['user_id', 'is_active'])
    
    # ============================================================================
    # 4. SCREENING_RESULTS TABLE (TimescaleDB Hypertable)
    # ============================================================================
    op.create_table(
        'screening_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('criteria_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('run_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('instruments_scanned', sa.Integer(), nullable=True),
        sa.Column('instruments_passed', sa.Integer(), nullable=True),
        sa.Column('results', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        
        sa.ForeignKeyConstraint(['criteria_id'], ['screening_criteria.id'], ondelete='CASCADE'),
    )
    
    # Indexes for screening_results (before converting to hypertable)
    op.create_index('idx_screening_results_criteria_id', 'screening_results', ['criteria_id'])
    op.create_index('idx_screening_results_user_id', 'screening_results', ['user_id'])
    op.create_index('idx_screening_results_run_at', 'screening_results', ['run_at'])
    op.create_index('idx_screening_results_criteria_run', 'screening_results', ['criteria_id', 'run_at'])
    
    # Convert screening_results to TimescaleDB hypertable (partitioned by run_at)
    op.execute("""
        SELECT create_hypertable('screening_results', 'run_at', 
                                 chunk_time_interval => INTERVAL '7 days',
                                 if_not_exists => TRUE);
    """)
    
    # Add retention policy: 7 days for screening results (Requirement 16.3)
    op.execute("""
        SELECT add_retention_policy('screening_results', INTERVAL '7 days', if_not_exists => TRUE);
    """)
    
    # ============================================================================
    # 5. ANOMALY_EVENTS TABLE (TimescaleDB Hypertable)
    # ============================================================================
    op.create_table(
        'anomaly_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('instrument', sa.String(50), nullable=False),
        sa.Column('asset_class', sa.String(20), nullable=False),
        sa.Column('exchange', sa.String(20), nullable=True),
        sa.Column('anomaly_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('z_score', sa.Float(), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('volume', sa.Float(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('affected_instruments', postgresql.ARRAY(sa.String()), nullable=True),
    )
    
    # Indexes for anomaly_events (before converting to hypertable)
    op.create_index('idx_anomaly_instrument', 'anomaly_events', ['instrument'])
    op.create_index('idx_anomaly_type', 'anomaly_events', ['anomaly_type'])
    op.create_index('idx_anomaly_severity', 'anomaly_events', ['severity'])
    op.create_index('idx_anomaly_detected_at', 'anomaly_events', ['detected_at'])
    op.create_index('idx_anomaly_instrument_detected', 'anomaly_events', ['instrument', 'detected_at'])
    op.create_index('idx_anomaly_type_severity_detected', 'anomaly_events', ['anomaly_type', 'severity', 'detected_at'])
    
    # Convert anomaly_events to TimescaleDB hypertable (partitioned by detected_at)
    op.execute("""
        SELECT create_hypertable('anomaly_events', 'detected_at', 
                                 chunk_time_interval => INTERVAL '1 day',
                                 if_not_exists => TRUE);
    """)
    
    # Add retention policies for anomaly_events (Requirement 16.2)
    # Note: Tier-based retention (90 days Pro, 30 days free) will be handled at application level
    # Here we set a conservative 90-day default
    op.execute("""
        SELECT add_retention_policy('anomaly_events', INTERVAL '90 days', if_not_exists => TRUE);
    """)
    
    # ============================================================================
    # 6. ALERT_RULES TABLE
    # ============================================================================
    op.create_table(
        'alert_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('instruments', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('asset_classes', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('anomaly_types', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('min_severity', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('channels', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('max_alerts_per_hour', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('quiet_hours_start', sa.String(5), nullable=True),
        sa.Column('quiet_hours_end', sa.String(5), nullable=True),
        sa.Column('webhook_url', sa.String(500), nullable=True),
        sa.Column('webhook_secret', sa.String(100), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Indexes for alert_rules
    op.create_index('idx_alert_rules_user_id', 'alert_rules', ['user_id'])
    op.create_index('idx_alert_rules_enabled', 'alert_rules', ['enabled'])
    op.create_index('idx_alert_rules_user_enabled', 'alert_rules', ['user_id', 'enabled'])
    
    # ============================================================================
    # 7. ALERT_DELIVERY_LOG TABLE
    # ============================================================================
    op.create_table(
        'alert_delivery_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('anomaly_event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('alert_rule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('detection_to_delivery_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        
        sa.ForeignKeyConstraint(['anomaly_event_id'], ['anomaly_events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['alert_rule_id'], ['alert_rules.id'], ondelete='CASCADE'),
    )
    
    # Indexes for alert_delivery_log
    op.create_index('idx_alert_delivery_anomaly_event_id', 'alert_delivery_log', ['anomaly_event_id'])
    op.create_index('idx_alert_delivery_alert_rule_id', 'alert_delivery_log', ['alert_rule_id'])
    op.create_index('idx_alert_delivery_user_id', 'alert_delivery_log', ['user_id'])
    op.create_index('idx_alert_delivery_created_at', 'alert_delivery_log', ['created_at'])
    op.create_index('idx_alert_delivery_user_created', 'alert_delivery_log', ['user_id', 'created_at'])
    op.create_index('idx_alert_delivery_event_rule', 'alert_delivery_log', ['anomaly_event_id', 'alert_rule_id'])
    
    print("✓ Created all tables for Algo Builder, Backtesting, Screening & Alert Engine")
    print("✓ Configured TimescaleDB hypertables: anomaly_events, screening_results")
    print("✓ Applied retention policies: anomaly_events (90 days), screening_results (7 days)")


def downgrade() -> None:
    """Drop all tables in reverse order"""
    
    # Drop tables in reverse order (respecting foreign key constraints)
    op.drop_table('alert_delivery_log')
    op.drop_table('alert_rules')
    op.drop_table('anomaly_events')
    op.drop_table('screening_results')
    op.drop_table('screening_criteria')
    op.drop_table('backtest_results')
    op.drop_table('strategies')
    
    print("✓ Dropped all Algo Builder, Backtesting, Screening & Alert Engine tables")
