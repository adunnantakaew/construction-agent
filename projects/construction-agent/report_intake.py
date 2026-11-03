"""
Construction Agent — "report intake" helper functions.
This simulates the chat workflow described in DESIGN.md section 3:
  ช่าง/FM พิมพ์รายงานในแชท -> บันทึกเป็น reported_done (ร่าง) -> SE/OP ยืนยัน -> verified_done

Usage (import and call from the agent's own reasoning, or run manually for testing):

    from report_intake import submit_report, verify_update, daily_summary

    submit_report(
        project_id="MRC-2026-025",
        reported_by="FM-ไอซ์",
        raw_text="วันนี้ 2026-10-20 เริ่มงานเสาเข็มแล้ว",
        task_name_hint="งานเสาเข็ม",
        new_status="in_progress",
    )

    verify_update(update_id="U-xxxx", verified_by="SE-เรย์", approve=True)

    print(daily_summary("MRC-2026-025"))
"""
import uuid
import json
from datetime import datetime, date
from difflib import SequenceMatcher
from schema import get_conn, init_schema


def _similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def find_matching_task(project_id: str, task_name_hint: str, threshold: float = 0.55):
    """Fuzzy-match a free-text task name against this project's task list.
    Returns (task_id, task_name, score) of best match, or None if nothing clears threshold.
    Never guesses silently below threshold -- caller must ask the user to clarify.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT task_id, task_name FROM project_tasks WHERE project_id=?", (project_id,)
    ).fetchall()
    conn.close()
    best = None
    best_score = 0.0
    for task_id, task_name in rows:
        score = _similar(task_name_hint, task_name)
        if score > best_score:
            best_score = score
            best = (task_id, task_name)
    if best and best_score >= threshold:
        return (*best, best_score)
    return None


def submit_report(project_id: str, reported_by: str, raw_text: str,
                   task_name_hint: str = None, new_status: str = "reported_done",
                   reported_date: str = None):
    """Record a draft update. Does NOT change project_tasks.status until verified.
    Returns a dict describing what happened, including whether task matching
    needs human clarification.
    """
    init_schema()
    conn = get_conn()
    cur = conn.cursor()

    # check project exists
    proj = cur.execute("SELECT project_id FROM projects WHERE project_id=?", (project_id,)).fetchone()
    if not proj:
        conn.close()
        return {"ok": False, "error": f"ไม่พบโครงการ {project_id} ในระบบ ต้องถาม OP ยืนยันรหัสก่อน"}

    match = find_matching_task(project_id, task_name_hint) if task_name_hint else None

    update_id = f"U-{uuid.uuid4().hex[:8]}"
    reported_date = reported_date or date.today().isoformat()

    cur.execute("""
        INSERT INTO updates (update_id, project_id, task_id, reported_date, status_before,
            status_after, reported_by, raw_text)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        update_id, project_id, match[0] if match else None, reported_date,
        None, new_status, reported_by, raw_text,
    ))
    conn.commit()
    conn.close()

    if not match:
        return {
            "ok": True,
            "update_id": update_id,
            "needs_clarification": True,
            "message": f"บันทึกร่างแล้ว (update_id={update_id}) แต่จับคู่งานไม่ได้จากคำว่า '{task_name_hint}' "
                       f"— กรุณาระบุชื่องานให้ตรงกับแผน หรือยืนยันว่าเป็นงานใหม่นอกแผน",
        }
    task_id, task_name, score = match
    return {
        "ok": True,
        "update_id": update_id,
        "matched_task_id": task_id,
        "matched_task_name": task_name,
        "match_score": round(score, 2),
        "needs_clarification": False,
        "message": f"บันทึกร่างแล้ว (update_id={update_id}) จับคู่กับงาน '{task_name}' "
                   f"— สถานะเป็น '{new_status}' รอ SE/OP ยืนยัน",
    }


def verify_update(update_id: str, verified_by: str, approve: bool = True, note: str = None):
    """SE/OP confirms (or rejects) a draft update. Only on approve=True does
    project_tasks.status actually change to the reported status (mapped to verified_*).
    """
    conn = get_conn()
    cur = conn.cursor()
    upd = cur.execute("SELECT project_id, task_id, status_after FROM updates WHERE update_id=?",
                       (update_id,)).fetchone()
    if not upd:
        conn.close()
        return {"ok": False, "error": f"ไม่พบ update_id {update_id}"}
    project_id, task_id, status_after = upd

    now = datetime.now().isoformat(timespec="seconds")
    cur.execute("""
        UPDATE updates SET verified_by=?, verified_at=? WHERE update_id=?
    """, (verified_by, now, update_id))

    if approve and task_id:
        final_status = "verified_done" if status_after == "reported_done" else status_after
        today = date.today().isoformat()
        cur.execute("""
            UPDATE project_tasks
            SET status=?, updated_at=?,
                actual_start = COALESCE(actual_start, ?),
                actual_end = CASE WHEN ?='verified_done' THEN ? ELSE actual_end END
            WHERE task_id=?
        """, (final_status, now, today, final_status, today, task_id))

    conn.commit()
    conn.close()
    if not approve:
        return {"ok": True, "message": f"ปฏิเสธ update {update_id} แล้ว ({note or 'ไม่ระบุเหตุผล'}) — ต้องให้ผู้รายงานแก้ไขและส่งใหม่"}
    return {"ok": True, "message": f"ยืนยัน update {update_id} แล้วโดย {verified_by}"}


def daily_summary(project_id: str = None, overdue_days: int = 0):
    """Return a Thai-language status summary. If project_id is None, summarizes all
    active (non-cancelled, non-delivered) pilot projects.
    """
    conn = get_conn()
    cur = conn.cursor()

    if project_id:
        projects = cur.execute(
            "SELECT project_id, project_code FROM projects WHERE project_id=?", (project_id,)
        ).fetchall()
    else:
        projects = cur.execute(
            "SELECT project_id, project_code FROM projects WHERE stage NOT IN ('ยกเลิก','ส่งมอบ')"
        ).fetchall()

    today = date.today()
    lines = [f"สรุปสถานะ ณ {today.isoformat()}", ""]

    for pid, pcode in projects:
        lines.append(f"📋 {pcode}")
        tasks = cur.execute("""
            SELECT task_id, task_name, planned_start, planned_end, status
            FROM project_tasks WHERE project_id=? ORDER BY planned_start
        """, (pid,)).fetchall()

        in_progress = [t for t in tasks if t[4] in ("in_progress", "reported_done")]
        overdue = []
        upcoming = []
        for (tid, name, pstart, pend, status) in tasks:
            if status == "verified_done":
                continue
            if pend:
                pend_d = datetime.strptime(pend, "%Y-%m-%d").date()
                if pend_d < today and status != "verified_done":
                    overdue.append((name, pend, status))
                elif pstart and datetime.strptime(pstart, "%Y-%m-%d").date() <= today <= pend_d:
                    upcoming.append((name, pend, status))

        pending_review = cur.execute("""
            SELECT count(*) FROM updates WHERE project_id=? AND verified_at IS NULL
        """, (pid,)).fetchone()[0]

        if upcoming:
            lines.append("  งานที่กำลังทำ/ควรทำตอนนี้:")
            for name, pend, status in upcoming:
                lines.append(f"    - {name} (ครบกำหนด {pend}, สถานะ {status})")
        if overdue:
            lines.append("  ⚠️ งานล่าช้า (เลยกำหนดแผน):")
            for name, pend, status in overdue:
                lines.append(f"    - {name} (ควรเสร็จ {pend}, สถานะ {status})")
        if pending_review:
            lines.append(f"  🕐 มีรายงานรอตรวจ {pending_review} รายการ")
        if not upcoming and not overdue and not pending_review:
            lines.append("  (ไม่มีงานที่ต้องติดตามเป็นพิเศษในตอนนี้)")
        lines.append("")

    conn.close()
    return "\n".join(lines)


if __name__ == "__main__":
    print(daily_summary())
