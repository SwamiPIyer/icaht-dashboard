# config.py - Production-ready configuration
import os
from datetime import timedelta

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production-immediately'
    
    # Database settings - automatically uses PostgreSQL on Heroku
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///icaht_dashboard.db'
    
    # Fix for Heroku PostgreSQL URL format
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
    
    # ICAHT grading parameters
    EARLY_ICAHT_DAYS = int(os.environ.get('EARLY_ICAHT_DAYS', 30))
    LATE_ICAHT_DAYS = int(os.environ.get('LATE_ICAHT_DAYS', 100))
    MAX_GAP_DAYS = int(os.environ.get('MAX_GAP_DAYS', 7))
    RECOVERY_DAYS = int(os.environ.get('RECOVERY_DAYS', 3))
    ANC_THRESHOLD_500 = int(os.environ.get('ANC_THRESHOLD_500', 500))
    ANC_THRESHOLD_100 = int(os.environ.get('ANC_THRESHOLD_100', 100))
    
    # Security settings for production
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
