import io
from pathlib import Path
from decimal import Decimal
import re
import unittest
import fitz
from openpyxl import load_workbook
import test_university_reports as fixtures
from test_adaptive_result_parser import fixture_document,custom_document
from result_data.models import DataCorrection,ResultSourceData,ReportStudent,StudentSummary
from result_data.parsers import DBATUCrystalReportParser
from result_data.parsers.value_normalizer import parse_grade
from result_data.services.export_service import build_pdf_export,build_excel_export
from result_data.services.faculty_report_service import build_faculty_report
from result_data.services.grade_repair_service import repair_missing_grades
from result_data.services.grade_service import display_grade
from result_data.services.report_pdf_service import ASSET


class ExactTemplateAndGradeTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.UniversityReportTests();self.case.setUp()
        self.job=self.case.job;self.db=self.case.db
    def tearDown(self):self.case.tearDown()

    def test_reference_letterhead_is_reused_without_student_records(self):
        original=fitz.open(ASSET)
        self.assertFalse(re.search(r'\d{12,20}',''.join(p.get_text() for p in original)))
        result=fitz.open(stream=build_pdf_export(self.job).data,filetype='pdf')
        clip=fitz.Rect(0,0,594.96,170)
        self.assertEqual(original[0].get_pixmap(clip=clip).samples,result[0].get_pixmap(clip=clip).samples)
        self.assertTrue(all(p.rect.width<p.rect.height for p in result))
        text='\n'.join(p.get_text() for p in result)
        for label in ['OVERALL RESULT','SUBJECT WISE RESULT','TOPPER LIST','FAILED STUDENTS','ALL STUDENTS RESULTS','GENDER','SEAT NO.']:
            self.assertIn(label,text)
        self.assertNotIn('Highest SGPA:',text)
        self.assertNotIn('Example subject 1\nSUB1\nResult\nSGPA',text)

    def test_seventy_four_students_follow_reference_continuation(self):
        self.job.report.students[0].seat_number='2502533111844012'
        for index in range(16,75):
            s=ReportStudent(seat_number=str(99000000000000+index),name=f'Example Student {index}',gender_marker='M',source_page=1,result_status='PASS')
            s.summary=StudentSummary(reported_sgpa=Decimal('7.5'),reported_status='PASS')
            self.job.report.students.append(s)
        self.db.session.flush()
        result=fitz.open(stream=build_pdf_export(self.job).data,filetype='pdf')
        self.assertEqual(len(result),7)
        for page in result[-3:]:self.assertIn('STUDENT NAME',page.get_text())
        self.assertIn('RESULT ANALYSIS',result[-1].get_text())
        for student in self.job.report.students:self.assertIn(student.seat_number,'\n'.join(p.get_text() for p in result))

    def test_excel_recovers_raw_printed_grade_and_labels_real_missing(self):
        result=self.job.report.students[0].subject_results[0]
        result.grade=None;result.grade_raw='8.5 / AB / 34 (G-4)'
        second=self.job.report.students[0].subject_results[1]
        second.grade=None;second.grade_raw='|';second.expected_grade='AA'
        values=build_faculty_report(self.job)['students'][0]['grades']
        self.assertEqual(values,['AB','NOT PRINTED'])
        book=load_workbook(io.BytesIO(build_excel_export(self.job).data))
        self.assertEqual(book['Student Results']['D11'].value,'AB')
        self.assertEqual(book['Student Results']['E11'].value,'NOT PRINTED')
        self.assertIn('NOT PRINTED',book['Student Results']['A8'].value)

    def test_non_applicable_elective_is_explicit(self):
        student=self.job.report.students[-1];student.source_page=2
        self.job.report.source_data=ResultSourceData(data={'page_subject_codes':{'1':['SUB1','SUB2'],'2':['SUB1']}})
        self.assertEqual(build_faculty_report(self.job)['students'][-1]['grades'][1],'N/A')

    def test_manual_clear_is_not_undone_by_repair_or_raw_fallback(self):
        result=self.job.report.students[0].subject_results[0];result.grade=None
        self.job.report.corrections.append(DataCorrection(student=result.student,subject_result=result,
            entity_type='SUBJECT_RESULT',entity_label='SUB1',field_name='grade',previous_value='BB',new_value=None,
            reason='Faculty cleared the value for review.'))
        self.db.session.flush()
        self.assertIsNone(display_grade(result))
        self.assertEqual(repair_missing_grades(self.job,'/missing'),0)
        self.assertIsNone(result.grade)

    def test_existing_missing_label_is_repaired_without_reextracting(self):
        result=self.job.report.students[0].subject_results[0];result.grade=None
        before=len(self.job.report.students)
        count=repair_missing_grades(self.job,'/missing')
        self.assertEqual(count,1)
        self.assertEqual(result.grade,'BB')
        self.assertEqual(len(self.job.report.students),before)
        self.assertEqual(self.job.status,'REVIEW_REQUIRED')
        self.assertTrue(any(c.entity_type=='SOURCE_GRADE_REPAIR' for c in self.job.report.corrections))

    def test_grade_spacing_and_standalone_audit(self):
        parsed=parse_grade('8.5 / AB / 34 ( G-4 )')
        self.assertEqual(parsed.grade,'AB');self.assertEqual(parsed.grace_marks,4)
        result=self.job.report.students[0].subject_results[0]
        result.subject.is_audit=True;result.audit_grade=None;result.grade_raw='AU'
        self.assertEqual(display_grade(result),'AU')

    def test_shifted_grade_baseline_stays_in_its_own_subject(self):
        def shift(words):
            for word in words:
                if word[4]=='7/CC/14' and 500<word[0]<600:
                    word[1]+=7;word[3]+=7
            return words
        document=fixture_document([3],transform=shift)
        path=Path(fixtures.base.TEST_DIR)/'shifted_grade.pdf';document.save(path);document.close()
        report=DBATUCrystalReportParser().parse(path)
        result=next(r for r in report.students[0].subject_results if r.subject_code=='BTECPL406')
        self.assertEqual(result.grade,'CC')


if __name__=='__main__':unittest.main()
