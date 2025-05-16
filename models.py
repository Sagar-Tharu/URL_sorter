from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_url = db.Column(db.String(500), nullable=False)
    short_url = db.Column(db.String(10), unique=True, nullable=False)
    click_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_accessed = db.Column(db.DateTime)
    title = db.Column(db.String(200))
    description = db.Column(db.String(500))
    tags = db.Column(db.String(200))  # Comma-separated tags
    is_active = db.Column(db.Boolean, default=True)
    expiry_date = db.Column(db.DateTime)
    password = db.Column(db.String(100))  # For password-protected URLs
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    ip_address = db.Column(db.String(45))  # For tracking who created the URL
    is_custom = db.Column(db.Boolean, default=False)  # Whether it's a custom URL
    qr_code = db.Column(db.String(200))  # Path to stored QR code image

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    urls = db.relationship('URL', backref='user', lazy=True)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)

class ClickLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url_id = db.Column(db.Integer, db.ForeignKey('url.id'), nullable=False)
    clicked_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(200))
    referrer = db.Column(db.String(500))
    country = db.Column(db.String(2))
    city = db.Column(db.String(100))
    device_type = db.Column(db.String(50))
    browser = db.Column(db.String(50))
    url = db.relationship('URL', backref='clicks')

