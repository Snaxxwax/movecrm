"""
Input validation and sanitization module for MoveCRM
Provides comprehensive validation for all user inputs
"""

import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union
from decimal import Decimal, InvalidOperation
import bleach
from marshmallow import Schema, fields, validate, ValidationError


class ValidationError(Exception):
    """Custom validation error"""
    pass


def sanitize_string(value: str, max_length: int = 255) -> str:
    """Sanitize string input to prevent XSS"""
    if not isinstance(value, str):
        raise ValidationError("Value must be a string")
    
    # Remove HTML tags and dangerous characters
    cleaned = bleach.clean(value, tags=[], strip=True)
    
    # Trim whitespace
    cleaned = cleaned.strip()
    
    # Check length
    if len(cleaned) > max_length:
        raise ValidationError(f"String too long (max {max_length} characters)")
    
    return cleaned


def validate_email(email: str) -> str:
    """Validate and sanitize email address"""
    if not isinstance(email, str):
        raise ValidationError("Email must be a string")
    
    email = email.strip().lower()
    
    # Basic email regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError("Invalid email format")
    
    if len(email) > 255:
        raise ValidationError("Email too long")
    
    return email


def validate_phone(phone: str) -> str:
    """Validate and sanitize phone number"""
    if not isinstance(phone, str):
        raise ValidationError("Phone must be a string")
    
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone)
    
    # Check length (US phone numbers)
    if len(digits_only) < 10 or len(digits_only) > 15:
        raise ValidationError("Invalid phone number length")
    
    # Format as (XXX) XXX-XXXX for US numbers
    if len(digits_only) == 10:
        return f"({digits_only[:3]}) {digits_only[3:6]}-{digits_only[6:]}"
    elif len(digits_only) == 11 and digits_only[0] == '1':
        return f"+1 ({digits_only[1:4]}) {digits_only[4:7]}-{digits_only[7:]}"
    else:
        return f"+{digits_only}"


def validate_decimal(value: Union[str, int, float, Decimal], min_value: float = 0, 
                    max_value: float = 999999.99, decimal_places: int = 2) -> Decimal:
    """Validate and convert to decimal"""
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError("Invalid decimal value")
    
    if decimal_value < Decimal(str(min_value)):
        raise ValidationError(f"Value must be at least {min_value}")
    
    if decimal_value > Decimal(str(max_value)):
        raise ValidationError(f"Value must be at most {max_value}")
    
    # Check decimal places
    if decimal_value.as_tuple().exponent < -decimal_places:
        raise ValidationError(f"Too many decimal places (max {decimal_places})")
    
    return decimal_value


def validate_integer(value: Union[str, int], min_value: int = 0, max_value: int = 999999) -> int:
    """Validate integer value"""
    try:
        int_value = int(value)
    except (ValueError, TypeError):
        raise ValidationError("Invalid integer value")
    
    if int_value < min_value:
        raise ValidationError(f"Value must be at least {min_value}")
    
    if int_value > max_value:
        raise ValidationError(f"Value must be at most {max_value}")
    
    return int_value


def validate_date(value: Union[str, date]) -> date:
    """Validate date value"""
    if isinstance(value, date):
        return value
    
    if isinstance(value, str):
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            try:
                return datetime.strptime(value, '%m/%d/%Y').date()
            except ValueError:
                raise ValidationError("Invalid date format (use YYYY-MM-DD or MM/DD/YYYY)")
    
    raise ValidationError("Invalid date value")


def validate_uuid(value: str) -> str:
    """Validate UUID format"""
    if not isinstance(value, str):
        raise ValidationError("UUID must be a string")
    
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    if not re.match(uuid_pattern, value.lower()):
        raise ValidationError("Invalid UUID format")
    
    return value.lower()


def validate_slug(value: str) -> str:
    """Validate tenant slug format"""
    if not isinstance(value, str):
        raise ValidationError("Slug must be a string")
    
    value = value.strip().lower()
    
    # Only allow lowercase letters, numbers, and hyphens
    if not re.match(r'^[a-z0-9-]+$', value):
        raise ValidationError("Slug can only contain lowercase letters, numbers, and hyphens")
    
    if len(value) < 2 or len(value) > 50:
        raise ValidationError("Slug must be 2-50 characters long")
    
    if value.startswith('-') or value.endswith('-'):
        raise ValidationError("Slug cannot start or end with hyphen")
    
    return value


# Marshmallow schemas for complex validation

class QuoteCreateSchema(Schema):
    """Schema for quote creation validation"""
    customer_email = fields.Email(required=True)
    customer_name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    customer_phone = fields.Str(required=False, allow_none=True, validate=validate.Length(max=20))
    pickup_address = fields.Str(required=True, validate=validate.Length(min=5, max=500))
    delivery_address = fields.Str(required=True, validate=validate.Length(min=5, max=500))
    move_date = fields.Date(required=True)
    notes = fields.Str(required=False, allow_none=True, validate=validate.Length(max=2000))
    total_cubic_feet = fields.Decimal(required=True, validate=validate.Range(min=0, max=10000))
    items = fields.List(fields.Dict(), required=False, missing=[])


class QuoteItemSchema(Schema):
    """Schema for quote item validation"""
    name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    quantity = fields.Int(required=True, validate=validate.Range(min=1, max=1000))
    cubic_feet = fields.Decimal(required=True, validate=validate.Range(min=0, max=1000))


class UserCreateSchema(Schema):
    """Schema for user creation validation"""
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8, max=128))
    first_name = fields.Str(required=False, allow_none=True, validate=validate.Length(max=100))
    last_name = fields.Str(required=False, allow_none=True, validate=validate.Length(max=100))
    phone = fields.Str(required=False, allow_none=True, validate=validate.Length(max=20))
    role = fields.Str(required=False, missing='customer', 
                     validate=validate.OneOf(['admin', 'staff', 'customer']))


class LoginSchema(Schema):
    """Schema for login validation"""
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    tenant_slug = fields.Str(required=True, validate=validate.Length(min=2, max=50))


def validate_request_data(schema: Schema, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate request data against schema"""
    try:
        return schema.load(data)
    except ValidationError as e:
        raise ValidationError(f"Validation failed: {e.messages}")


def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filename"""
    if not isinstance(filename, str):
        raise ValidationError("Filename must be a string")
    
    # Remove path components
    filename = filename.split('/')[-1].split('\\')[-1]
    
    # Remove dangerous characters
    filename = re.sub(r'[^a-zA-Z0-9._-]', '', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')
    
    if not filename:
        raise ValidationError("Invalid filename")
    
    return filename


def validate_file_type(filename: str, allowed_types: List[str]) -> bool:
    """Validate file type by extension"""
    if not filename:
        return False
    
    extension = filename.lower().split('.')[-1] if '.' in filename else ''
    return extension in [t.lower() for t in allowed_types]


def validate_file_size(file_size: int, max_size_mb: int = 50) -> bool:
    """Validate file size"""
    max_size_bytes = max_size_mb * 1024 * 1024
    return file_size <= max_size_bytes

