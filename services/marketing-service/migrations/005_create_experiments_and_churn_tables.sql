-- Migration: Create A/B testing and churn prevention tables
-- Description: Tables for experiments, assignments, conversions, and churn signals

-- Experiments table
CREATE TABLE IF NOT EXISTS experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    hypothesis TEXT,
    status VARCHAR(20) DEFAULT 'draft', -- 'draft', 'running', 'paused', 'completed'
    variants JSONB NOT NULL, -- [{"name": "control", "weight": 50}, {"name": "variant_a", "weight": 50}]
    traffic_allocation INTEGER DEFAULT 100, -- Percentage of traffic to include
    variant_stats JSONB DEFAULT '{}',
    winner VARCHAR(50),
    confidence_level DECIMAL(5,2),
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_experiments_status ON experiments(status);
CREATE INDEX idx_experiments_created_by ON experiments(created_by);
CREATE INDEX idx_experiments_started_at ON experiments(started_at);

-- Experiment assignments table
CREATE TABLE IF NOT EXISTS experiment_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    user_id UUID,
    session_id VARCHAR(255),
    variant VARCHAR(50) NOT NULL,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_experiment_assignments_experiment_id ON experiment_assignments(experiment_id);
CREATE INDEX idx_experiment_assignments_user_id ON experiment_assignments(user_id);
CREATE INDEX idx_experiment_assignments_session_id ON experiment_assignments(session_id);
CREATE INDEX idx_experiment_assignments_variant ON experiment_assignments(variant);

-- Experiment conversions table
CREATE TABLE IF NOT EXISTS experiment_conversions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES experiment_assignments(id) ON DELETE CASCADE,
    conversion_type VARCHAR(100) NOT NULL,
    value DECIMAL(10,2),
    converted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_experiment_conversions_assignment_id ON experiment_conversions(assignment_id);
CREATE INDEX idx_experiment_conversions_type ON experiment_conversions(conversion_type);
CREATE INDEX idx_experiment_conversions_converted_at ON experiment_conversions(converted_at);

-- Churn signals table
CREATE TABLE IF NOT EXISTS churn_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    signal_type VARCHAR(100) NOT NULL, -- 'login_frequency_drop', 'feature_usage_stop', 'support_ticket_spike', 'billing_page_visits'
    signal_strength VARCHAR(20) NOT NULL, -- 'low', 'medium', 'high'
    signal_value JSONB,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    action_taken VARCHAR(100), -- 'email_sent', 'discount_offered', 'support_contacted'
    action_taken_at TIMESTAMP WITH TIME ZONE,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_churn_signals_user_id ON churn_signals(user_id);
CREATE INDEX idx_churn_signals_type ON churn_signals(signal_type);
CREATE INDEX idx_churn_signals_strength ON churn_signals(signal_strength);
CREATE INDEX idx_churn_signals_detected_at ON churn_signals(detected_at);
CREATE INDEX idx_churn_signals_resolved ON churn_signals(resolved);

-- Marketing events table (for server-side tracking)
CREATE TABLE IF NOT EXISTS marketing_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_name VARCHAR(100) NOT NULL,
    user_id UUID,
    session_id VARCHAR(255),
    properties JSONB,
    page_url TEXT,
    referrer TEXT,
    utm_params JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_marketing_events_event_name ON marketing_events(event_name);
CREATE INDEX idx_marketing_events_user_id ON marketing_events(user_id);
CREATE INDEX idx_marketing_events_session_id ON marketing_events(session_id);
CREATE INDEX idx_marketing_events_created_at ON marketing_events(created_at);

-- Partition marketing_events by month for performance
-- Note: Partitions should be created monthly via cron job

-- Content performance table
CREATE TABLE IF NOT EXISTS content_performance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_type VARCHAR(50) NOT NULL, -- 'blog_post', 'landing_page', 'lead_magnet'
    content_id VARCHAR(255) NOT NULL,
    slug VARCHAR(255),
    title VARCHAR(500),
    page_views INTEGER DEFAULT 0,
    unique_visitors INTEGER DEFAULT 0,
    avg_time_on_page INTEGER, -- seconds
    bounce_rate DECIMAL(5,2),
    conversion_rate DECIMAL(5,2),
    conversions INTEGER DEFAULT 0,
    date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(content_id, date)
);

CREATE INDEX idx_content_performance_content_id ON content_performance(content_id);
CREATE INDEX idx_content_performance_type ON content_performance(content_type);
CREATE INDEX idx_content_performance_date ON content_performance(date);
CREATE INDEX idx_content_performance_slug ON content_performance(slug);

-- Comments
COMMENT ON TABLE experiments IS 'A/B testing experiments configuration';
COMMENT ON TABLE experiment_assignments IS 'User/session assignments to experiment variants';
COMMENT ON TABLE experiment_conversions IS 'Conversion events for experiment analysis';
COMMENT ON TABLE churn_signals IS 'Detected churn risk signals for proactive retention';
COMMENT ON TABLE marketing_events IS 'Server-side marketing event tracking';
COMMENT ON TABLE content_performance IS 'Daily content performance metrics';

COMMENT ON COLUMN experiments.variants IS 'Array of variant configurations with names and traffic weights';
COMMENT ON COLUMN experiments.traffic_allocation IS 'Percentage of total traffic included in experiment (0-100)';
COMMENT ON COLUMN churn_signals.signal_value IS 'Additional signal data (e.g., login frequency drop percentage)';
