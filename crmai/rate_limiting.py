"""
Rate limiting module for MoveCRM
Implements per-tenant and per-IP rate limiting to prevent abuse
"""

import time
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import os
import json
from typing import Dict, Optional, Tuple


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded"""
    pass


from src.db import DatabaseManager # Import the new DatabaseManager

class RateLimiter:
    """Rate limiter using Redis for fast lookups and PostgreSQL for persistence"""
    
    def __init__(self):
        self.redis_client = self._get_redis_client()
        
    def _get_redis_client(self):
        """Get Redis client"""
        redis_url = os.getenv(\'REDIS_URL\', \'redis://localhost:6379/0\')
        return redis.from_url(redis_url, decode_responses=True)
    
    # Removed _get_db_connection as DatabaseManager is used directly
    # def _get_db_connection(self):
    #     """Get database connection"""
    #     return psycopg2.connect(
    #         host=os.getenv(\'DB_HOST\', \'localhost\'),
    #         port=os.getenv(\'DB_PORT\', \'5432\'),
    #         database=os.getenv(\'DB_NAME\', \'movecrm\'),
    #         user=os.getenv(\'DB_USER\', \'movecrm\'),
    #         password=os.getenv(\'DB_PASSWORD\', \'movecrm_password\')
    #     )
    def _get_client_ip(self) -> str:
        """Get client IP address"""
        # Check for forwarded IP first (behind proxy/load balancer)
        forwarded_ip = request.headers.get('X-Forwarded-For')
        if forwarded_ip:
            return forwarded_ip.split(',')[0].strip()
        
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip
        
        return request.remote_addr or '127.0.0.1'
    
    def _get_rate_limit_key(self, identifier: str, endpoint: str, window_minutes: int) -> str:
        """Generate Redis key for rate limiting"""
        window_start = int(time.time() // (window_minutes * 60))
        return f"rate_limit:{identifier}:{endpoint}:{window_start}"
    
    def check_rate_limit(self, identifier: str, endpoint: str, limit: int, 
                        window_minutes: int = 1) -> Tuple[bool, Dict[str, int]]:
        """
        Check if request is within rate limit
        Returns (is_allowed, rate_limit_info)
        """
        key = self._get_rate_limit_key(identifier, endpoint, window_minutes)
        
        try:
            # Get current count from Redis
            current_count = self.redis_client.get(key)
            current_count = int(current_count) if current_count else 0
            
            # Check if limit exceeded
            if current_count >= limit:
                return False, {
                    'limit': limit,
                    'remaining': 0,
                    'reset_time': int(time.time() + (window_minutes * 60)),
                    'window_minutes': window_minutes
                }
            
            # Increment counter
            pipe = self.redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_minutes * 60)
            pipe.execute()
            
            remaining = limit - (current_count + 1)
            
            return True, {
                'limit': limit,
                'remaining': remaining,
                'reset_time': int(time.time() + (window_minutes * 60)),
                'window_minutes': window_minutes
            }
            
        except redis.RedisError:
            # Fallback to database if Redis is unavailable
            return self._check_rate_limit_db(identifier, endpoint, limit, window_minutes)
    
    def _check_rate_limit_db(self, identifier: str, endpoint: str, limit: int, 
                           window_minutes: int) -> Tuple[bool, Dict[str, int]]:
        """Fallback rate limiting using database"""
        with DatabaseManager() as cursor:
            window_start = datetime.utcnow() - timedelta(minutes=window_minutes)
            
            # Get current count
            cursor.execute("""
                SELECT COUNT(*) as count FROM rate_limits 
                WHERE identifier = %s AND endpoint = %s AND created_at > %s
            """, (identifier, endpoint, window_start))
            
            result = cursor.fetchone()
            current_count = result[\"count\"] if result else 0
            
            if current_count >= limit:
                return False, {
                    \"limit\": limit,
                    \"remaining\": 0,
                    \"reset_time\": int(time.time() + (window_minutes * 60)),
                    \"window_minutes\": window_minutes
                }
            
            # Record this request
            cursor.execute("""
                INSERT INTO rate_limits (identifier, endpoint, created_at)
                VALUES (%s, %s, %s)
            """, (identifier, endpoint, datetime.utcnow()))
            
            remaining = limit - (current_count + 1)
            
            return True, {
                \"limit\": limit,
                \"remaining\": remaining,
                \"reset_time\": int(time.time() + (window_minutes * 60)),
                \"window_minutes\": window_minutes
            }
    
    def cleanup_old_records(self, days_old: int = 7):
        """Clean up old rate limit records from database"""
        with DatabaseManager() as cursor:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            cursor.execute("""
                DELETE FROM rate_limits WHERE created_at < %s
            """, (cutoff_date,))


# Global rate limiter instance
rate_limiter = RateLimiter()


# Rate limiting configurations
RATE_LIMITS = {
    'default': {'limit': 100, 'window': 1},  # 100 requests per minute
    'auth_login': {'limit': 5, 'window': 5},  # 5 login attempts per 5 minutes
    'auth_register': {'limit': 3, 'window': 60},  # 3 registrations per hour
    'quote_create': {'limit': 10, 'window': 1},  # 10 quotes per minute
    'quote_list': {'limit': 50, 'window': 1},  # 50 list requests per minute
    'file_upload': {'limit': 20, 'window': 5},  # 20 uploads per 5 minutes
    'ai_detection': {'limit': 5, 'window': 1},  # 5 AI requests per minute (expensive)
    'public_quote': {'limit': 20, 'window': 5},  # 20 public quotes per 5 minutes
}


def get_rate_limit_config(endpoint: str) -> Dict[str, int]:
    """Get rate limit configuration for endpoint"""
    return RATE_LIMITS.get(endpoint, RATE_LIMITS['default'])


def apply_rate_limit(endpoint: str, per_tenant: bool = True, per_ip: bool = True):
    """
    Decorator to apply rate limiting to endpoints
    
    Args:
        endpoint: Endpoint identifier for rate limiting
        per_tenant: Apply rate limiting per tenant
        per_ip: Apply rate limiting per IP address
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            config = get_rate_limit_config(endpoint)
            limit = config['limit']
            window = config['window']
            
            # Check IP-based rate limiting
            if per_ip:
                client_ip = rate_limiter._get_client_ip()
                ip_identifier = f"ip:{client_ip}"
                
                allowed, rate_info = rate_limiter.check_rate_limit(
                    ip_identifier, endpoint, limit, window
                )
                
                if not allowed:
                    response = jsonify({
                        'error': 'Rate limit exceeded',
                        'message': f'Too many requests from IP {client_ip}',
                        'rate_limit': rate_info
                    })
                    response.status_code = 429
                    response.headers['X-RateLimit-Limit'] = str(rate_info['limit'])
                    response.headers['X-RateLimit-Remaining'] = str(rate_info['remaining'])
                    response.headers['X-RateLimit-Reset'] = str(rate_info['reset_time'])
                    response.headers['Retry-After'] = str(window * 60)
                    return response
            
            # Check tenant-based rate limiting
            if per_tenant:
                tenant_id = None
                
                # Get tenant from authenticated user
                if hasattr(request, 'current_user'):
                    tenant_id = request.current_user.get('tenant_id')
                
                # Fallback to header for public endpoints
                if not tenant_id:
                    tenant_slug = request.headers.get('X-Tenant-Slug')
                    if tenant_slug:
                        # Get tenant ID from slug (simplified for rate limiting)
                        tenant_id = f"slug:{tenant_slug}"
                
                if tenant_id:
                    tenant_identifier = f"tenant:{tenant_id}"
                    
                    allowed, rate_info = rate_limiter.check_rate_limit(
                        tenant_identifier, endpoint, limit * 10, window  # Higher limit for tenants
                    )
                    
                    if not allowed:
                        response = jsonify({
                            'error': 'Rate limit exceeded',
                            'message': 'Too many requests from your organization',
                            'rate_limit': rate_info
                        })
                        response.status_code = 429
                        response.headers['X-RateLimit-Limit'] = str(rate_info['limit'])
                        response.headers['X-RateLimit-Remaining'] = str(rate_info['remaining'])
                        response.headers['X-RateLimit-Reset'] = str(rate_info['reset_time'])
                        response.headers['Retry-After'] = str(window * 60)
                        return response
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def rate_limit_headers(response, rate_info: Dict[str, int]):
    """Add rate limit headers to response"""
    response.headers['X-RateLimit-Limit'] = str(rate_info['limit'])
    response.headers['X-RateLimit-Remaining'] = str(rate_info['remaining'])
    response.headers['X-RateLimit-Reset'] = str(rate_info['reset_time'])
    return response


# Convenience decorators for common endpoints
def rate_limit_auth(f):
    """Rate limit for authentication endpoints"""
    return apply_rate_limit('auth_login', per_tenant=False, per_ip=True)(f)


def rate_limit_api(f):
    """Rate limit for general API endpoints"""
    return apply_rate_limit('default', per_tenant=True, per_ip=True)(f)


def rate_limit_expensive(f):
    """Rate limit for expensive operations (AI, file uploads)"""
    return apply_rate_limit('ai_detection', per_tenant=True, per_ip=True)(f)


def rate_limit_public(f):
    """Rate limit for public endpoints"""
    return apply_rate_limit('public_quote', per_tenant=True, per_ip=True)(f)

