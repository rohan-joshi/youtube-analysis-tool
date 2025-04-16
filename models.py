from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Authentication data
    auth_provider = db.Column(db.String(20))  # 'google', 'github', etc.
    last_login = db.Column(db.DateTime)
    
    # User role and subscription
    role = db.Column(db.String(20), default="user")  # 'user', 'admin'
    subscription_tier = db.Column(db.String(20), default="free")
    subscription_id = db.Column(db.String(100))
    subscription_expires = db.Column(db.DateTime)
    
    # Relationships
    analyses = db.relationship('Analysis', backref='user', lazy=True)
    prompt_templates = db.relationship('PromptTemplate', backref='user', lazy=True)
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_premium(self):
        return self.subscription_tier in ['premium', 'enterprise']
    
    @property
    def monthly_quota(self):
        """Return monthly analysis quota based on subscription tier."""
        if self.subscription_tier == 'premium':
            return 100
        elif self.subscription_tier == 'enterprise':
            return float('inf')  # unlimited
        else:
            return 5  # free tier
    
    def get_analyses_this_month(self):
        """Get count of analyses done this month."""
        start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return Analysis.query.filter_by(
            user_id=self.id
        ).filter(
            Analysis.created_at >= start_of_month
        ).count()
    
    def has_quota_available(self):
        """Check if user has quota available for a new analysis."""
        if self.subscription_tier == 'enterprise':
            return True
        return self.get_analyses_this_month() < self.monthly_quota

class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    video_url = db.Column(db.String(200), nullable=False)
    video_title = db.Column(db.String(200))
    status = db.Column(db.String(20), default="pending")
    model = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    transcript_file = db.Column(db.String(200))
    analysis_file = db.Column(db.String(200))
    custom_prompt = db.Column(db.Text)

class PromptTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    prompt_text = db.Column(db.Text, nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @staticmethod
    def get_default_templates():
        return [
            {
                "name": "Investment Analysis",
                "prompt_text": """
The following is a transcript from a YouTube video titled "{video_title}".

Transcript:
{transcript}

Please provide:
1. A detailed summary of the main ideas with emphasis on explaining the macroeconomic behavior. I understand a lot of economic fundamentals but there are holes in my knowledge so I need some educating on how everything fits together. Explain like i'm 10y/o.
2. Specific investment trades or opportunities suggested or implied
3. Potential risks, downsides, and tradeoffs for each suggested trade
4. Any limitations or biases in the analysis presented in the video

Format your response in clear sections with headings.
                """
            },
            {
                "name": "Technical Analysis",
                "prompt_text": """
The following is a transcript from a YouTube video titled "{video_title}".

Transcript:
{transcript}

Please provide:
1. A summary of the technical analysis presented in the video
2. Key technical indicators mentioned and their significance
3. Price targets and important support/resistance levels discussed
4. Entry and exit points recommended
5. Timeline for the analysis (short-term vs long-term)
6. Any conflicting signals or uncertainties in the analysis

Format your response in clear sections with headings and bullet points where appropriate.
                """
            },
            {
                "name": "Educational Summary",
                "prompt_text": """
The following is a transcript from a YouTube video titled "{video_title}".

Transcript:
{transcript}

Please provide:
1. A comprehensive educational summary of the key concepts discussed
2. Clear explanations of technical terms and jargon for beginners
3. How these concepts relate to current market conditions
4. Historical context or examples that illustrate these concepts
5. Common misconceptions that were addressed
6. Resources or further reading for someone wanting to learn more

Format your response as an educational guide with clear headings, definitions, and examples.
                """
            }
        ]