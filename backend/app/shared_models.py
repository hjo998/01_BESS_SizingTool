"""BESS Sizing Tool — Shared DB models for multi-user design management."""
import json
import sqlite3
from datetime import datetime
from typing import List, Optional


def get_db(db_path: str) -> sqlite3.Connection:
    """Open a database connection with row factory and WAL mode."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_shared_db(db_path: str) -> None:
    """Create shared DB tables if they do not exist. Safe to call repeatedly."""
    conn = get_db(db_path)
    try:
        # Users table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT    NOT NULL UNIQUE,
                email           TEXT    NOT NULL UNIQUE,
                password_hash   TEXT    NOT NULL,
                display_name    TEXT    NOT NULL,
                department      TEXT,
                role            TEXT    NOT NULL DEFAULT 'engineer',
                is_active       BOOLEAN NOT NULL DEFAULT 1,
                created_at      TEXT    NOT NULL,
                last_login_at   TEXT
            )
        """)

        # Shared designs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS designs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name    TEXT    NOT NULL,
                revision        INTEGER NOT NULL DEFAULT 1,
                status          TEXT    NOT NULL DEFAULT 'draft',
                input_data      TEXT    NOT NULL,
                result_data     TEXT    NOT NULL,
                description     TEXT,
                created_by      INTEGER NOT NULL REFERENCES users(id),
                created_at      TEXT    NOT NULL,
                updated_by      INTEGER REFERENCES users(id),
                updated_at      TEXT    NOT NULL,
                submitted_by    INTEGER REFERENCES users(id),
                submitted_at    TEXT,
                UNIQUE(project_name, revision)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_designs_project ON designs(project_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_designs_status ON designs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_designs_created_by ON designs(created_by)")

        # Unlock log
        conn.execute("""
            CREATE TABLE IF NOT EXISTS unlock_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                design_id       INTEGER NOT NULL REFERENCES designs(id),
                unlocked_by     INTEGER NOT NULL REFERENCES users(id),
                reason          TEXT    NOT NULL,
                unlocked_at     TEXT    NOT NULL,
                relocked_at     TEXT,
                relocked_by     INTEGER REFERENCES users(id)
            )
        """)

        # Audit log
        conn.execute("""
            CREATE TABLE IF NOT EXISTS design_audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                design_id   INTEGER NOT NULL REFERENCES designs(id),
                action      TEXT    NOT NULL,
                actor_id    INTEGER NOT NULL REFERENCES users(id),
                detail      TEXT,
                created_at  TEXT    NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_design ON design_audit_log(design_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON design_audit_log(action)")

        # Migration: add user_id to projects table if it exists
        try:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()]
            if cols and 'user_id' not in cols:
                conn.execute("ALTER TABLE projects ADD COLUMN user_id INTEGER REFERENCES users(id)")
        except sqlite3.OperationalError:
            pass  # projects table doesn't exist yet

        conn.commit()
    finally:
        conn.close()


# ─── User helpers ───────────────────────────────────────────

def create_user(db_path: str, username: str, email: str, password_hash: str,
                display_name: str, department: str = None, role: str = 'engineer') -> int:
    """Insert a new user. Returns user id."""
    now = datetime.utcnow().isoformat()
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO users (username, email, password_hash, display_name,
                                  department, role, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (username, email, password_hash, display_name, department, role, now)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_username(db_path: str, username: str) -> Optional[dict]:
    """Find user by username."""
    conn = get_db(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(db_path: str, user_id: int) -> Optional[dict]:
    """Find user by id."""
    conn = get_db(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_last_login(db_path: str, user_id: int) -> None:
    """Update the last_login_at timestamp."""
    now = datetime.utcnow().isoformat()
    conn = get_db(db_path)
    try:
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id))
        conn.commit()
    finally:
        conn.close()


# ─── Design helpers ─────────────────────────────────────────

def create_design(db_path: str, project_name: str, input_data: dict,
                  result_data: dict, created_by: int, description: str = None) -> dict:
    """Create a new design (revision 1) or next revision if project exists."""
    now = datetime.utcnow().isoformat()
    conn = get_db(db_path)
    try:
        # Determine revision number
        row = conn.execute(
            "SELECT MAX(revision) as max_rev FROM designs WHERE project_name = ?",
            (project_name,)
        ).fetchone()
        revision = (row['max_rev'] or 0) + 1

        cursor = conn.execute(
            """INSERT INTO designs (project_name, revision, status, input_data, result_data,
                                    description, created_by, created_at, updated_by, updated_at)
               VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)""",
            (project_name, revision, json.dumps(input_data), json.dumps(result_data),
             description, created_by, now, created_by, now)
        )
        design_id = cursor.lastrowid

        # Audit log
        conn.execute(
            """INSERT INTO design_audit_log (design_id, action, actor_id, detail, created_at)
               VALUES (?, 'created', ?, ?, ?)""",
            (design_id, created_by, f"Rev.{revision} created", now)
        )
        conn.commit()

        return get_design_by_id(db_path, design_id)
    finally:
        conn.close()


def get_design_by_id(db_path: str, design_id: int) -> Optional[dict]:
    """Get a single design with parsed JSON fields."""
    conn = get_db(db_path)
    try:
        row = conn.execute(
            """SELECT d.*, u1.display_name as creator_name, u2.display_name as updater_name,
                      u3.display_name as submitter_name
               FROM designs d
               LEFT JOIN users u1 ON d.created_by = u1.id
               LEFT JOIN users u2 ON d.updated_by = u2.id
               LEFT JOIN users u3 ON d.submitted_by = u3.id
               WHERE d.id = ?""",
            (design_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d['input_data'] = json.loads(d['input_data'])
        d['result_data'] = json.loads(d['result_data'])
        return d
    finally:
        conn.close()


def list_designs(db_path: str, project: str = None, status: str = None,
                 user_id: int = None, date_from: str = None, date_to: str = None,
                 sort: str = 'updated_at', page: int = 1, per_page: int = 20) -> dict:
    """List designs with filtering and pagination."""
    conn = get_db(db_path)
    try:
        where = []
        params = []

        if project:
            where.append("d.project_name LIKE ?")
            params.append(f"%{project}%")
        if status:
            where.append("d.status = ?")
            params.append(status)
        if user_id:
            where.append("d.created_by = ?")
            params.append(user_id)
        if date_from:
            where.append("d.created_at >= ?")
            params.append(date_from)
        if date_to:
            where.append("d.created_at <= ?")
            params.append(date_to + "T23:59:59")

        where_clause = " AND ".join(where) if where else "1=1"

        # Validate sort column
        allowed_sorts = ['updated_at', 'created_at', 'project_name', 'revision', 'status']
        if sort not in allowed_sorts:
            sort = 'updated_at'

        # Count total
        total = conn.execute(
            f"SELECT COUNT(*) FROM designs d WHERE {where_clause}", params
        ).fetchone()[0]

        # Fetch page
        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""SELECT d.*, u.display_name as creator_name
                FROM designs d
                LEFT JOIN users u ON d.created_by = u.id
                WHERE {where_clause}
                ORDER BY d.{sort} DESC
                LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ).fetchall()

        designs = []
        for row in rows:
            d = dict(row)
            # Don't include full data in list view
            d.pop('input_data', None)
            d.pop('result_data', None)
            designs.append(d)

        return {
            'designs': designs,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        }
    finally:
        conn.close()


def update_design(db_path: str, design_id: int, user_id: int,
                  input_data: dict = None, result_data: dict = None,
                  description: str = None) -> Optional[dict]:
    """Update a design. Only allowed if status is 'draft' or 'unlocked'."""
    conn = get_db(db_path)
    try:
        design = conn.execute("SELECT * FROM designs WHERE id = ?", (design_id,)).fetchone()
        if not design:
            return None
        if design['status'] == 'submitted':
            raise PermissionError("Design is locked. Unlock first.")

        fields = []
        values = []
        now = datetime.utcnow().isoformat()

        if input_data is not None:
            fields.append("input_data = ?")
            values.append(json.dumps(input_data))
        if result_data is not None:
            fields.append("result_data = ?")
            values.append(json.dumps(result_data))
        if description is not None:
            fields.append("description = ?")
            values.append(description)

        if not fields:
            return get_design_by_id(db_path, design_id)

        fields.extend(["updated_by = ?", "updated_at = ?"])
        values.extend([user_id, now])
        values.append(design_id)

        conn.execute(f"UPDATE designs SET {', '.join(fields)} WHERE id = ?", values)

        conn.execute(
            """INSERT INTO design_audit_log (design_id, action, actor_id, detail, created_at)
               VALUES (?, 'updated', ?, 'Design data updated', ?)""",
            (design_id, user_id, now)
        )
        conn.commit()
        return get_design_by_id(db_path, design_id)
    finally:
        conn.close()


def submit_design(db_path: str, design_id: int, user_id: int) -> Optional[dict]:
    """Mark a design as submitted (locked)."""
    conn = get_db(db_path)
    try:
        design = conn.execute("SELECT * FROM designs WHERE id = ?", (design_id,)).fetchone()
        if not design:
            return None
        if design['status'] not in ('draft', 'unlocked'):
            raise ValueError("Only draft or unlocked designs can be submitted")

        now = datetime.utcnow().isoformat()

        # If unlocked, close the unlock_log entry
        if design['status'] == 'unlocked':
            conn.execute(
                """UPDATE unlock_log SET relocked_at = ?, relocked_by = ?
                   WHERE design_id = ? AND relocked_at IS NULL""",
                (now, user_id, design_id)
            )

        conn.execute(
            """UPDATE designs SET status = 'submitted', submitted_by = ?,
                      submitted_at = ?, updated_by = ?, updated_at = ?
               WHERE id = ?""",
            (user_id, now, user_id, now, design_id)
        )

        conn.execute(
            """INSERT INTO design_audit_log (design_id, action, actor_id, detail, created_at)
               VALUES (?, 'submitted', ?, 'Design submitted', ?)""",
            (design_id, user_id, now)
        )
        conn.commit()
        return get_design_by_id(db_path, design_id)
    finally:
        conn.close()


def unlock_design(db_path: str, design_id: int, user_id: int, reason: str) -> Optional[dict]:
    """Unlock a submitted design for editing."""
    conn = get_db(db_path)
    try:
        design = conn.execute("SELECT * FROM designs WHERE id = ?", (design_id,)).fetchone()
        if not design:
            return None
        if design['status'] != 'submitted':
            raise ValueError("Only submitted designs can be unlocked")

        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE designs SET status = 'unlocked', updated_by = ?, updated_at = ? WHERE id = ?",
            (user_id, now, design_id)
        )
        conn.execute(
            """INSERT INTO unlock_log (design_id, unlocked_by, reason, unlocked_at)
               VALUES (?, ?, ?, ?)""",
            (design_id, user_id, reason, now)
        )
        conn.execute(
            """INSERT INTO design_audit_log (design_id, action, actor_id, detail, created_at)
               VALUES (?, 'unlocked', ?, ?, ?)""",
            (design_id, user_id, reason, now)
        )
        conn.commit()
        return get_design_by_id(db_path, design_id)
    finally:
        conn.close()


def relock_design(db_path: str, design_id: int, user_id: int) -> Optional[dict]:
    """Re-lock (re-submit) an unlocked design."""
    conn = get_db(db_path)
    try:
        design = conn.execute("SELECT * FROM designs WHERE id = ?", (design_id,)).fetchone()
        if not design:
            return None
        if design['status'] != 'unlocked':
            raise ValueError("Only unlocked designs can be relocked")

        now = datetime.utcnow().isoformat()

        # Close the unlock_log entry
        conn.execute(
            """UPDATE unlock_log SET relocked_at = ?, relocked_by = ?
               WHERE design_id = ? AND relocked_at IS NULL""",
            (now, user_id, design_id)
        )

        conn.execute(
            """UPDATE designs SET status = 'submitted', submitted_by = ?,
                      submitted_at = ?, updated_by = ?, updated_at = ?
               WHERE id = ?""",
            (user_id, now, user_id, now, design_id)
        )

        conn.execute(
            """INSERT INTO design_audit_log (design_id, action, actor_id, detail, created_at)
               VALUES (?, 'relocked', ?, 'Design relocked after unlock', ?)""",
            (design_id, user_id, now)
        )
        conn.commit()
        return get_design_by_id(db_path, design_id)
    finally:
        conn.close()


def create_new_revision(db_path: str, source_design_id: int, user_id: int) -> Optional[dict]:
    """Create a new revision by copying data from an existing design."""
    conn = get_db(db_path)
    try:
        source = conn.execute("SELECT * FROM designs WHERE id = ?", (source_design_id,)).fetchone()
        if not source:
            return None

        max_rev = conn.execute(
            "SELECT MAX(revision) FROM designs WHERE project_name = ?",
            (source['project_name'],)
        ).fetchone()[0]
        new_rev = (max_rev or 0) + 1

        now = datetime.utcnow().isoformat()
        cursor = conn.execute(
            """INSERT INTO designs (project_name, revision, status, input_data, result_data,
                                    description, created_by, created_at, updated_by, updated_at)
               VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)""",
            (source['project_name'], new_rev, source['input_data'], source['result_data'],
             f"Rev.{new_rev} based on Rev.{source['revision']}", user_id, now, user_id, now)
        )
        design_id = cursor.lastrowid

        conn.execute(
            """INSERT INTO design_audit_log (design_id, action, actor_id, detail, created_at)
               VALUES (?, 'revision_created', ?, ?, ?)""",
            (design_id, user_id, f"Rev.{new_rev} from Rev.{source['revision']}", now)
        )
        conn.commit()
        return get_design_by_id(db_path, design_id)
    finally:
        conn.close()


def delete_design(db_path: str, design_id: int, user_id: int) -> bool:
    """Delete a design. Only drafts can be deleted."""
    conn = get_db(db_path)
    try:
        design = conn.execute("SELECT * FROM designs WHERE id = ?", (design_id,)).fetchone()
        if not design:
            return False
        if design['status'] != 'draft':
            raise PermissionError("Only draft designs can be deleted")

        # Delete related records first (FK constraints)
        conn.execute("DELETE FROM design_audit_log WHERE design_id = ?", (design_id,))
        conn.execute("DELETE FROM unlock_log WHERE design_id = ?", (design_id,))
        conn.execute("DELETE FROM designs WHERE id = ?", (design_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_audit_log(db_path: str, design_id: int = None, page: int = 1, per_page: int = 50) -> dict:
    """Get audit log entries, optionally filtered by design_id."""
    conn = get_db(db_path)
    try:
        where = "1=1"
        params = []
        if design_id:
            where = "a.design_id = ?"
            params = [design_id]

        total = conn.execute(
            f"SELECT COUNT(*) FROM design_audit_log a WHERE {where}", params
        ).fetchone()[0]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""SELECT a.*, u.display_name as actor_name, d.project_name, d.revision
                FROM design_audit_log a
                LEFT JOIN users u ON a.actor_id = u.id
                LEFT JOIN designs d ON a.design_id = d.id
                WHERE {where}
                ORDER BY a.created_at DESC
                LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ).fetchall()

        return {
            'logs': [dict(row) for row in rows],
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        }
    finally:
        conn.close()


def get_project_revisions(db_path: str, project_name: str) -> List[dict]:
    """Get all revisions for a project name, ordered by revision number."""
    conn = get_db(db_path)
    try:
        rows = conn.execute(
            """SELECT d.id, d.project_name, d.revision, d.status,
                      d.created_by, d.created_at, d.submitted_at,
                      u.display_name as creator_name
               FROM designs d
               LEFT JOIN users u ON d.created_by = u.id
               WHERE d.project_name = ?
               ORDER BY d.revision ASC""",
            (project_name,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
