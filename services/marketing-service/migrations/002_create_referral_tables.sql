-- Migration: Create referral program tables
-- Description: Tables for referral link generation, tracking, and rewards

-- Referrers table
CREATE TABLE IF NOT EXISTS referrers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE,
    referral_code VARCHAR(20) NOT NULL UNIQUE,
    total_referrals INTEGER DEFAULT 0,
    successful_referrals INTEGER DEFAULT 0,
    pending_referrals INTEGER DEFAULT 0,
    total_rewards_paise BIGINT DEFAULT 0,
    pending_rewards_paise BIGINT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_referrers_user_id ON referrers(user_id);
CREATE INDEX idx_referrers_code ON referrers(referral_code);
CREATE INDEX idx_referrers_status ON referrers(status);

-- Referrals table
CREATE TABLE IF NOT EXISTS referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id UUID NOT NULL REFERENCES referrers(id) ON DELETE CASCADE,
    referred_user_id UUID NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    signup_at TIMESTAMP WITH TIME ZONE,
    activated_at TIMESTAMP WITH TIME ZONE,
    converted_at TIMESTAMP WITH TIME ZONE,
    referrer_reward_paise BIGINT,
    referred_reward_paise BIGINT,
    referrer_reward_granted BOOLEAN DEFAULT FALSE,
    referred_reward_granted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(referrer_id, referred_user_id)
);

CREATE INDEX idx_referrals_referrer_id ON referrals(referrer_id);
CREATE INDEX idx_referrals_referred_user_id ON referrals(referred_user_id);
CREATE INDEX idx_referrals_status ON referrals(status);
CREATE INDEX idx_referrals_created_at ON referrals(created_at);

-- Referral rewards table
CREATE TABLE IF NOT EXISTS referral_rewards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_id UUID NOT NULL REFERENCES referrals(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    reward_type VARCHAR(50) NOT NULL,
    reward_value_paise BIGINT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    granted_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_referral_rewards_user_id ON referral_rewards(user_id);
CREATE INDEX idx_referral_rewards_referral_id ON referral_rewards(referral_id);
CREATE INDEX idx_referral_rewards_status ON referral_rewards(status);
CREATE INDEX idx_referral_rewards_expires_at ON referral_rewards(expires_at);

-- Comments
COMMENT ON TABLE referrers IS 'Stores referral codes and stats for users who refer others';
COMMENT ON TABLE referrals IS 'Tracks individual referral relationships and their status';
COMMENT ON TABLE referral_rewards IS 'Stores rewards granted for successful referrals';

COMMENT ON COLUMN referrers.referral_code IS 'Unique 8-character referral code for the user';
COMMENT ON COLUMN referrals.status IS 'pending, completed, cancelled';
COMMENT ON COLUMN referral_rewards.reward_type IS 'free_month, discount, credit';
COMMENT ON COLUMN referral_rewards.status IS 'pending, granted, expired';
