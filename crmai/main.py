import os
import sys
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory
from flask_cors import CORS
from src.models import db
from src.routes.quotes import quotes_bp
from src.routes.public import public_bp
from src.routes.detection import detection_bp
from src.routes.admin import admin_bp

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Enable CORS for all routes
CORS(app, origins="*")

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'movecrm-dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/movecrm')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['YOLOE_SERVICE_URL'] = os.getenv('YOLOE_SERVICE_URL', 'http://localhost:8001')
app.config['RUNPOD_API_KEY'] = os.getenv('RUNPOD_API_KEY', '')
app.config['S3_BUCKET'] = os.getenv('S3_BUCKET', 'movecrm-uploads')
app.config['S3_ACCESS_KEY'] = os.getenv('S3_ACCESS_KEY', '')
app.config['S3_SECRET_KEY'] = os.getenv('S3_SECRET_KEY', '')
app.config['S3_ENDPOINT'] = os.getenv('S3_ENDPOINT', '')

# Register blueprints
app.register_blueprint(quotes_bp, url_prefix='/api/quotes')
app.register_blueprint(public_bp, url_prefix='/public')
app.register_blueprint(detection_bp, url_prefix='/api/detection')
app.register_blueprint(admin_bp, url_prefix='/api/admin')

# Initialize database
db.init_app(app)
with app.app_context():
    db.create_all()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
