"""
Construction Agent — SQLite schema + seed data
Design ref: projects/construction-agent/DESIGN.md
"""
import sqlite3
import os
import json
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "construction.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id      TEXT PRIMARY KEY,   -- canonical e.g. MRC-2026-025
    project_code    TEXT NOT NULL,      -- full display name e.g. "MRC-2026-025 บ้านกาด แม่วาง"
    aliases         TEXT,               -- JSON list of other codes/spellings seen
    customer_name   TEXT,
    house_type      TEXT,               -- '1_floor' | '2_floor' | 'unknown'
    province        TEXT,
    district        TEXT,
    subdistrict     TEXT,
    stage           TEXT,               -- จอง/operation/ก่อสร้าง/ส่งมอบ/ยกเลิก
    owner_se        TEXT,
    owner_fm        TEXT,
    book_date       TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS task_templates (
    template_task_id TEXT NOT NULL,     -- stable id e.g. T-FOUND-01
    template_version TEXT NOT NULL DEFAULT 'v0.1',
    house_type        TEXT NOT NULL,    -- '1_floor' | '2_floor' | 'both'
    wbs_label          TEXT,            -- original display WBS number (may repeat; not a key)
    phase              TEXT,            -- ฐานราก/โครงสร้าง/หลังคา/ไฟฟ้า/ประปา/ตกแต่ง/อื่นๆ
    task_name          TEXT NOT NULL,
    owner_role         TEXT,            -- SE/FM/OP/ช่าง
    offset_days        INTEGER,         -- days from project construction start (placeholder, needs SE confirm)
    duration_days       INTEGER,        -- placeholder, needs SE confirm
    qc_gate             INTEGER DEFAULT 0, -- 1 if needs QC checkpoint before next phase
    seq                  INTEGER,       -- display order
    PRIMARY KEY (template_task_id, template_version)
);

CREATE TABLE IF NOT EXISTS plan_versions (
    plan_version_id   TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL REFERENCES projects(project_id),
    baseline_version    TEXT,
    forecast_version     TEXT,
    approved_by           TEXT,
    approved_at            TEXT,
    change_reason           TEXT,
    created_at               TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_tasks (
    task_id          TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL REFERENCES projects(project_id),
    template_task_id   TEXT,
    template_version     TEXT,
    task_name              TEXT NOT NULL,
    phase                   TEXT,
    owner_id                 TEXT,
    planned_start              TEXT,
    planned_end                 TEXT,
    actual_start                  TEXT,
    actual_end                     TEXT,
    status                          TEXT DEFAULT 'planned', -- planned/in_progress/reported_done/verified_done/blocked
    progress_pct                      REAL DEFAULT 0,
    effort_hours                        REAL,
    evidence_id                          TEXT,
    created_at                             TEXT DEFAULT (datetime('now')),
    updated_at                               TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS updates (
    update_id       TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL REFERENCES projects(project_id),
    task_id             TEXT REFERENCES project_tasks(task_id),
    reported_date         TEXT,
    status_before           TEXT,
    status_after             TEXT,
    reported_by               TEXT,
    raw_text                   TEXT,
    verified_by                 TEXT,
    verified_at                   TEXT,
    evidence_id                    TEXT,
    created_at                      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS issues_decisions (
    issue_id        TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL REFERENCES projects(project_id),
    task_id             TEXT REFERENCES project_tasks(task_id),
    description           TEXT,
    owner_id                TEXT,
    due_date                  TEXT,
    blocked_tasks               TEXT, -- JSON list of task_id
    decision                      TEXT,
    resolved_at                     TEXT,
    created_at                        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sales_pipeline (
    pipeline_id       TEXT PRIMARY KEY,   -- derived from project code, e.g. MRC-2025-011
    project_code       TEXT NOT NULL,      -- full display name as in backlog, e.g. "MRC-2025-011 อุโมงค์ ลำพูน"
    customer_name        TEXT,            -- parsed remainder after code (best effort)
    stage                  TEXT,           -- จอง/operation/ก่อสร้าง/ยกเลิก (ตามคอลัมน์ "สถานะ" ไฟล์ Back log)
    operation_owner          TEXT,         -- คอลัมน์ Operation
    sale_owner                TEXT,        -- คอลัมน์ Sale ผู้รับผิดชอบ
    pd_owner                    TEXT,
    oe_owner                      TEXT,
    se_owner                        TEXT,
    fm_owner                          TEXT,
    date_book                           TEXT,
    date_permit                           TEXT, -- Date (ขออนุญาตก่อสร้าง)
    date_loan                               TEXT, -- Date (สินเชื่อ)
    date_foundation                           TEXT, -- Date (ลงเสาเอก)
    date_handover                               TEXT, -- Date (ส่งมอบ)
    price                                          REAL,
    booking_done                                     INTEGER, -- จอง
    deposit_done                                       INTEGER, -- มัดจำ
    contract_done                                        INTEGER, -- ทำสัญญา
    addon_done                                             INTEGER, -- เพิ่มลด
    condition_notes                                           TEXT, -- Condition free text log from Sale
    monthly_breakdown                                           TEXT, -- JSON {"69-1": amount, ...}
    total_amount                                                  REAL,
    data_issues                                                     TEXT, -- JSON list of flags e.g. ["missing_sale_owner"]
    source_row                                                        INTEGER, -- original row number in backlog xlsx
    created_at                                                           TEXT DEFAULT (datetime('now')),
    updated_at                                                             TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS qc_defects (
    defect_id        TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL REFERENCES projects(project_id),
    task_id               TEXT REFERENCES project_tasks(task_id),
    location                TEXT,
    severity                  TEXT,
    description                 TEXT,
    owner_id                      TEXT,
    due_date                        TEXT,
    before_photo                      TEXT,
    after_photo                        TEXT,
    checked_by                           TEXT,
    status                                 TEXT DEFAULT 'open', -- open/fixed/verified
    created_at                               TEXT DEFAULT (datetime('now')),
    closed_at                                  TEXT
);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_schema():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_schema()
    print("Schema created at", DB_PATH)
