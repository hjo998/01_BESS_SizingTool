"""BESS Sizing Tool — Shared Design API Blueprint."""
import json
from flask import Blueprint, current_app, jsonify, render_template, request, session

from .decorators import login_required, admin_required, get_current_user_id
from .shared_models import (
    create_design, get_design_by_id, list_designs, update_design,
    submit_design, unlock_design, relock_design, create_new_revision,
    delete_design, get_audit_log, get_project_revisions
)

shared_bp = Blueprint('shared', __name__)


# ─── Page routes ────────────────────────────────────────────

@shared_bp.route('/admin/audit')
@admin_required
def admin_audit_page():
    """Admin audit log page."""
    return render_template('admin_audit.html')


@shared_bp.route('/shared/')
@login_required
def shared_list():
    """Shared designs list page."""
    return render_template('shared_list.html')


@shared_bp.route('/shared/<int:design_id>')
@login_required
def shared_detail(design_id):
    """Shared design detail page."""
    db_path = current_app.config['DATABASE']
    design = get_design_by_id(db_path, design_id)
    if not design:
        return render_template('shared_list.html'), 404
    return render_template('shared_detail.html', design=design)


@shared_bp.route('/shared/project/<path:project_name>/revisions')
@login_required
def revision_timeline(project_name):
    """Revision timeline page for a project."""
    db_path = current_app.config['DATABASE']
    revisions = get_project_revisions(db_path, project_name)
    return render_template('shared_list.html',
                         project_filter=project_name,
                         revisions=revisions)


# ─── API routes ─────────────────────────────────────────────

@shared_bp.route('/api/shared/designs', methods=['GET'])
@login_required
def api_list_designs():
    """List designs with filters and pagination."""
    db_path = current_app.config['DATABASE']
    result = list_designs(
        db_path,
        project=request.args.get('project'),
        status=request.args.get('status'),
        user_id=request.args.get('user', type=int),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        sort=request.args.get('sort', 'updated_at'),
        page=request.args.get('page', 1, type=int),
        per_page=request.args.get('per_page', 20, type=int),
    )
    return jsonify(result)


@shared_bp.route('/api/shared/designs', methods=['POST'])
@login_required
def api_create_design():
    """Upload a new design to shared DB."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    project_name = data.get('project_name', '').strip()
    input_data = data.get('input_data')
    result_data = data.get('result_data')

    if not project_name:
        return jsonify({'error': 'project_name is required'}), 400
    if not input_data or not result_data:
        return jsonify({'error': 'input_data and result_data are required'}), 400

    db_path = current_app.config['DATABASE']
    user_id = get_current_user_id()
    description = data.get('description', '')

    design = create_design(db_path, project_name, input_data, result_data,
                          user_id, description)
    return jsonify(design), 201


@shared_bp.route('/api/shared/designs/<int:design_id>', methods=['GET'])
@login_required
def api_get_design(design_id):
    """Get design detail."""
    db_path = current_app.config['DATABASE']
    design = get_design_by_id(db_path, design_id)
    if not design:
        return jsonify({'error': 'Design not found'}), 404
    return jsonify(design)


@shared_bp.route('/api/shared/designs/<int:design_id>', methods=['PUT'])
@login_required
def api_update_design(design_id):
    """Update a draft/unlocked design."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    db_path = current_app.config['DATABASE']
    user_id = get_current_user_id()

    try:
        design = update_design(
            db_path, design_id, user_id,
            input_data=data.get('input_data'),
            result_data=data.get('result_data'),
            description=data.get('description'),
        )
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403

    if not design:
        return jsonify({'error': 'Design not found'}), 404
    return jsonify(design)


@shared_bp.route('/api/shared/designs/<int:design_id>', methods=['DELETE'])
@login_required
def api_delete_design(design_id):
    """Delete a draft design."""
    db_path = current_app.config['DATABASE']
    user_id = get_current_user_id()

    try:
        deleted = delete_design(db_path, design_id, user_id)
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403

    if not deleted:
        return jsonify({'error': 'Design not found'}), 404
    return jsonify({'message': 'Design deleted'})


@shared_bp.route('/api/shared/designs/<int:design_id>/submit', methods=['POST'])
@login_required
def api_submit_design(design_id):
    """Mark design as submitted (locked)."""
    db_path = current_app.config['DATABASE']
    user_id = get_current_user_id()

    try:
        design = submit_design(db_path, design_id, user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    if not design:
        return jsonify({'error': 'Design not found'}), 404
    return jsonify(design)


@shared_bp.route('/api/shared/designs/<int:design_id>/unlock', methods=['POST'])
@login_required
def api_unlock_design(design_id):
    """Unlock a submitted design for editing."""
    data = request.get_json()
    reason = (data or {}).get('reason', '').strip()
    if not reason:
        return jsonify({'error': 'Unlock reason is required'}), 400

    db_path = current_app.config['DATABASE']
    user_id = get_current_user_id()

    try:
        design = unlock_design(db_path, design_id, user_id, reason)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    if not design:
        return jsonify({'error': 'Design not found'}), 404
    return jsonify(design)


@shared_bp.route('/api/shared/designs/<int:design_id>/relock', methods=['POST'])
@login_required
def api_relock_design(design_id):
    """Re-lock (re-submit) an unlocked design."""
    db_path = current_app.config['DATABASE']
    user_id = get_current_user_id()

    try:
        design = relock_design(db_path, design_id, user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    if not design:
        return jsonify({'error': 'Design not found'}), 404
    return jsonify(design)


@shared_bp.route('/api/shared/designs/<int:design_id>/new-revision', methods=['POST'])
@login_required
def api_new_revision(design_id):
    """Create a new revision from an existing design."""
    db_path = current_app.config['DATABASE']
    user_id = get_current_user_id()

    design = create_new_revision(db_path, design_id, user_id)
    if not design:
        return jsonify({'error': 'Source design not found'}), 404
    return jsonify(design), 201


@shared_bp.route('/api/shared/designs/<int:design_id>/audit-log', methods=['GET'])
@login_required
def api_audit_log(design_id):
    """Get audit log for a specific design."""
    db_path = current_app.config['DATABASE']
    page = request.args.get('page', 1, type=int)
    result = get_audit_log(db_path, design_id=design_id, page=page)
    return jsonify(result)


@shared_bp.route('/api/shared/audit-log', methods=['GET'])
@admin_required
def api_all_audit_log():
    """Get all audit logs (admin only)."""
    db_path = current_app.config['DATABASE']
    page = request.args.get('page', 1, type=int)
    result = get_audit_log(db_path, page=page)
    return jsonify(result)


@shared_bp.route('/api/shared/users', methods=['GET'])
@login_required
def api_list_users():
    """List users for filter dropdowns (id + display_name only)."""
    from .shared_models import get_db
    db_path = current_app.config['DATABASE']
    conn = get_db(db_path)
    try:
        rows = conn.execute(
            "SELECT id, display_name FROM users WHERE is_active = 1 ORDER BY display_name"
        ).fetchall()
        return jsonify({'users': [dict(r) for r in rows]})
    finally:
        conn.close()
