"""
Analytics and Reporting Module for MoveCRM
Provides business intelligence and performance metrics
"""

from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal
import json

from .auth import get_db_connection
from .validation import validate_integer, validate_date, ValidationError


class AnalyticsEngine:
    """Comprehensive analytics and reporting engine"""
    
    def __init__(self):
        pass
    
    def get_dashboard_metrics(self, tenant_id: str, date_range: int = 30) -> Dict[str, Any]:
        """Get key dashboard metrics for the specified date range"""
        
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=date_range)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Total quotes in period
            cursor.execute("""
                SELECT COUNT(*) as total_quotes,
                       COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_quotes,
                       COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_quotes,
                       COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_quotes,
                       SUM(CASE WHEN status = 'approved' THEN total_amount ELSE 0 END) as approved_revenue,
                       SUM(total_amount) as total_quote_value,
                       AVG(total_amount) as avg_quote_value
                FROM quotes
                WHERE tenant_id = %s AND created_at >= %s AND created_at <= %s
            """, (tenant_id, start_date, end_date))
            
            quote_metrics = cursor.fetchone()
            
            # Conversion rate
            conversion_rate = 0
            if quote_metrics['total_quotes'] > 0:
                conversion_rate = (quote_metrics['approved_quotes'] / quote_metrics['total_quotes']) * 100
            
            # Previous period comparison
            prev_start = start_date - timedelta(days=date_range)
            prev_end = start_date
            
            cursor.execute("""
                SELECT COUNT(*) as prev_total_quotes,
                       COUNT(CASE WHEN status = 'approved' THEN 1 END) as prev_approved_quotes,
                       SUM(CASE WHEN status = 'approved' THEN total_amount ELSE 0 END) as prev_approved_revenue
                FROM quotes
                WHERE tenant_id = %s AND created_at >= %s AND created_at < %s
            """, (tenant_id, prev_start, prev_end))
            
            prev_metrics = cursor.fetchone()
            
            # Calculate growth rates
            quote_growth = 0
            revenue_growth = 0
            
            if prev_metrics['prev_total_quotes'] > 0:
                quote_growth = ((quote_metrics['total_quotes'] - prev_metrics['prev_total_quotes']) / 
                               prev_metrics['prev_total_quotes']) * 100
            
            if prev_metrics['prev_approved_revenue'] and prev_metrics['prev_approved_revenue'] > 0:
                revenue_growth = ((float(quote_metrics['approved_revenue'] or 0) - 
                                 float(prev_metrics['prev_approved_revenue'])) / 
                                float(prev_metrics['prev_approved_revenue'])) * 100
            
            # Top customers by quote value
            cursor.execute("""
                SELECT customer_email, customer_name, 
                       COUNT(*) as quote_count,
                       SUM(total_amount) as total_value,
                       AVG(total_amount) as avg_value
                FROM quotes
                WHERE tenant_id = %s AND created_at >= %s AND created_at <= %s
                GROUP BY customer_email, customer_name
                ORDER BY total_value DESC
                LIMIT 10
            """, (tenant_id, start_date, end_date))
            
            top_customers = cursor.fetchall()
            
            # Recent activity
            cursor.execute("""
                SELECT quote_number, customer_name, status, total_amount, created_at
                FROM quotes
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT 10
            """, (tenant_id,))
            
            recent_quotes = cursor.fetchall()
            
            # Convert datetime and decimal objects
            for quote in recent_quotes:
                if quote.get('created_at'):
                    quote['created_at'] = quote['created_at'].isoformat()
                if quote.get('total_amount'):
                    quote['total_amount'] = float(quote['total_amount'])
            
            for customer in top_customers:
                if customer.get('total_value'):
                    customer['total_value'] = float(customer['total_value'])
                if customer.get('avg_value'):
                    customer['avg_value'] = float(customer['avg_value'])
            
            return {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'days': date_range
                },
                'quotes': {
                    'total': quote_metrics['total_quotes'],
                    'approved': quote_metrics['approved_quotes'],
                    'pending': quote_metrics['pending_quotes'],
                    'rejected': quote_metrics['rejected_quotes'],
                    'conversion_rate': round(conversion_rate, 2),
                    'growth_rate': round(quote_growth, 2)
                },
                'revenue': {
                    'approved_revenue': float(quote_metrics['approved_revenue'] or 0),
                    'total_quote_value': float(quote_metrics['total_quote_value'] or 0),
                    'avg_quote_value': float(quote_metrics['avg_quote_value'] or 0),
                    'growth_rate': round(revenue_growth, 2)
                },
                'top_customers': top_customers,
                'recent_activity': recent_quotes
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def get_quote_trends(self, tenant_id: str, period: str = 'daily', 
                        days: int = 30) -> Dict[str, Any]:
        """Get quote trends over time"""
        
        if period not in ['daily', 'weekly', 'monthly']:
            raise ValidationError("Period must be daily, weekly, or monthly")
        
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            if period == 'daily':
                date_trunc = 'day'
                date_format = 'YYYY-MM-DD'
            elif period == 'weekly':
                date_trunc = 'week'
                date_format = 'YYYY-"W"WW'
            else:  # monthly
                date_trunc = 'month'
                date_format = 'YYYY-MM'
            
            cursor.execute(f"""
                SELECT 
                    DATE_TRUNC(%s, created_at::date) as period_date,
                    TO_CHAR(DATE_TRUNC(%s, created_at::date), %s) as period_label,
                    COUNT(*) as total_quotes,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_quotes,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_quotes,
                    COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_quotes,
                    SUM(CASE WHEN status = 'approved' THEN total_amount ELSE 0 END) as revenue,
                    AVG(total_amount) as avg_quote_value
                FROM quotes
                WHERE tenant_id = %s AND created_at >= %s AND created_at <= %s
                GROUP BY DATE_TRUNC(%s, created_at::date)
                ORDER BY period_date
            """, (date_trunc, date_trunc, date_format, tenant_id, start_date, end_date, date_trunc))
            
            trends = cursor.fetchall()
            
            # Convert data types
            for trend in trends:
                if trend.get('period_date'):
                    trend['period_date'] = trend['period_date'].isoformat()
                if trend.get('revenue'):
                    trend['revenue'] = float(trend['revenue'])
                if trend.get('avg_quote_value'):
                    trend['avg_quote_value'] = float(trend['avg_quote_value'])
            
            return {
                'period': period,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'trends': trends
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def get_performance_metrics(self, tenant_id: str, date_range: int = 30) -> Dict[str, Any]:
        """Get detailed performance metrics"""
        
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=date_range)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Quote response time analysis
            cursor.execute("""
                SELECT 
                    AVG(EXTRACT(EPOCH FROM (approved_at - created_at))/3600) as avg_response_hours,
                    MIN(EXTRACT(EPOCH FROM (approved_at - created_at))/3600) as min_response_hours,
                    MAX(EXTRACT(EPOCH FROM (approved_at - created_at))/3600) as max_response_hours
                FROM quotes
                WHERE tenant_id = %s AND status = 'approved' 
                AND approved_at IS NOT NULL
                AND created_at >= %s AND created_at <= %s
            """, (tenant_id, start_date, end_date))
            
            response_times = cursor.fetchone()
            
            # Quote value distribution
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN total_amount < 500 THEN 1 END) as under_500,
                    COUNT(CASE WHEN total_amount >= 500 AND total_amount < 1000 THEN 1 END) as range_500_1000,
                    COUNT(CASE WHEN total_amount >= 1000 AND total_amount < 2000 THEN 1 END) as range_1000_2000,
                    COUNT(CASE WHEN total_amount >= 2000 AND total_amount < 5000 THEN 1 END) as range_2000_5000,
                    COUNT(CASE WHEN total_amount >= 5000 THEN 1 END) as over_5000
                FROM quotes
                WHERE tenant_id = %s AND created_at >= %s AND created_at <= %s
            """, (tenant_id, start_date, end_date))
            
            value_distribution = cursor.fetchone()
            
            # Most popular items
            cursor.execute("""
                SELECT 
                    qi.detected_name,
                    COUNT(*) as frequency,
                    AVG(qi.cubic_feet) as avg_cubic_feet,
                    SUM(qi.total_price) as total_revenue
                FROM quote_items qi
                JOIN quotes q ON qi.quote_id = q.id
                WHERE q.tenant_id = %s AND q.created_at >= %s AND q.created_at <= %s
                GROUP BY qi.detected_name
                ORDER BY frequency DESC
                LIMIT 20
            """, (tenant_id, start_date, end_date))
            
            popular_items = cursor.fetchall()
            
            # Convert data types
            for item in popular_items:
                if item.get('avg_cubic_feet'):
                    item['avg_cubic_feet'] = float(item['avg_cubic_feet'])
                if item.get('total_revenue'):
                    item['total_revenue'] = float(item['total_revenue'])
            
            # Seasonal trends (by month)
            cursor.execute("""
                SELECT 
                    EXTRACT(MONTH FROM created_at) as month,
                    TO_CHAR(created_at, 'Month') as month_name,
                    COUNT(*) as quote_count,
                    AVG(total_amount) as avg_value
                FROM quotes
                WHERE tenant_id = %s AND created_at >= %s - INTERVAL '1 year'
                GROUP BY EXTRACT(MONTH FROM created_at), TO_CHAR(created_at, 'Month')
                ORDER BY month
            """, (tenant_id, start_date))
            
            seasonal_trends = cursor.fetchall()
            
            # Convert data types
            for trend in seasonal_trends:
                if trend.get('avg_value'):
                    trend['avg_value'] = float(trend['avg_value'])
            
            return {
                'response_times': {
                    'avg_hours': float(response_times['avg_response_hours'] or 0),
                    'min_hours': float(response_times['min_response_hours'] or 0),
                    'max_hours': float(response_times['max_response_hours'] or 0)
                },
                'value_distribution': dict(value_distribution),
                'popular_items': popular_items,
                'seasonal_trends': seasonal_trends
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def get_customer_analytics(self, tenant_id: str, date_range: int = 90) -> Dict[str, Any]:
        """Get customer behavior analytics"""
        
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=date_range)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Customer acquisition trends
            cursor.execute("""
                SELECT 
                    DATE_TRUNC('week', created_at) as week,
                    COUNT(DISTINCT customer_email) as new_customers
                FROM quotes
                WHERE tenant_id = %s AND created_at >= %s AND created_at <= %s
                GROUP BY DATE_TRUNC('week', created_at)
                ORDER BY week
            """, (tenant_id, start_date, end_date))
            
            acquisition_trends = cursor.fetchall()
            
            # Customer lifetime value
            cursor.execute("""
                SELECT 
                    customer_email,
                    customer_name,
                    COUNT(*) as total_quotes,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_quotes,
                    SUM(CASE WHEN status = 'approved' THEN total_amount ELSE 0 END) as lifetime_value,
                    AVG(total_amount) as avg_quote_value,
                    MIN(created_at) as first_quote_date,
                    MAX(created_at) as last_quote_date
                FROM quotes
                WHERE tenant_id = %s
                GROUP BY customer_email, customer_name
                HAVING COUNT(*) > 1
                ORDER BY lifetime_value DESC
                LIMIT 50
            """, (tenant_id,))
            
            customer_ltv = cursor.fetchall()
            
            # Repeat customer analysis
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN quote_count = 1 THEN 'One-time'
                        WHEN quote_count = 2 THEN 'Repeat (2)'
                        WHEN quote_count BETWEEN 3 AND 5 THEN 'Regular (3-5)'
                        ELSE 'Frequent (6+)'
                    END as customer_type,
                    COUNT(*) as customer_count,
                    AVG(lifetime_value) as avg_lifetime_value
                FROM (
                    SELECT 
                        customer_email,
                        COUNT(*) as quote_count,
                        SUM(CASE WHEN status = 'approved' THEN total_amount ELSE 0 END) as lifetime_value
                    FROM quotes
                    WHERE tenant_id = %s
                    GROUP BY customer_email
                ) customer_stats
                GROUP BY 
                    CASE 
                        WHEN quote_count = 1 THEN 'One-time'
                        WHEN quote_count = 2 THEN 'Repeat (2)'
                        WHEN quote_count BETWEEN 3 AND 5 THEN 'Regular (3-5)'
                        ELSE 'Frequent (6+)'
                    END
                ORDER BY avg_lifetime_value DESC
            """, (tenant_id,))
            
            customer_segments = cursor.fetchall()
            
            # Convert data types
            for trend in acquisition_trends:
                if trend.get('week'):
                    trend['week'] = trend['week'].isoformat()
            
            for customer in customer_ltv:
                if customer.get('lifetime_value'):
                    customer['lifetime_value'] = float(customer['lifetime_value'])
                if customer.get('avg_quote_value'):
                    customer['avg_quote_value'] = float(customer['avg_quote_value'])
                if customer.get('first_quote_date'):
                    customer['first_quote_date'] = customer['first_quote_date'].isoformat()
                if customer.get('last_quote_date'):
                    customer['last_quote_date'] = customer['last_quote_date'].isoformat()
            
            for segment in customer_segments:
                if segment.get('avg_lifetime_value'):
                    segment['avg_lifetime_value'] = float(segment['avg_lifetime_value'])
            
            return {
                'acquisition_trends': acquisition_trends,
                'top_customers': customer_ltv,
                'customer_segments': customer_segments
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def generate_report(self, tenant_id: str, report_type: str, 
                       start_date: date, end_date: date) -> Dict[str, Any]:
        """Generate comprehensive business report"""
        
        if report_type not in ['summary', 'detailed', 'financial']:
            raise ValidationError("Invalid report type")
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get tenant info
            cursor.execute("""
                SELECT name, slug FROM tenants WHERE id = %s
            """, (tenant_id,))
            
            tenant_info = cursor.fetchone()
            
            report_data = {
                'report_type': report_type,
                'tenant': dict(tenant_info) if tenant_info else {},
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                },
                'generated_at': datetime.utcnow().isoformat()
            }
            
            if report_type in ['summary', 'detailed']:
                # Basic metrics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_quotes,
                        COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_quotes,
                        COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_quotes,
                        COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_quotes,
                        SUM(total_amount) as total_quote_value,
                        SUM(CASE WHEN status = 'approved' THEN total_amount ELSE 0 END) as approved_revenue,
                        AVG(total_amount) as avg_quote_value,
                        COUNT(DISTINCT customer_email) as unique_customers
                    FROM quotes
                    WHERE tenant_id = %s AND created_at >= %s AND created_at <= %s
                """, (tenant_id, start_date, end_date))
                
                metrics = cursor.fetchone()
                report_data['summary_metrics'] = dict(metrics)
                
                # Convert decimal values
                for key, value in report_data['summary_metrics'].items():
                    if isinstance(value, Decimal):
                        report_data['summary_metrics'][key] = float(value)
            
            if report_type == 'detailed':
                # Add detailed breakdowns
                report_data.update({
                    'performance_metrics': self.get_performance_metrics(tenant_id, 
                        (end_date - start_date).days),
                    'customer_analytics': self.get_customer_analytics(tenant_id, 
                        (end_date - start_date).days)
                })
            
            if report_type == 'financial':
                # Financial-specific metrics
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN status = 'approved' THEN subtotal ELSE 0 END) as gross_revenue,
                        SUM(CASE WHEN status = 'approved' THEN tax_amount ELSE 0 END) as tax_collected,
                        SUM(CASE WHEN status = 'approved' THEN total_amount ELSE 0 END) as net_revenue,
                        AVG(CASE WHEN status = 'approved' THEN total_amount END) as avg_deal_size,
                        COUNT(CASE WHEN status = 'approved' THEN 1 END) as closed_deals
                    FROM quotes
                    WHERE tenant_id = %s AND created_at >= %s AND created_at <= %s
                """, (tenant_id, start_date, end_date))
                
                financial_metrics = cursor.fetchone()
                
                # Convert decimal values
                for key, value in financial_metrics.items():
                    if isinstance(value, Decimal):
                        financial_metrics[key] = float(value)
                
                report_data['financial_metrics'] = dict(financial_metrics)
            
            return report_data
            
        finally:
            cursor.close()
            conn.close()


# Global analytics engine instance
analytics_engine = AnalyticsEngine()

