"""
Generate project_tasks rows for each pilot project from a task template.

v2 (current): all 3 pilot projects confirmed by owner as house_type='1_floor' (2026-10-31).
Uses template_version='v1-wbs-estimated' (real WBS extracted from Construction Plan 1 floor.xlsx),
whose offset_days are estimated/interpolated from a handful of milestone anchors in the source
Gantt sheet -- see load_real_templates.py docstring for caveats. duration_days is not set for
this template (point-in-time checkpoints, not day-ranged bars).

Planned dates are anchored to a project's assumed construction-start date (day 0 = ลงเสาเอก):
  - If no confirmed ลงเสาเอก (pile-laying) date exists, we anchor to book_date + 30 days
    as a rough placeholder (flagged) until SE confirms actual start.
"""
import json
from datetime import datetime, timedelta
from schema import get_conn, init_schema

TEMPLATE_VERSION = "v1-wbs-estimated"

# project_id -> anchor construction start date (YYYY-MM-DD) + note on source
ANCHORS = {
    "MRC-2026-025": {"start": "2026-10-03", "source": "placeholder: book_date+30d (ไม่มีวันลงเสาเอกยืนยัน)"},
    "MRC-2026-026": {"start": "2026-11-26", "source": "วันลงเสาเอกจากชีต Operation (unconfirmed baseline)"},
    "MRC-2026-027": {"start": "2026-11-06", "source": "placeholder: book_date+30d (วันลงเสาเอกในชีตเป็น 2026-01-27 ซึ่งอยู่ก่อนวันจอง จึงไม่ใช้ ต้องถาม OP)"},
}

# all 3 pilot projects confirmed 1_floor by owner on 2026-10-31
HOUSE_TYPES = {
    "MRC-2026-025": "1_floor",
    "MRC-2026-026": "1_floor",
    "MRC-2026-027": "1_floor",
}

def gen_tasks(replace_existing=False):
    init_schema()
    conn = get_conn()
    cur = conn.cursor()

    count = 0
    for project_id, anchor in ANCHORS.items():
        house_type = HOUSE_TYPES[project_id]

        cur.execute("UPDATE projects SET house_type=? WHERE project_id=?", (house_type, project_id))

        if replace_existing:
            cur.execute("DELETE FROM project_tasks WHERE project_id=? AND template_version!=?",
                        (project_id, TEMPLATE_VERSION))

        templates = cur.execute(
            "SELECT template_task_id, house_type, phase, task_name, owner_role, offset_days, duration_days, qc_gate, seq "
            "FROM task_templates WHERE template_version=? AND house_type=? ORDER BY seq",
            (TEMPLATE_VERSION, house_type)
        ).fetchall()

        start = datetime.strptime(anchor["start"], "%Y-%m-%d")
        for (tt_id, h_type, phase, task_name, owner_role, offset, duration, qc_gate, seq) in templates:
            planned_start = (start + timedelta(days=offset)).strftime("%Y-%m-%d")
            planned_end = (start + timedelta(days=offset + (duration or 0))).strftime("%Y-%m-%d")
            task_id = f"{project_id}-{tt_id}"
            cur.execute("""
                INSERT INTO project_tasks (task_id, project_id, template_task_id, template_version,
                    task_name, phase, owner_id, planned_start, planned_end, status)
                VALUES (?,?,?,?,?,?,?,?,?, 'planned')
                ON CONFLICT(task_id) DO NOTHING
            """, (task_id, project_id, tt_id, TEMPLATE_VERSION, task_name, phase, owner_role,
                  planned_start, planned_end))
            count += 1

        # record plan version note
        cur.execute("""
            INSERT OR IGNORE INTO plan_versions (plan_version_id, project_id, baseline_version, change_reason)
            VALUES (?, ?, ?, ?)
        """, (f"{project_id}-PV2", project_id, TEMPLATE_VERSION,
              f"house_type={house_type} (owner confirmed 2026-10-31); {anchor['source']}"))

    conn.commit()
    conn.close()
    print(f"Generated {count} project_tasks across {len(ANCHORS)} pilot projects using template_version='{TEMPLATE_VERSION}'.")

if __name__ == "__main__":
    gen_tasks()
