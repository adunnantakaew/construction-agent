# AI Agent งานก่อสร้าง (Construction Planning & Site Tracking)

สถานะ: ออกแบบเริ่มต้น (v0.1) — 2026-10-31
ขอบเขตรอบนี้: รวม Agent 2 (Project Planning / Co-PM) + Agent 4 (Site & Quality Control)
LINE intake: **เชื่อมต่อแล้ว (2026-10-31)** — OpenClaw route ของ LINE account ที่ตั้งค่าไว้ส่งข้อความเข้า Construction Agent โดยตรง; ใช้ workflow/ขอบเขตข้อมูลตาม `AGENTS.md` ใน workspace นี้ การบันทึกรายงานยังอาศัย prototype `report_intake.py` และต้องเป็น draft เท่านั้น

---

## 1. เป้าหมาย

ให้ Agent ตัวเดียวทำหน้าที่:

1. **วางแผน (Co-PM)**: นำเข้า WBS ต้นแบบ (บ้าน 1 ชั้น / 2 ชั้น) → สร้างแผนงานต่อโครงการ → ติดตามแผนจริงเทียบแผนหลัก (baseline vs actual)
2. **ติดตามหน้างาน (Site/QC)**: รับรายงานประจำวัน/สัปดาห์จากช่าง/FM → จับคู่กับงานในแผน → สร้าง Daily Report + Defect/Punch list → แจ้งงานล่าช้าหรือติดขัด
3. **สรุปทุกเช้า**: ให้ภาพรวมสถานะของโครงการที่ Active อยู่ (งานวันนี้ งานค้าง บล็อกเกอร์) — ส่งเป็นข้อความสรุปในแชทเมื่อมีคนขอ (ยังไม่มีการส่ง LINE อัตโนมัติ)

สิ่งที่ **ไม่ทำในรอบนี้**: Dashboard ลูกค้า, เอกสารขออนุญาต (Agent 3), สัญญา/งวดเงิน (Agent 5), LINE broadcast/แจ้งเตือนอัตโนมัติ, Critical Path คำนวณจริง (รอข้อมูล dependency ให้ครบก่อน — ดูข้อ 6)

---

## 2. ขอบเขตข้อมูล (Data Model)

ใช้ชื่อตารางตามที่ Mirana review เสนอไว้แล้ว (06_Data_MD) แต่ตัดเฉพาะส่วนที่เกี่ยวกับวางแผน+หน้างาน:

| ตาราง | Key | ฟิลด์หลัก | หมายเหตุ |
|---|---|---|---|
| **Projects** | project_id (PK) | project_code, aliases[], house_type (1ชั้น/2ชั้น), stage, owner_se, owner_fm, start_date | project_code ต้อง OP ยืนยันก่อนนำเข้า ไม่เดาจากชื่อไฟล์ |
| **Task_Templates** | template_task_id + version | house_type, wbs_label, task_name, owner_role, offset_days, duration_days, qc_gate(bool) | แยกจาก WBS เลขลำดับเดิม (กันเลขซ้ำ เช่น 9.5 ซ้ำที่เจอใน Operation Plan) |
| **Project_Tasks** | task_id (PK) | project_id, template_task_id, owner_id, planned_start/end, actual_start/end, status, progress_pct, effort_hours, evidence_id | 1 แถว = 1 งานใน 1 โครงการ |
| **Plan_Versions** | plan_version_id | project_id, baseline_version, forecast_version, approved_by, change_reason | ห้ามทับ baseline อัตโนมัติเมื่อมีงานล่าช้า |
| **Updates** | update_id | project_id, task_id, reported_date, status_before/after, reported_by, verified_by, evidence_id | "รายงานว่าเสร็จ" ≠ "ตรวจว่าเสร็จ" (reported_done vs verified_done) |
| **Issues_Decisions** | issue_id | project_id, task_id, description, owner_id, due_date, blocked_tasks[], resolved_at | สำหรับงานค้าง/บล็อกเกอร์ |
| **QC_Defects** | defect_id | project_id, task_id, location, severity, owner, due_date, before/after_photo, checked_by | Punch list |

สถานะงาน (status): `planned → in_progress → reported_done → verified_done` (ไม่อนุญาตข้ามจาก reported ไป verified โดยอัตโนมัติ — ต้อง SE ยืนยัน)

---

## 3. Workflow (แทนที่ LINE ด้วยแชทไปก่อน)

```
[ช่าง/FM พิมพ์รายงานในแชทถึง Agent]
        ↓
Agent แยก: project_id, วันที่, งานที่ทำ, สถานะ, ปัญหา (ตามรูปแบบที่ทีมใช้อยู่แล้วใน LINE)
        ↓
ถ้า project_id/งานไม่ชัดเจน → Agent ถามกลับ ไม่เดา
        ↓
บันทึกเป็น "reported_done" (ร่าง) ลง Updates
        ↓
SE/OP ตรวจและยืนยัน (พิมพ์ "ยืนยัน" หรือสั่งแก้) → เปลี่ยนเป็น verified_done
        ↓
Dashboard/สรุปเช้า อัปเดตจากข้อมูลที่ verified แล้วเท่านั้น (reported ที่ยังไม่ verified จะโชว์ว่า "รอตรวจ")
```

รูปแบบข้อความที่ใช้ได้เลย (อิงจากตัวอย่างใน Ai Agent Data.xlsx ที่ทีมส่งใน LINE อยู่แล้ว):

```
โครงการ: MRC-2026-016 หนองป่าข้าว
วันที่: 19/10/69
งาน: เทคอนกรีตเสาชั้น 1 - เสร็จ
     วางแผ่นพื้นชั้น 1 - กำลังทำ
ปัญหา: ไม่มี
```

Agent จะ map งาน → template task ด้วยชื่อ/คำใกล้เคียง ถ้า match ไม่ได้ (เช่น ชื่อหมวดซ้ำที่เจอใน R09) จะถามกลับแทนที่จะเดา

---

## 4. ฟีเจอร์ MVP (เรียงตามลำดับสร้าง)

| # | ฟีเจอร์ | รายละเอียด | ต้องมีข้อมูลอะไรก่อน |
|---|---|---|---|
| 1 | **Master Project + Task Template** | นำเข้า 2-3 โครงการนำร่อง + WBS บ้าน 1 ชั้น/2 ชั้น (ล้าง ID ซ้ำ) | ยืนยัน project_code จริง (ดูข้อ 6.1) |
| 2 | **รับรายงานผ่านแชท → บันทึกร่าง** | พาร์สข้อความแบบด้านบน, กันข้อความซ้ำ (idempotent) | รูปแบบข้อความที่ทีมใช้ (มีแล้ว) |
| 3 | **ตรวจ/ยืนยันสถานะ** | SE/OP พิมพ์ยืนยันในแชท → เปลี่ยนสถานะ + log ผู้ตรวจ | - |
| 4 | **Plan vs Actual** | เทียบ planned_date กับ actual ต่องาน บอกว่าล่าช้ากี่วัน | baseline ที่ SE อนุมัติ |
| 5 | **Daily/Weekly Report & งานค้าง** | สรุปที่ขอได้ตามสั่ง (ยังไม่ auto-push ไป LINE): งานวันนี้ งานค้างเกิน X วัน บล็อกเกอร์ | ข้อ 1-4 |
| 6 | **QC / Defect (punch list)** | เปิด-ปิดรายการ defect ผูกกับ task และโครงการ | ยังไม่มี checklist ที่อนุมัติ (ดูข้อ 6.3) — เริ่มแบบ free-text ไปก่อนได้ |
| 7 | **รับข้อความผ่าน LINE OA** | OpenClaw route ไปยัง Construction Agent แล้ว; การรับรายงาน/เขียน draft ยังใช้ prototype และต้องทำตามกติกาใน `AGENTS.md` | LINE account connected; ไม่รวม broadcast หรือการยืนยันงานอัตโนมัติ |
| 8 | **(ภายหลัง) Critical Path จริง** | ต้องมี dependency/duration/calendar ครบ | รอ SE เติมข้อมูล |

---

## 5. เก็บข้อมูลที่ไหน

เสนอ 2 ทางเลือก — เลือกได้ตามที่สะดวก:

- **ทางเลือก A (เริ่มเร็ว)**: เก็บเป็นไฟล์ข้อมูลโครงสร้าง (เช่น SQLite หรือ Google Sheet ที่ผมเขียนผ่าน API ให้) ที่รันในเวิร์คสเปซนี้ ผมดูแล query/report ให้ผ่านแชทได้เลย ไม่ต้องตั้งเซิร์ฟเวอร์
- **ทางเลือก B**: ต่อกับ Google Sheets ที่ทีมใช้อยู่ (Operation Plan / Construction Plan เดิม) ให้ผมอ่าน-เขียนตรง — ข้อดีคือทีมเห็นในที่เดิม ข้อเสียคือเสี่ยงชนกับการแก้ไฟล์ต้นฉบับ (ตามที่ Mirana review เตือนไว้ R07-R10)

แนะนำ **A ก่อนสำหรับ Pilot** (กันกระทบไฟล์เดิม) แล้วค่อยเชื่อม B ทีหลังถ้าอยากให้ทีมดูผ่าน Sheets เหมือนเดิม

---

## 6. สิ่งที่ต้องคอนเฟิร์มก่อนเริ่มนำเข้าข้อมูลจริง

ไม่บล็อกการออกแบบ แต่บล็อก "ข้อมูลจริง" ไม่ให้ผิดบ้าน:

1. **รหัสโครงการชนกัน** — MRC-2026-008 (แม่โจ้) vs MRC-2025-008, และ MRC-2026-022 vs MRC-2025-022 (ดอยสะเก็ด) เป็นบ้านเดียวกันพิมพ์ปีผิด หรือคนละหลัง? (ต้องรู้ก่อนนำเข้า ไม่งั้นบันทึกงานผิดโครงการ)
2. **เลือก 2-3 โครงการนำร่อง** — ขอ 1 บ้านชั้นเดียว, 1 บ้านสองชั้น, 1 โครงการที่มีปัญหาค้างอยู่ (ตามที่เสนอใน Mirana plan P01) — จะใช้โครงการไหนบ้าง?
3. **WBS ต้นแบบ** — ใช้ Operation Plan / Construction Plan (1 ชั้น, 2 ชั้น) ที่แนบมาเป็นต้นแบบได้เลยไหม หรือมีเวอร์ชันใหม่กว่านี้?
4. **นิยาม "เสร็จ"** — งานนับเป็น % ความคืบหน้าแบบถ่วงน้ำหนัก หรือแค่ checkbox เสร็จ/ไม่เสร็จพอสำหรับช่วงแรก? (ละเอียดขึ้นทีหลังได้)
5. **ผู้ตรวจยืนยัน (verified_done)** — ให้ SE เป็นคนกดยืนยันในแชทใช่ไหม หรือใครอีกบ้าง?

ตอบเท่าที่สะดวกครับ ข้อ 2-3 สำคัญสุดเพราะเป็นตัวกำหนดว่าจะเริ่มนำเข้าข้อมูลโครงการไหนก่อน ข้อที่เหลือใช้ค่าเริ่มต้นตามข้างบนไปก่อนได้ แล้วปรับทีหลังได้เรื่อยๆ

---

## 7. ขั้นต่อไป (ถ้าคอนเฟิร์มแล้ว)

1. ผมสร้างฐานข้อมูล (ทางเลือก A) พร้อม schema ข้อ 2
2. นำเข้า Task_Templates จาก Construction/Operation Plan (บ้าน 1/2 ชั้น) — ล้าง ID ซ้ำ
3. นำเข้าโครงการนำร่อง 2-3 โครงการที่เลือก
4. ทดสอบ: ส่งข้อความรายงานตัวอย่างแบบ LINE เดิมเข้ามาในแชทนี้ ให้ Agent พาร์ส+บันทึก+ขอยืนยัน
5. ทดสอบขอสรุปสถานะ/งานค้างของโครงการนำร่อง
