"""BESS Sizing Tool — Auth decorators."""
from functools import wraps
from flask import session, redirect, url_for, request, jsonify


def login_required(f):
    """Require authenticated user. API calls get 401, pages redirect to login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Login required'}), 401
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Require admin role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Login required'}), 401
            return redirect(url_for('auth.login_page'))
        if session.get('user_role') != 'admin':
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Admin access required'}), 403
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


def get_current_user_id():
    """Get current user id from session, or None."""
    return session.get('user_id')
