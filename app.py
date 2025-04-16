import os
import markdown2
from flask import Flask, render_template, request, flash, redirect, url_for, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, URL, Optional, Length
import threading
from werkzeug.utils import secure_filename
from flask_login import current_user, login_required
import youtube_analysis
from models import db, User, Analysis, PromptTemplate
from auth import auth_bp, login_manager, create_oauth_blueprints

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///youtube_analysis.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'output'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
db.init_app(app)

# Initialize Flask-Login
login_manager.init_app(app)

# Register the auth blueprint
app.register_blueprint(auth_bp, url_prefix='/auth')

# Create OAuth blueprints
google_bp, github_bp = create_oauth_blueprints(app)

# Create the database tables
with app.app_context():
    db.create_all()
    # Add default prompt templates if they don't exist
    default_templates = PromptTemplate.query.filter_by(is_default=True).all()
    if not default_templates:
        for template in PromptTemplate.get_default_templates():
            db.session.add(PromptTemplate(
                name=template['name'],
                prompt_text=template['prompt_text'],
                is_default=True
            ))
        db.session.commit()

# Keep track of analysis jobs
analysis_jobs = {}

class YoutubeForm(FlaskForm):
    url = StringField('YouTube URL', validators=[DataRequired(), URL()])
    model = SelectField('LLM Model', choices=[
        ('claude-3-7-sonnet-20250219', 'Claude 3.7 Sonnet'),
        ('claude-3-sonnet-20240229', 'Claude 3 Sonnet'),
        ('gpt-4', 'GPT-4'),
        ('gpt-3.5-turbo', 'GPT-3.5 Turbo')
    ])
    prompt_template = SelectField('Prompt Template', validators=[Optional()], coerce=int)
    custom_prompt = TextAreaField('Custom Prompt', validators=[Optional(), Length(max=5000)],
                              render_kw={"rows": 10, "placeholder": "Enter your custom prompt template here...\n\nUse {video_title} and {transcript} placeholders in your template."})
    submit = SubmitField('Analyze')

def run_analysis(job_id, url, model, custom_prompt=None, prompt_id=None, user_id=None):
    """Run the analysis in a background thread"""
    try:
        analysis_jobs[job_id]['status'] = 'Downloading audio...'
        audio_file, video_title = youtube_analysis.download_audio(url, 'output')
        
        analysis_jobs[job_id]['status'] = 'Transcribing audio...'
        transcript = youtube_analysis.transcribe_audio(audio_file)
        
        # Get the prompt text
        final_prompt = None
        if prompt_id and prompt_id > 0:
            template = PromptTemplate.query.get(prompt_id)
            if template:
                final_prompt = template.prompt_text
        elif custom_prompt:
            final_prompt = custom_prompt
        
        analysis_jobs[job_id]['status'] = 'Analyzing transcript...'
        analysis = youtube_analysis.analyze_with_llm(
            transcript, video_title, model, final_prompt)
        
        analysis_jobs[job_id]['status'] = 'Saving results...'
        transcript_file, analysis_file = youtube_analysis.save_outputs(
            transcript, analysis, video_title, 'output')
        
        # Save analysis to database
        analysis_record = Analysis(
            user_id=user_id,
            video_url=url,
            video_title=video_title,
            status='Completed',
            model=model,
            transcript_file=transcript_file,
            analysis_file=analysis_file,
            custom_prompt=final_prompt if final_prompt else None
        )
        db.session.add(analysis_record)
        db.session.commit()
        
        # Update job with analysis ID
        analysis_jobs[job_id]['analysis_id'] = analysis_record.id
        
        analysis_jobs[job_id]['status'] = 'Completed'
        analysis_jobs[job_id]['result'] = {
            'transcript_file': os.path.basename(transcript_file),
            'analysis_file': os.path.basename(analysis_file),
            'video_title': video_title
        }
    except Exception as e:
        analysis_jobs[job_id]['status'] = 'Failed'
        analysis_jobs[job_id]['error'] = str(e)

@app.route('/', methods=['GET', 'POST'])
def index():
    form = YoutubeForm()
    
    # Get prompt templates for the dropdown
    default_templates = PromptTemplate.query.filter_by(is_default=True).all()
    template_choices = [(0, 'Default')] + [(t.id, t.name) for t in default_templates]
    
    # Add user's custom templates if logged in
    if current_user.is_authenticated:
        user_templates = PromptTemplate.query.filter_by(user_id=current_user.id).all()
        if user_templates:
            template_choices += [(t.id, f"My Template: {t.name}") for t in user_templates]
    
    form.prompt_template.choices = template_choices
    
    if form.validate_on_submit():
        url = form.url.data
        model = form.model.data
        prompt_id = form.prompt_template.data
        custom_prompt = form.custom_prompt.data if form.custom_prompt.data else None
        
        # Check if user has quota (if authenticated)
        user_id = None
        if current_user.is_authenticated:
            user_id = current_user.id
            if not current_user.has_quota_available():
                flash("You've reached your monthly analysis limit. Please upgrade to premium for more analyses.", "warning")
                return redirect(url_for('index'))
        
        # Create a job ID
        job_id = str(len(analysis_jobs) + 1)
        analysis_jobs[job_id] = {
            'status': 'Starting...', 
            'url': url, 
            'model': model,
            'prompt_id': prompt_id if prompt_id else None,
            'custom_prompt': custom_prompt,
            'user_id': user_id
        }
        
        # Start analysis in background
        thread = threading.Thread(
            target=run_analysis, 
            args=(job_id, url, model, custom_prompt, prompt_id, user_id)
        )
        thread.daemon = True
        thread.start()
        
        return redirect(url_for('status', job_id=job_id))
    
    return render_template('index.html', form=form)

@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in analysis_jobs:
        flash('Job not found', 'danger')
        return redirect(url_for('index'))
    
    job = analysis_jobs[job_id]
    return render_template('status.html', job=job, job_id=job_id)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(
        app.config['UPLOAD_FOLDER'], 
        filename,
        as_attachment=True
    )

@app.route('/view/<filename>')
def view_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            
        # Only render markdown for analysis files
        if filename.endswith('_analysis.md'):
            # Convert markdown to HTML
            html_content = markdown2.markdown(
                content,
                extras=['tables', 'code-friendly', 'fenced-code-blocks', 'header-ids']
            )
            return render_template('view_analysis.html', 
                                 title=filename,
                                 html_content=html_content)
        else:
            # Just display plain text for transcript files
            return render_template('view_transcript.html', 
                                 title=filename, 
                                 content=content)
    except Exception as e:
        flash(f"Error loading file: {str(e)}", 'danger')
        return redirect(url_for('history'))

@app.route('/view_analysis/<job_id>')
def view_analysis(job_id):
    if job_id not in analysis_jobs:
        flash('Job not found', 'danger')
        return redirect(url_for('index'))
    
    job = analysis_jobs[job_id]
    
    if job['status'] != 'Completed':
        flash('Analysis not yet completed', 'warning')
        return redirect(url_for('status', job_id=job_id))
    
    # Get the transcript and analysis files
    transcript_file = os.path.join(app.config['UPLOAD_FOLDER'], job['result']['transcript_file'])
    analysis_file = os.path.join(app.config['UPLOAD_FOLDER'], job['result']['analysis_file'])
    
    try:
        # Read transcript
        with open(transcript_file, 'r') as f:
            transcript_content = f.read()
        
        # Read and render analysis as HTML
        with open(analysis_file, 'r') as f:
            analysis_content = f.read()
        
        html_content = markdown2.markdown(
            analysis_content,
            extras=['tables', 'code-friendly', 'fenced-code-blocks', 'header-ids']
        )
        
        return render_template('view_analysis_split.html',
                            title=job['result']['video_title'],
                            transcript_content=transcript_content,
                            html_content=html_content,
                            job=job)
    except Exception as e:
        flash(f"Error loading analysis: {str(e)}", 'danger')
        return redirect(url_for('history'))

@app.route('/history')
def history():
    return render_template('history.html', jobs=analysis_jobs)

@app.route('/prompts')
def prompts():
    # Get default templates
    default_templates = PromptTemplate.query.filter_by(is_default=True).all()
    
    # Get user templates if authenticated
    user_templates = []
    if current_user.is_authenticated:
        user_templates = PromptTemplate.query.filter_by(user_id=current_user.id).all()
    
    return render_template('prompts.html', 
                          default_templates=default_templates,
                          user_templates=user_templates)

@app.route('/prompt/<int:template_id>')
def view_prompt(template_id):
    template = PromptTemplate.query.get_or_404(template_id)
    
    # Check access permissions - users can only view their own or default templates
    if template.user_id and template.user_id != current_user.id:
        flash("You don't have permission to view this template.", "danger")
        return redirect(url_for('prompts'))
        
    return render_template('view_prompt.html', template=template)

@app.route('/prompt/create', methods=['GET', 'POST'])
@login_required
def create_prompt():
    form = PromptTemplateForm()
    
    if form.validate_on_submit():
        template = PromptTemplate(
            user_id=current_user.id,
            name=form.name.data,
            prompt_text=form.prompt_text.data,
            is_default=False
        )
        db.session.add(template)
        db.session.commit()
        
        flash("Prompt template created successfully!", "success")
        return redirect(url_for('view_prompt', template_id=template.id))
    
    return render_template('create_prompt.html', form=form)

# Form for prompt template creation
class PromptTemplateForm(FlaskForm):
    name = StringField('Template Name', validators=[DataRequired()])
    prompt_text = TextAreaField('Prompt Template', validators=[DataRequired()],
                           render_kw={"rows": 15, "placeholder": "Enter your prompt template here...\n\nUse {video_title} and {transcript} placeholders in your template."})
    submit = SubmitField('Save Template')

if __name__ == '__main__':
    app.run(debug=True)