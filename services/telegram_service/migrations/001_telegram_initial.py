"""
Telegram Service Initial Migration

Creates tables for Telegram Bot Service.
Requirements: 8.1, 9.1, 24.1
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001_telegram_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Telegram connections table
    op.create_table(
        'telegram_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('telegram_user_id', sa.String(50), nullable=False, unique=True, index=True),
        sa.Column('telegram_username', sa.String(100), nullable=True),
        sa.Column('telegram_first_name', sa.String(100), nullable=True),
        sa.Column('telegram_last_name', sa.String(100), nullable=True),
        sa.Column('auth_token', sa.String(100), nullable=True, index=True),
        sa.Column('auth_token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('auth_attempts', sa.Integer(), default=0),
        sa.Column('auth_blocked_until', sa.DateTime(), nullable=True),
        sa.Column('status', sa.Enum('pending', 'connected', 'disconnected', 'error', 'revoked', name='connection_status'), default='pending', nullable=False),
        sa.Column('connected_at', sa.DateTime(), nullable=True),
        sa.Column('disconnected_at', sa.DateTime(), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('session_expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    op.create_index('idx_telegram_user_lookup', 'telegram_connections', ['telegram_user_id', 'status'])
    op.create_index('idx_telegram_auth_token', 'telegram_connections', ['auth_token', 'auth_token_expires_at'])
    
    # Telegram preferences table
    op.create_table(
        'telegram_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('telegram_connections.id'), unique=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('order_notifications', sa.Boolean(), default=True, nullable=False),
        sa.Column('execution_notifications', sa.Boolean(), default=True, nullable=False),
        sa.Column('rejection_notifications', sa.Boolean(), default=True, nullable=False),
        sa.Column('position_notifications', sa.Boolean(), default=False, nullable=False),
        sa.Column('system_notifications', sa.Boolean(), default=True, nullable=False),
        sa.Column('batch_notifications', sa.Boolean(), default=True, nullable=False),
        sa.Column('batch_window_seconds', sa.Integer(), default=5, nullable=False),
        sa.Column('require_confirmation', sa.Boolean(), default=True, nullable=False),
        sa.Column('confirmation_timeout_seconds', sa.Integer(), default=60, nullable=False),
        sa.Column('rate_limit_per_minute', sa.Integer(), default=10, nullable=False),
        sa.Column('use_emojis', sa.Boolean(), default=True, nullable=False),
        sa.Column('use_monospace_for_numbers', sa.Boolean(), default=True, nullable=False),
        sa.Column('timezone', sa.String(50), default='UTC', nullable=False),
        sa.Column('enabled_symbols', postgresql.JSONB(), nullable=True),
        sa.Column('disabled_symbols', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Telegram command logs table
    op.create_table(
        'telegram_command_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('telegram_connections.id'), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('telegram_user_id', sa.String(50), nullable=False, index=True),
        sa.Column('command_type', sa.Enum('buy', 'sell', 'positions', 'orders', 'cancel', 'status', 'help', 'start', 'auth', 'unknown', name='command_type'), nullable=False),
        sa.Column('command_text', sa.Text(), nullable=False),
        sa.Column('parsed_parameters', postgresql.JSONB(), default=dict, nullable=True),
        sa.Column('executed_at', sa.DateTime(), default=sa.func.now(), nullable=False),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('rate_limited', sa.Boolean(), default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), nullable=False),
    )
    
    op.create_index('idx_command_log_user_time', 'telegram_command_logs', ['user_id', 'executed_at'])
    op.create_index('idx_command_log_type_time', 'telegram_command_logs', ['command_type', 'executed_at'])
    
    # Telegram order prompts table
    op.create_table(
        'telegram_order_prompts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('telegram_connections.id'), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('telegram_message_id', sa.String(50), nullable=True, index=True),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('order_type', sa.String(20), nullable=False),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('trigger_price', sa.Float(), nullable=True),
        sa.Column('product_type', sa.String(20), default='INTRADAY', nullable=False),
        sa.Column('status', sa.Enum('pending', 'confirmed', 'cancelled', 'expired', 'executed', name='order_prompt_status'), default='pending', nullable=False),
        sa.Column('sent_at', sa.DateTime(), default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.Column('response_action', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    op.create_index('idx_order_prompt_status', 'telegram_order_prompts', ['status', 'expires_at'])
    op.create_index('idx_order_prompt_user', 'telegram_order_prompts', ['user_id', 'created_at'])
    
    # Telegram auth tokens table
    op.create_table(
        'telegram_auth_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('token', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('used_by_telegram_user_id', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), nullable=False),
    )
    
    op.create_index('idx_auth_token_lookup', 'telegram_auth_tokens', ['token', 'expires_at'])


def downgrade():
    op.drop_index('idx_auth_token_lookup', table_name='telegram_auth_tokens')
    op.drop_table('telegram_auth_tokens')
    
    op.drop_index('idx_order_prompt_user', table_name='telegram_order_prompts')
    op.drop_index('idx_order_prompt_status', table_name='telegram_order_prompts')
    op.drop_table('telegram_order_prompts')
    
    op.drop_index('idx_command_log_type_time', table_name='telegram_command_logs')
    op.drop_index('idx_command_log_user_time', table_name='telegram_command_logs')
    op.drop_table('telegram_command_logs')
    
    op.drop_table('telegram_preferences')
    
    op.drop_index('idx_telegram_auth_token', table_name='telegram_connections')
    op.drop_index('idx_telegram_user_lookup', table_name='telegram_connections')
    op.drop_table('telegram_connections')
    
    # Drop enum types
    op.execute("DROP TYPE IF EXISTS connection_status")
    op.execute("DROP TYPE IF EXISTS command_type")
    op.execute("DROP TYPE IF EXISTS order_prompt_status")
