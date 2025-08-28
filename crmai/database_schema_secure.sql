-- MoveCRM Secure Database Schema
-- Multi-tenant PostgreSQL database design with security improvements

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tenants table - core multi-tenancy
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255),
    logo_url TEXT,
    brand_colors JSONB DEFAULT '{}',
    settings JSONB DEFAULT '{}',
    subscription_plan VARCHAR(50) DEFAULT 'basic',
    subscription_status VARCHAR(50) DEFAULT 'active',
    max_users INTEGER DEFAULT 10,
    max_quotes_per_month INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Users table - staff and customers with secure authentication
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    supertokens_user_id VARCHAR(255) UNIQUE,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255), -- bcrypt hash
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(20),
    role VARCHAR(50) DEFAULT 'customer', -- admin, staff, customer
    permissions JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT true,
    email_verified BOOLEAN DEFAULT false,
    last_login TIMESTAMP WITH TIME ZONE,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    password_reset_token VARCHAR(255),
    password_reset_expires TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, email)
);

-- API Keys table for programmatic access
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,
    permissions JSONB DEFAULT '[]',
    last_used TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Audit log for security tracking
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id UUID,
    ip_address INET,
    user_agent TEXT,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Item catalog - predefined moving items
CREATE TABLE item_catalog (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    aliases TEXT[], -- for YOLOE detection mapping
    category VARCHAR(100),
    base_cubic_feet DECIMAL(8,2),
    labor_multiplier DECIMAL(4,2) DEFAULT 1.0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Pricing rules per tenant
CREATE TABLE pricing_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    rate_per_cubic_foot DECIMAL(8,2) NOT NULL,
    labor_rate_per_hour DECIMAL(8,2) NOT NULL,
    minimum_charge DECIMAL(8,2) DEFAULT 0,
    distance_rate_per_mile DECIMAL(8,2) DEFAULT 0,
    tax_rate DECIMAL(4,4) DEFAULT 0.08,
    is_default BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Quotes - main entity with enhanced security
CREATE TABLE quotes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES users(id),
    quote_number VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- pending, approved, rejected, expired
    customer_email VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(20),
    customer_name VARCHAR(255),
    pickup_address TEXT,
    delivery_address TEXT,
    move_date DATE,
    notes TEXT,
    total_cubic_feet DECIMAL(10,2) DEFAULT 0,
    total_labor_hours DECIMAL(6,2) DEFAULT 0,
    distance_miles DECIMAL(8,2) DEFAULT 0,
    subtotal DECIMAL(10,2) DEFAULT 0,
    tax_amount DECIMAL(10,2) DEFAULT 0,
    total_amount DECIMAL(10,2) DEFAULT 0,
    pricing_rule_id UUID REFERENCES pricing_rules(id),
    expires_at TIMESTAMP WITH TIME ZONE,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP WITH TIME ZONE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Quote items - detected items in quotes
CREATE TABLE quote_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    quote_id UUID NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    item_catalog_id UUID REFERENCES item_catalog(id),
    detected_name VARCHAR(255),
    quantity INTEGER DEFAULT 1,
    cubic_feet DECIMAL(8,2),
    labor_hours DECIMAL(6,2),
    unit_price DECIMAL(8,2),
    total_price DECIMAL(8,2),
    confidence_score DECIMAL(4,3), -- YOLOE detection confidence
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Media files - images/videos uploaded with quotes
CREATE TABLE quote_media (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    quote_id UUID NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR(100),
    file_hash VARCHAR(64), -- SHA-256 hash for integrity
    is_processed BOOLEAN DEFAULT false,
    yoloe_results JSONB,
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- YOLOE detection jobs
CREATE TABLE detection_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    quote_id UUID REFERENCES quotes(id),
    media_ids UUID[],
    job_type VARCHAR(50) NOT NULL, -- 'auto' or 'text'
    prompt TEXT, -- for text-based detection
    status VARCHAR(50) DEFAULT 'pending', -- pending, processing, completed, failed
    runpod_job_id VARCHAR(255),
    results JSONB,
    error_message TEXT,
    processing_time_seconds INTEGER,
    cost_cents INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Enhanced rate limiting table
CREATE TABLE rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id),
    user_id UUID REFERENCES users(id),
    identifier VARCHAR(255) NOT NULL, -- IP, tenant, or user identifier
    endpoint VARCHAR(255) NOT NULL,
    request_count INTEGER DEFAULT 1,
    window_start TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identifier, endpoint, window_start)
);

-- Session management for enhanced security
CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    ip_address INET,
    user_agent TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Email templates for notifications
CREATE TABLE email_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    template_type VARCHAR(100) NOT NULL, -- quote_created, quote_approved, etc.
    subject VARCHAR(255) NOT NULL,
    html_content TEXT NOT NULL,
    text_content TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, template_type)
);

-- Indexes for performance
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_supertokens_id ON users(supertokens_user_id);
CREATE INDEX idx_api_keys_tenant_id ON api_keys(tenant_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_audit_logs_tenant_id ON audit_logs(tenant_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX idx_item_catalog_tenant_id ON item_catalog(tenant_id);
CREATE INDEX idx_pricing_rules_tenant_id ON pricing_rules(tenant_id);
CREATE INDEX idx_quotes_tenant_id ON quotes(tenant_id);
CREATE INDEX idx_quotes_customer_id ON quotes(customer_id);
CREATE INDEX idx_quotes_status ON quotes(status);
CREATE INDEX idx_quotes_created_at ON quotes(created_at);
CREATE INDEX idx_quote_items_quote_id ON quote_items(quote_id);
CREATE INDEX idx_quote_media_quote_id ON quote_media(quote_id);
CREATE INDEX idx_detection_jobs_tenant_id ON detection_jobs(tenant_id);
CREATE INDEX idx_detection_jobs_status ON detection_jobs(status);
CREATE INDEX idx_rate_limits_identifier ON rate_limits(identifier, endpoint);
CREATE INDEX idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX idx_user_sessions_token ON user_sessions(session_token);

-- Row Level Security (RLS) for multi-tenant isolation
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE item_catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE quote_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE quote_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE detection_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_templates ENABLE ROW LEVEL SECURITY;

-- RLS Policies for tenant isolation
CREATE POLICY tenant_isolation_users ON users
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation_quotes ON quotes
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Add more RLS policies as needed...

-- Functions for security
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Function to log audit events
CREATE OR REPLACE FUNCTION log_audit_event(
    p_tenant_id UUID,
    p_user_id UUID,
    p_action VARCHAR,
    p_resource_type VARCHAR DEFAULT NULL,
    p_resource_id UUID DEFAULT NULL,
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL,
    p_details JSONB DEFAULT '{}'
)
RETURNS UUID AS $$
DECLARE
    audit_id UUID;
BEGIN
    INSERT INTO audit_logs (
        tenant_id, user_id, action, resource_type, resource_id,
        ip_address, user_agent, details
    ) VALUES (
        p_tenant_id, p_user_id, p_action, p_resource_type, p_resource_id,
        p_ip_address, p_user_agent, p_details
    ) RETURNING id INTO audit_id;
    
    RETURN audit_id;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at timestamps
CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_item_catalog_updated_at BEFORE UPDATE ON item_catalog FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_pricing_rules_updated_at BEFORE UPDATE ON pricing_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_quotes_updated_at BEFORE UPDATE ON quotes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_email_templates_updated_at BEFORE UPDATE ON email_templates FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Sample data for development (with secure passwords)
INSERT INTO tenants (slug, name, domain, brand_colors, settings, subscription_plan) VALUES 
('demo', 'Demo Moving Company', 'demo.movecrm.com', '{"primary": "#2563eb", "secondary": "#64748b"}', '{"allow_customer_login": true}', 'premium'),
('acme-movers', 'ACME Movers', 'acme.movecrm.com', '{"primary": "#dc2626", "secondary": "#374151"}', '{"allow_customer_login": false}', 'basic');

-- Sample admin users (passwords should be hashed in application)
-- Password: 'AdminPass123!' (hash would be generated by bcrypt)
INSERT INTO users (tenant_id, email, password_hash, first_name, last_name, role, is_active, email_verified) 
SELECT id, 'admin@demo.movecrm.com', '$2b$12$example_hash_here', 'Demo', 'Admin', 'admin', true, true 
FROM tenants WHERE slug = 'demo';

-- Sample pricing rules
INSERT INTO pricing_rules (tenant_id, name, rate_per_cubic_foot, labor_rate_per_hour, minimum_charge, tax_rate, is_default) 
SELECT id, 'Standard Pricing', 1.50, 75.00, 150.00, 0.08, true FROM tenants WHERE slug = 'demo';

INSERT INTO pricing_rules (tenant_id, name, rate_per_cubic_foot, labor_rate_per_hour, minimum_charge, tax_rate, is_default) 
SELECT id, 'Premium Pricing', 2.00, 95.00, 200.00, 0.08, true FROM tenants WHERE slug = 'acme-movers';

-- Sample item catalog
INSERT INTO item_catalog (tenant_id, name, aliases, category, base_cubic_feet, labor_multiplier) 
SELECT t.id, 'Sofa', ARRAY['couch', 'sectional', 'loveseat'], 'Furniture', 35.0, 1.2 FROM tenants t WHERE t.slug = 'demo';

INSERT INTO item_catalog (tenant_id, name, aliases, category, base_cubic_feet, labor_multiplier) 
SELECT t.id, 'Dining Table', ARRAY['table', 'dining table', 'kitchen table'], 'Furniture', 25.0, 1.0 FROM tenants t WHERE t.slug = 'demo';

INSERT INTO item_catalog (tenant_id, name, aliases, category, base_cubic_feet, labor_multiplier) 
SELECT t.id, 'Refrigerator', ARRAY['fridge', 'refrigerator', 'freezer'], 'Appliances', 45.0, 1.5 FROM tenants t WHERE t.slug = 'demo';

-- Sample email templates
INSERT INTO email_templates (tenant_id, template_type, subject, html_content, text_content)
SELECT t.id, 'quote_created', 'Your Moving Quote #{quote_number}', 
'<h1>Thank you for your quote request!</h1><p>Your quote #{quote_number} has been created and is being reviewed.</p>',
'Thank you for your quote request! Your quote #{quote_number} has been created and is being reviewed.'
FROM tenants t WHERE t.slug = 'demo';

