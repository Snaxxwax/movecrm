"""
Enhanced Quote Management System for MoveCRM
Provides advanced quote workflows, templates, and automation
"""

from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional
import uuid
import json
from decimal import Decimal
import psycopg2
from psycopg2.extras import RealDictCursor
from enum import Enum

from .auth import get_db_connection
from .validation import validate_request_data, QuoteCreateSchema, ValidationError
from .user_management import user_manager


class QuoteStatus(Enum):
    DRAFT = 'draft'
    PENDING = 'pending'
    UNDER_REVIEW = 'under_review'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    EXPIRED = 'expired'
    CONVERTED = 'converted'


class QuoteWorkflow:
    """Advanced quote workflow management"""
    
    def __init__(self):
        pass
    
    def create_quote(self, tenant_id: str, customer_data: Dict[str, Any], 
                    items: List[Dict[str, Any]], created_by: str,
                    template_id: str = None, auto_approve: bool = False) -> Dict[str, Any]:
        """Create quote with advanced workflow features"""
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get pricing rules
            cursor.execute("""
                SELECT * FROM pricing_rules 
                WHERE tenant_id = %s AND is_default = true AND is_active = true
                LIMIT 1
            """, (tenant_id,))
            
            pricing = cursor.fetchone()
            if not pricing:
                raise ValidationError("No pricing rules configured")
            
            # Calculate totals
            total_cubic_feet = sum(item.get('cubic_feet', 0) for item in items)
            labor_hours = self._calculate_labor_hours(items, total_cubic_feet)
            
            subtotal = self._calculate_subtotal(
                total_cubic_feet, labor_hours, pricing, customer_data.get('distance_miles', 0)
            )
            
            tax_amount = subtotal * float(pricing['tax_rate'])
            total_amount = subtotal + tax_amount
            
            # Determine initial status
            status = QuoteStatus.DRAFT.value
            if auto_approve or total_amount < float(pricing.get('auto_approve_threshold', 1000)):
                status = QuoteStatus.APPROVED.value
            elif total_amount > float(pricing.get('review_threshold', 5000)):
                status = QuoteStatus.UNDER_REVIEW.value
            else:
                status = QuoteStatus.PENDING.value
            
            # Generate quote number
            quote_number = self._generate_quote_number(tenant_id)
            
            # Set expiration date
            expires_at = datetime.utcnow() + timedelta(days=30)
            
            # Create quote
            cursor.execute("""
                INSERT INTO quotes (
                    tenant_id, quote_number, customer_email, customer_name, 
                    customer_phone, pickup_address, delivery_address, move_date,
                    notes, total_cubic_feet, total_labor_hours, distance_miles,
                    subtotal, tax_amount, total_amount, pricing_rule_id,
                    status, expires_at, created_by
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                tenant_id, quote_number, customer_data['customer_email'],
                customer_data['customer_name'], customer_data.get('customer_phone'),
                customer_data['pickup_address'], customer_data['delivery_address'],
                customer_data.get('move_date'), customer_data.get('notes', ''),
                total_cubic_feet, labor_hours, customer_data.get('distance_miles', 0),
                subtotal, tax_amount, total_amount, pricing['id'],
                status, expires_at, created_by
            ))
            
            quote_id = cursor.fetchone()['id']
            
            # Add quote items
            for item in items:
                self._add_quote_item(cursor, quote_id, item, pricing)
            
            # Auto-approve if applicable
            if status == QuoteStatus.APPROVED.value:
                cursor.execute("""
                    UPDATE quotes 
                    SET approved_by = %s, approved_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (created_by, quote_id))
            
            # Log audit event
            cursor.execute("""
                SELECT log_audit_event(%s, %s, 'quote_created', 'quote', %s, %s, %s, %s)
            """, (
                tenant_id, created_by, quote_id, None, None,
                psycopg2.extras.Json({
                    'quote_number': quote_number,
                    'total_amount': float(total_amount),
                    'status': status
                })
            ))
            
            conn.commit()
            
            # Send notifications if approved
            if status == QuoteStatus.APPROVED.value:
                self._send_quote_notification(quote_id, 'approved')
            
            return {
                'quote_id': str(quote_id),
                'quote_number': quote_number,
                'status': status,
                'total_amount': float(total_amount),
                'expires_at': expires_at.isoformat()
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def update_quote_status(self, quote_id: str, new_status: str, 
                           updated_by: str, notes: str = '') -> Dict[str, Any]:
        """Update quote status with workflow validation"""
        
        if new_status not in [status.value for status in QuoteStatus]:
            raise ValidationError("Invalid status")
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get current quote
            cursor.execute("""
                SELECT * FROM quotes WHERE id = %s
            """, (quote_id,))
            
            quote = cursor.fetchone()
            if not quote:
                raise ValidationError("Quote not found")
            
            current_status = quote['status']
            
            # Validate status transition
            if not self._is_valid_status_transition(current_status, new_status):
                raise ValidationError(f"Invalid status transition from {current_status} to {new_status}")
            
            # Update quote
            update_fields = ['status = %s', 'updated_at = CURRENT_TIMESTAMP']
            update_values = [new_status]
            
            if new_status == QuoteStatus.APPROVED.value:
                update_fields.extend(['approved_by = %s', 'approved_at = CURRENT_TIMESTAMP'])
                update_values.append(updated_by)
            
            if notes:
                update_fields.append('notes = COALESCE(notes, \'\') || %s')
                update_values.append(f'\n\nStatus Update: {notes}')
            
            update_values.append(quote_id)
            
            cursor.execute(f"""
                UPDATE quotes 
                SET {', '.join(update_fields)}
                WHERE id = %s
                RETURNING quote_number, customer_email, total_amount
            """, update_values)
            
            updated_quote = cursor.fetchone()
            
            # Log audit event
            cursor.execute("""
                SELECT log_audit_event(%s, %s, 'quote_status_updated', 'quote', %s, %s, %s, %s)
            """, (
                quote['tenant_id'], updated_by, quote_id, None, None,
                psycopg2.extras.Json({
                    'old_status': current_status,
                    'new_status': new_status,
                    'notes': notes
                })
            ))
            
            conn.commit()
            
            # Send notifications
            self._send_quote_notification(quote_id, new_status)
            
            return {
                'quote_id': str(quote_id),
                'quote_number': updated_quote['quote_number'],
                'old_status': current_status,
                'new_status': new_status,
                'updated_at': datetime.utcnow().isoformat()
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def create_quote_template(self, tenant_id: str, template_data: Dict[str, Any],
                             created_by: str) -> str:
        """Create reusable quote template"""
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                INSERT INTO quote_templates (
                    tenant_id, name, description, default_items, 
                    pricing_adjustments, terms_conditions, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                tenant_id, template_data['name'], template_data.get('description', ''),
                psycopg2.extras.Json(template_data.get('default_items', [])),
                psycopg2.extras.Json(template_data.get('pricing_adjustments', {})),
                template_data.get('terms_conditions', ''), created_by
            ))
            
            template_id = cursor.fetchone()['id']
            conn.commit()
            
            return str(template_id)
            
        finally:
            cursor.close()
            conn.close()
    
    def get_quote_analytics(self, tenant_id: str, quote_id: str) -> Dict[str, Any]:
        """Get detailed analytics for a specific quote"""
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get quote details
            cursor.execute("""
                SELECT q.*, pr.name as pricing_rule_name
                FROM quotes q
                LEFT JOIN pricing_rules pr ON q.pricing_rule_id = pr.id
                WHERE q.id = %s AND q.tenant_id = %s
            """, (quote_id, tenant_id))
            
            quote = cursor.fetchone()
            if not quote:
                raise ValidationError("Quote not found")
            
            # Get quote items with analytics
            cursor.execute("""
                SELECT qi.*, ic.category
                FROM quote_items qi
                LEFT JOIN item_catalog ic ON qi.item_catalog_id = ic.id
                WHERE qi.quote_id = %s
                ORDER BY qi.total_price DESC
            """, (quote_id,))
            
            items = cursor.fetchall()
            
            # Get similar quotes for comparison
            cursor.execute("""
                SELECT AVG(total_amount) as avg_similar_quote,
                       COUNT(*) as similar_quote_count
                FROM quotes
                WHERE tenant_id = %s 
                AND total_cubic_feet BETWEEN %s AND %s
                AND id != %s
            """, (
                tenant_id, 
                float(quote['total_cubic_feet']) * 0.8,
                float(quote['total_cubic_feet']) * 1.2,
                quote_id
            ))
            
            similar_quotes = cursor.fetchone()
            
            # Get status history
            cursor.execute("""
                SELECT action, details, created_at
                FROM audit_logs
                WHERE resource_type = 'quote' AND resource_id = %s
                ORDER BY created_at DESC
            """, (quote_id,))
            
            status_history = cursor.fetchall()
            
            # Convert data types
            for item in items:
                if item.get('cubic_feet'):
                    item['cubic_feet'] = float(item['cubic_feet'])
                if item.get('total_price'):
                    item['total_price'] = float(item['total_price'])
            
            for event in status_history:
                if event.get('created_at'):
                    event['created_at'] = event['created_at'].isoformat()
            
            return {
                'quote': dict(quote),
                'items': items,
                'comparison': {
                    'avg_similar_quote': float(similar_quotes['avg_similar_quote'] or 0),
                    'similar_quote_count': similar_quotes['similar_quote_count']
                },
                'status_history': status_history
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def _calculate_labor_hours(self, items: List[Dict[str, Any]], 
                              total_cubic_feet: float) -> float:
        """Calculate estimated labor hours based on items and volume"""
        
        base_hours = total_cubic_feet / 50  # Base calculation
        
        # Adjust for item complexity
        complexity_multiplier = 1.0
        for item in items:
            if item.get('category') == 'Appliances':
                complexity_multiplier += 0.1
            elif item.get('category') == 'Furniture':
                complexity_multiplier += 0.05
        
        return base_hours * complexity_multiplier
    
    def _calculate_subtotal(self, cubic_feet: float, labor_hours: float,
                           pricing: Dict[str, Any], distance_miles: float) -> float:
        """Calculate quote subtotal with all components"""
        
        space_cost = cubic_feet * float(pricing['rate_per_cubic_foot'])
        labor_cost = labor_hours * float(pricing['labor_rate_per_hour'])
        distance_cost = distance_miles * float(pricing.get('distance_rate_per_mile', 0))
        
        subtotal = space_cost + labor_cost + distance_cost
        
        # Apply minimum charge
        minimum_charge = float(pricing.get('minimum_charge', 0))
        return max(subtotal, minimum_charge)
    
    def _add_quote_item(self, cursor, quote_id: str, item: Dict[str, Any],
                       pricing: Dict[str, Any]):
        """Add item to quote with proper calculations"""
        
        cubic_feet = float(item.get('cubic_feet', 0))
        quantity = int(item.get('quantity', 1))
        unit_price = cubic_feet * float(pricing['rate_per_cubic_foot'])
        total_price = unit_price * quantity
        
        cursor.execute("""
            INSERT INTO quote_items (
                quote_id, detected_name, quantity, cubic_feet,
                unit_price, total_price, confidence_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            quote_id, item.get('name', 'Unknown'), quantity,
            cubic_feet, unit_price, total_price,
            item.get('confidence_score')
        ))
    
    def _generate_quote_number(self, tenant_id: str) -> str:
        """Generate unique quote number"""
        
        date_part = datetime.now().strftime('%Y%m%d')
        random_part = str(uuid.uuid4())[:8].upper()
        
        return f"QUOTE-{date_part}-{random_part}"
    
    def _is_valid_status_transition(self, current_status: str, new_status: str) -> bool:
        """Validate if status transition is allowed"""
        
        valid_transitions = {
            QuoteStatus.DRAFT.value: [QuoteStatus.PENDING.value, QuoteStatus.REJECTED.value],
            QuoteStatus.PENDING.value: [QuoteStatus.UNDER_REVIEW.value, QuoteStatus.APPROVED.value, QuoteStatus.REJECTED.value],
            QuoteStatus.UNDER_REVIEW.value: [QuoteStatus.APPROVED.value, QuoteStatus.REJECTED.value, QuoteStatus.PENDING.value],
            QuoteStatus.APPROVED.value: [QuoteStatus.CONVERTED.value, QuoteStatus.EXPIRED.value],
            QuoteStatus.REJECTED.value: [QuoteStatus.PENDING.value],
            QuoteStatus.EXPIRED.value: [QuoteStatus.PENDING.value],
            QuoteStatus.CONVERTED.value: []  # Terminal state
        }
        
        return new_status in valid_transitions.get(current_status, [])
    
    def _send_quote_notification(self, quote_id: str, status: str):
        """Send notification based on quote status change"""
        
        # This would integrate with email service
        # For now, just log the notification
        print(f"Notification: Quote {quote_id} status changed to {status}")
    
    def expire_old_quotes(self, tenant_id: str) -> int:
        """Expire quotes that have passed their expiration date"""
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE quotes 
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = %s 
                AND status IN (%s, %s)
                AND expires_at < CURRENT_TIMESTAMP
            """, (
                QuoteStatus.EXPIRED.value, tenant_id,
                QuoteStatus.PENDING.value, QuoteStatus.UNDER_REVIEW.value
            ))
            
            expired_count = cursor.rowcount
            conn.commit()
            
            return expired_count
            
        finally:
            cursor.close()
            conn.close()


# Global quote workflow instance
quote_workflow = QuoteWorkflow()

