-- Migration: Create leads and email subscribers tables
-- Task: 9.1 - Create lead capture backend endpoint
-- Requirements: 5.2, 5.9
-- Description: Tables for lead magnets, leads, and email subscribers

-- Lead magnets table
CREATE TABLE IF NOT EXISTS lead_magnets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(255) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    type VARCHAR(50) NOT NULL, -- 'pdf', 'excel', 'calculator', 'guide'
    download_url TEXT NOT NULL,
    thumbnail_url TEXT,
    landing_page_url TEXT,
    status VARCHAR(20) DEFAULT 'active',
    downloads_count INTEGER DEFAULT 0,
    conversion_rate DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_lead_magnets_slug ON lead_magnets(slug);
CREATE INDEX idx_lead_magnets_type ON lead_magnets(type);
CREATE INDEX idx_lead_magnets_status ON lead_magnets(status);

-- Leads table
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    source VARCHAR(100) NOT NULL, -- 'popup', 'inline', 'footer', 'lead_magnet'
    sources TEXT[], -- Array of all sources
    lead_magnet_id UUID REFERENCES lead_magnets(id),
    page_url TEXT,
    utm_params JSONB,
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'unsubscribed', 'bounced'
    converted_to_user BOOLEAN DEFAULT FALSE,
    user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_leads_email ON leads(email);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_source ON leads(source);
CREATE INDEX idx_leads_lead_magnet_id ON leads(lead_magnet_id);
CREATE INDEX idx_leads_created_at ON leads(created_at);
CREATE INDEX idx_leads_converted ON leads(converted_to_user);

-- Email subscribers table
CREATE TABLE IF NOT EXISTS email_subscribers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    source VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'unsubscribed', 'bounced'
    preferences JSONB DEFAULT '{}',
    subscribed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    unsubscribed_at TIMESTAMP WITH TIME ZONE,
    resubscribed_at TIMESTAMP WITH TIME ZONE,
    last_email_sent_at TIMESTAMP WITH TIME ZONE,
    email_open_count INTEGER DEFAULT 0,
    email_click_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_email_subscribers_email ON email_subscribers(email);
CREATE INDEX idx_email_subscribers_status ON email_subscribers(status);
CREATE INDEX idx_email_subscribers_source ON email_subscribers(source);
CREATE INDEX idx_email_subscribers_subscribed_at ON email_subscribers(subscribed_at);

-- Comments
COMMENT ON TABLE lead_magnets IS 'Stores lead magnet resources (PDFs, calculators, guides)';
COMMENT ON TABLE leads IS 'Stores captured leads with source attribution';
COMMENT ON TABLE email_subscribers IS 'Stores email newsletter subscribers';

COMMENT ON COLUMN leads.sources IS 'Array of all sources where this lead was captured';
COMMENT ON COLUMN leads.utm_params IS 'UTM parameters from first capture';
COMMENT ON COLUMN email_subscribers.preferences IS 'Email preference settings (frequency, content types)';
