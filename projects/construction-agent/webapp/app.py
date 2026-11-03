"""
Construction Agent — overview web dashboard (Flask)

Read-only web app over the SQLite prototype DB at ../db/construction.db.
Run:
    cd projects/construction-agent/webapp
    python3 app.py
Serves on 0.0.0.0:<PORT env var, default 8077>.

Pages:
  /                 overview: all pilot projects, progress bars, overdue counts
  /project/<id>     project detail: full task list (phase, planned dates, status),
                     pending updates, QC gates
  /sale             sale dashboard: customer pipeline (ลงข้อมูลลูกค้าทำแบบ/เสนอราคา),
                     by stage, by sale owner, data-quality flags (Sale ต้องแก้ไขเอง)
Data API (used by the pages' JS, same-origin):
  /api/overview
  /api/project/<id>
  /api/sale
"""
import json
import os
import sys
import sqlite3
from datetime import date, datetime
from flask import Flask, jsonify, render_template, abort

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.path.join(ROOT, "db", "construction.db")
TEMPLATE_VERSION = "v1-wbs-estimated"

app = Flask(__name__)


def q(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def project_summary(pid=None):
    where = "WHERE project_id=?" if pid else ""
    params = (pid,) if pid else ()
    projects = q(f"""
        SELECT project_id, project_code, customer_name, stage, house_type, book_date, province, district
        FROM projects {where} ORDER BY project_id
    """, params)

    today = date.today().isoformat()
    out = []
    for p in projects:
        tasks = q("""
            SELECT pt.task_id, pt.task_name, pt.phase, pt.planned_start, pt.planned_end,
                   pt.actual_start, pt.actual_end, pt.status, tt.qc_gate, tt.seq
            FROM project_tasks pt
            LEFT JOIN task_templates tt
                ON pt.template_task_id = tt.template_task_id AND pt.template_version = tt.template_version
            WHERE pt.project_id=? AND pt.template_version=?
            ORDER BY tt.seq, pt.planned_start
        """, (p["project_id"], TEMPLATE_VERSION))

        status_counts = {}
        overdue = []
        in_progress_today = []
        next_qc = None
        for t in tasks:
            status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1
            if t["status"] != "verified_done" and t["planned_end"] and t["planned_end"] < today:
                overdue.append(t)
            elif (t["status"] != "verified_done" and t["planned_start"]
                  and t["planned_start"] <= today <= (t["planned_end"] or t["planned_start"])):
                in_progress_today.append(t)
            if t["qc_gate"] and t["status"] != "verified_done" and next_qc is None:
                next_qc = t

        pending_review = q(
            "SELECT update_id, task_id, reported_by, reported_date, status_after, raw_text "
            "FROM updates WHERE project_id=? AND verified_at IS NULL ORDER BY reported_date DESC",
            (p["project_id"],)
        )

        open_defects = q(
            "SELECT defect_id, description, severity, status FROM qc_defects "
            "WHERE project_id=? AND status!='verified'", (p["project_id"],)
        )

        open_issues = q(
            "SELECT issue_id, description, owner_id, due_date FROM issues_decisions "
            "WHERE project_id=? AND resolved_at IS NULL", (p["project_id"],)
        )

        total = len(tasks)
        done = status_counts.get("verified_done", 0)
        dates = [t["planned_start"] for t in tasks if t["planned_start"]] + \
                [t["planned_end"] for t in tasks if t["planned_end"]]

        out.append({
            "project_id": p["project_id"],
            "project_code": p["project_code"],
            "customer_name": p["customer_name"],
            "stage": p["stage"],
            "house_type": p["house_type"],
            "book_date": p["book_date"],
            "location": ", ".join(x for x in [p["district"], p["province"]] if x),
            "total_tasks": total,
            "done_tasks": done,
            "progress_pct": round(100 * done / total, 1) if total else 0,
            "status_counts": status_counts,
            "overdue_count": len(overdue),
            "overdue": overdue[:30],
            "in_progress_today": in_progress_today,
            "next_qc": next_qc,
            "pending_review": pending_review,
            "open_defects": open_defects,
            "open_issues": open_issues,
            "date_start": min(dates) if dates else None,
            "date_end": max(dates) if dates else None,
            "tasks": tasks,
        })
    return out


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/project/<pid>")
def project_page(pid):
    summary = project_summary(pid)
    if not summary:
        abort(404)
    return render_template("project.html", project_id=pid)


def sale_pipeline_summary():
    rows = q("""
        SELECT pipeline_id, project_code, customer_name, stage, sale_owner, operation_owner,
               pd_owner, oe_owner, se_owner, fm_owner, date_book, date_permit, date_loan,
               date_foundation, date_handover, price, booking_done, deposit_done,
               contract_done, addon_done, condition_notes, monthly_breakdown, total_amount,
               data_issues, source_row, updated_at
        FROM sales_pipeline ORDER BY source_row
    """)
    for r in rows:
        r["data_issues"] = json.loads(r["data_issues"]) if r["data_issues"] else []
        r["monthly_breakdown"] = json.loads(r["monthly_breakdown"]) if r["monthly_breakdown"] else {}

    stage_order = ["จอง", "operation", "ก่อสร้าง", "ยกเลิก"]
    by_stage = {}
    for r in rows:
        by_stage.setdefault(r["stage"] or "ไม่ระบุ", []).append(r)

    owner_totals = {}
    for r in rows:
        owner = r["sale_owner"] or "ไม่ระบุ"
        owner_totals.setdefault(owner, {"count": 0, "price_sum": 0.0})
        owner_totals[owner]["count"] += 1
        owner_totals[owner]["price_sum"] += r["price"] or 0

    flagged = [r for r in rows if r["data_issues"]]

    return {
        "projects": rows,
        "stage_order": stage_order,
        "by_stage_count": {k: len(v) for k, v in by_stage.items()},
        "owner_totals": owner_totals,
        "flagged": flagged,
        "flagged_count": len(flagged),
        "total_count": len(rows),
        "total_price": sum(r["price"] or 0 for r in rows),
    }


@app.route("/sale")
def sale_page():
    return render_template("sale.html")


@app.route("/api/sale")
def api_sale():
    return jsonify({"today": date.today().isoformat(), **sale_pipeline_summary()})


@app.route("/api/overview")
def api_overview():
    summary = project_summary()
    # trim heavy task list for the overview payload
    for p in summary:
        p.pop("tasks", None)
    return jsonify({"today": date.today().isoformat(), "projects": summary})


@app.route("/api/project/<pid>")
def api_project(pid):
    summary = project_summary(pid)
    if not summary:
        abort(404)
    return jsonify({"today": date.today().isoformat(), "project": summary[0]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8077))
    app.run(host="0.0.0.0", port=port, debug=False)
