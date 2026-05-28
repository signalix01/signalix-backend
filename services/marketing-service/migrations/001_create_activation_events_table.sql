-- Migration: Create user_activation_events table
-- Task: 22 - Implement activation event tracking
-- Requirements: 10.1, 10.8

-- Create user_activation_events table
CREATE TABLE IF NOT EXISTS user_activation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes for performance
    CONSTRAINT user_activation_events_event_type_check 
        CHECK (event_type IN (
            'risk_profile_saved',
            'watchlist_added',
            'first_analysis_run',
            'first_signal_viewed',
            'activation_completed'
        ))
);

-- Create indexes
CREATE INDEX idx_user_activation_events_user_id ON user_activation_events(user_id);
CREATE INDEX idx_user_activation_events_event_type ON user_activation_events(event_type);
CREATE INDEX idx_user_activation_events_timestamp ON user_activation_events(timestamp);
CREATE INDEX idx_user_activation_events_created_at ON user_activation_events(created_at);

-- Create unique constraint to prevent duplicate events per user
CREATE UNIQUE INDEX idx_user_activation_events_unique 
    ON user_activation_events(user_id, event_type);

-- Add comment
COMMENT ON TABLE user_activation_events IS 'Tracks user activation milestone events';
COMMENT ON COLUMN user_activation_events.event_type IS 'Type of activation event: risk_profile_saved, watchlist_added, first_analysis_run, first_signal_viewed, activation_completed';
COMMENT ON COLUMN user_activation_events.metadata IS 'Additional event metadata in JSON format';
