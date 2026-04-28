"""BESS Sizing Tool — SQLite project persistence helpers (no ORM)."""
import json
import os
import sqlite3
from datetime import datetime
from typing import List, Optional

# Shared data directory path
_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def _resolve_pcs_product(config_name):
    """Return short PCS product name (e.g. 'M-series') from pcs_config_map.json."""
    if not config_name:
        return None
    try:
        with open(os.path.join(_DATA_DIR, 'pcs_config_map.json'), 'r', encoding='utf-8') as f:
            entries = json.load(f)
        for e in entries:
            if e.get('config_name') == config_name:
                return e.get('model', config_name)
    except Exception:
        pass
    return config_name.split('+')[0].strip() or None


def get_db(db_path: str) -> sqlite3.Connection:
    """Open a database connection with row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    """Create the projects and cases tables if they do not already exist."""
    conn = get_db(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                input_data  TEXT    NOT NULL,
                result_data TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL REFERENCES projects(id),
                case_name   TEXT    NOT NULL DEFAULT 'Case 1',
                case_memo   TEXT    DEFAULT '',
                input_data  TEXT    NOT NULL,
                result_data TEXT    DEFAULT NULL,
                is_baseline INTEGER DEFAULT 0,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cases_project ON cases(project_id)
        """)
        conn.commit()

        # Auto-migration: projects with input_data but no corresponding cases
        projects = conn.execute(
            "SELECT id, input_data, result_data, created_at FROM projects"
        ).fetchall()
        now = datetime.utcnow().isoformat()
        for project in projects:
            count = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE project_id = ?", (project["id"],)
            ).fetchone()[0]
            if count == 0:
                result_val = project["result_data"]
                # result_data may be an empty JSON object or null-equivalent
                result_to_store = result_val if result_val and result_val != "null" else None
                conn.execute(
                    """INSERT INTO cases
                           (project_id, case_name, case_memo, input_data, result_data,
                            is_baseline, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        project["id"],
                        "Case 1",
                        "",
                        project["input_data"],
                        result_to_store,
                        1,
                        project["created_at"],
                        now,
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def save_project(db_path: str, title: str, input_data: dict, result_data: dict) -> int:
    """Insert or update a project record.

    If a project with the same title already exists it is updated;
    otherwise a new row is inserted.

    Returns the row id of the saved project.
    """
    now = datetime.utcnow().isoformat()
    input_json = json.dumps(input_data)
    result_json = json.dumps(result_data)

    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM projects WHERE title = ?", (title,)
        ).fetchone()

        if row:
            conn.execute(
                """UPDATE projects
                   SET input_data = ?, result_data = ?, updated_at = ?
                   WHERE id = ?""",
                (input_json, result_json, now, row["id"]),
            )
            project_id = row["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO projects (title, input_data, result_data, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (title, input_json, result_json, now, now),
            )
            project_id = cursor.lastrowid

        conn.commit()
        return project_id
    finally:
        conn.close()


def list_projects(db_path: str) -> list:
    """Return a summary list of all saved projects with case_count and best_result_summary."""
    conn = get_db(db_path)
    try:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM projects ORDER BY updated_at DESC"
        ).fetchall()
        projects = [dict(row) for row in rows]

        for proj in projects:
            pid = proj['id']
            # Case count
            cnt = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE project_id = ?", (pid,)
            ).fetchone()
            proj['case_count'] = cnt[0] if cnt else 0

            # All cases summary for project card display
            case_rows = conn.execute(
                """SELECT case_name, input_data, result_data FROM cases
                   WHERE project_id = ?
                   ORDER BY created_at ASC""",
                (pid,)
            ).fetchall()
            cases_summary = []
            for cr in case_rows:
                inp_raw = cr['input_data']
                res_raw = cr['result_data']
                inp = json.loads(inp_raw) if isinstance(inp_raw, str) and inp_raw else {}
                rd = None
                if res_raw and res_raw != '{}' and res_raw != 'null':
                    try:
                        rd = json.loads(res_raw) if isinstance(res_raw, str) else res_raw
                    except Exception:
                        pass
                summary_obj = rd.get('summary', {}) if rd else {}
                bat = rd.get('battery', {}) if rd else {}
                # Oversizing year = first augmentation wave year, or project_life
                aug_waves = inp.get('augmentation_waves') or inp.get('augmentation', [])
                oversizing_year = aug_waves[0]['year'] if aug_waves else inp.get('project_life')
                cases_summary.append({
                    'case_name': cr['case_name'],
                    'battery_product_type': inp.get('battery_product_type'),
                    'pcs_product': _resolve_pcs_product(inp.get('pcs_configuration')),
                    'required_power_mw': summary_obj.get('required_power_mw') or inp.get('required_power_mw'),
                    'installation_energy_dc_mwh': round(bat.get('installation_energy_dc_mwh', 0), 2) if bat.get('installation_energy_dc_mwh') else inp.get('required_energy_mwh'),
                    'power_factor': inp.get('power_factor', 0.95),
                    'oversizing_year': oversizing_year,
                    'no_of_pcs': summary_obj.get('no_of_pcs') or bat.get('no_of_pcs'),
                    'no_of_links': summary_obj.get('no_of_links') or bat.get('no_of_links'),
                    'has_result': rd is not None and bool(bat),
                })
            proj['cases_summary'] = cases_summary
            # Keep best_result_summary for backward compat
            proj['best_result_summary'] = cases_summary[0] if cases_summary and cases_summary[0].get('has_result') else None

        return projects
    finally:
        conn.close()


def delete_project(db_path: str, project_id: int) -> bool:
    """Delete a project and all its cases by id. Returns True if a row was deleted."""
    conn = get_db(db_path)
    try:
        # Cascade: delete all cases belonging to this project first
        conn.execute("DELETE FROM cases WHERE project_id = ?", (project_id,))
        cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_project(db_path: str, project_id: int) -> Optional[dict]:
    """Return a single project record (with input and result data) or None."""
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return None
        project = dict(row)
        project["input_data"] = json.loads(project["input_data"])
        project["result_data"] = json.loads(project["result_data"])
        return project
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Cases CRUD
# ---------------------------------------------------------------------------

def list_cases(db_path: str, project_id: int) -> List[dict]:
    """Return all cases for a project ordered by created_at ASC.

    Each entry includes: id, case_name, case_memo, is_baseline,
    has_result (bool), created_at, updated_at.
    """
    conn = get_db(db_path)
    try:
        rows = conn.execute(
            """SELECT id, case_name, case_memo, is_baseline,
                      (result_data IS NOT NULL) AS has_result,
                      created_at, updated_at
               FROM cases
               WHERE project_id = ?
               ORDER BY created_at ASC""",
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_case(db_path: str, case_id: int) -> Optional[dict]:
    """Return full case record with parsed input_data and result_data, or None."""
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM cases WHERE id = ?", (case_id,)
        ).fetchone()
        if row is None:
            return None
        case = dict(row)
        case["input_data"] = json.loads(case["input_data"])
        if case["result_data"] is not None:
            case["result_data"] = json.loads(case["result_data"])
        return case
    finally:
        conn.close()


def create_case(
    db_path: str,
    project_id: int,
    case_name: str,
    input_data: dict,
    case_memo: str = "",
) -> int:
    """Insert a new case. Auto-names to 'Case N' when case_name is empty.

    Returns the id of the newly created case.
    """
    conn = get_db(db_path)
    try:
        if not case_name:
            count = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE project_id = ?", (project_id,)
            ).fetchone()[0]
            case_name = f"Case {count + 1}"

        now = datetime.utcnow().isoformat()
        cursor = conn.execute(
            """INSERT INTO cases
                   (project_id, case_name, case_memo, input_data,
                    result_data, is_baseline, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, 0, ?, ?)""",
            (project_id, case_name, case_memo, json.dumps(input_data), now, now),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_case(
    db_path: str,
    case_id: int,
    case_name: Optional[str] = None,
    case_memo: Optional[str] = None,
    input_data: Optional[dict] = None,
    result_data: Optional[dict] = None,
) -> bool:
    """Update specified fields of a case. Returns True if a row was updated."""
    fields = []
    values = []

    if case_name is not None:
        fields.append("case_name = ?")
        values.append(case_name)
    if case_memo is not None:
        fields.append("case_memo = ?")
        values.append(case_memo)
    if input_data is not None:
        fields.append("input_data = ?")
        values.append(json.dumps(input_data))
    if result_data is not None:
        fields.append("result_data = ?")
        values.append(json.dumps(result_data))

    if not fields:
        return False

    now = datetime.utcnow().isoformat()
    fields.append("updated_at = ?")
    values.append(now)
    values.append(case_id)

    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            f"UPDATE cases SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_case(db_path: str, case_id: int) -> bool:
    """Delete a case by id. Returns True if a row was deleted."""
    conn = get_db(db_path)
    try:
        cursor = conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def clone_case(db_path: str, case_id: int, new_name: Optional[str] = None) -> int:
    """Copy a case's input_data into a new case in the same project.

    result_data is NOT copied — the clone starts uncalculated.
    new_name defaults to '<original_name> (Copy)'.
    Returns the id of the new case.
    """
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT project_id, case_name, case_memo, input_data FROM cases WHERE id = ?",
            (case_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Case {case_id} not found")

        name = new_name if new_name else f"{row['case_name']} (Copy)"
        now = datetime.utcnow().isoformat()
        cursor = conn.execute(
            """INSERT INTO cases
                   (project_id, case_name, case_memo, input_data,
                    result_data, is_baseline, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, 0, ?, ?)""",
            (row["project_id"], name, row["case_memo"], row["input_data"], now, now),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_cases_for_comparison(db_path: str, case_ids: List[int]) -> List[dict]:
    """Return full data for multiple cases that have already been calculated.

    Only cases with result_data are included in the result.
    """
    if not case_ids:
        return []

    placeholders = ", ".join("?" * len(case_ids))
    conn = get_db(db_path)
    try:
        rows = conn.execute(
            f"""SELECT * FROM cases
                WHERE id IN ({placeholders})
                  AND result_data IS NOT NULL""",
            case_ids,
        ).fetchall()
        results = []
        for row in rows:
            case = dict(row)
            case["input_data"] = json.loads(case["input_data"])
            case["result_data"] = json.loads(case["result_data"])
            results.append(case)
        return results
    finally:
        conn.close()
