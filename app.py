import os
import markdown2
from flask import Flask, render_template, request, flash, redirect, url_for, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, URL, Optional, Length
import threading
from werkzeug.utils import secure_filename
import youtube_analysis
from models import db, User, Analysis, PromptTemplate

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///youtube_analysis.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'output'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
db.init_app(app)

# Create database tables if they don't exist
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

def run_analysis(job_id, url, model, custom_prompt=None, prompt_id=None):
    """Run the analysis in a background thread"""
    try:
        analysis_jobs[job_id]['status'] = 'Downloading audio...'
        audio_file, video_title = youtube_analysis.download_audio(url, 'output')
        
        analysis_jobs[job_id]['status'] = 'Transcribing audio...'
        transcript = youtube_analysis.transcribe_audio(audio_file)
        
        # Get the prompt text
        final_prompt = None
        if prompt_id and prompt_id > 0:
            with app.app_context():
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
        with app.app_context():
            analysis_record = Analysis(
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
    with app.app_context():
        templates = PromptTemplate.query.filter_by(is_default=True).all()
        form.prompt_template.choices = [(0, 'Default')] + [(t.id, t.name) for t in templates]
    
    if form.validate_on_submit():
        url = form.url.data
        model = form.model.data
        prompt_id = form.prompt_template.data
        custom_prompt = form.custom_prompt.data if form.custom_prompt.data else None
        
        # Create a job ID
        job_id = str(len(analysis_jobs) + 1)
        analysis_jobs[job_id] = {
            'status': 'Starting...', 
            'url': url, 
            'model': model,
            'prompt_id': prompt_id if prompt_id else None,
            'custom_prompt': custom_prompt
        }
        
        # Start analysis in background
        thread = threading.Thread(
            target=run_analysis, 
            args=(job_id, url, model, custom_prompt, prompt_id)
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
def prompt_templates():
    with app.app_context():
        templates = PromptTemplate.query.filter_by(is_default=True).all()
    return render_template('prompts.html', templates=templates)

@app.route('/prompt/<int:template_id>')
def view_prompt(template_id):
    with app.app_context():
        template = PromptTemplate.query.get_or_404(template_id)
    return render_template('view_prompt.html', template=template)

if __name__ == '__main__':
    app.run(debug=True)