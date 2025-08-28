from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime
import uuid

app = Flask(__name__)
CORS(app, origins="*")

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'movecrm'),
        user=os.getenv('DB_USER', 'movecrm'),
        password=os.getenv('DB_PASSWORD', 'movecrm_password')
    )

# Health check endpoint
@app.route('/health')
def health():
    try:
        conn = get_db_connection()
        conn.close()
        db_status = 'connected'
    except:
        db_status = 'disconnected'
    
    return jsonify({
        'status': 'healthy',
        'service': 'backend',
        'database': db_status,
        'version': '1.0'
    })

# Root endpoint
@app.route('/')
def root():
    return jsonify({
        'service': 'MoveCRM Backend API',
        'version': '1.0',
        'endpoints': [
            '/health',
            '/api/quotes (GET, POST)',
            '/api/quotes/<id> (GET)',
            '/api/estimate (POST)'
        ]
    })

# Create quote
@app.route('/api/quotes', methods=['POST'])
def create_quote():
    try:
        data = request.json
        
        # Generate quote number
        quote_number = f"QUOTE-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        
        # Connect to database
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get default tenant (demo)
        cursor.execute("SELECT id FROM tenants WHERE slug = 'demo' LIMIT 1")
        tenant = cursor.fetchone()
        tenant_id = tenant['id'] if tenant else None
        
        # Calculate estimate (simple calculation)
        total_cubic_feet = data.get('totalCubicFeet', 0)
        rate_per_cubic_foot = 1.50  # Default rate
        labor_hours = total_cubic_feet / 50  # Rough estimate
        labor_rate = 75.00  # Per hour
        
        subtotal = (total_cubic_feet * rate_per_cubic_foot) + (labor_hours * labor_rate)
        tax_amount = subtotal * 0.08  # 8% tax
        total_amount = subtotal + tax_amount
        
        # Insert quote
        insert_query = """
            INSERT INTO quotes (
                tenant_id, quote_number, customer_email, customer_name, 
                customer_phone, pickup_address, delivery_address, move_date,
                notes, total_cubic_feet, total_labor_hours, subtotal, 
                tax_amount, total_amount, status
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending'
            ) RETURNING id, quote_number, total_amount
        """
        
        cursor.execute(insert_query, (
            tenant_id,
            quote_number,
            data.get('customerEmail', ''),
            data.get('customerName', ''),
            data.get('customerPhone', ''),
            data.get('pickupAddress', ''),
            data.get('deliveryAddress', ''),
            data.get('moveDate'),
            data.get('notes', ''),
            total_cubic_feet,
            labor_hours,
            subtotal,
            tax_amount,
            total_amount
        ))
        
        quote = cursor.fetchone()
        quote_id = quote['id']
        
        # Insert quote items
        items = data.get('items', [])
        for item in items:
            cursor.execute("""
                INSERT INTO quote_items (quote_id, item_name, quantity, price)
                VALUES (%s, %s, %s, %s)
            """, (
                quote_id,
                item.get('name', 'Unknown'),
                item.get('quantity', 1),
                item.get('cubicFeet', 0) * rate_per_cubic_foot
            ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'quote_number': quote_number,
            'estimated_total': round(total_amount, 2),
            'message': 'Quote created successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error creating quote: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to create quote',
            'error': str(e)
        }), 500

# Get all quotes
@app.route('/api/quotes', methods=['GET'])
def get_quotes():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, quote_number, customer_name, customer_email, 
                   total_amount, status, created_at
            FROM quotes
            ORDER BY created_at DESC
            LIMIT 100
        """)
        
        quotes = cursor.fetchall()
        
        # Convert datetime objects to strings
        for quote in quotes:
            if quote.get('created_at'):
                quote['created_at'] = quote['created_at'].isoformat()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'quotes': quotes,
            'count': len(quotes)
        })
        
    except Exception as e:
        app.logger.error(f"Error fetching quotes: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch quotes',
            'error': str(e)
        }), 500

# Get single quote
@app.route('/api/quotes/<quote_id>')
def get_quote(quote_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get quote
        cursor.execute("""
            SELECT * FROM quotes WHERE id = %s OR quote_number = %s
        """, (quote_id, quote_id))
        
        quote = cursor.fetchone()
        
        if not quote:
            return jsonify({
                'status': 'error',
                'message': 'Quote not found'
            }), 404
        
        # Get quote items
        cursor.execute("""
            SELECT * FROM quote_items WHERE quote_id = %s
        """, (quote['id'],))
        
        items = cursor.fetchall()
        quote['items'] = items
        
        # Convert datetime objects
        if quote.get('created_at'):
            quote['created_at'] = quote['created_at'].isoformat()
        if quote.get('move_date'):
            quote['move_date'] = quote['move_date'].isoformat()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'quote': quote
        })
        
    except Exception as e:
        app.logger.error(f"Error fetching quote: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch quote',
            'error': str(e)
        }), 500

# Quick estimate endpoint
@app.route('/api/estimate', methods=['POST'])
def get_estimate():
    try:
        data = request.json
        
        # Simple estimation logic
        total_cubic_feet = data.get('totalCubicFeet', 0)
        distance = data.get('distance', 10)  # Default 10 miles
        
        # Rates
        rate_per_cubic_foot = 1.50
        rate_per_mile = 2.00
        labor_rate = 75.00
        
        # Calculate
        labor_hours = total_cubic_feet / 50
        space_cost = total_cubic_feet * rate_per_cubic_foot
        labor_cost = labor_hours * labor_rate
        travel_cost = distance * rate_per_mile
        
        subtotal = space_cost + labor_cost + travel_cost
        tax = subtotal * 0.08
        total = subtotal + tax
        
        return jsonify({
            'status': 'success',
            'estimate': {
                'cubic_feet': total_cubic_feet,
                'labor_hours': round(labor_hours, 1),
                'space_cost': round(space_cost, 2),
                'labor_cost': round(labor_cost, 2),
                'travel_cost': round(travel_cost, 2),
                'subtotal': round(subtotal, 2),
                'tax': round(tax, 2),
                'total': round(total, 2)
            }
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to calculate estimate',
            'error': str(e)
        }), 500

# Authentication endpoints (mock for now)
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    # Mock authentication
    if email and password:
        return jsonify({
            'status': 'success',
            'token': str(uuid.uuid4()),
            'user': {
                'email': email,
                'role': 'admin'
            }
        })
    
    return jsonify({
        'status': 'error',
        'message': 'Invalid credentials'
    }), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    return jsonify({
        'status': 'success',
        'message': 'Logged out successfully'
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
