"""
Authentication and authorization module for MoveCRM
Implements JWT-based authentication with proper security measures
"""

import jwt
import bcrypt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import re
from typing import Optional, Dict, Any


class AuthenticationError(Exception):
    """Custom exception for authentication errors"""
    pass


class AuthorizationError(Exception):
    """Custom exception for authorization errors"""
    pass


from src.db import DatabaseManager # Import the new DatabaseManager

# Removed direct database connection function
# def get_db_connection():
#     """Get database connection"""
#     return psycopg2.connect(
#         host=os.getenv(\'DB_HOST\', \'localhost\'),
#         port=os.getenv(\'DB_PORT\', \'5432\'),
#         database=os.getenv(\'DB_NAME\', \'movecrm\'),
#         user=os.getenv(\'DB_USER\', \'movecrm\'),
#         password=os.getenv(\'DB_PASSWORD\', \'movecrm_password\')
#     )


def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password: str) -> bool:
    """Validate password strength"""
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'\d', password):
        return False
    return True


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def generate_jwt_token(user_id: str, tenant_id: str, role: str) -> str:
    """Generate JWT token for authenticated user"""
    payload = {
        'user_id': user_id,
        'tenant_id': tenant_id,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=24),
        'iat': datetime.utcnow()
    }
    
    secret_key = os.getenv('JWT_SECRET_KEY')
    if not secret_key:
        raise ValueError("JWT_SECRET_KEY environment variable not set")
    
    return jwt.encode(payload, secret_key, algorithm='HS256')


def decode_jwt_token(token: str) -> Dict[str, Any]:
    """Decode and validate JWT token"""
    secret_key = os.getenv('JWT_SECRET_KEY')
    if not secret_key:
        raise ValueError("JWT_SECRET_KEY environment variable not set")
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")


def authenticate_user(email: str, password: str, tenant_slug: str) -> Dict[str, Any]:
    """Authenticate user credentials"""
    if not validate_email(email):
        raise AuthenticationError("Invalid email format")
    
    if not email or not password or not tenant_slug:
        raise AuthenticationError("Email, password, and tenant are required")
    
    with DatabaseManager() as cursor:
        # Get tenant
        cursor.execute("SELECT id FROM tenants WHERE slug = %s AND is_active = true", (tenant_slug,))
        tenant = cursor.fetchone()
        if not tenant:
            raise AuthenticationError("Invalid tenant")
        
        # Get user
        cursor.execute("""
            SELECT id, email, password_hash, role, is_active 
            FROM users 
            WHERE email = %s AND tenant_id = %s
        """, (email, tenant[\"id\"]))
        
        user = cursor.fetchone()
        if not user:
            raise AuthenticationError("Invalid credentials")
        
        if not user[\"is_active\"]:
            raise AuthenticationError("Account is disabled")
        
        # Verify password
        if not verify_password(password, user[\"password_hash\"]):
            raise AuthenticationError("Invalid credentials")
        
        # Update last login
        cursor.execute("""
            UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s
        """, (user[\"id\"],))
        
        return {
            \"user_id\": str(user[\"id\"]),
            \"tenant_id\": str(tenant[\"id\"]),
            \"email\": user[\"email\"],
            \"role\": user[\"role\"]
        }


def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header:
            try:
                token = auth_header.split(' ')[1]  # Bearer <token>
            except IndexError:
                return jsonify({'error': 'Invalid authorization header format'}), 401
        
        if not token:
            return jsonify({'error': 'Authentication token required'}), 401
        
        try:
            payload = decode_jwt_token(token)
            request.current_user = payload
        except AuthenticationError as e:
            return jsonify({'error': str(e)}), 401
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_role(required_role: str):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            user_role = request.current_user.get('role')
            if user_role != required_role and user_role != 'admin':
                return jsonify({'error': 'Insufficient privileges'}), 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def get_tenant_from_request() -> Optional[str]:
    """Extract tenant ID from current request"""
    if hasattr(request, 'current_user'):
        return request.current_user.get('tenant_id')
    
    # Fallback to header-based tenant (for public endpoints)
    tenant_slug = request.headers.get('X-Tenant-Slug')
    if tenant_slug:
        with DatabaseManager() as cursor:
            cursor.execute("SELECT id FROM tenants WHERE slug = %s AND is_active = true", (tenant_slug,))
            tenant = cursor.fetchone()
            return str(tenant[\"id\"]) if tenant else None
    
    return None


def create_user(email: str, password: str, tenant_id: str, role: str = 'customer', 
                first_name: str = '', last_name: str = '', phone: str = '') -> str:
    """Create new user account"""
    if not validate_email(email):
        raise ValueError("Invalid email format")
    
    if not validate_password(password):
        raise ValueError("Password must be at least 8 characters with uppercase, lowercase, and number")
    
    if role not in ['admin', 'staff', 'customer']:
        raise ValueError("Invalid role")
    
    password_hash = hash_password(password)
    
    with DatabaseManager() as cursor:
        # Check if user already exists
        cursor.execute("""
            SELECT id FROM users WHERE email = %s AND tenant_id = %s
        """, (email, tenant_id))
        
        if cursor.fetchone():
            raise ValueError("User already exists")
        
        # Create user
        cursor.execute("""
            INSERT INTO users (tenant_id, email, password_hash, role, first_name, last_name, phone)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (tenant_id, email, password_hash, role, first_name, last_name, phone))
        
        user = cursor.fetchone()
        
        return str(user[\"id\"])

