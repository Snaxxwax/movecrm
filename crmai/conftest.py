"""
Pytest configuration and fixtures for MoveCRM backend tests.
"""
import os
import sys
import pytest
from unittest.mock import Mock, patch
from flask import Flask
from faker import Faker

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from src.models import db, Tenant, User, ItemCatalog, PricingRule, Quote, QuoteItem
except ImportError:
    # Simplified models for testing
    from flask_sqlalchemy import SQLAlchemy
    import uuid
    from decimal import Decimal
    
    db = SQLAlchemy()
    
    class Tenant(db.Model):
        __tablename__ = 'tenants'
        id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
        slug = db.Column(db.String(50), unique=True, nullable=False)
        name = db.Column(db.String(255), nullable=False)
        domain = db.Column(db.String(255))
        is_active = db.Column(db.Boolean, default=True)
        
        def to_dict(self):
            return {
                'id': self.id,
                'slug': self.slug,
                'name': self.name,
                'domain': self.domain,
                'is_active': self.is_active
            }
    
    class User(db.Model):
        __tablename__ = 'users'
        id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
        tenant_id = db.Column(db.String(36), db.ForeignKey('tenants.id'), nullable=False)
        supertokens_user_id = db.Column(db.String(255))
        email = db.Column(db.String(255), nullable=False)
        first_name = db.Column(db.String(100))
        last_name = db.Column(db.String(100))
        phone = db.Column(db.String(20))
        role = db.Column(db.String(50), default='customer')
        is_active = db.Column(db.Boolean, default=True)
        
        def to_dict(self):
            return {
                'id': self.id,
                'tenant_id': self.tenant_id,
                'supertokens_user_id': self.supertokens_user_id,
                'email': self.email,
                'first_name': self.first_name,
                'last_name': self.last_name,
                'phone': self.phone,
                'role': self.role,
                'is_active': self.is_active
            }
from src.main import app as main_app


fake = Faker()


@pytest.fixture(scope=\'session\')
def app():
    """Create and configure a new app instance for each test session."""
    # Create test app with test configuration
    app = Flask(__name__)
    app.config.update({
        \'TESTING\': True,
        \'SECRET_KEY\': \'test-secret-key\',
        \'SQLALCHEMY_DATABASE_URI\': \'sqlite:///:memory:\',
        \'SQLALCHEMY_TRACK_MODIFICATIONS\': False,
        \'WTF_CSRF_ENABLED\': False,
        \'YOLOE_SERVICE_URL\': \'http://mock-yoloe:8001\',
        \'S3_BUCKET\': \'test-bucket\',
        \'S3_ACCESS_KEY\': \'test-access-key\',
        \'S3_SECRET_KEY\': \'test-secret-key\',
        \'S3_ENDPOINT\': \'http://mock-s3:9000\',
    })
    
    # Initialize database
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture(scope='function')
def app_context(app):
    """Create an application context."""
    with app.app_context():
        yield app


@pytest.fixture(scope='function')
def db_session(app_context):
    """Create a database session for testing."""
    db.create_all()
    yield db.session
    db.session.rollback()
    db.drop_all()


@pytest.fixture
def sample_tenant(db_session):
    """Create a sample tenant for testing."""
    tenant = Tenant(
        slug='test-company',
        name='Test Moving Company',
        domain='test-company.movecrm.com',
        brand_colors={'primary': '#007bff', 'secondary': '#6c757d'},
        settings={'timezone': 'UTC', 'currency': 'USD'},
        is_active=True
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


@pytest.fixture
def sample_user(db_session, sample_tenant):
    """Create a sample user for testing."""
    user = User(
        tenant_id=sample_tenant.id,
        supertokens_user_id='test-user-123',
        email='test@example.com',
        first_name='John',
        last_name='Doe',
        phone='+1234567890',
        role='admin',
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_customer(db_session, sample_tenant):
    """Create a sample customer for testing."""
    customer = User(
        tenant_id=sample_tenant.id,
        supertokens_user_id='customer-123',
        email='customer@example.com',
        first_name='Jane',
        last_name='Customer',
        phone='+1987654321',
        role='customer',
        is_active=True
    )
    db_session.add(customer)
    db_session.commit()
    return customer


@pytest.fixture
def sample_item_catalog(db_session, sample_tenant):
    """Create sample item catalog entries for testing."""
    items = [
        ItemCatalog(
            tenant_id=sample_tenant.id,
            name='Sofa',
            aliases=['Couch', 'Sectional'],
            category='Furniture',
            base_cubic_feet=35.5,
            labor_multiplier=1.2,
            is_active=True
        ),
        ItemCatalog(
            tenant_id=sample_tenant.id,
            name='Refrigerator',
            aliases=['Fridge', 'Freezer'],
            category='Appliances',
            base_cubic_feet=28.0,
            labor_multiplier=1.5,
            is_active=True
        )
    ]
    for item in items:
        db_session.add(item)
    db_session.commit()
    return items


@pytest.fixture
def sample_pricing_rule(db_session, sample_tenant):
    """Create a sample pricing rule for testing."""
    rule = PricingRule(
        tenant_id=sample_tenant.id,
        name='Standard Pricing',
        rate_per_cubic_foot=8.50,
        labor_rate_per_hour=85.00,
        minimum_charge=150.00,
        distance_rate_per_mile=2.50,
        is_default=True,
        is_active=True
    )
    db_session.add(rule)
    db_session.commit()
    return rule


@pytest.fixture
def sample_quote(db_session, sample_tenant, sample_customer, sample_pricing_rule):
    """Create a sample quote for testing."""
    quote = Quote(
        tenant_id=sample_tenant.id,
        customer_id=sample_customer.id,
        quote_number='Q-2024-0001',
        status='pending',
        customer_email=sample_customer.email,
        customer_phone=sample_customer.phone,
        customer_name=f"{sample_customer.first_name} {sample_customer.last_name}",
        pickup_address='123 Main St, City, State 12345',
        delivery_address='456 Oak Ave, Another City, State 67890',
        notes='Handle with care',
        total_cubic_feet=150.0,
        total_labor_hours=8.5,
        distance_miles=25.0,
        subtotal=1275.00,
        tax_amount=102.00,
        total_amount=1377.00,
        pricing_rule_id=sample_pricing_rule.id
    )
    db_session.add(quote)
    db_session.commit()
    return quote


@pytest.fixture
def auth_headers(sample_tenant):
    """Create authentication headers for API testing."""
    return {
        'X-Tenant-Slug': sample_tenant.slug,
        'Content-Type': 'application/json',
        'Authorization': 'Bearer fake-jwt-token'
    }


@pytest.fixture
def mock_supertokens():
    """Mock SuperTokens responses."""
    with patch('src.routes.auth.verify_session') as mock_session, \
         patch('src.routes.auth.get_user_by_id') as mock_get_user:
        
        mock_session_instance = Mock()
        mock_session_instance.get_user_id.return_value = 'test-user-123'
        mock_session.return_value = mock_session_instance
        
        mock_get_user.return_value = {
            'id': 'test-user-123',
            'email': 'test@example.com'
        }
        
        yield {
            'verify_session': mock_session,
            'get_user_by_id': mock_get_user,
            'session': mock_session_instance
        }


@pytest.fixture
def mock_yoloe_service():
    """Mock YOLOE service responses."""
    mock_response = {
        'job_id': 'test-job-123',
        'status': 'completed',
        'results': [
            {
                'item_name': 'sofa',
                'confidence': 0.95,
                'cubic_feet': 35.5,
                'quantity': 1
            },
            {
                'item_name': 'table',
                'confidence': 0.87,
                'cubic_feet': 12.0,
                'quantity': 1
            }
        ]
    }
    
    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response
        yield mock_post


# Utility functions for tests
def create_test_tenant(db_session, slug='test-tenant', name='Test Company'):
    """Utility function to create a test tenant."""
    tenant = Tenant(
        slug=slug,
        name=name,
        domain=f'{slug}.movecrm.com',
        is_active=True
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


def create_test_user(db_session, tenant, email='test@example.com', role='customer'):
    """Utility function to create a test user."""
    user = User(
        tenant_id=tenant.id,
        supertokens_user_id=f'user-{fake.uuid4()}',
        email=email,
        first_name=fake.first_name(),
        last_name=fake.last_name(),
        role=role,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    return user


class TestDataFactory:
    """Factory class for creating test data."""
    
    @staticmethod
    def create_tenant(db_session, **kwargs):
        defaults = {
            'slug': fake.slug(),
            'name': fake.company(),
            'domain': f'{fake.slug()}.movecrm.com',
            'is_active': True
        }
        defaults.update(kwargs)
        tenant = Tenant(**defaults)
        db_session.add(tenant)
        db_session.commit()
        return tenant
    
    @staticmethod
    def create_user(db_session, tenant, **kwargs):
        defaults = {
            'tenant_id': tenant.id,
            'supertokens_user_id': f'user-{fake.uuid4()}',
            'email': fake.email(),
            'first_name': fake.first_name(),
            'last_name': fake.last_name(),
            'role': 'customer',
            'is_active': True
        }
        defaults.update(kwargs)
        user = User(**defaults)
        db_session.add(user)
        db_session.commit()
        return user


@pytest.fixture
def test_data_factory():
    """Provide the TestDataFactory for creating test data."""
    return TestDataFactory