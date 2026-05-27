ECE SMS — Batch / Division Support Patch

WHAT THIS PATCH ADDS
1. Adds Student.division and Student.batch fields.
2. Adds /batches admin page to assign Division + Batch to students.
3. Adds optional Division/Batch filters to:
   - CT/Internal marks template download
   - CT individual report download
   - Lab page/template/report
   - External page/template/report
4. Keeps subject enrollments and existing marks untouched.

FILES TO COPY INTO ece_sms ROOT
- app.py
- models.py
- batch_utils.py
- routes_batches.py
- routes_lab.py
- routes_external.py
- lab_report_utils.py
- external_report_utils.py
- lab_excel_utils.py
- external_excel_utils.py

FILES TO COPY INTO templates/
- batch_assignment.html
- ct1.html
- lab.html
- external.html

SQL TO RUN FIRST
- sql/phase_batch_division_schema.sql

TEST COMMAND
python -m py_compile app.py models.py batch_utils.py routes_batches.py routes_lab.py routes_external.py lab_report_utils.py external_report_utils.py lab_excel_utils.py external_excel_utils.py

TEST FLOW
1. Run SQL.
2. Replace files.
3. Run py_compile.
4. Start Flask: python app.py
5. Login as ADMIN.
6. Open /batches.
7. Assign a few students to Division A, Batch A1.
8. Open /lab or /ct1.
9. Select Division A / Batch A1 and download template.
