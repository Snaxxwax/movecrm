"""
User Management Module for MoveCRM
Provides comprehensive user management and role-based access control
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from flask import request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

from .auth import hash_password, validate_email, validate_password, get_db_connection
from .validation import sanitize_string, validate_integer, ValidationError


class UserManager:
    """Comprehensive user management system"""
    
    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.smtp_from_email = os.getenv('SMTP_FROM_EMAIL')
    
    def create_user(self, tenant_id: str, email: str, role: str = 'customer',
                   first_name: str = '', last_name: str = '', phone: str = '',
                   send_invitation: bool = True, created_by: str = None) -> Dict[str, Any]:
        """Create new user with invitation email"""
        
        if not validate_email(email):
            raise ValidationError("Invalid email format")
        
        if role not in ['admin', 'staff', 'customer']:
            raise ValidationError("Invalid role")
        
        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)
        password_hash = hash_password(temp_password)
        
        # Generate password reset token
        reset_token = secrets.token_urlsafe(32)
        reset_expires = datetime.utcnow() + timedelta(hours=24)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Check if user already exists
            cursor.execute("""
                SELECT id FROM users WHERE email = %s AND tenant_id = %s
            """, (email, tenant_id))
            
            if cursor.fetchone():
                raise ValidationError("User already exists")
            
            # Create user
            cursor.execute("""
                INSERT INTO users (
                    tenant_id, email, password_hash, first_name, last_name, 
                    phone, role, password_reset_token, password_reset_expires
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, email, role
            """, (
                tenant_id, email, password_hash, first_name, last_name,
                phone, role, reset_token, reset_expires
            ))
            
            user = cursor.fetchone()
            user_id = user['id']
            
            # Log audit event
            cursor.execute("""
                SELECT log_audit_event(%s, %s, 'user_created', 'user', %s, %s, %s, %s)
            """, (
                tenant_id, created_by, user_id,
                request.remote_addr if request else None,
                request.headers.get('User-Agent') if request else None,
                psycopg2.extras.Json({'email': email, 'role': role})
            ))
            
            conn.commit()
            
            # Send invitation email
            if send_invitation and self.smtp_host:
                self._send_invitation_email(
                    email, first_name, temp_password, reset_token, tenant_id
                )
            
            return {
                'user_id': str(user_id),
                'email': email,
                'role': role,
                'temporary_password': temp_password if not send_invitation else None,
                'reset_token': reset_token if not send_invitation else None
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def update_user(self, user_id: str, tenant_id: str, updates: Dict[str, Any],
                   updated_by: str = None) -> Dict[str, Any]:
        """Update user information"""
        
        allowed_fields = ['first_name', 'last_name', 'phone', 'role', 'is_active']
        update_fields = []
        update_values = []
        
        for field, value in updates.items():
            if field not in allowed_fields:
                continue
                
            if field in ['first_name', 'last_name', 'phone']:
                value = sanitize_string(value, max_length=100)
            elif field == 'role' and value not in ['admin', 'staff', 'customer']:
                raise ValidationError("Invalid role")
            elif field == 'is_active' and not isinstance(value, bool):
                raise ValidationError("is_active must be boolean")
            
            update_fields.append(f"{field} = %s")
            update_values.append(value)
        
        if not update_fields:
            raise ValidationError("No valid fields to update")
        
        update_values.extend([user_id, tenant_id])
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Update user
            query = f"""
                UPDATE users 
                SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND tenant_id = %s
                RETURNING id, email, first_name, last_name, phone, role, is_active
            """
            
            cursor.execute(query, update_values)
            user = cursor.fetchone()
            
            if not user:
                raise ValidationError("User not found")
            
            # Log audit event
            cursor.execute("""
                SELECT log_audit_event(%s, %s, 'user_updated', 'user', %s, %s, %s, %s)
            """, (
                tenant_id, updated_by, user_id,
                request.remote_addr if request else None,
                request.headers.get('User-Agent') if request else None,
                psycopg2.extras.Json(updates)
            ))
            
            conn.commit()
            
            return dict(user)
            
        finally:
            cursor.close()
            conn.close()
    
    def list_users(self, tenant_id: str, page: int = 1, limit: int = 50,
                  role_filter: str = None, search: str = None) -> Dict[str, Any]:
        """List users with pagination and filtering"""
        
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Build query
            where_conditions = ["tenant_id = %s"]
            params = [tenant_id]
            
            if role_filter and role_filter in ['admin', 'staff', 'customer']:
                where_conditions.append("role = %s")
                params.append(role_filter)
            
            if search:
                search_term = f"%{sanitize_string(search, max_length=100)}%"
                where_conditions.append("""
                    (first_name ILIKE %s OR last_name ILIKE %s OR email ILIKE %s)
                """)
                params.extend([search_term, search_term, search_term])
            
            where_clause = " AND ".join(where_conditions)
            
            # Get users
            query = f"""
                SELECT id, email, first_name, last_name, phone, role, 
                       is_active, email_verified, last_login, created_at
                FROM users
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            
            params.extend([limit, offset])
            cursor.execute(query, params)
            users = cursor.fetchall()
            
            # Convert datetime objects
            for user in users:
                if user.get('last_login'):
                    user['last_login'] = user['last_login'].isoformat()
                if user.get('created_at'):
                    user['created_at'] = user['created_at'].isoformat()
            
            # Get total count
            count_query = f"""
                SELECT COUNT(*) as total FROM users WHERE {where_clause}
            """
            cursor.execute(count_query, params[:-2])  # Exclude limit and offset
            total_count = cursor.fetchone()['total']
            
            return {
                'users': users,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total_count,
                    'pages': (total_count + limit - 1) // limit
                }
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def get_user(self, user_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get single user details"""
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT id, email, first_name, last_name, phone, role,
                       is_active, email_verified, last_login, created_at,
                       failed_login_attempts, locked_until
                FROM users
                WHERE id = %s AND tenant_id = %s
            """, (user_id, tenant_id))
            
            user = cursor.fetchone()
            if not user:
                return None
            
            # Convert datetime objects
            if user.get('last_login'):
                user['last_login'] = user['last_login'].isoformat()
            if user.get('created_at'):
                user['created_at'] = user['created_at'].isoformat()
            if user.get('locked_until'):
                user['locked_until'] = user['locked_until'].isoformat()
            
            return dict(user)
            
        finally:
            cursor.close()
            conn.close()
    
    def delete_user(self, user_id: str, tenant_id: str, deleted_by: str = None) -> bool:
        """Soft delete user (deactivate)"""
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Deactivate user instead of hard delete
            cursor.execute("""
                UPDATE users 
                SET is_active = false, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND tenant_id = %s
                RETURNING email
            """, (user_id, tenant_id))
            
            user = cursor.fetchone()
            if not user:
                return False
            
            # Log audit event
            cursor.execute("""
                SELECT log_audit_event(%s, %s, 'user_deactivated', 'user', %s, %s, %s, %s)
            """, (
                tenant_id, deleted_by, user_id,
                request.remote_addr if request else None,
                request.headers.get('User-Agent') if request else None,
                psycopg2.extras.Json({'email': user['email']})
            ))
            
            conn.commit()
            return True
            
        finally:
            cursor.close()
            conn.close()
    
    def reset_password(self, user_id: str, tenant_id: str, new_password: str,
                      reset_by: str = None) -> str:
        """Reset user password"""
        
        if not validate_password(new_password):
            raise ValidationError(
                "Password must be at least 8 characters with uppercase, lowercase, and number"
            )
        
        password_hash = hash_password(new_password)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                UPDATE users 
                SET password_hash = %s, password_reset_token = NULL, 
                    password_reset_expires = NULL, failed_login_attempts = 0,
                    locked_until = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND tenant_id = %s
                RETURNING email
            """, (password_hash, user_id, tenant_id))
            
            user = cursor.fetchone()
            if not user:
                raise ValidationError("User not found")
            
            # Log audit event
            cursor.execute("""
                SELECT log_audit_event(%s, %s, 'password_reset', 'user', %s, %s, %s, %s)
            """, (
                tenant_id, reset_by, user_id,
                request.remote_addr if request else None,
                request.headers.get('User-Agent') if request else None,
                psycopg2.extras.Json({'email': user['email']})
            ))
            
            conn.commit()
            return "Password reset successfully"
            
        finally:
            cursor.close()
            conn.close()
    
    def get_user_activity(self, user_id: str, tenant_id: str, 
                         days: int = 30) -> List[Dict[str, Any]]:
        """Get user activity from audit logs"""
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT action, resource_type, ip_address, created_at, details
                FROM audit_logs
                WHERE user_id = %s AND tenant_id = %s 
                AND created_at > CURRENT_TIMESTAMP - INTERVAL '%s days'
                ORDER BY created_at DESC
                LIMIT 100
            """, (user_id, tenant_id, days))
            
            activities = cursor.fetchall()
            
            # Convert datetime objects
            for activity in activities:
                if activity.get('created_at'):
                    activity['created_at'] = activity['created_at'].isoformat()
            
            return activities
            
        finally:
            cursor.close()
            conn.close()
    
    def _send_invitation_email(self, email: str, first_name: str, 
                              temp_password: str, reset_token: str, tenant_id: str):
        """Send invitation email to new user"""
        
        if not self.smtp_host:
            return
        
        try:
            # Get tenant info for branding
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT name, domain FROM tenants WHERE id = %s
            """, (tenant_id,))
            
            tenant = cursor.fetchone()
            tenant_name = tenant['name'] if tenant else 'MoveCRM'
            
            cursor.close()
            conn.close()
            
            # Create email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'Welcome to {tenant_name} - Account Created'
            msg['From'] = self.smtp_from_email
            msg['To'] = email
            
            # Email content
            text_content = f"""
            Welcome to {tenant_name}!
            
            Your account has been created. Here are your login details:
            
            Email: {email}
            Temporary Password: {temp_password}
            
            Please log in and change your password immediately.
            
            Best regards,
            {tenant_name} Team
            """
            
            html_content = f"""
            <html>
            <body>
                <h2>Welcome to {tenant_name}!</h2>
                <p>Your account has been created. Here are your login details:</p>
                <ul>
                    <li><strong>Email:</strong> {email}</li>
                    <li><strong>Temporary Password:</strong> {temp_password}</li>
                </ul>
                <p>Please log in and change your password immediately.</p>
                <p>Best regards,<br>{tenant_name} Team</p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
                
        except Exception as e:
            # Log error but don't fail user creation
            print(f"Failed to send invitation email: {str(e)}")


# Global user manager instance
user_manager = UserManager()

