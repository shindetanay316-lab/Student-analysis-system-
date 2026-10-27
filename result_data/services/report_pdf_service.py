"""Portrait report reproducing the supplied college result-analysis template.

The original letterheads are reused as vector artwork. Section order, labels,
column geometry, black borders, signatures and continuation pages follow the
reference; the grade matrix remains an Excel worksheet.
"""
from datetime import date
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
import re

import pymupdf
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle
from .faculty_report_service import build_faculty_report,template_defaults

ASSET=Path(__file__).resolve().parents[2]/'static/result_data/templates/college_analysis_letterheads.pdf'
W,H=594.9600219726562,842.0399780273438
ROMANS=('','I','II','III','IV','V','VI','VII','VIII')


def decimal_text(value):return f'{value:.2f}' if value is not None else '—'


class Writer:
    def __init__(self,model):self.model=model;self.pages=[]

    def page(self,template):
        self.template=template;self.stream=BytesIO();self.canvas=Canvas(self.stream,pagesize=(W,H))

    def end(self):
        self.canvas.setFont('Times-Roman',11.04)
        self.canvas.drawRightString(551.16,H-827.04,f'Page | {len(self.pages)+1}')
        self.canvas.showPage();self.canvas.save();self.pages.append((self.template,self.stream.getvalue()))

    def text(self,text,y,size=15.96,bold=True,x=299.76):
        self.canvas.setFont('Times-Bold' if bold else 'Times-Roman',size)
        self.canvas.drawCentredString(x,H-y,str(text))

    def heading(self,section):
        report=self.model['report']
        raw=str(report.semester or '')
        if raw.isdigit():sem=int(raw)
        else:sem=next((i for i,r in enumerate(ROMANS) if r==raw.upper()),0)
        year={1:'FIRST',2:'FIRST',3:'SECOND',4:'SECOND',5:'THIRD',6:'THIRD',7:'FINAL',8:'FINAL'}.get(sem,'')
        self.year=year.title()+' Year' if year else 'Semester '+raw
        sem_label=ROMANS[sem] if 0<sem<len(ROMANS) else raw
        kind=(report.examination_type or '').upper().replace('.','')
        title=f'RESULT ANALYSIS OF {year} YEAR ECE SEM-{sem_label} {kind}'.replace('  ',' ').strip()
        baseline=216.98 if section=='TOPPER LIST' else 186.14 if section=='ALL STUDENTS RESULTS' else 206.06
        # Keep the template's two-line examination heading.
        size=15.96
        from reportlab.pdfbase.pdfmetrics import stringWidth
        if stringWidth(title,'Times-Bold',size)>490:size=490/stringWidth(title,'Times-Bold',size)*size
        self.text(title,baseline,size)
        self.text('EXAM '+(report.examination_session or '').upper(),baseline+18.48)
        department='Department of Electronics and Computer Engineering'
        if section in {'OVERALL RESULT','FAILED STUDENTS'}:
            self.text(section,245.81)
            self.text(department,281.21,14.04)
        elif section=='SUBJECT WISE RESULT':
            self.text(department,241.13,14.04);self.text(section,261.89)
        elif section=='TOPPER LIST':
            self.text(department,252.05,14.04);self.text(section,272.81)
        else:
            self.text(section,225.86);self.text(department,242.45,14.04)

    def signatures(self,baseline):
        names=self.model['options']['signatures']
        self.canvas.setFont('Times-Bold',12)
        self.canvas.drawString(63.504,H-baseline,'RESULT ANALYSIS')
        self.canvas.drawString(63.504,H-baseline-13.8,'COORDINATOR')
        for x,role in [(242.75,'HOD'),(364.10,'DEAN ACADEMICS'),(486.05,'PRINCIPAL')]:
            self.canvas.drawCentredString(x,H-baseline,role)
        for key,x in [('coordinator',63.504),('hod',242.82),('dean',364.05),('principal',486.05)]:
            value=names.get(key,'')
            from reportlab.pdfbase.pdfmetrics import stringWidth
            available=126 if key=='coordinator' else 108
            if stringWidth(value,'Times-Bold',12)<=available:
                if key=='coordinator':self.canvas.drawString(x,H-baseline-27.6,value)
                else:self.canvas.drawCentredString(x,H-baseline-27.6,value)
            else:
                style=ParagraphStyle('signature',fontName='Times-Bold',fontSize=12,leading=13.8,
                    alignment=TA_LEFT if key=='coordinator' else TA_CENTER)
                p=Paragraph(escape(value),style);_,height=p.wrap(available,100)
                left=x if key=='coordinator' else x-available/2
                p.drawOn(self.canvas,left,H-baseline-27.6-height+12)


    def table(self,headers,rows,widths,top,x,header_height=23.94,font=11.04,min_height=23.94,minimums=None,left_columns=(2,)):
        def cell(value,index,header=False):
            value='' if value is None else str(value)
            cell_font=font
            # Longer university PRNs must stay intact inside the fixed template.
            if not header and headers[index]=='SEAT NO.':
                from reportlab.pdfbase.pdfmetrics import stringWidth
                measured=stringWidth(value,'Times-Roman',font)
                if measured>widths[index]-6:cell_font=font*(widths[index]-6)/measured
            style=ParagraphStyle('t',fontName='Times-Bold' if header else 'Times-Roman',
                fontSize=cell_font,leading=13.68 if font>=11 else 11.04,
                alignment=TA_LEFT if not header and index in left_columns else TA_CENTER)
            return Paragraph(escape(value).replace('\n','<br/>'),style)
        data=[[cell(h,i,True) for i,h in enumerate(headers)]]+[[cell(v,i) for i,v in enumerate(row)] for row in rows]
        heights=[header_height]
        for ri,row in enumerate(data[1:]):
            need=max(p.wrap(widths[i]-6,10000)[1] for i,p in enumerate(row))+4.56
            heights.append(max(min_height,need,minimums[ri] if minimums else 0))
        table=Table(data,colWidths=widths,rowHeights=heights,repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.HexColor('#555555')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),4.2),
            ('BOTTOMPADDING',(0,0),(-1,-1),.36),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),
            ('LEFTPADDING',(0,0),(-1,0),.1),('RIGHTPADDING',(0,0),(-1,0),.1)]))
        width,height=table.wrap(W,H)
        return table,height

    def draw(self,table,top,x):
        _width,height=table.wrap(W,H);table.drawOn(self.canvas,x,H-top-height);return top+height

    def render(self):
        background=pymupdf.open(ASSET);out=pymupdf.open()
        for template,overlay in self.pages:
            out.insert_pdf(background,from_page=template,to_page=template)
            with pymupdf.open(stream=overlay,filetype='pdf') as body:
                out[-1].show_pdf_page(out[-1].rect,body,0)
        out.set_metadata({'title':'University Result Analysis','subject':self.model['status'],
                          'author':'CSMSS Chh. Shahu College of Engineering'})
        return out.tobytes(garbage=4,deflate=True)


def build_faculty_pdf(job):
    model=build_faculty_report(job);writer=Writer(model);counts=model['counts']
    writer.page(0);writer.heading('OVERALL RESULT')
    try:stamp=date.fromisoformat(model['options']['report_date']).strftime('%d/%m/%Y')
    except ValueError:stamp=model['options']['report_date']
    writer.canvas.setFont('Times-Roman',11.04);writer.canvas.drawRightString(548.28,H-188.78,stamp)
    percentage=model['analysis']['summary']['pass_rate']
    table,_=writer.table(['CLASS','TOTAL','ALL CLEAR','WITHHELD','BACKLOG','PERCENTAGE'],
        [[writer.year+'\n(ECE)',len(model['students']),counts['PASS'],counts['WITHHELD'],counts['FAIL'],
          decimal_text(percentage)+'%' if percentage is not None else '—']],
        [75.84,63.02,92.06,72,75.14,111.86],297.17,53.54,font=12,min_height=34.2,left_columns=(0,))
    writer.draw(table,297.17,53.54);writer.signatures(470.71);writer.end()

    # Subject table keeps the template's code-before-name order and white header.
    headers=['SR.\nNO.','SUBJE\nCT\nCODE','SUBJECT\nNAME','Name of faculty','TOTAL','PASSED','FAILED','Passing\n%']
    widths=[30,70.56,107.78,94.58,45,45,49.44,48.26]
    rows=[[r['serial'],r['code'],r['name'],r['faculty'],r['appeared'],r['passed'],r['failed'],
           (f"{r['pass_rate']:.1f}%" if r['pass_rate'] is not None and r['pass_rate']==100 else f"{r['pass_rate']:.2f}%" if r['pass_rate'] is not None else '—')]
          for r in model['subject_rows']]
    minimums=[template_defaults()['subject_row_heights'].get(r['code'],31.92) for r in model['subject_rows']]
    pending=list(zip(rows,minimums))
    while pending or not rows:
        writer.page(1);writer.heading('SUBJECT WISE RESULT')
        count=len(pending)
        while True:
            block=pending[:count]
            table,height=writer.table(headers,[r for r,_ in block],widths,278.33,53.54,47.88,
                                      min_height=31.92,minimums=[h for _,h in block])
            if height<=445 or count<=1:break
            count-=1
        writer.draw(table,278.33,53.54);writer.signatures(764.04);writer.end()
        pending=pending[count:]
        if not pending:break

    writer.page(2);writer.heading('TOPPER LIST')
    by_prn={s.seat_number:s for s in job.report.students}
    rows=[[i,s['seat_number'],s['name'],by_prn[s['seat_number']].gender_marker or '',decimal_text(s['sgpa'])]
          for i,s in enumerate(model['top_students'],1)]
    table,_=writer.table(['RANK','SEAT NO.','STUDENT NAME','GENDER','SGPA'],rows,
                         [42,91.58,175.5,55.56,38.3],289.37,96.14,font=12)
    writer.draw(table,289.37,96.14);writer.signatures(725.04);writer.end()

    pending=list(model['failed_students'])
    while pending or not model['failed_students']:
        writer.page(3);writer.heading('FAILED STUDENTS')
        writer.text('Total Failed / ATKT: '+str(len(model['failed_students'])),311.21)
        count=min(12,len(pending))
        while True:
            block=pending[:count]
            rows=[[r['serial'],r['prn'],r['name'],r['gender'],decimal_text(r['sgpa']),r['result']] for r in block]
            for i,row in enumerate(rows,1):row[0]=len(model['failed_students'])-len(pending)+i
            table,height=writer.table(['SR. NO.','SEAT NO.','STUDENT NAME','GENDER','SGPA','RESULT'],rows,
                [54.84,96.74,171.02,63.74,44.28,59.3],327.53,53.54,font=12)
            if height<345 or count<=1:break
            count-=1
        bottom=writer.draw(table,327.53,53.54)
        writer.signatures(max(489.55,bottom+114.14));writer.end()
        pending=pending[count:]
        if not pending:break

    pending=list(model['students']);first=True
    while pending or first:
        # Continuation pages reproduce the reference's compact repeated table.
        last_fits=len(pending)<=(16 if first else 25)
        template=4 if first else 6 if last_fits else 5
        writer.page(template)
        top=261.65 if first else 42.62 if last_fits else 21.14
        if first:
            writer.heading('ALL STUDENTS RESULTS');writer.text('Total Students: '+str(len(model['students'])),258.53,14.04)
        limit=21 if first else 32
        count=min(limit,len(pending))
        if not last_fits and len(pending)<=limit and count>1:
            count-=1  # retain a final record for the signature continuation page
        while True:
            block=pending[:count]
            rows=[[r['serial'],r['prn'],r['name'],r['gender'],decimal_text(r['sgpa']),r['result']] for r in block]
            table,height=writer.table(['SR. NO.','SEAT NO.','STUDENT NAME','GENDER','SGPA','RESULT'],rows,
                [42,72.74,174.02,48.02,33,45.02],top,90.5,font=9.12)
            available=(665 if last_fits else 792)-top
            if height<=available or count<=1:break
            count-=1
        bottom=writer.draw(table,top,90.5)
        pending=pending[count:]
        if not pending and bottom<670:writer.signatures(694.66)
        writer.end();first=False
        if not pending:break
    return writer.render()
