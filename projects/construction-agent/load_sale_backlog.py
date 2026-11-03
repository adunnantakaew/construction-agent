"""
Load Sale/Customer Backlog xlsx -> sales_pipeline table.

Source: ข้อมูลลูกค้า Back log.xlsx (sheet "Back log")
Columns (Thai header row, row 1 in sheet):
  Project, สถานะ, Operation, Saleผู้รับผิดชอบ, PD, OE, SE, FM,
  Date (Book), Date (ขออนุญาาตก่อสร้าง), Date (สินเชื่อ), Date (ลงเสาเอก), Date (ส่งมอบ),
  สถานะ (repeated), ราคา, จอง, มัดจำ, ทำสัญญา, เพิ่มลด, Condition,
  69-1 .. 69-12 (monthly revenue breakdown, พ.ศ. 2569 = ปี 2026), Total

Design ref: projects/construction-agent/DESIGN.md
This feeds the Sale dashboard (/sale) — separate pipeline from construction WBS tasks.
Data issues (missing owner, missing price, etc.) are flagged, not guessed — Sale ต้องแก้ไขข้อมูลของตัวเอง.
"""
import json
import os
import re
import sqlite3
import sys
import datetime

import openpyxl

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "db", "construction.db")

MONTH_COLS = [f"69-{i}" for i in range(1, 13)]


def ser(v):
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    return v


def parse_code_and_name(project_cell):
    """'MRC-2025-011 อุโมงค์ ลำพูน' -> ('MRC-2025-011', 'อุโมงค์ ลำพูน')"""
    if not project_cell:
        return None, None
    s = str(project_cell).strip()
    m = re.match(r"^(MRC-\d{4}-\d+)\s*(.*)$", s)
    if m:
        return m.group(1), (m.group(2).strip() or None)
    # fallback: no recognizable code pattern -> whole string is the name, no code
    return None, s


def load(xlsx_path, sheet_name="Back log"):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    hdr = rows[0]
    col = {name: i for i, name in enumerate(hdr) if name is not None}

    records = []
    for row_num, r in enumerate(rows[2:], start=3):  # row 2 is an aggregate/total row
        if not r[col["Project"]]:
            continue
        rec = {}
        for name, i in col.items():
            rec[name] = ser(r[i])
        records.append((row_num, rec))
    return records


def to_pipeline_row(row_num, rec):
    code, name_remainder = parse_code_and_name(rec.get("Project"))
    pipeline_id = code or f"ROW-{row_num}"

    monthly = {m: rec.get(m) for m in MONTH_COLS if rec.get(m) not in (None, 0)}

    issues = []
    if not code:
        issues.append("no_project_code_pattern")
    if not rec.get("Saleผู้รับผิดชอบ"):
        issues.append("missing_sale_owner")
    if not rec.get("ราคา"):
        issues.append("missing_price")
    if not rec.get("Date (Book)"):
        issues.append("missing_book_date")
    stage = rec.get("สถานะ")
    if stage in ("ก่อสร้าง", "operation") and not rec.get("SE"):
        issues.append("missing_se_owner_for_active_stage")
    if stage == "operation" and not rec.get("FM"):
        issues.append("missing_fm_owner_for_operation_stage")

    def b(v):
        if v is None:
            return None
        return 1 if v else 0

    return {
        "pipeline_id": pipeline_id,
        "project_code": rec.get("Project"),
        "customer_name": name_remainder,
        "stage": stage,
        "operation_owner": rec.get("Operation"),
        "sale_owner": rec.get("Saleผู้รับผิดชอบ"),
        "pd_owner": rec.get("PD"),
        "oe_owner": rec.get("OE"),
        "se_owner": rec.get("SE"),
        "fm_owner": rec.get("FM"),
        "date_book": rec.get("Date (Book)"),
        "date_permit": rec.get("Date (ขออนุญาาตก่อสร้าง)"),
        "date_loan": rec.get("Date (สินเชื่อ)"),
        "date_foundation": rec.get("Date (ลงเสาเอก)"),
        "date_handover": rec.get("Date (ส่งมอบ)"),
        "price": rec.get("ราคา"),
        "booking_done": b(rec.get("จอง")),
        "deposit_done": b(rec.get("มัดจำ")),
        "contract_done": b(rec.get("ทำสัญญา")),
        "addon_done": b(rec.get("เพิ่มลด")),
        "condition_notes": rec.get("Condition"),
        "monthly_breakdown": json.dumps(monthly, ensure_ascii=False) if monthly else None,
        "total_amount": rec.get("Total"),
        "data_issues": json.dumps(issues, ensure_ascii=False) if issues else None,
        "source_row": row_num,
    }


def upsert(conn, row):
    cols = list(row.keys())
    placeholders = ", ".join(f":{c}" for c in cols)
    collist = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "pipeline_id")
    sql = f"""
        INSERT INTO sales_pipeline ({collist}, updated_at)
        VALUES ({placeholders}, datetime('now'))
        ON CONFLICT(pipeline_id) DO UPDATE SET {updates}, updated_at=datetime('now')
    """
    conn.execute(sql, row)


def main():
    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not xlsx_path:
        print("usage: python3 load_sale_backlog.py <path-to-backlog.xlsx>")
        sys.exit(1)

    import schema
    schema.init_schema()

    records = load(xlsx_path)
    conn = schema.get_conn()
    n_issues = 0
    for row_num, rec in records:
        row = to_pipeline_row(row_num, rec)
        if row["data_issues"]:
            n_issues += 1
        upsert(conn, row)
    conn.commit()
    conn.close()
    print(f"Loaded {len(records)} sales_pipeline rows ({n_issues} with data issues flagged) from {xlsx_path}")


if __name__ == "__main__":
    main()
