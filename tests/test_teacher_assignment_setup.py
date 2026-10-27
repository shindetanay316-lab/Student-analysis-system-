import re
import unittest
import test_workflows as base
from models import db, User, Subject, Semester, Student, Enrollment
from teaching_models import TeachingAssignment,StaffAccessAudit
from routes_teaching import normalize_academic_year


class AssignmentSetupTests(unittest.TestCase):
    def setUp(self):
        self.fixture=base.WorkflowTestCase();self.fixture.setUp()
        self.client=self.fixture.client
        self.teacher=User.query.filter_by(username='teacher').one()

    def tearDown(self):self.fixture.tearDown()

    def token(self):
        page=self.client.get('/teachers')
        return re.search(rb'name="csrf_token" value="([^"]+)"',page.data).group(1).decode()

    def assign(self,**changes):
        fields={'teacher_id':self.teacher.user_id,'subject_code':'TH601','semester_id':6,'academic_year':'2026-27','csrf_token':self.token()}
        fields.update(changes)
        return self.client.post('/teachers/assign',data=fields)

    def test_page_defaults_to_active_semester_with_real_enabled_subjects(self):
        response=self.client.get('/teachers');self.assertEqual(response.status_code,200)
        text=response.data.decode()
        options=re.search(r'<select id="subject".*?</select>',text,re.S).group()
        self.assertIn('TH601',options);self.assertIn('LB601',options)
        self.assertNotIn('EL600"',options);self.assertNotIn('disabled',options)
        self.assertIn('Type the subject name or code',text)
        self.assertIn('subject-assignment-form',text)
        self.assertNotIn('filterSubjects()',text)

    def test_all_semesters_and_editable_academic_year_exist_without_seeded_terms(self):
        response=self.client.get('/teachers?academic_year=2026-27&semester_id=6')
        text=response.data.decode();self.assertEqual(response.status_code,200)
        select=re.search(r'<select id="semester".*?</select>',text,re.S).group()
        for sem in range(1,9):self.assertIn(f'value="{sem}"',select)
        self.assertIn('name="academic_year" class="form-control"',text)
        self.assertIn('value="2026-27"',text)
        self.assertIsNone(db.session.get(Semester,(6,'2026-27')))

    def test_new_year_assignment_creates_only_needed_term_and_preserves_active_term(self):
        response=self.assign();self.assertEqual(response.status_code,302)
        self.assertIn('academic_year=2026-27',response.location)
        term=db.session.get(Semester,(6,'2026-27'));self.assertIsNotNone(term);self.assertFalse(term.is_active)
        self.assertTrue(db.session.get(Semester,(6,'2025-26')).is_active)
        self.assertIsNone(db.session.get(Semester,(7,'2026-27')))
        self.assertEqual(TeachingAssignment.query.filter_by(academic_year='2026-27').count(),1)
        self.assertIsNotNone(StaffAccessAudit.query.filter_by(action='ACADEMIC_TERM_CREATED').first())
        self.assertEqual(self.assign(academic_year='2026-2027').status_code,302)
        self.assertEqual(TeachingAssignment.query.count(),1)
        self.fixture.logout();self.fixture.login('teacher','teacher123')
        page=self.client.get('/my-subjects');self.assertIn(b'2026-27',page.data)
        self.assertEqual(self.client.get('/ct1?subject_code=TH601&semester_id=6&academic_year=2026-27&exam_type=CT1').status_code,200)
        self.assertEqual(self.client.get('/ct1?subject_code=TH601&semester_id=6&academic_year=2025-26&exam_type=CT1').status_code,403)

    def test_empty_semester_gives_setup_link_and_no_unusable_assignment_form(self):
        response=self.client.get('/teachers?academic_year=2026-27&semester_id=7')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'No active subjects are configured for Semester 7',response.data)
        self.assertIn(b'/subjects?semester_id=7',response.data)
        self.assertNotIn(b'id="subject-assignment-form"',response.data)
        self.assertNotIn(b'id="subject"',response.data)

    def test_subject_added_to_another_semester_can_be_loaded_and_assigned(self):
        db.session.add(Subject(subject_code='TH701',subject_name='Semester Seven Example',semester_id=7,subject_type='THEORY',is_active=True))
        db.session.commit()
        response=self.client.get('/teachers?academic_year=2026-27&semester_id=7')
        self.assertIn(b'Semester Seven Example',response.data)
        self.assertNotIn(b'value="TH601"',re.search(rb'<select id="subject".*?</select>',response.data,re.S).group())
        self.assertEqual(self.assign(subject_code='TH701',semester_id=7).status_code,302)

    def test_roster_preview_distinguishes_cohorts_divisions_batches_and_years(self):
        import json
        db.session.add(Student(prn='OTHER',name='Another cohort',year_of_admission=2024,division='C',batch='C2'))
        db.session.add(Enrollment(prn='OTHER',subject_code='TH601',semester_id=6,academic_year='2025-26'))
        db.session.add(Enrollment(prn='S001',subject_code='TH601',semester_id=6,academic_year='2024-25'))
        db.session.commit()
        page=self.client.get('/teachers?academic_year=2025-26&semester_id=6')
        data=json.loads(re.search(rb'<script type="application/json" id="assignment-roster-data">(.*?)</script>',page.data,re.S).group(1))
        self.assertEqual(sum(row['count'] for row in data['TH601']),4)
        self.assertTrue(any(row['cohort']==2024 and row['division']=='C' and row['batch']=='C2' for row in data['TH601']))
        page=self.client.get('/teachers?academic_year=2026-27&semester_id=6')
        data=json.loads(re.search(rb'<script type="application/json" id="assignment-roster-data">(.*?)</script>',page.data,re.S).group(1))
        self.assertEqual(data['TH601'],[])

    def test_invalid_year_or_mismatched_subject_creates_no_term(self):
        for year in ['2026-29','nonsense','2026-2028']:
            self.assertEqual(self.assign(academic_year=year).status_code,400)
        self.assertEqual(self.assign(semester_id=7).status_code,400)
        self.assertIsNone(db.session.get(Semester,(7,'2026-27')))
        self.assertEqual(TeachingAssignment.query.count(),0)
        self.assertEqual(normalize_academic_year('2026 / 2027'),'2026-27')

    def test_teacher_cannot_create_term_through_assignment(self):
        token=self.token();self.fixture.logout();self.fixture.login('teacher','teacher123')
        self.assertEqual(self.client.post('/teachers/assign',data={'csrf_token':token,'teacher_id':self.teacher.user_id,
            'subject_code':'TH601','semester_id':6,'academic_year':'2026-27'}).status_code,403)
        self.assertIsNone(db.session.get(Semester,(6,'2026-27')))


if __name__=='__main__':unittest.main()
