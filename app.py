import os
from flask import Flask, render_template, request, flash, redirect, url_for, send_from_directory
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField
from wtforms.validators import DataRequired, URL
import threading
from werkzeug.utils import secure_filename
import youtube_analysis

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'output'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
    submit = SubmitField('Analyze')

def run_analysis(job_id, url, model):
    """Run the analysis in a background thread"""
    try:
        analysis_jobs[job_id]['status'] = 'Downloading audio...'
        audio_file, video_title = youtube_analysis.download_audio(url, 'output')
        
        analysis_jobs[job_id]['status'] = 'Transcribing audio...'
        transcript = youtube_analysis.transcribe_audio(audio_file)
        
        analysis_jobs[job_id]['status'] = 'Analyzing transcript...'
        analysis = youtube_analysis.analyze_with_llm(transcript, video_title, model)
        
        analysis_jobs[job_id]['status'] = 'Saving results...'
        transcript_file, analysis_file = youtube_analysis.save_outputs(
            transcript, analysis, video_title, 'output')
        
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
    if form.validate_on_submit():
        url = form.url.data
        model = form.model.data
        
        # Create a job ID
        job_id = str(len(analysis_jobs) + 1)
        analysis_jobs[job_id] = {'status': 'Starting...', 'url': url, 'model': model}
        
        # Start analysis in background
        thread = threading.Thread(target=run_analysis, args=(job_id, url, model))
        thread.daemon = True
        thread.start()
        
        return redirect(url_for('status', job_id=job_id))
    
    return render_template('index.html', form=form)

@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in analysis_jobs:
        flash('Job not found')
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

@app.route('/history')
def history():
    return render_template('history.html', jobs=analysis_jobs)

if __name__ == '__main__':
    app.run(debug=True)