-- MoveCRM MVP Database Schema
-- Multi-tenant PostgreSQL database design

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tenants table - core multi-tenancy
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255),
    logo_url TEXT,
    brand_colors JSONB DEFAULT '{}',
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Users table - staff and customers
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    supertokens_user_id VARCHAR(255) UNIQUE,
    email VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(20),
    role VARCHAR(50) DEFAULT 'customer', -- admin, staff, customer
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, email)
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
    is_default BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Quotes - main entity
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
    is_processed BOOLEAN DEFAULT false,
    yoloe_results JSONB,
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Rate limiting table
CREATE TABLE rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id),
    ip_address INET,
    endpoint VARCHAR(255) NOT NULL,
    request_count INTEGER DEFAULT 1,
    window_start TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, ip_address, endpoint, window_start)
);

-- Indexes for performance
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_supertokens_id ON users(supertokens_user_id);
CREATE INDEX idx_item_catalog_tenant_id ON item_catalog(tenant_id);
CREATE INDEX idx_pricing_rules_tenant_id ON pricing_rules(tenant_id);
CREATE INDEX idx_quotes_tenant_id ON quotes(tenant_id);
CREATE INDEX idx_quotes_customer_id ON quotes(customer_id);
CREATE INDEX idx_quotes_status ON quotes(status);
CREATE INDEX idx_quote_items_quote_id ON quote_items(quote_id);
CREATE INDEX idx_quote_media_quote_id ON quote_media(quote_id);
CREATE INDEX idx_detection_jobs_tenant_id ON detection_jobs(tenant_id);
CREATE INDEX idx_detection_jobs_status ON detection_jobs(status);
CREATE INDEX idx_rate_limits_tenant_ip ON rate_limits(tenant_id, ip_address);

-- Row Level Security (RLS) for multi-tenant isolation
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE item_catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE quote_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE quote_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE detection_jobs ENABLE ROW LEVEL SECURITY;

-- RLS Policies (to be implemented in application layer with tenant_id context)
-- These would be created dynamically based on the current tenant context

-- Trigger to update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_item_catalog_updated_at BEFORE UPDATE ON item_catalog FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_pricing_rules_updated_at BEFORE UPDATE ON pricing_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_quotes_updated_at BEFORE UPDATE ON quotes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Sample data for development
INSERT INTO tenants (slug, name, domain, brand_colors, settings) VALUES 
('demo', 'Demo Moving Company', 'demo.movecrm.com', '{"primary": "#2563eb", "secondary": "#64748b"}', '{"allow_customer_login": true}'),
('acme-movers', 'ACME Movers', 'acme.movecrm.com', '{"primary": "#dc2626", "secondary": "#374151"}', '{"allow_customer_login": false}');

-- Sample pricing rules
INSERT INTO pricing_rules (tenant_id, name, rate_per_cubic_foot, labor_rate_per_hour, minimum_charge, is_default) 
SELECT id, 'Standard Pricing', 1.50, 75.00, 150.00, true FROM tenants WHERE slug = 'demo';

INSERT INTO pricing_rules (tenant_id, name, rate_per_cubic_foot, labor_rate_per_hour, minimum_charge, is_default) 
SELECT id, 'Premium Pricing', 2.00, 95.00, 200.00, true FROM tenants WHERE slug = 'acme-movers';

-- Sample item catalog
INSERT INTO item_catalog (tenant_id, name, aliases, category, base_cubic_feet, labor_multiplier) 
SELECT t.id, 'Sofa', ARRAY['couch', 'sectional', 'loveseat'], 'Furniture', 35.0, 1.2 FROM tenants t WHERE t.slug = 'demo';

INSERT INTO item_catalog (tenant_id, name, aliases, category, base_cubic_feet, labor_multiplier) 
SELECT t.id, 'Dining Table', ARRAY['table', 'dining table', 'kitchen table'], 'Furniture', 25.0, 1.0 FROM tenants t WHERE t.slug = 'demo';

INSERT INTO item_catalog (tenant_id, name, aliases, category, base_cubic_feet, labor_multiplier) 
SELECT t.id, 'Refrigerator', ARRAY['fridge', 'refrigerator', 'freezer'], 'Appliances', 45.0, 1.5 FROM tenants t WHERE t.slug = 'demo';

INSERT INTO item_catalog (tenant_id, name, aliases, category, base_cubic_feet, labor_multiplier) 
SELECT t.id, 'Mattress', ARRAY['bed', 'mattress', 'queen bed', 'king bed'], 'Bedroom', 20.0, 0.8 FROM tenants t WHERE t.slug = 'demo';

