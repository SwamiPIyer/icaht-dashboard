# auth.py - Authentication blueprint with login/logout
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, create_user
from functools import wraps

# Create authentication blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

def admin_required(f):
    """Decorator to require admin role for certain routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            if request.is_json:
                return jsonify({'error': 'Admin access required'}), 403
            flash('Admin access required', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        if request.is_json:
            # Handle AJAX login request
            data = request.get_json()
            username = data.get('username', '').strip()
            password = data.get('password', '')
        else:
            # Handle form submission
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
        
        if not username or not password:
            error_msg = 'Username and password are required'
            if request.is_json:
                return jsonify({'error': error_msg}), 400
            flash(error_msg, 'error')
            return render_template('auth/login.html')
        
        # Find user by username or email
        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).filter_by(is_active=True).first()
        
        if user and user.check_password(password):
            # Successful login
            login_user(user, remember=True)
            user.update_last_login()
            
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': 'Login successful',
                    'redirect': url_for('index'),
                    'user': {
                        'username': user.username,
                        'role': user.role
                    }
                })
            
            flash(f'Welcome back, {user.username}!', 'success')
            
            # Redirect to next page or dashboard
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        
        else:
            # Failed login
            error_msg = 'Invalid username or password'
            if request.is_json:
                return jsonify({'error': error_msg}), 401
            flash(error_msg, 'error')
    
    # GET request - show login form
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    username = current_user.username
    logout_user()
    flash(f'You have been logged out. Goodbye, {username}!', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration (if enabled)"""
    # You can disable registration in production by adding a check here
    # if not app.config.get('REGISTRATION_ENABLED', False):
    #     return abort(404)
    
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json()
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            confirm_password = data.get('confirm_password', '')
        else:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters long')
        
        if not email or '@' not in email:
            errors.append('Valid email address is required')
        
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters long')
        
        if password != confirm_password:
            errors.append('Passwords do not match')
        
        if errors:
            error_msg = '; '.join(errors)
            if request.is_json:
                return jsonify({'error': error_msg}), 400
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html')
        
        # Create user
        user, message = create_user(username, email, password)
        
        if user:
            # Registration successful
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': 'Registration successful! You can now log in.',
                    'redirect': url_for('auth.login')
                })
            
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('auth.login'))
        else:
            # Registration failed
            if request.is_json:
                return jsonify({'error': message}), 400
            flash(message, 'error')
    
    return render_template('auth/register.html')

@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    # Get user's job history
    jobs = current_user.processing_jobs[:10]  # Last 10 jobs
    
    return render_template('auth/profile.html', user=current_user, jobs=jobs)

@auth_bp.route('/api/user-info')
@login_required
def user_info():
    """API endpoint to get current user info"""
    return jsonify({
        'user_id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'role': current_user.role,
        'last_login': current_user.last_login.isoformat() if current_user.last_login else None,
        'created_at': current_user.created_at.isoformat()
    })

@auth_bp.route('/admin/users')
@admin_required
def admin_users():
    """Admin page to manage users"""
    users = User.query.all()
    return render_template('auth/admin_users.html', users=users)

@auth_bp.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    """Toggle user active/inactive status"""
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot modify your own account'}), 400
    
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'User {user.username} has been {status}', 'success')
    
    if request.is_json:
        return jsonify({'success': True, 'is_active': user.is_active})
    
    return redirect(url_for('auth.admin_users'))

@auth_bp.route('/admin/create-user', methods=['POST'])
@admin_required
def admin_create_user():
    """Admin function to create new user"""
    data = request.get_json() if request.is_json else request.form
    
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'user')
    
    if not all([username, email, password]):
        error_msg = 'Username, email, and password are required'
        if request.is_json:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, 'error')
        return redirect(url_for('auth.admin_users'))
    
    user, message = create_user(username, email, password, role)
    
    if user:
        success_msg = f'User {username} created successfully'
        if request.is_json:
            return jsonify({'success': True, 'message': success_msg})
        flash(success_msg, 'success')
    else:
        if request.is_json:
            return jsonify({'error': message}), 400
        flash(message, 'error')
    
    return redirect(url_for('auth.admin_users'))# models.py - Complete database models for authentication and persistence
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
