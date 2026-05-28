-- Migration: Create affiliate program tables
-- Task: 30.1 - Implement affiliate dashboard backend
-- Requirements: 12.7, 12.8
-- Description: Tables for affiliate registration, tracking, commissions, and payouts

-- Affiliates table
CREATE TABLE IF NOT EXISTS affiliates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE,  -- Optional: link to user account if affiliate is also a user
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    affiliate_code VARCHAR(20) NOT NULL UNIQUE,
    commission_rate DECIMAL(5,2) DEFAULT 20.00,  -- Default 20%
    status VARCHAR(20) DEFAULT 'pending',  -- pending, active, suspended, inactive
    payment_method VARCHAR(50),  -- bank_transfer, paypal, upi
    payment_details JSONB DEFAULT '{}',  -- Bank account, PayPal email, UPI ID, etc.
    total_clicks INTEGER DEFAULT 0,
    total_signups INTEGER DEFAULT 0,
    total_conversions INTEGER DEFAULT 0,
    total_commission_paise BIGINT DEFAULT 0,
    pending_commission_paise BIGINT DEFAULT 0,
    paid_commission_paise BIGINT DEFAULT 0,
    notes TEXT,
    approved_at TIMESTAMP WITH TIME ZONE,
    approved_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_affiliates_user_id ON affiliates(user_id);
CREATE INDEX idx_affiliates_email ON affiliates(email);
CREATE INDEX idx_affiliates_code ON affiliates(affiliate_code);
CREATE INDEX idx_affiliates_status ON affiliates(status);
CREATE INDEX idx_affiliates_created_at ON affiliates(created_at);

-- Affiliate clicks table (for tracking link clicks)
CREATE TABLE IF NOT EXISTS affiliate_clicks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    affiliate_id UUID NOT NULL REFERENCES affiliates(id) ON DELETE CASCADE,
    visitor_id VARCHAR(255),  -- Anonymous visitor tracking ID
    ip_address INET,
    user_agent TEXT,
    referrer_url TEXT,
    landing_page TEXT,
    utm_params JSONB DEFAULT '{}',
    clicked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_affiliate_clicks_affiliate_id ON affiliate_clicks(affiliate_id);
CREATE INDEX idx_affiliate_clicks_visitor_id ON affiliate_clicks(visitor_id);
CREATE INDEX idx_affiliate_clicks_clicked_at ON affiliate_clicks(clicked_at);

-- Affiliate conversions table (tracks referred users)
CREATE TABLE IF NOT EXISTS affiliate_conversions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    affiliate_id UUID NOT NULL REFERENCES affiliates(id) ON DELETE CASCADE,
    referred_user_id UUID NOT NULL,
    subscription_id UUID,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, active, cancelled, completed
    signup_at TIMESTAMP WITH TIME ZONE,
    first_payment_at TIMESTAMP WITH TIME ZONE,
    cancelled_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,  -- After 12 months
    total_commission_paise BIGINT DEFAULT 0,
    paid_commission_paise BIGINT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(affiliate_id, referred_user_id)
);

CREATE INDEX idx_affiliate_conversions_affiliate_id ON affiliate_conversions(affiliate_id);
CREATE INDEX idx_affiliate_conversions_referred_user_id ON affiliate_conversions(referred_user_id);
CREATE INDEX idx_affiliate_conversions_subscription_id ON affiliate_conversions(subscription_id);
CREATE INDEX idx_affiliate_conversions_status ON affiliate_conversions(status);
CREATE INDEX idx_affiliate_conversions_created_at ON affiliate_conversions(created_at);

-- Affiliate commissions table (tracks individual commission payments)
CREATE TABLE IF NOT EXISTS affiliate_commissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    affiliate_id UUID NOT NULL REFERENCES affiliates(id) ON DELETE CASCADE,
    conversion_id UUID NOT NULL REFERENCES affiliate_conversions(id) ON DELETE CASCADE,
    referred_user_id UUID NOT NULL,
    subscription_id UUID NOT NULL,
    payment_id VARCHAR(255),  -- Stripe/Razorpay payment ID
    commission_amount_paise BIGINT NOT NULL,
    commission_rate DECIMAL(5,2) NOT NULL,
    subscription_amount_paise BIGINT NOT NULL,
    period INTEGER NOT NULL,  -- 1-12 (month number)
    status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, paid, cancelled
    payment_date TIMESTAMP WITH TIME ZONE,
    payout_id UUID,  -- Reference to payout batch
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_affiliate_commissions_affiliate_id ON affiliate_commissions(affiliate_id);
CREATE INDEX idx_affiliate_commissions_conversion_id ON affiliate_commissions(conversion_id);
CREATE INDEX idx_affiliate_commissions_referred_user_id ON affiliate_commissions(referred_user_id);
CREATE INDEX idx_affiliate_commissions_subscription_id ON affiliate_commissions(subscription_id);
CREATE INDEX idx_affiliate_commissions_status ON affiliate_commissions(status);
CREATE INDEX idx_affiliate_commissions_period ON affiliate_commissions(period);
CREATE INDEX idx_affiliate_commissions_payment_date ON affiliate_commissions(payment_date);
CREATE INDEX idx_affiliate_commissions_payout_id ON affiliate_commissions(payout_id);
CREATE INDEX idx_affiliate_commissions_created_at ON affiliate_commissions(created_at);

-- Affiliate payouts table (batch payouts)
CREATE TABLE IF NOT EXISTS affiliate_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    affiliate_id UUID NOT NULL REFERENCES affiliates(id) ON DELETE CASCADE,
    amount_paise BIGINT NOT NULL,
    commission_count INTEGER NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    payment_reference VARCHAR(255),  -- Transaction ID, UTR, etc.
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    scheduled_date DATE,
    processed_at TIMESTAMP WITH TIME ZONE,
    processed_by UUID,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_affiliate_payouts_affiliate_id ON affiliate_payouts(affiliate_id);
CREATE INDEX idx_affiliate_payouts_status ON affiliate_payouts(status);
CREATE INDEX idx_affiliate_payouts_scheduled_date ON affiliate_payouts(scheduled_date);
CREATE INDEX idx_affiliate_payouts_processed_at ON affiliate_payouts(processed_at);
CREATE INDEX idx_affiliate_payouts_created_at ON affiliate_payouts(created_at);

-- Affiliate resources table (marketing materials)
CREATE TABLE IF NOT EXISTS affiliate_resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    resource_type VARCHAR(50) NOT NULL,  -- banner, email_template, social_copy, screenshot, video
    file_url TEXT,
    thumbnail_url TEXT,
    dimensions VARCHAR(50),  -- For banners: 728x90, 300x250, etc.
    format VARCHAR(20),  -- jpg, png, html, txt
    download_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_affiliate_resources_resource_type ON affiliate_resources(resource_type);
CREATE INDEX idx_affiliate_resources_status ON affiliate_resources(status);

-- Comments
COMMENT ON TABLE affiliates IS 'Stores affiliate partner information and stats';
COMMENT ON TABLE affiliate_clicks IS 'Tracks clicks on affiliate links';
COMMENT ON TABLE affiliate_conversions IS 'Tracks referred users and their subscription status';
COMMENT ON TABLE affiliate_commissions IS 'Individual commission records for each subscription payment (12 months)';
COMMENT ON TABLE affiliate_payouts IS 'Batch payout records to affiliates';
COMMENT ON TABLE affiliate_resources IS 'Marketing materials available for affiliates';

COMMENT ON COLUMN affiliates.commission_rate IS 'Commission percentage (default 20%)';
COMMENT ON COLUMN affiliates.status IS 'pending (awaiting approval), active, suspended, inactive';
COMMENT ON COLUMN affiliate_commissions.period IS 'Month number (1-12) for recurring commission tracking';
COMMENT ON COLUMN affiliate_commissions.status IS 'pending (awaiting approval), approved (ready for payout), paid, cancelled';

