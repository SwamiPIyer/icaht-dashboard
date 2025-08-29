# app.py - Updated Flask application with authentication and database persistence
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
from flask_login import LoginManager, login_required, current_user
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import uuid
from werkzeug.utils import secure_filename
import io
import base64
import hashlib

# Import our models and authentication
from models import db, init_database, User, ProcessingJob, PatientResult, ProcessingAudit
from auth import auth_bp
from utils.data_processor import DataProcessor
from utils.icaht_grader import ICahtGrader
from utils.excel_handler import ExcelHandler
from config import Config

def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access the ICAHT dashboard.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    
    # Initialize database
    with app.app_context():
        init_database(app)
    
    return app

app = create_app()

# Initialize processors
data_processor = DataProcessor()
icaht_grader = ICahtGrader()
excel_handler = ExcelHandler()

def log_audit(job_id, action, details=None):
    """Helper function to log audit trail"""
    audit = ProcessingAudit(
        job_id=job_id,
        user_id=current_user.id,
        action=action,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:255]
    )
    
    if details:
        audit.set_details(details)
    
    db.session.add(audit)
    db.session.commit()

def calculate_file_hash(filepath):
    """Calculate MD5 hash of file for duplicate detection"""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

@app.route('/')
@login_required
def index():
    """Main dashboard page - now requires login"""
    # Get user's recent jobs
    recent_jobs = ProcessingJob.query.filter_by(user_id=current_user.id)\
                                   .order_by(ProcessingJob.created_at.desc())\
                                   .limit(5).all()
    
    return render_template('index.html', recent_jobs=recent_jobs)

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    """Handle file upload and initial validation - now with persistence"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'error': 'Please upload an Excel file (.xlsx or .xls)'}), 400
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}_{filename}")
        file.save(filepath)
        
        # Calculate file hash and size
        file_hash = calculate_file_hash(filepath)
        file_size = os.path.getsize(filepath)
        
        # Check for duplicate files
        existing_job = ProcessingJob.query.filter_by(
            user_id=current_user.id,
            file_hash=file_hash
        ).first()
        
        if existing_job:
            os.remove(filepath)  # Clean up uploaded file
            return jsonify({
                'warning': f'This file was already processed on {existing_job.created_at.strftime("%Y-%m-%d %H:%M")}',
                'existing_job_id': existing_job.id,
                'suggestion': 'Would you like to view the existing results instead?'
            }), 409
        
        # Validate file structure
        validation_result = excel_handler.validate_file(filepath)
        if not validation_result['valid']:
            os.remove(filepath)  # Clean up invalid file
            return jsonify({'error': validation_result['message']}), 400
        
        # Load and preview data
        df = excel_handler.load_data(filepath)
        preview_data = df.head(10).to_dict('records')
        
        # Create processing job record
        job_name = f"ICAHT Analysis - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        job = ProcessingJob(
            user_id=current_user.id,
            job_name=job_name,
            original_filename=file.filename,
            file_hash=file_hash,
            file_size=file_size,
            status='uploaded'
        )
        
        db.session.add(job)
        db.session.commit()
        
        # Log audit trail
        log_audit(job.id, 'upload', {
            'filename': file.filename,
            'file_size': file_size,
            'row_count': len(df),
            'patient_count': df['patient_id'].nunique() if 'patient_id' in df.columns else 0
        })
        
        return jsonify({
            'job_id': job.id,
            'file_id': file_id,  # Still needed for backward compatibility
            'filename': file.filename,
            'row_count': len(df),
            'preview': preview_data,
            'columns': list(df.columns),
            'patients': df['patient_id'].nunique() if 'patient_id' in df.columns else 0
        })
        
    except Exception as e:
        return jsonify({'error': f'File processing failed: {str(e)}'}), 500

@app.route('/api/process', methods=['POST'])
@login_required
def process_icaht():
    """Process ICAHT grading - now with database persistence"""
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        settings = data.get('settings', {})
        
        if not job_id:
            return jsonify({'error': 'Job ID required'}), 400
        
        # Get job and verify ownership
        job = ProcessingJob.query.filter_by(id=job_id, user_id=current_user.id).first()
        if not job:
            return jsonify({'error': 'Job not found or access denied'}), 404
        
        # Find uploaded file
        upload_dir = app.config['UPLOAD_FOLDER']
        filepath = None
        for filename in os.listdir(upload_dir):
            if filename.startswith(f"{data.get('file_id', '')}_"):
                filepath = os.path.join(upload_dir, filename)
                break
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        # Update job status and settings
        job.status = 'processing'
        job.started_at = datetime.utcnow()
        job.set_settings(settings)
        db.session.commit()
        
        # Log processing start
        log_audit(job.id, 'process_start', {'settings': settings})
        
        # Load data
        df = excel_handler.load_data(filepath)
        
        # Process data
        processed_data = data_processor.prepare_data(df, settings)
        
        # Grade ICAHT
        early_grades = icaht_grader.grade_early_icaht(processed_data['early'])
        late_grades = icaht_grader.grade_late_icaht(processed_data['late'])
        
        # Combine results
        final_grades = icaht_grader.combine_grades(early_grades, late_grades)
        
        # Store results in database
        for _, row in final_grades.iterrows():
            result = PatientResult(
                job_id=job.id,
                patient_id=row['patient_id'],
                early_icaht_grade=row.get('early_icaht_grade'),
                duration_below_500_max=row.get('duration_below_500_max', 0),
                duration_below_100_max=row.get('duration_below_100_max', 0),
                grade_4_special=row.get('grade_4_special', False),
                late_icaht_grade=row.get('late_icaht_grade'),
                anc_1=row.get('anc_1'),
                anc_2=row.get('anc_2'),
                anc_count=row.get('anc_count', 0)
            )
            db.session.add(result)
        
        # Update job completion
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        job.total_patients = len(final_grades)
        job.grade_4_special_cases = final_grades.get('grade_4_special', False).sum()
        db.session.commit()
        
        # Generate summary statistics
        summary = icaht_grader.generate_summary(final_grades, processed_data)
        
        # Log processing completion
        log_audit(job.id, 'process_complete', {
            'total_patients': len(final_grades),
            'summary': summary
        })
        
        # Clean up uploaded file
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'job_id': job.id,
            'results': final_grades.to_dict('records'),
            'summary': summary,
            'processed_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        # Update job with error
        if 'job' in locals():
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.session.commit()
            
            log_audit(job.id, 'process_error', {'error': str(e)})
        
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@app.route('/api/job-history')
@login_required
def get_job_history():
    """Get user's processing job history"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        jobs_query = ProcessingJob.query.filter_by(user_id=current_user.id)\
                                      .order_by(ProcessingJob.created_at.desc())
        
        jobs_paginated = jobs_query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        jobs_data = []
        for job in jobs_paginated.items:
            job_data = {
                'id': job.id,
                'job_name': job.job_name,
                'original_filename': job.original_filename,
                'status': job.status,
                'created_at': job.created_at.isoformat(),
                'total_patients': job.total_patients,
                'grade_4_special_cases': job.grade_4_special_cases
            }
            
            if job.completed_at:
                job_data['completed_at'] = job.completed_at.isoformat()
                duration = job.get_duration()
                if duration:
                    job_data['duration_seconds'] = duration.total_seconds()
            
            if job.error_message:
                job_data['error_message'] = job.error_message
            
            jobs_data.append(job_data)
        
        return jsonify({
            'jobs': jobs_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': jobs_paginated.total,
                'pages': jobs_paginated.pages,
                'has_next': jobs_paginated.has_next,
                'has_prev': jobs_paginated.has_prev
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to load job history: {str(e)}'}), 500

@app.route('/api/job-results/<int:job_id>')
@login_required
def get_job_results(job_id):
    """Get results for a specific job"""
    try:
        # Verify job ownership
        job = ProcessingJob.query.filter_by(id=job_id, user_id=current_user.id).first()
        if not job:
            return jsonify({'error': 'Job not found or access denied'}), 404
        
        if job.status != 'completed':
            return jsonify({'error': 'Job is not completed'}), 400
        
        # Get results
        results = PatientResult.query.filter_by(job_id=job_id).all()
        
        results_data = [result.to_dict() for result in results]
        
        # Generate summary from stored data
        summary = {
            'total_patients': job.total_patients,
            'grade_4_special_cases': job.grade_4_special_cases,
            'job_info': {
                'name': job.job_name,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat(),
                'settings': job.get_settings()
            }
        }
        
        # Log view action
        log_audit(job.id, 'view_results')
        
        return jsonify({
            'results': results_data,
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to load results: {str(e)}'}), 500

@app.route('/api/export', methods=['POST'])
@login_required
def export_results():
    """Export results to Excel - with audit logging"""
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        
        if job_id:
            # Export specific job
            job = ProcessingJob.query.filter_by(id=job_id, user_id=current_user.id).first()
            if not job:
                return jsonify({'error': 'Job not found or access denied'}), 404
            
            results = PatientResult.query.filter_by(job_id=job_id).all()
            results_df = pd.DataFrame([result.to_dict() for result in results])
            
            log_audit(job.id, 'export')
        else:
            # Legacy: export from provided results data
            results_data = data.get('results', [])
            if not results_data:
                return jsonify({'error': 'No results to export'}), 400
            
            results_df = pd.DataFrame(results_data)
        
        if results_df.empty:
            return jsonify({'error': 'No results to export'}), 400
        
        # Create Excel file in memory
        output = io.BytesIO()
        excel_handler.export_results(results_df, output)
        output.seek(0)
        
        # Encode for download
        excel_data = base64.b64encode(output.getvalue()).decode()
        
        filename = f'ICAHT_Grades_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return jsonify({
            'excel_data': excel_data,
            'filename': filename
        })
        
    except Exception as e:
        return jsonify({'error': f'Export failed: {str(e)}'}), 500

@app.route('/api/sample-data')
@login_required
def get_sample_data():
    """Provide sample data for testing"""
    try:
        sample_file = os.path.join('sample_data', 'Synthetic_ANC_Dataset.xlsx')
        if not os.path.exists(sample_file):
            return jsonify({'error': 'Sample data not available'}), 404
        
        df = excel_handler.load_data(sample_file)
        
        return jsonify({
            'data': df.to_dict('records'),
            'columns': list(df.columns),
            'row_count': len(df),
            'patients': df['patient_id'].nunique()
        })
        
    except Exception as e:
        return jsonify({'error': f'Sample data loading failed: {str(e)}'}), 500

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

if __name__ == '__main__':
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
