from flask import Blueprint, render_template, redirect, url_for, current_app

page_bp = Blueprint('page_bp', __name__)

def get_firebase_config():
    return {
        'apiKey': current_app.config.get('FIREBASE_API_KEY', ''),
        'authDomain': current_app.config.get('FIREBASE_AUTH_DOMAIN', ''),
        'projectId': current_app.config.get('FIREBASE_PROJECT_ID', ''),
        'storageBucket': current_app.config.get('FIREBASE_STORAGE_BUCKET', ''),
        'messagingSenderId': current_app.config.get('FIREBASE_MESSAGING_SENDER_ID', ''),
        'appId': current_app.config.get('FIREBASE_APP_ID', ''),
    }

@page_bp.route('/')
def index():
    return redirect(url_for('page_bp.dashboard'))

@page_bp.route('/login')
def login():
    return render_template('auth.html', firebase_config=get_firebase_config())

@page_bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', firebase_config=get_firebase_config())

@page_bp.route('/profile')
def profile():
    return render_template('profile.html', firebase_config=get_firebase_config())

@page_bp.route('/income')
def income():
    return render_template('income.html', firebase_config=get_firebase_config())

@page_bp.route('/expenses')
@page_bp.route('/finance')
def expenses():
    return render_template('expenses.html', firebase_config=get_firebase_config())

@page_bp.route('/savings')
def savings():
    return render_template('savings.html', firebase_config=get_firebase_config())

@page_bp.route('/study')
@page_bp.route('/productivity')
def study():
    return render_template('study.html', firebase_config=get_firebase_config())

@page_bp.route('/academics')
def academics():
    return render_template('academics.html', firebase_config=get_firebase_config())

@page_bp.route('/habits')
def habits():
    return render_template('habits.html', firebase_config=get_firebase_config())

@page_bp.route('/fitness')
def fitness():
    return render_template('fitness.html', firebase_config=get_firebase_config())

@page_bp.route('/goals')
def goals():
    return render_template('goals.html', firebase_config=get_firebase_config())

@page_bp.route('/activity-history')
def activity_history():
    return render_template('activity_history.html', firebase_config=get_firebase_config())

@page_bp.route('/simulation')
def simulation():
    return render_template('simulation.html', firebase_config=get_firebase_config())

@page_bp.route('/chat')
@page_bp.route('/assistant')
def chat():
    return render_template('chat.html', firebase_config=get_firebase_config())
