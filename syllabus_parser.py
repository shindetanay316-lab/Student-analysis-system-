"""Extract DBATU teaching/evaluation tables, retaining printed evidence per row.

No language model, guessed codes or inferred credit values are used. This uses
the serial-number and course-code groups to join wrapped text and options.
"""
import re
import fitz

ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8}


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def number(value, *, audit=False):
    text = clean(value)
    if text.upper() == 'AU' and audit:
        return '0'
    match = re.fullmatch(r'(?:[a-z]\s+)?(\d+(?:\.\d+)?)[*†‡]?', text)
    return match[1] if match else ''


def extract_syllabus(content):
    if len(content) > 20 * 1024 * 1024:
        raise ValueError('Syllabus PDF must be at most 20 MB.')
    try:
        document = fitz.open(stream=content, filetype='pdf')
    except Exception as exc:
        raise ValueError('Cannot read this PDF. Upload an unlocked, valid PDF.') from exc
    if document.needs_pass:
        document.close()
        raise ValueError('Upload an unlocked syllabus PDF.')
    if len(document) > 300:
        document.close()
        raise ValueError('Upload at most 300 syllabus pages at a time.')
    courses, warnings = [], []
    try:
        for page in document:
            text = page.get_text(sort=True)
            # Detailed lesson tables do not contain this combined scheme header.
            if not (re.search(r'Course', text, re.I) and re.search(r'Code', text, re.I) and re.search(r'Evaluation\s+Scheme', text, re.I)):
                continue
            semester_match = re.search(r'Semester\s*[-:]?\s*(VIII|VII|VI|IV|V|III|II|I|[1-8])\b', text, re.I)
            if not semester_match:
                warnings.append(f'Page {page.number + 1}: scheme table has no identifiable semester. Review the source.')
                continue
            raw_sem = semester_match[1].upper()
            semester = int(raw_sem) if raw_sem.isdigit() else ROMAN[raw_sem]
            group_match = re.search(r'GROUP\s+([AB])\b', text, re.I)
            group = group_match[1].upper() if group_match else 'COMMON'
            for table in page.find_tables().tables:
                data = table.extract()
                if not any('Course' in str(row[2]) and 'Code' in str(row[2]) for row in data if len(row) == 12):
                    continue
                blocks, block = [], []
                for row in data + [[None] * 12]:
                    if len(row) != 12 or not any(clean(v) for v in row) or any(clean(v).lower() == 'total' for v in (row[1], row[3])):
                        if block:
                            blocks.append(block)
                            block = []
                    else:
                        block.append(row)
                for block in blocks:
                    anchors = {clean(r[0]) for r in block if clean(r[0]).isdigit()}
                    if not anchors:
                        continue
                    # Fully ruled tables have one uninterrupted block; split on
                    # the next serial number, retaining merged option rows.
                    groups = []
                    if len(anchors) > 1:
                        grouped, current = {}, None
                        for row in block:
                            found = re.search(r'(\d{3})[A-Z]?\b', clean(row[2]))
                            course_no = str(int(found[1]) % 100) if found else None
                            if clean(row[0]).isdigit():
                                current = clean(row[0])
                            elif course_no in anchors:
                                current = course_no
                            if current:
                                grouped.setdefault(current, []).append(row)
                        groups = list(grouped.values())
                    else:
                        groups = [block]
                    for group_rows in groups:
                        values = []
                        for col in range(12):
                            parts = list(dict.fromkeys(clean(r[col]) for r in group_rows if clean(r[col])))
                            values.append(' '.join(parts))
                        courses.extend(_course_rows(values, semester, group, page.number + 1, len(courses), warnings))
        # Some printed titles run over the table border. Complete a truncated
        # title only when exactly one fuller title is printed elsewhere here.
        for row in courses:
            base = re.sub(r'\s+Lab$', '', row['name'], flags=re.I)
            lab = bool(re.search(r'\s+Lab$', row['name'], re.I))
            candidates = set()
            for other in courses:
                other_base = re.sub(r'\s+Lab$', '', other['name'], flags=re.I)
                other_lab = bool(re.search(r'\s+Lab$', other['name'], re.I))
                if re.search(r'[A-Za-z]{5,}$', base) and lab == other_lab and other_base.startswith(base) and 0 < len(other_base) - len(base) <= 4:
                    candidates.add(other['name'])
            if len(candidates) == 1:
                row['name'] = candidates.pop()
                row['issues'].append('Truncated title completed from another printed course title in this PDF; verify against the source.')
        if not courses:
            warnings.append('No supported teaching/evaluation table was found. Add verified course rows manually. Scanned PDFs need a searchable text layer.')
        return courses, warnings
    finally:
        document.close()


def _course_rows(values, semester, group, page_number, offset, warnings):
    courses = []
    code_list = re.findall(r'\b[A-Z0-9][A-Z0-9._/-]{4,19}\b', values[2].upper())
    title = values[3]
    option_names = re.findall(r'(?:^|\s)([A-Z])\.\s*(.*?)(?=\s+[A-Z]\.\s|$)', title)
    # Printed A/B/C options share scheme values; keep each as an option.
    options = option_names if len(option_names) > 1 else [('', title)]
    if len(code_list) > 1 and len(code_list) != len(options):
        warnings.append(f'Page {page_number}, course {values[0]}: check option/code alignment.')
    for index, (letter, name) in enumerate(options):
        code = code_list[index] if index < len(code_list) else ''
        is_audit = values[11].upper() == 'AU'
        practical = number(values[6])
        kind = 'AUDIT' if is_audit else 'PROJECT' if re.search(r'project', name, re.I) else 'LAB' if re.search(r'\blab\b|workshop|practical', name, re.I) or (practical and float(practical) > 0 and not letter) else 'THEORY'
        choice = f'S{semester}-{group}-{values[0]}' if letter or re.search(r'bucket|elective', name, re.I) else ''
        issues = []
        if not code:
            issues.append('Code is not printed; enter a verified code with evidence, or exclude this row.')
        if 'XXX' in code or re.search(r'bucket', name, re.I):
            issues.append('Bucket/placeholder: confirm actual options separately; this is a parent, not an enrollable course.')
        if any(number(values[c], audit=(c == 11)) == '' for c in (4, 5, 6, 11)):
            issues.append('Check the teaching hours/credits against the source.')
        courses.append(dict(
            row_id=offset + len(courses) + 1, semester_id=semester, group=group,
            code=code, name=name, category=values[1], subject_type=kind,
            credits=number(values[11], audit=True), l=number(values[4]),
            t=number(values[5]), p=practical, ca=values[7], mse=values[8],
            ese=values[9], total=values[10], is_audit=is_audit,
            choice_group=choice, is_bucket=bool(re.search(r'bucket', name, re.I) or 'XXX' in code),
            include=bool(code), evidence='', page=page_number,
            source_text=' | '.join(values), issues=issues,
        ))
    return courses
