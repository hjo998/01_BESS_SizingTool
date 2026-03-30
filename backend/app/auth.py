"""BESS Sizing Tool — Authentication Blueprint."""
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .shared_models import create_user, get_user_by_username, get_user_by_id, update_last_login

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login')
def login_page():
    """Render login page."""
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    return render_template('login.html')


@auth_bp.route('/register')
def register_page():
    """Render registration page."""
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    return render_template('register.html')


@auth_bp.route('/api/login', methods=['POST'])
def login():
    """Authenticate user and create session."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    db_path = current_app.config['DATABASE']
    user = get_user_by_username(db_path, username)

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid username or password'}), 401

    if not user['is_active']:
        return jsonify({'error': 'Account is deactivated'}), 403

    # Set session
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['display_name'] = user['display_name']
    session['user_role'] = user['role']

    update_last_login(db_path, user['id'])

    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user['id'],
            'username': user['username'],
            'display_name': user['display_name'],
            'department': user['department'],
            'role': user['role']
        }
    })


@auth_bp.route('/api/register', methods=['POST'])
def register():
    """Register a new user."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    display_name = data.get('display_name', '').strip()
    department = data.get('department', '').strip() or None

    # Validation
    errors = []
    if not username or len(username) < 3:
        errors.append('Username must be at least 3 characters')
    if not email or '@' not in email:
        errors.append('Valid email is required')
    if not password or len(password) < 4:
        errors.append('Password must be at least 4 characters')
    if not display_name:
        errors.append('Display name is required')
    if errors:
        return jsonify({'error': '; '.join(errors)}), 400

    db_path = current_app.config['DATABASE']

    # Check duplicates
    existing = get_user_by_username(db_path, username)
    if existing:
        return jsonify({'error': 'Username already taken'}), 409

    password_hash = generate_password_hash(password)
    user_id = create_user(db_path, username, email, password_hash, display_name, department)

    return jsonify({
        'message': 'Registration successful',
        'user': {
            'id': user_id,
            'username': username,
            'display_name': display_name
        }
    }), 201


@auth_bp.route('/api/logout', methods=['POST'])
def logout():
    """Clear user session."""
    session.clear()
    return jsonify({'message': 'Logged out'})


@auth_bp.route('/me')
def me():
    """Return current user info or redirect to login."""
    if 'user_id' not in session:
        if request.headers.get('Accept', '').startswith('application/json'):
            return jsonify({'error': 'Not logged in'}), 401
        return redirect(url_for('auth.login_page'))

    db_path = current_app.config['DATABASE']
    user = get_user_by_id(db_path, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login_page'))

    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'display_name': user['display_name'],
        'department': user['department'],
        'role': user['role']
    })
