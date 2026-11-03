"""
Real task templates derived from attached WBS source files:
  - WBS - Master Construction Schedule มาตรฐาน/Construction Plan 1 floor.xlsx
  - WBS - Master Construction Schedule มาตรฐาน/Construction Plan 2 floor.xlsx

IMPORTANT ASSUMPTIONS (flagged, need SE confirmation before treating as approved baseline):
  1. The source Gantt sheets mark task timing with CELL COLOR across "Week" columns rather than
     explicit start/duration numbers. Only a handful of milestone rows (ลงเสาเอก, each QC gate,
     ตรวจบ้านรอบที่ 1-3, ส่งมอบ) had a clearly colored week-cell we could extract reliably.
  2. All other task rows' offset_days are LINEARLY INTERPOLATED between those milestone anchors
     by row position -- this is a reasonable approximation of sequence/pacing, NOT a verified
     per-task duration. Two consecutive interpolated tasks may show the same offset_day (meaning
     "happens around the same time") rather than an exact duration.
  3. Day 0 = งานลงเสาเอก (pile-laying / construction start date).
  4. house_type scope:
       - 1_floor template: rows from "งานก่อสร้าง" + "(Construction process)" + "งานส่งมอบ" sections
         of Construction Plan 1 floor.xlsx (91 tasks)
       - 2_floor template: rows from "งานก่อสร้าง (Construction)" + "งานส่งมอบ" sections
         of Construction Plan 2 floor.xlsx (115 tasks, includes ชั้น 2 structural tasks)
  5. QC gate = True only for rows literally named "QC - ..." or "บริษัทตรวจบ้าน..." (inspection
     checkpoints) -- these require SE sign-off before downstream tasks are considered unblocked.
  6. duration_days is NOT set per task (no reliable per-task duration in source) -- only
     offset_days (when the task is expected to start, roughly). Downstream code should treat each
     task as a point-in-time checkpoint rather than a multi-day bar until SE supplies real
     durations.

Run this to (re)load the 'v1-wbs-estimated' template version into task_templates,
replacing the earlier fully-generic 'v0.1-placeholder' once house_type per pilot project
is confirmed (see projects/construction-agent/DESIGN.md open questions).
"""
import json
import os
from schema import get_conn, init_schema

HERE = os.path.dirname(__file__)
EXTRACTED = os.path.join(HERE, "source_files", "extracted")

QC_KEYWORDS = ("QC -", "บริษัทตรวจบ้าน")

def load_template_json(filename):
    with open(os.path.join(EXTRACTED, filename), encoding="utf-8") as f:
        return json.load(f)

def to_template_rows(data, house_type, prefix):
    rows = []
    for idx, x in enumerate(data, start=1):
        task_name = x["task"].strip()
        qc_gate = 1 if any(k in task_name for k in QC_KEYWORDS) else 0
        template_task_id = f"{prefix}-{x['row']:04d}"
        rows.append((
            template_task_id, house_type, str(x["row"]), x["section"], task_name,
            "SE/FM", x["offset_day_est"], None, qc_gate, idx,
        ))
    return rows

def load_real_templates():
    init_schema()
    conn = get_conn()
    cur = conn.cursor()

    t1 = to_template_rows(load_template_json("template_1floor_estimated.json"), "1_floor", "WBS1F")
    t2 = to_template_rows(load_template_json("template_2floor_estimated.json"), "2_floor", "WBS2F")

    version = "v1-wbs-estimated"
    for t in t1 + t2:
        cur.execute("""
            INSERT INTO task_templates (template_task_id, template_version, house_type, wbs_label,
                phase, task_name, owner_role, offset_days, duration_days, qc_gate, seq)
            VALUES (?, ?, ?,?,?,?,?,?,?,?,?)
            ON CONFLICT(template_task_id, template_version) DO UPDATE SET
                offset_days=excluded.offset_days, qc_gate=excluded.qc_gate, seq=excluded.seq
        """, (t[0], version, *t[1:]))

    conn.commit()
    conn.close()
    print(f"Loaded template version '{version}': {len(t1)} tasks (1_floor), {len(t2)} tasks (2_floor)")

if __name__ == "__main__":
    load_real_templates()
