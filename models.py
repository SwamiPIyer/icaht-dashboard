# models.py - Complete database models for authentication and persistence
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model for authentication"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'user' or 'admin'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationship to processing jobs
    processing_jobs = db.relationship('ProcessingJob', backref='user', cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<User {self.username}>'

class ProcessingJob(db.Model):
    """Track processing jobs and their results"""
    __tablename__ = 'processing_jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Job details
    job_name = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, processing, completed, failed
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Error handling
    error_message = db.Column(db.Text)
    
    # Processing settings (stored as JSON)
    settings = db.Column(db.Text)
    
    # Results summary
    total_patients = db.Column(db.Integer, default=0)
    grade_4_special_cases = db.Column(db.Integer, default=0)
    
    # File information
    file_size = db.Column(db.Integer)  # in bytes
    file_hash = db.Column(db.String(64))  # for duplicate detection
    
    # Relationships
    results = db.relationship('PatientResult', backref='job', cascade='all, delete-orphan')
    audit_logs = db.relationship('ProcessingAudit', backref='job', cascade='all, delete-orphan')
    
    def set_settings(self, settings_dict):
        """Store settings as JSON string"""
        self.settings = json.dumps(settings_dict)
    
    def get_settings(self):
        """Retrieve settings from JSON string"""
        if self.settings:
            return json.loads(self.settings)
        return {}
    
    def get_duration(self):
        """Calculate processing duration"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    def __repr__(self):
        return f'<ProcessingJob {self.id}: {self.job_name}>'

class PatientResult(db.Model):
    """Store individual patient ICAHT grading results"""
    __tablename__ = 'patient_results'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('processing_jobs.id'), nullable=False)
    patient_id = db.Column(db.String(100), nullable=False)
    
    # Early ICAHT results
    early_icaht_grade = db.Column(db.String(20))
    duration_below_500_max = db.Column(db.Integer, default=0)
    duration_below_100_max = db.Column(db.Integer, default=0)
    grade_4_special = db.Column(db.Boolean, default=False)
    exceedances_500 = db.Column(db.Integer, default=0)
    exceedances_100 = db.Column(db.Integer, default=0)
    
    # Late ICAHT results
    late_icaht_grade = db.Column(db.String(20))
    anc_1 = db.Column(db.Float)  # Lowest ANC value
    anc_2 = db.Column(db.Float)  # Second lowest ANC value
    anc_count = db.Column(db.Integer, default=0)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """Convert result to dictionary for JSON response"""
        return {
            'patient_id': self.patient_id,
            'early_icaht_grade': self.early_icaht_grade,
            'late_icaht_grade': self.late_icaht_grade,
            'duration_below_500_max': self.duration_below_500_max,
            'duration_below_100_max': self.duration_below_100_max,
            'grade_4_special': self.grade_4_special,
            'anc_1': self.anc_1,
            'anc_2': self.anc_2,
            'anc_count': self.anc_count
        }
    
    def __repr__(self):
        return f'<PatientResult {self.patient_id}: Early {self.early_icaht_grade}, Late {self.late_icaht_grade}>'

class ProcessingAudit(db.Model):
    """Audit trail for processing operations"""
    __tablename__ = 'processing_audits'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('processing_jobs.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    action = db.Column(db.String(100), nullable=False)  # 'upload', 'validate', 'process', 'export', 'view'
    details = db.Column(db.Text)  # JSON string with additional details
    ip_address = db.Column(db.String(45))  # IPv4 or IPv6
    user_agent = db.Column(db.String(255))
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_details(self, details_dict):
        """Store details as JSON string"""
        self.details = json.dumps(details_dict)
    
    def get_details(self):
        """Retrieve details from JSON string"""
        if self.details:
            return json.loads(self.details)
        return {}
    
    def __repr__(self):
        return f'<ProcessingAudit {self.action} by User {self.user_id}>'

# Database utility functions
def init_database(app):
    """Initialize database with app context"""
    with app.app_context():
        db.create_all()
        
        # Create default admin user if none exists
        admin_user = User.query.filter_by(role='admin').first()
        if not admin_user:
            admin = User(
                username='admin',
                email='admin@icaht.local',
                role='admin'
            )
            admin.set_password('admin123')  # Change this in production!
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created: admin/admin123")

def create_user(username, email, password, role='user'):
    """Helper function to create a new user"""
    # Check if user already exists
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return None, "User with this username or email already exists"
    
    user = User(username=username, email=email, role=role)
    user.set_password(password)
    
    try:
        db.session.add(user)
        db.session.commit()
        return user, "User created successfully"
    except Exception as e:
        db.session.rollback()
        return None, f"Error creating user: {str(e)}"
