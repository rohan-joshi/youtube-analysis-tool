import os
from flask import Blueprint, redirect, url_for, flash, session, current_app, request
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.contrib.github import make_github_blueprint, github
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from sqlalchemy.orm.exc import NoResultFound
from models import db, User

# Create Blueprint for auth routes
auth_bp = Blueprint('auth', __name__)

# Initialize login manager
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# Load user function for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Function to create OAuth blueprints
def create_oauth_blueprints(app):
    # Configure Google OAuth
    google_bp = make_google_blueprint(
        client_id=os.environ.get("GOOGLE_CLIENT_ID", "placeholder-id"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", "placeholder-secret"),
        scope=["profile", "email"],
        redirect_to="auth.google_login_callback"
    )
    
    # Configure GitHub OAuth
    github_bp = make_github_blueprint(
        client_id=os.environ.get("GITHUB_CLIENT_ID", "placeholder-id"),
        client_secret=os.environ.get("GITHUB_CLIENT_SECRET", "placeholder-secret"),
        scope=["user:email"],
        redirect_to="auth.github_login_callback"
    )
    
    app.register_blueprint(google_bp, url_prefix="/login")
    app.register_blueprint(github_bp, url_prefix="/login")
    
    return google_bp, github_bp

# Login page route
@auth_bp.route('/login')
def login():
    # Only show login page if user is not already logged in
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    return redirect(url_for('auth.login_options'))

# Login options page
@auth_bp.route('/login_options')
def login_options():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    return render_template('login.html')

# Google login callback
@auth_bp.route('/login/google/callback')
def google_login_callback():
    if not google.authorized:
        flash("Login failed with Google.", "danger")
        return redirect(url_for('auth.login_options'))
    
    resp = google.get("/oauth2/v1/userinfo")
    if not resp.ok:
        flash("Failed to get user info from Google.", "danger")
        return redirect(url_for('auth.login_options'))
    
    user_info = resp.json()
    email = user_info["email"]
    name = user_info.get("name", email.split('@')[0])
    
    # Check if user exists
    user = User.query.filter_by(email=email).first()
    
    if not user:
        # Create new user
        user = User(email=email, name=name)
        db.session.add(user)
        db.session.commit()
        flash("Account created successfully!", "success")
    
    # Log in the user
    login_user(user)
    flash(f"Welcome, {user.name}!", "success")
    
    # Redirect to the page the user was trying to access, or to the index
    next_page = session.get('next', url_for('index'))
    return redirect(next_page)

# GitHub login callback
@auth_bp.route('/login/github/callback')
def github_login_callback():
    if not github.authorized:
        flash("Login failed with GitHub.", "danger")
        return redirect(url_for('auth.login_options'))
    
    resp = github.get("/user")
    if not resp.ok:
        flash("Failed to get user info from GitHub.", "danger")
        return redirect(url_for('auth.login_options'))
    
    user_info = resp.json()
    
    # GitHub doesn't always return email in user info, so we need to get emails separately
    email_resp = github.get("/user/emails")
    if not email_resp.ok:
        flash("Failed to get email from GitHub.", "danger")
        return redirect(url_for('auth.login_options'))
    
    emails = email_resp.json()
    if not emails:
        flash("No email found in your GitHub account.", "danger")
        return redirect(url_for('auth.login_options'))
    
    # Get primary or first email
    primary_emails = [e for e in emails if e.get('primary')]
    email = primary_emails[0]['email'] if primary_emails else emails[0]['email']
    
    name = user_info.get("name")
    if not name:
        name = user_info.get("login") or email.split('@')[0]
    
    # Check if user exists
    user = User.query.filter_by(email=email).first()
    
    if not user:
        # Create new user
        user = User(email=email, name=name)
        db.session.add(user)
        db.session.commit()
        flash("Account created successfully!", "success")
    
    # Log in the user
    login_user(user)
    flash(f"Welcome, {user.name}!", "success")
    
    # Redirect to the page the user was trying to access, or to the index
    next_page = session.get('next', url_for('index'))
    return redirect(next_page)

# Logout route
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))

# User profile route
@auth_bp.route('/profile')
@login_required
def profile():
    analyses = Analysis.query.filter_by(user_id=current_user.id).order_by(Analysis.created_at.desc()).all()
    return render_template('profile.html', user=current_user, analyses=analyses)

# Import the missing render_template function
from flask import render_template
from models import Analysis