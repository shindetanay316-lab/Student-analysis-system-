CREATE TABLE IF NOT EXISTS internal_marks_submissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    subject_code VARCHAR(20) NOT NULL,
    semester_id INT NOT NULL,
    academic_year VARCHAR(10) NOT NULL,
    exam_type VARCHAR(20) NOT NULL,
    division VARCHAR(10) NOT NULL DEFAULT 'ALL',
    batch VARCHAR(10) NOT NULL DEFAULT 'ALL',
    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_internal_marks_submission_subject
        FOREIGN KEY (subject_code) REFERENCES subjects(subject_code)
        ON DELETE CASCADE,
    CONSTRAINT uq_internal_marks_submission_scope
        UNIQUE (subject_code, semester_id, academic_year, exam_type, division, batch)
);
