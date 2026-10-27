"""Regression fixtures retain real layout coordinates but replace all identities.

They are rendered into actual PDFs, so tests cover PDF decoding as well as
mapping. Source PDFs containing student identities are not bundled.
"""
import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import pymupdf

from result_data.parsers import DBATUCrystalReportParser, PDFExtractionError, UnsupportedPDFError

FIXTURES = json.loads((Path(__file__).parent / 'fixtures' / 'dbatu_layouts.json').read_text())


def fixture_document(indices, size=(1587, 842), transform=None):
    document = pymupdf.open()
    for index in indices:
        source = pymupdf.open()
        page = source.new_page(width=1587, height=842)
        words = copy.deepcopy(FIXTURES[index]['words'])
        if transform:
            words = transform(words)
        for x0,y0,x1,y1,text in words:
            font_size = (y1-y0)/1.374
            page.insert_text((x0,y0+font_size*1.075), text, fontsize=font_size)
        output = document.new_page(width=size[0], height=size[1])
        output.show_pdf_page(output.rect, source, 0, keep_proportion=False)
        source.close()
    return document


def custom_document(rows=('ESE TOTAL','CA INTERNAL','MID INTERNAL','INT TOTAL'),
                    maxima=('60/20','20','20',None), marks=('040','015','010',None),
                    columns=('CS101','CS102'), additional_summary=False):
    document = pymupdf.open()
    p = document.new_page(width=1587,height=842)
    def text(x,y,value,size=8):
        p.insert_text((x,y),value,fontsize=size)
    text(600,30,'Dr. Babasaheb Ambedkar Technological University')
    text(42,45,'EXAMINATION : Bachelor of Technology (Example Engineering) SEMESTER - 1 Summer 2026 ( Regular )')
    for i,code in enumerate(columns):
        text(40+400*i,65,code+' : EXAMPLE SUBJECT '+str(i+1)+' (Credit :4 )')
    text(21,110,'Seat No. (Gen.)Name INSTITUTE Code - Name')
    text(1538,110,'Result')
    text(1400,120,'SGPA');text(1364,130,'Tot.GrP.-80.00');text(1448,130,'Cr.8.00');text(1498,140,'Total Marks(200)')
    if additional_summary:
        text(1470,120,'Bonus(10)')
    for i,code in enumerate(columns):text(120+100*i,145,code)
    text(23,170,'CREDIT')
    for i in range(len(columns)):text(140+100*i,170,'4')
    for j,label in enumerate(rows):
        text(23,185+15*j,label)
        for i in range(len(columns)):
            if maxima[j] is not None:text(130+100*i,185+15*j,maxima[j])
    text(23,185+15*len(rows),'TOTAL')
    for i in range(len(columns)):text(130+100*i,185+15*len(rows),'100/40')
    start=290
    text(21,start,'99000000000001',10)
    text(112,start,'SAMPLE STUDENT 99999 - Example Institute',10)
    text(1530,start,'PASS',10)
    text(21,start+26,'99999 (Whole)')
    for j,mark in enumerate(marks):
        for i in range(len(columns)):
            if mark is not None:text(130+100*i,start+10.54+18.6*j,mark,10)
    total_y=start+10.54+18.6*len(rows)
    for i in range(len(columns)):
        text(130+100*i,total_y,'065',10)
        text(130+100*i,total_y+21.76,'7/CC/28',7)
        text(130+100*i,total_y+33.16,'JUNE - 2026',7)
    text(1395,start+12.99,'7.00',10)
    text(1395,start+27.44,'56.00',10)
    text(1532,start+27.44,'8.00',10)
    text(1540,start+41.32,'130',10)
    if additional_summary:text(1480,start+12.99,'5',10)
    return document


class AdaptiveResultParserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.parser = DBATUCrystalReportParser()

    def tearDown(self):
        self.temp.cleanup()

    def parse_document(self, doc):
        path=Path(self.temp.name)/'sample.pdf'
        doc.save(path);doc.close()
        return self.parser.parse(path)

    def test_each_real_layout_and_expected_summaries(self):
        expected=[(12,None,'137.50','20','738'), (8,None,'97','19','345'),
                  (8,None,None,None,'379'), (9,'6.11','134.50','22','486'),
                  (9,None,None,None,None), (8,'6.48','142.50','22','453')]
        for i,values in enumerate(expected):
            with self.subTest(layout=i):
                report=self.parse_document(fixture_document([i]))
                self.assertEqual(len(report.students), FIXTURES[i]['students'])
                self.assertEqual(len(report.subjects),values[0])
                if i==4:continue
                summary=report.students[0].summary
                for field,value in zip(('reported_sgpa','reported_total_grade_points','reported_earned_credits','reported_total_marks'),values[1:]):
                    self.assertEqual(getattr(summary,field), Decimal(value) if value else None,field)

    def test_short_codes_and_multiline_catalogue(self):
        report=self.parse_document(fixture_document([3]))
        subjects={s.code:s for s in report.subjects}
        self.assertIn('BTBS404',subjects)
        self.assertIn('BTUHV34',subjects)
        self.assertEqual(subjects['BTECPL406'].credits,Decimal('2'))
        self.assertEqual(subjects['BTECPL406'].name,'PYTHON PROGRAMMING LAB AND DATABASE MANAGEMENT SYSTEM LAB')
        self.assertNotIn('BTECPE405A',subjects)

    def test_elective_switch_between_pages_has_no_fake_missing_subject(self):
        report=self.parse_document(fixture_document([3,4]))
        self.assertEqual(len(report.subjects),10)
        self.assertIn('BTECPE405B',report.page_subject_codes[1])
        self.assertNotIn('BTECPE405A',report.page_subject_codes[1])
        self.assertIn('BTECPE405A',report.page_subject_codes[2])
        for student in report.students:
            self.assertEqual(len(student.subject_results),9)
            self.assertEqual({r.subject_code for r in student.subject_results},set(report.page_subject_codes[student.source_page]))

    def test_scaled_pdf_keeps_values(self):
        original=self.parse_document(fixture_document([0]))
        scaled=self.parse_document(fixture_document([0],size=(1000,600)))
        self.assertEqual([s.code for s in original.subjects],[s.code for s in scaled.subjects])
        self.assertEqual([s.summary for s in original.students],[s.summary for s in scaled.students])
        for left,right in zip(original.students,scaled.students):
            self.assertEqual([r.total for r in left.subject_results],[r.total for r in right.subject_results])
            self.assertEqual([r.grade_raw for r in left.subject_results],[r.grade_raw for r in right.subject_results])

    def test_old_office_record_extra_summary_columns_retained(self):
        report=self.parse_document(fixture_document([1]))
        values=report.students[0].summary.additional_values
        self.assertEqual(values['external_total']['numeric_value'],'153')
        self.assertEqual(values['internal_total']['numeric_value'],'192')
        self.assertTrue(any('percentage' in s.summary.additional_values for s in report.students if s.result_status=='PASS'))
        subject=next(s for s in report.subjects if s.code=='BTES211P')
        self.assertEqual(subject.total_maximum,Decimal('50'))
        self.assertIsNone(subject.total_minimum)

    def test_cancellation_carried_forward_and_absence_are_preserved(self):
        report=self.parse_document(fixture_document([2]))
        self.assertEqual(report.students[0].result_status,'CANCEL')
        self.assertEqual(report.students[0].summary.reported_total_marks,Decimal('379'))
        self.assertTrue(any(r.attempt_session=='APRIL - 2024' for r in report.students[0].subject_results))
        carried=[v for s in report.students for r in s.subject_results for _,v in r.components if v.is_carried_forward]
        self.assertTrue(carried)
        report=self.parse_document(fixture_document([0]))
        self.assertTrue(any(v.special_code=='AB' for s in report.students for r in s.subject_results for _,v in r.components))

    def test_printed_grade_placeholder_is_preserved(self):
        report=self.parse_document(fixture_document([3]))
        result=next(r for r in report.students[0].subject_results if r.subject_code=='BTUHV34')
        self.assertEqual(result.total.numeric_value,Decimal('62'))
        self.assertEqual(result.grade_raw,'|')
        self.assertIsNone(result.grade)

    def test_added_assessment_row_is_extracted(self):
        report=self.parse_document(custom_document(rows=('ESE TOTAL','CA INTERNAL','MID INTERNAL','TW'),
            maxima=('60/20','20','20','10'),marks=('040','015','010','007')))
        result=report.students[0].subject_results[0]
        self.assertEqual(dict(result.components)['TW'].numeric_value,Decimal('7'))
        self.assertEqual(result.total.numeric_value,Decimal('65'))
        self.assertEqual(result.grade,'CC')

    def test_omitted_assessment_row_does_not_shift_later_values(self):
        report=self.parse_document(custom_document(rows=('ESE TOTAL','CA INTERNAL'),
            maxima=('80/20','20'),marks=('050','015')))
        result=report.students[0].subject_results[0]
        self.assertEqual([v.numeric_value for _,v in result.components],[Decimal('50'),Decimal('15')])
        self.assertEqual(result.total.numeric_value,Decimal('65'))
        self.assertEqual(result.credit_points,Decimal('28'))

    def test_internal_only_report_does_not_require_ese_row(self):
        report=self.parse_document(custom_document(rows=('INT TOTAL',),maxima=('100',),marks=('065',)))
        self.assertEqual(report.students[0].subject_results[0].components[0][0],'INTERNAL_TOTAL')
        self.assertEqual(report.students[0].subject_results[0].total.numeric_value,Decimal('65'))

    def test_extra_and_fewer_subject_columns(self):
        for codes in [('CS101',),('CS101','CS102','CS103')]:
            with self.subTest(codes=codes):
                report=self.parse_document(custom_document(columns=codes))
                self.assertEqual([s.code for s in report.subjects],list(codes))
                self.assertEqual(len(report.students[0].subject_results),len(codes))

    def test_new_optional_summary_heading_is_retained(self):
        report=self.parse_document(custom_document(additional_summary=True))
        self.assertEqual(report.students[0].summary.additional_values['bonus_10']['numeric_value'],'5')
        self.assertEqual(report.students[0].summary.reported_sgpa,Decimal('7'))

    def test_distinct_ese_rows_do_not_collide(self):
        report=self.parse_document(custom_document(rows=('ESE TOTAL','ESE TOTAL','CA INTERNAL'),
            maxima=('30/10','30/10','40'),marks=('020','025','020')))
        self.assertEqual([a.component_type for a in report.subjects[0].assessments],['ESE','ESE_1','CA'])
        self.assertEqual([v.numeric_value for _,v in report.students[0].subject_results[0].components],[Decimal('20'),Decimal('25'),Decimal('20')])

    def test_blank_mark_remains_missing_without_shifting(self):
        report=self.parse_document(custom_document(rows=('ESE TOTAL','CA INTERNAL','MID INTERNAL'),
            maxima=('60/20','20','20'),marks=('040',None,'010')))
        result=report.students[0].subject_results[0]
        self.assertEqual({k:v.numeric_value for k,v in result.components},{'ESE':Decimal('40'),'MID':Decimal('10')})
        self.assertEqual(result.total.numeric_value,Decimal('65'))

    def test_catalogue_missing_subject_definition_uses_printed_code(self):
        def remove_definition(words):
            return [w for w in words if not (w[4]=='BTHM403' and w[1]<100)]
        report=self.parse_document(fixture_document([3],transform=remove_definition))
        self.assertEqual(len(report.subjects),9)
        self.assertIn('BTHM403',[s.code for s in report.subjects])

    def test_missing_credit_label_does_not_join_credits_to_codes(self):
        report=self.parse_document(fixture_document([3],transform=lambda words:[w for w in words if w[4]!='CREDIT']))
        self.assertIn('BTUHV34',[s.code for s in report.subjects])
        self.assertEqual(report.students[0].summary.reported_total_marks,Decimal('486'))

    def test_omitted_summary_heading_does_not_shift_other_summary_fields(self):
        report=self.parse_document(fixture_document([3],transform=lambda words:[w for w in words if w[4]!='SGPA']))
        summary=report.students[0].summary
        self.assertIsNone(summary.reported_sgpa)
        self.assertEqual(summary.reported_total_grade_points,Decimal('134.50'))
        self.assertEqual(summary.reported_earned_credits,Decimal('22'))
        self.assertEqual(summary.reported_total_marks,Decimal('486'))

    def test_missing_printed_total_does_not_move_component_marks(self):
        doc=custom_document()
        page=doc[0]
        totals=[w for w in page.get_text('words') if w[4]=='065']
        for w in totals:page.add_redact_annot(pymupdf.Rect(w[:4]))
        page.apply_redactions()
        report=self.parse_document(doc)
        result=report.students[0].subject_results[0]
        self.assertIsNone(result.total)
        self.assertEqual({k:v.numeric_value for k,v in result.components},{'ESE':Decimal('40'),'CA':Decimal('15'),'MID':Decimal('10')})

    def test_duplicate_seat_number_is_not_silently_dropped(self):
        with self.assertRaisesRegex(PDFExtractionError,'Duplicate seat'):
            self.parse_document(fixture_document([5,5]))

    def test_image_only_pdf_has_actionable_error(self):
        doc=pymupdf.open();doc.new_page()
        with self.assertRaisesRegex(UnsupportedPDFError,'OCR'):
            self.parse_document(doc)


if __name__=='__main__':unittest.main()
