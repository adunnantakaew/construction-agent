"""
Seed data for Construction Agent MVP pilot.
Projects: 3 ล่าสุด (operation/จอง stage) from Customer Dashboard MRC 2026 - Operation(สำหรับลูกค้า):
  - MRC-2026-025 บ้านกาด แม่วาง   (สถานะ: จอง)
  - MRC-2026-026 เหมืองง่า ศรีสองเมือง (สถานะ: operation)
  - MRC-2026-027 สันผีเสื้อ 2        (สถานะ: จอง)

NOTE: house_type (1_floor/2_floor) is NOT explicitly recorded in source sheet.
Marked 'unknown' here -- needs OP/SE confirmation before applying a task template.
Task templates below are a GENERIC placeholder built from the construction phases
named in Ai_Agent_Data.xlsx (ฐานราก/โครงสร้าง/หลังคา/ไฟฟ้า/ประปา/ตกแต่ง) because the
actual Operation Plan / Construction Plan source files (S04-S07 in Mirana review)
were not attached to this chat. offset_days/duration_days are PLACEHOLDERS flagged
for SE review -- do not treat as approved baseline.
"""
import sqlite3
import json
from schema import get_conn, init_schema

PROJECTS = [
    {
        "project_id": "MRC-2026-025",
        "project_code": "MRC-2026-025 บ้านกาด แม่วาง",
        "aliases": [],
        "customer_name": "ฟ้า",
        "house_type": "unknown",
        "province": "เชียงใหม่", "district": "แม่วาง", "subdistrict": "บ้านกาด",
        "stage": "จอง",
        "owner_se": "เรย์", "owner_fm": "ไอซ์",
        "book_date": "2026-09-03",
        "notes": "เกรดมิราน่า / 3นอน 2น้ำ 1โถง 1ครัว ซักล้าง / งบ 2.5 ล้าน (กู้)",
    },
    {
        "project_id": "MRC-2026-026",
        "project_code": "MRC-2026-026 เหมืองง่า ศรีสองเมือง",
        "aliases": [],
        "customer_name": "เชน",
        "house_type": "unknown",
        "province": "ลำพูน", "district": "เมือง", "subdistrict": "เหมืองง่า",
        "stage": "operation",
        "owner_se": "เบล", "owner_fm": "ดวงใจ",
        "book_date": "2026-09-14",
        "notes": "เกรดมาตรฐาน / 4นอน 2น้ำ 1โถง 1ครัว ซักล้าง / งบ 1.35 ล้าน (เงินสด) / ลงเสาเอกประมาณ 2026-11-26",
    },
    {
        "project_id": "MRC-2026-027",
        "project_code": "MRC-2026-027 สันผีเสื้อ 2",
        "aliases": [],
        "customer_name": "อีฟ",
        "house_type": "unknown",
        "province": "เชียงใหม่", "district": "เมือง", "subdistrict": "สันผีเสื้อ",
        "stage": "จอง",
        "owner_se": "เบล", "owner_fm": "ไอซ์",
        "book_date": "2026-10-07",
        "notes": "เกรดมิราน่า / 2นอน 1ห้องทำงาน 3น้ำ 1โถง 1pantry 1ซักล้าง / งบ 2.5 ล้าน (กู้)",
    },
]

# Generic placeholder task template -- PENDING SE confirmation (offsets/durations not approved baseline)
TASK_TEMPLATE = [
    # (template_task_id, house_type, wbs_label, phase, task_name, owner_role, offset_days, duration_days, qc_gate, seq)
    ("T-PREP-01", "both", "0", "เตรียมงาน", "เคลียร์พื้นที่ / ปักผัง",          "FM", 0,  3, 0, 1),
    ("T-FOUND-01","both", "1", "ฐานราก",     "งานเสาเข็ม",                     "FM", 3,  5, 1, 2),
    ("T-FOUND-02","both", "2", "ฐานราก",     "งานขุดดิน + ฐานราก คาน คสล.",     "FM", 8,  7, 1, 3),
    ("T-STRUC-01","both", "3", "โครงสร้าง",  "งานเสาชั้น 1",                   "FM", 15, 5, 0, 4),
    ("T-STRUC-02","2_floor","4","โครงสร้าง","งานพื้น/คาน ชั้น 2",             "FM", 20, 7, 1, 5),
    ("T-STRUC-03","both", "5", "โครงสร้าง",  "งานผนังก่ออิฐ",                 "FM", 27, 10,0, 6),
    ("T-ROOF-01", "both", "6", "หลังคา",     "งานโครงหลังคา + มุงหลังคา",      "FM", 37, 7, 1, 7),
    ("T-MEP-01",  "both", "7", "ระบบไฟฟ้า/ประปา", "เดินท่อ/สายไฟฝังผนัง (ก่อนฉาบ)", "ช่าง", 44, 7, 1, 8),
    ("T-FINISH-01","both","8", "ตกแต่ง",     "ฉาบปูน/ฝ้าเพดาน",               "FM", 51, 10,0, 9),
    ("T-FINISH-02","both","9", "ตกแต่ง",     "ปูกระเบื้อง",                    "ช่าง", 61, 7, 0, 10),
    ("T-FINISH-03","both","10","ตกแต่ง",     "สี/วัสดุตกแต่งภายใน-นอก",        "ช่าง", 68, 10,0, 11),
    ("T-MEP-02",  "both", "11","ระบบไฟฟ้า/ประปา", "ติดตั้งสุขภัณฑ์/เครื่องใช้ไฟฟ้า", "ช่าง", 78, 5, 1, 12),
    ("T-QC-01",   "both", "12","ตรวจรับ",    "QC ตรวจรับงานก่อนส่งมอบ",        "SE", 83, 3, 1, 13),
    ("T-HANDOVER-01","both","13","ส่งมอบ",   "ส่งมอบบ้าน",                     "OP", 86, 2, 0, 14),
]

def seed():
    init_schema()
    conn = get_conn()
    cur = conn.cursor()

    for p in PROJECTS:
        cur.execute("""
            INSERT INTO projects (project_id, project_code, aliases, customer_name, house_type,
                province, district, subdistrict, stage, owner_se, owner_fm, book_date, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(project_id) DO UPDATE SET
                project_code=excluded.project_code, stage=excluded.stage, notes=excluded.notes
        """, (
            p["project_id"], p["project_code"], json.dumps(p["aliases"], ensure_ascii=False),
            p["customer_name"], p["house_type"], p["province"], p["district"], p["subdistrict"],
            p["stage"], p["owner_se"], p["owner_fm"], p["book_date"], p["notes"],
        ))

    for t in TASK_TEMPLATE:
        cur.execute("""
            INSERT INTO task_templates (template_task_id, template_version, house_type, wbs_label,
                phase, task_name, owner_role, offset_days, duration_days, qc_gate, seq)
            VALUES (?, 'v0.1-placeholder', ?,?,?,?,?,?,?,?,?)
            ON CONFLICT(template_task_id, template_version) DO NOTHING
        """, (t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8], t[9]))

    conn.commit()
    conn.close()
    print(f"Seeded {len(PROJECTS)} projects and {len(TASK_TEMPLATE)} task templates.")

if __name__ == "__main__":
    seed()
