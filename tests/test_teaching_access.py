import io
import re
import unittest
from datetime import date,time
from openpyxl import load_workbook
import test_workflows as base
from models import db,User,Subject,Semester,TheoryMarks,ExternalMarks,AttendanceEntry,AttendanceSession,TimetableSlot
from teaching_models import TeachingAssignment,StaffAccessState,StaffAccessAudit
from attendance_utils import generate_attendance_template


class TeachingAccessTests(unittest.TestCase):
    def setUp(self):
        self.fixture=base.WorkflowTestCase();self.fixture.setUp()
        self.client=self.fixture.client;self.app=base.app
        self.teacher=User.query.filter_by(username='teacher').one()
        self.assignment=TeachingAssignment(teacher_id=self.teacher.user_id,subject_code='TH601',semester_id=6,academic_year='2025-26')
        db.session.add(self.assignment);db.session.commit()

    def tearDown(self):self.fixture.tearDown()

    def token(self):
        from flask import g
        g.pop('csrf_token',None)
        response=self.client.get('/profile/password')
        return re.search(rb'name="csrf_token" value="([^"]+)"',response.data).group(1).decode()

    def teacher_login(self):
        self.fixture.logout();self.fixture.login('teacher','teacher123')

    def post(self,url,data):
        return self.client.post(url,data={**data,'csrf_token':self.token()})

    def test_admin_accounts_assignments_and_audit_render(self):
        page=self.client.get('/teachers');self.assertEqual(page.status_code,200)
        self.assertIn(b'Teacher accounts',page.data)
        response=self.post('/teachers/create',{'username':'new.teacher','password':'temporary123'})
        self.assertEqual(response.status_code,302)
        user=User.query.filter_by(username='new.teacher').one()
        self.assertTrue(user.check_password('temporary123'))
        self.assertTrue(db.session.get(StaffAccessState,user.user_id).must_change_password)
        self.assertEqual(self.post('/teachers/assign',{'teacher_id':user.user_id,'subject_code':'LB601','semester_id':6,'academic_year':'2025-26'}).status_code,302)
        self.assertEqual(TeachingAssignment.query.filter_by(teacher_id=user.user_id).count(),1)
        self.assertEqual(self.post('/teachers/assign',{'teacher_id':user.user_id,'subject_code':'LB601','semester_id':6,'academic_year':'2025-26'}).status_code,302)
        self.assertEqual(TeachingAssignment.query.filter_by(teacher_id=user.user_id).count(),1)
        self.assertTrue(StaffAccessAudit.query.filter_by(user_id=user.user_id,action='TEACHER_CREATED').first())
        self.assertNotIn('temporary123',str([x.details for x in StaffAccessAudit.query.all()]))

    def test_invalid_assignment_and_duplicate_username_are_rejected(self):
        fields={'teacher_id':self.teacher.user_id,'semester_id':6,'academic_year':'2025-26'}
        for change in ({'subject_code':'EL600'},{'subject_code':'TH601','semester_id':5},{'subject_code':'TH601','academic_year':'2030-33'}):
            self.assertEqual(self.post('/teachers/assign',{**fields,**change}).status_code,400)
        self.assertEqual(self.post('/teachers/create',{'username':'teacher','password':'temporary123'}).status_code,400)
        self.assertEqual(self.post('/teachers/create',{'username':'another','password':'short'}).status_code,400)

    def test_teacher_workspace_subject_dropdown_and_card_context(self):
        self.teacher_login()
        page=self.client.get('/');self.assertEqual(page.status_code,200)
        self.assertIn(b'My Subjects',page.data);self.assertIn(b'Theory Subject',page.data)
        self.assertNotIn(b'Lab Subject',page.data)
        self.assertIn(b'academic_year=2025-26',page.data)
        data=self.client.get('/api/theory-subjects?semester_id=6&academic_year=2025-26').json
        self.assertEqual([s['subject_code'] for s in data['subjects']],['TH601'])
        self.assertEqual(self.client.get('/api/lab-subjects?semester_id=6&academic_year=2025-26').json['subjects'],[])
        self.assertEqual(self.client.get('/api/theory-subjects?semester_id=6&academic_year=2024-25').json['subjects'],[])

    def test_no_assignment_grants_no_subject_access(self):
        self.assignment.is_active=False;db.session.commit();self.teacher_login()
        self.assertIn(b'No active subject assignments',self.client.get('/my-subjects').data)
        self.assertEqual(self.client.get('/download-ct1-template?subject_code=TH601&semester_id=6&academic_year=2025-26&exam_type=CT1').status_code,403)

    def test_cross_subject_year_and_route_tampering_is_denied(self):
        self.teacher_login()
        paths=['/ct1','/download-ct1-template','/download-ct1-report/excel','/download-internal-report/pdf',
            '/external','/download-external-template','/download-external-report/excel','/external/stats',
            '/lab','/download-lab-template','/download-lab-report/pdf','/attendance','/attendance/download-template','/attendance/defaulters/excel']
        for path in paths:
            code='LB601' if 'lab' in path else 'EL601A'
            response=self.client.get(path+f'?subject_code={code}&semester_id=6&academic_year=2025-26&exam_type=CT1')
            self.assertEqual(response.status_code,403,path)
        self.assertEqual(self.client.get('/ct1?subject_code=TH601&semester_id=6&academic_year=2024-25&exam_type=CT1').status_code,403)
        token=self.token()
        response=self.client.post('/external/save?subject_code=TH601&semester_id=6&academic_year=2025-26',json={
            'subject_code':'EL601A','semester_id':6,'academic_year':'2025-26','marks':[]},headers={'X-CSRFToken':token})
        self.assertEqual(response.status_code,403)
        response=self.client.post('/upload-ct1?subject_code=TH601',data={
            'subject_code':'EL601A','semester_id':6,'academic_year':'2025-26','csrf_token':token})
        self.assertEqual(response.status_code,403)

    def test_teacher_cannot_manage_staff_or_admin_setup(self):
        self.teacher_login()
        self.assertEqual(self.client.get('/teachers').status_code,403)
        self.assertEqual(self.post('/teachers/create',{'username':'intruder','password':'temporary123'}).status_code,403)
        self.assertEqual(self.post('/teachers/assignments/'+str(self.assignment.id)+'/revoke',{}).status_code,403)

    def test_assigned_teacher_uploads_and_revoked_template_cannot_write(self):
        self.teacher_login()
        query='?subject_code=TH601&semester_id=6&academic_year=2025-26&exam_type=CT1&division=A&batch=A1&subject_teacher=Teacher'
        response=self.client.get('/download-ct1-template'+query);self.assertEqual(response.status_code,200)
        data=self.fixture._fill_ct_template(response,[8]);token=self.token()
        self.assignment.is_active=False;db.session.commit()
        response=self.client.post('/upload-ct1',data={'subject_code':'TH601','semester_id':6,'academic_year':'2025-26','exam_type':'CT1',
            'division':'A','batch':'A1','csrf_token':token,'ct1_file':(io.BytesIO(data),'marks.xlsx')})
        self.assertEqual(response.status_code,403);self.assertEqual(TheoryMarks.query.count(),0)
        self.assignment.is_active=True;db.session.commit()
        response=self.client.post('/upload-ct1',data={'subject_code':'TH601','semester_id':6,'academic_year':'2025-26','exam_type':'CT1',
            'division':'A','batch':'A1','csrf_token':token,'ct1_file':(io.BytesIO(data),'marks.xlsx')})
        self.assertEqual(response.status_code,302);self.assertEqual(TheoryMarks.query.count(),0)
        self.assertEqual(self.client.post(response.location+'/confirm',data={'csrf_token':token}).status_code,302)
        self.assertEqual(TheoryMarks.query.count(),1)

    def test_attendance_workbook_metadata_cannot_override_assignment(self):
        from models import Student
        meta={'semester_id':6,'academic_year':'2025-26','subject_code':'LB601','subject_name':'Lab Subject','division':'A','batch':'A1'}
        from types import SimpleNamespace
        values=[{'date':date(2026,1,5),'slot':SimpleNamespace(start_time=time(10),end_time=time(11),session_type='LAB'),'label':'05/01/2026 10:00'}]
        stream,_=generate_attendance_template(meta,[db.session.get(Student,'S001')],values)
        self.teacher_login();token=self.token()
        response=self.client.post('/attendance/upload',data={'csrf_token':token,'subject_code':'TH601',
            'attendance_file':(stream,'attendance.xlsx')})
        self.assertEqual(response.status_code,403)
        self.assertEqual(AttendanceEntry.query.count(),0);self.assertEqual(AttendanceSession.query.count(),0)

    def test_disable_and_password_reset_invalidate_sessions(self):
        self.teacher_login();self.assertEqual(self.client.get('/my-subjects').status_code,200)
        state=StaffAccessState(user_id=self.teacher.user_id,credential_version=1,must_change_password=True)
        db.session.add(state);db.session.commit()
        self.assertEqual(self.client.get('/my-subjects').status_code,302)
        self.assertIn('/login',self.client.get('/my-subjects').location)
        self.fixture.login('teacher','teacher123')
        self.assertIn('/profile/password',self.client.get('/my-subjects').location)
        response=self.post('/profile/password',{'current_password':'teacher123','new_password':'teacher-new-123','confirm_password':'teacher-new-123'})
        self.assertEqual(response.status_code,302,response.data);self.assertEqual(self.client.get('/my-subjects').status_code,200)
        self.teacher.is_active=False;db.session.commit()
        self.assertIn('/login',self.client.get('/my-subjects').location)

    def test_csrf_required_for_new_admin_forms_and_teacher_writes(self):
        self.assertEqual(self.client.post('/teachers/create',data={'username':'bad','password':'temporary123'}).status_code,400)
        self.teacher_login()
        self.assertEqual(self.client.post('/upload-ct1',data={'subject_code':'TH601','semester_id':6,'academic_year':'2025-26'}).status_code,400)

    def test_admin_revoke_keeps_marks_and_allows_reassignment(self):
        marks=TheoryMarks(prn='S001',subject_code='TH601',semester_id=6,academic_year='2025-26',ct1=8)
        db.session.add(marks);db.session.commit();key=marks.id
        response=self.post('/teachers/assignments/'+str(self.assignment.id)+'/revoke',{})
        self.assertEqual(response.status_code,302);self.assertFalse(self.assignment.is_active)
        self.assertEqual(db.session.get(TheoryMarks,key).ct1,8)
        self.assertEqual(self.post('/teachers/assign',{'teacher_id':self.teacher.user_id,'subject_code':'TH601','semester_id':6,'academic_year':'2025-26'}).status_code,302)
        self.assertTrue(self.assignment.is_active);self.assertEqual(TeachingAssignment.query.count(),1)

    def test_reset_and_deactivate_endpoints_preserve_assignments(self):
        self.assertEqual(self.post(f'/teachers/{self.teacher.user_id}/password',{'password':'temporary-new-123'}).status_code,302)
        state=db.session.get(StaffAccessState,self.teacher.user_id)
        self.assertEqual(state.credential_version,1);self.assertTrue(state.must_change_password)
        self.assertTrue(self.teacher.check_password('temporary-new-123'))
        self.assertEqual(self.post(f'/teachers/{self.teacher.user_id}/status',{'active':'0'}).status_code,302)
        self.assertFalse(self.teacher.is_active);self.assertTrue(self.assignment.is_active)
        self.assertEqual(self.post(f'/teachers/{self.teacher.user_id}/status',{'active':'1'}).status_code,302)
        self.assertTrue(self.teacher.is_active);self.assertEqual(state.credential_version,3)

    def test_assigned_external_json_write_and_csrf(self):
        self.teacher_login()
        data={'subject_code':'TH601','semester_id':6,'academic_year':'2025-26','marks':[{'student_id':'S001','external_marks':45}]}
        self.assertEqual(self.client.post('/external/save',json=data).status_code,400)
        response=self.client.post('/external/save',json=data,headers={'X-CSRFToken':self.token()})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(ExternalMarks.query.count(),0)
        self.assertEqual(self.post(response.json['review_url']+'/confirm',{}).status_code,302)
        self.assertEqual(ExternalMarks.query.filter_by(prn='S001',subject_code='TH601').one().external_marks,45)

    def test_legacy_migration_is_idempotent_and_does_not_restore_revocation(self):
        from upgrade_teacher_access import migrate_legacy_assignments
        self.teacher.assigned_subjects='TH601, LB601, UNKNOWN'
        self.assignment.is_active=False;db.session.commit()
        count,unresolved=migrate_legacy_assignments()
        self.assertEqual(count,1);self.assertEqual(unresolved,[('teacher','UNKNOWN')])
        self.assertFalse(self.assignment.is_active)
        self.assertEqual(migrate_legacy_assignments()[0],0)

    def test_assigned_subject_deletion_preserves_assignment_history(self):
        subject=Subject(subject_code='UNUSED601',subject_name='Unused assigned subject',semester_id=6,subject_type='THEORY',is_active=True)
        db.session.add(subject);db.session.flush()
        assignment=TeachingAssignment(teacher_id=self.teacher.user_id,subject_code=subject.subject_code,semester_id=6,academic_year='2025-26')
        db.session.add(assignment);db.session.commit()
        self.assertEqual(self.client.post('/subjects/UNUSED601/delete').status_code,302)
        self.assertIsNotNone(db.session.get(Subject,'UNUSED601'));self.assertFalse(subject.is_active)
        self.assertEqual(self.client.get('/teachers').status_code,200)
        self.teacher_login()
        self.assertEqual(self.client.get('/ct1?subject_code=UNUSED601&semester_id=6&academic_year=2025-26&exam_type=CT1').status_code,403)


if __name__=='__main__':unittest.main()
