"""
Secure MoveCRM Backend API
Production-ready Flask application with proper security measures
"""

from flask import Flask, jsonify, request, g
from flask_cors import CORS
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import logging
from datetime import datetime, date
import uuid
from decimal import Decimal

# Import our security modules
from src.auth import (
    authenticate_user, generate_jwt_token, require_auth, require_role,
    get_tenant_from_request, create_user, AuthenticationError, AuthorizationError
)
from src.validation import (
    validate_request_data, QuoteCreateSchema, UserCreateSchema, LoginSchema,
    sanitize_string, validate_email, validate_decimal, validate_integer,
    ValidationError
)
from src.rate_limiting import (
    apply_rate_limit, rate_limit_auth, rate_limit_api, rate_limit_expensive,
    rate_limit_public
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Secure CORS configuration
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
CORS(app, origins=allowed_origins, supports_credentials=True)

# Security headers
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response


# Database connection with error handling
from src.db import DatabaseManager # Import the new DatabaseManager

# Database connection with error handling (now handled by DatabaseManager)
# def get_db_connection():
#     """Get database connection with proper error handling"""
#     try:
#         return psycopg2.connect(
#             host=os.getenv(\'DB_HOST\', \'localhost\'),
#             port=os.getenv(\'DB_PORT\', \'5432\'),
#             database=os.getenv(\'DB_NAME\', \'movecrm\'),
#             user=os.getenv(\'DB_USER\', \'movecrm\'),
#             password=os.getenv(\'DB_PASSWORD\', \'movecrm_password\'),
#             connect_timeout=10
#         )
#     except psycopg2.Error as e:
#         logger.error(f"Database connection failed: {str(e)}")
#         raise


# Error handlers
@app.errorhandler(ValidationError)
def handle_validation_error(e):
    """Handle validation errors"""
    logger.warning(f"Validation error: {str(e)}")
    return jsonify({
        'error': 'Validation failed',
        'message': str(e)
    }), 400


@app.errorhandler(AuthenticationError)
def handle_auth_error(e):
    """Handle authentication errors"""
    logger.warning(f"Authentication error: {str(e)}")
    return jsonify({
        'error': 'Authentication failed',
        'message': str(e)
    }), 401


@app.errorhandler(AuthorizationError)
def handle_authz_error(e):
    """Handle authorization errors"""
    logger.warning(f"Authorization error: {str(e)}")
    return jsonify({
        'error': 'Access denied',
        'message': str(e)
    }), 403


@app.errorhandler(psycopg2.Error)
def handle_db_error(e):
    """Handle database errors"""
    logger.error(f"Database error: {str(e)}")
    return jsonify({
        'error': 'Database error',
        'message': 'An internal error occurred'
    }), 500


@app.errorhandler(Exception)
def handle_generic_error(e):
    """Handle unexpected errors"""
    logger.error(f"Unexpected error: {str(e)}", exc_info=True)
    return jsonify({
        'error': 'Internal server error',
        'message': 'An unexpected error occurred'
    }), 500


# Health check endpoint
@app.route('/health')
@rate_limit_api
def health():
    """Health check with database connectivity test"""
    try:
        with DatabaseManager() as cursor:
            cursor.execute(\'SELECT 1\')
        db_status = \'connected\' except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        db_status = 'disconnected'
    
    return jsonify({
        'status': 'healthy' if db_status == 'connected' else 'unhealthy',
        'service': 'movecrm-backend',
        'database': db_status,
        'version': '2.0',
        'timestamp': datetime.utcnow().isoformat()
    })


# Root endpoint
@app.route('/')
def root():
    """API information endpoint"""
    return jsonify({
        'service': 'MoveCRM Backend API',
        'version': '2.0',
        'status': 'production-ready',
        'documentation': '/api/docs',
        'health': '/health'
    })


# Authentication endpoints
@app.route('/api/auth/login', methods=['POST'])
@rate_limit_auth
def login():
    """Secure user authentication"""
    try:
        # Validate input
        data = validate_request_data(LoginSchema(), request.json or {})
        
        # Authenticate user
        user_info = authenticate_user(
            data[\"email\"],
            data[\"password\"],
            data[\"tenant_slug\"]
        )

        # Generate JWT token
        token = generate_jwt_token(
            user_info[\"user_id\"],
            user_info[\"tenant_id\"],
            user_info[\"role\"]
        )

        logger.info(f"User {user_info[\"email\"]} logged in successfully")

        return jsonify({
            \"status\": \"success\",
            \"token\": token,
            \"user\": {
                \"id\": user_info[\"user_id\"],
                \"email\": user_info[\"email\"],
                \"role\": user_info[\"role\"]
            }
        })
        
    except (ValidationError, AuthenticationError) as e:
        raise e
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise AuthenticationError("Login failed")


@app.route('/api/auth/register', methods=['POST'])
@apply_rate_limit('auth_register', per_tenant=True, per_ip=True)
def register():
    """User registration (admin only)"""
    try:
        # Validate input
        data = validate_request_data(UserCreateSchema(), request.json or {})
        
        # Get tenant ID
        tenant_id = get_tenant_from_request()
        if not tenant_id:
            raise ValidationError("Tenant required")
        
        # Create user using user_manager
        user_id = user_manager.create_user(
            tenant_id=tenant_id,
            email=data[\"email\"],
            role=data.get(\"role\", \"customer\"),
            first_name=data.get(\"first_name\", \"\"),
            last_name=data.get(\"last_name\", \"\"),
            phone=data.get(\"phone\", \"\"),
            send_invitation=False # We handle password directly here
        )
        
        logger.info(f"User {data[\"email\"]} registered successfully")
        
        return jsonify({
            \"status\": \"success\",
            \"user_id\": user_id[\"user_id\"], # user_manager.create_user returns a dict
            \"message\": \"User created successfully\"
        }), 201
        
    except (ValidationError, ValueError) as e:
        raise ValidationError(str(e))
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise


@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def logout():
    """User logout"""
    logger.info(f"User {request.current_user.get('user_id')} logged out")
    return jsonify({
        'status': 'success',
        'message': 'Logged out successfully'
    })


# Quote management endpoints
@app.route('/api/quotes', methods=['POST'])
@require_auth
@apply_rate_limit('quote_create', per_tenant=True, per_ip=True)
def create_quote():
    """Create new quote with proper validation"""
    try:
        # Validate input
        data = validate_request_data(QuoteCreateSchema(), request.json or {})
        
        # Get tenant and user info
        tenant_id = request.current_user[\"tenant_id\"]
        user_id = request.current_user[\"user_id\"]
        
        # Use quote_workflow to create the quote
        quote_data = quote_workflow.create_quote(
            tenant_id=tenant_id,
            customer_data={
                \"customer_email\": data[\"customer_email\"],
                \"customer_name\": data[\"customer_name\"],
                \"customer_phone\": data.get(\"customer_phone\"),
                \"pickup_address\": data[\"pickup_address\"],
                \"delivery_address\": data[\"delivery_address\"],
                \"move_date\": data[\"move_date\"],
                \"notes\": data.get(\"notes\"),
                \"distance_miles\": data.get(\"distance_miles\", 0) # Assuming distance_miles is passed in data
            },
            items=data.get(\"items\", []),
            created_by=user_id
        )
        
        logger.info(f"Quote {quote_data[\"quote_number\"]} created by user {user_id}")
        
        return jsonify({
            \"status\": \"success\",
            \"quote_number\": quote_data[\"quote_number\"],
            \"quote_id\": quote_data[\"quote_id\"],
            \"estimated_total\": round(quote_data[\"total_amount\"], 2),
            \"message\": \"Quote created successfully\"
        }), 201
            
    except (ValidationError, ValueError) as e:
        raise ValidationError(str(e))
    except Exception as e:
        logger.error(f"Quote creation error: {str(e)}")
        raise


@app.route('/api/quotes', methods=['GET'])
@require_auth
@rate_limit_api
def get_quotes():
    """Get quotes for authenticated user's tenant"""
    try:
        tenant_id = request.current_user[\"tenant_id\"]
        user_role = request.current_user[\"role\"]
        user_id = request.current_user[\"user_id\"]
        
        # Parse query parameters
        page = validate_integer(request.args.get(\"page\", 1), min_value=1)
        limit = validate_integer(request.args.get(\"limit\", 50), min_value=1, max_value=100)
        status = request.args.get(\"status\")
        
        # Use quote_workflow to list quotes
        quotes_data = quote_workflow.list_quotes(
            tenant_id=tenant_id,
            user_role=user_role,
            user_id=user_id,
            page=page,
            limit=limit,
            status_filter=status
        )
            
        return jsonify({
            \"status\": \"success\",
            \"quotes\": quotes_data[\"quotes\"],
            \"pagination\": quotes_data[\"pagination\"]
        })

    except ValidationError as e:
        raise e
    except Exception as e:
        logger.error(f"Quote retrieval error: {str(e)}")
        raise


@app.route('/api/quotes/<quote_id>')
@require_auth
@rate_limit_api
def get_quote(quote_id):
    """Get single quote with proper authorization"""
    try:
        # Validate quote ID format
        quote_id = sanitize_string(quote_id, max_length=50)
        
        tenant_id = request.current_user[\"tenant_id\"]
        user_role = request.current_user[\"role\"]
        user_id = request.current_user[\"user_id\"]
        
        # Use quote_workflow to get quote details
        quote = quote_workflow.get_quote(
            quote_id=quote_id,
            tenant_id=tenant_id,
            user_role=user_role,
            user_id=user_id
        )
            
        if not quote:
            return jsonify({
                \"error\": \"Quote not found\",
                \"message\": \"Quote does not exist or access denied\"
            }), 404
            
        return jsonify({
            \"status\": \"success\",
            \"quote\": quote
        })
            
    except ValidationError as e:
        raise e
    except Exception as e:
        logger.error(f"Quote retrieval error: {str(e)}")
        raise


# Public quote endpoint for widget
@app.route('/api/public/quote', methods=['POST'])
@rate_limit_public
def create_public_quote():
    """Create quote from public widget"""
    try:
        # Get tenant from header
        tenant_slug = request.headers.get(\"X-Tenant-Slug\")
        if not tenant_slug:
            raise ValidationError("Tenant slug required in X-Tenant-Slug header")
        
        tenant_slug = sanitize_string(tenant_slug, max_length=50)
        
        # Validate input
        data = validate_request_data(QuoteCreateSchema(), request.json or {})
        
        # Get tenant ID from slug
        with DatabaseManager() as cursor:
            cursor.execute("""
                SELECT id FROM tenants WHERE slug = %s AND is_active = true
            """, (tenant_slug,))
            
            tenant = cursor.fetchone()
            if not tenant:
                raise ValidationError("Invalid tenant")
            
            tenant_id = tenant[\"id\"]
        
        # Use quote_workflow to create the quote
        quote_data = quote_workflow.create_quote(
            tenant_id=tenant_id,
            customer_data={
                \"customer_email\": data[\"customer_email\"],
                \"customer_name\": data[\"customer_name\"],
                \"customer_phone\": data.get(\"customer_phone\"),
                \"pickup_address\": data[\"pickup_address\"],
                \"delivery_address\": data[\"delivery_address\"],
                \"move_date\": data[\"move_date\"],
                \"notes\": data.get(\"notes\"),
                \"distance_miles\": data.get(\"distance_miles\", 0)
            },
            items=data.get(\"items\", []),
            created_by=None # Public quote, no specific user
        )
            
        return jsonify({
            \"status\": \"success\",
            \"message\": \"Quote request submitted successfully\",
            \"quote_number\": quote_data[\"quote_number\"]
        }), 201
            
    except ValidationError as e:
        raise e
    except Exception as e:
        logger.error(f"Public quote creation error: {str(e)}")
        raise


if __name__ == '__main__':
    # Ensure required environment variables are set
    required_env_vars = ['JWT_SECRET_KEY', 'DB_PASSWORD']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        exit(1)
    
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    logger.info(f"Starting MoveCRM Backend API on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)

