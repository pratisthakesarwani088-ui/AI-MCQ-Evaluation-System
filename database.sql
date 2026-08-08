-- ============================================================
-- AI Assistant for MCQ Evaluation System - Database Schema
-- Database: MySQL
-- ============================================================
-- Run this file once to create the database and all tables.
-- Command (from MySQL shell):
--     SOURCE database.sql;
-- OR from terminal:
--     mysql -u root -p < database.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS mcq_evaluation_system
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE mcq_evaluation_system;

-- ------------------------------------------------------------
-- Table: exams
-- Stores the basic details of each exam created by the teacher.
-- exam_type decides which pipeline is used: AI-Based Evaluation
-- (Gemini generates the answer key) or OMR Evaluation (OpenCV
-- bubble-sheet detection).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exams (
    exam_id INT AUTO_INCREMENT PRIMARY KEY,
    exam_name VARCHAR(255) NOT NULL,
    subject VARCHAR(255) DEFAULT NULL,
    exam_type ENUM('AI', 'OMR') NOT NULL DEFAULT 'OMR',
    total_questions INT NOT NULL,
    marks_per_correct FLOAT NOT NULL,
    negative_marks FLOAT NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Table: question_papers
-- Stores every document a teacher uploads for an exam: the
-- question paper (PDF/DOCX/TXT/image) and, for OMR Evaluation,
-- the separate answer-key image. paper_type tells them apart.
-- extracted_text holds whatever text was pulled from the file,
-- which feeds the AI Assistant's "Generate Answer Key" feature.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS question_papers (
    paper_id INT AUTO_INCREMENT PRIMARY KEY,
    exam_id INT NOT NULL,
    paper_type ENUM('QUESTION_PAPER', 'ANSWER_KEY') NOT NULL,
    file_path VARCHAR(500) DEFAULT NULL,
    file_type ENUM('PDF', 'DOCX', 'TXT', 'IMAGE') DEFAULT NULL,
    extracted_text LONGTEXT DEFAULT NULL,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Table: questions
-- Individual MCQ questions for an exam, either extracted from an
-- uploaded question paper or entered manually by the teacher.
-- The correct option is NOT stored here -- it lives in
-- verified_answer_keys once generated/verified, keeping one
-- single source of truth for scoring.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS questions (
    question_id INT AUTO_INCREMENT PRIMARY KEY,
    exam_id INT NOT NULL,
    paper_id INT DEFAULT NULL,
    question_number INT NOT NULL,
    question_text TEXT NOT NULL,
    option_a VARCHAR(500) DEFAULT NULL,
    option_b VARCHAR(500) DEFAULT NULL,
    option_c VARCHAR(500) DEFAULT NULL,
    option_d VARCHAR(500) DEFAULT NULL,
    option_e VARCHAR(500) DEFAULT NULL,
    source ENUM('MANUAL', 'EXTRACTED') NOT NULL DEFAULT 'MANUAL',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE,
    FOREIGN KEY (paper_id) REFERENCES question_papers(paper_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Table: ai_responses
-- Log of every call made to the Gemini AI Assistant (generate
-- answer key, explain an answer, generate MCQs, analyze results,
-- find weak topics, suggestions) -- both the prompt and response.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_responses (
    response_id INT AUTO_INCREMENT PRIMARY KEY,
    exam_id INT DEFAULT NULL,
    request_type ENUM(
        'GENERATE_ANSWER_KEY',
        'EXPLAIN_ANSWER',
        'GENERATE_MCQS',
        'ANALYZE_RESULTS',
        'FIND_WEAK_TOPICS',
        'SUGGESTIONS'
    ) NOT NULL,
    prompt_text LONGTEXT DEFAULT NULL,
    response_text LONGTEXT DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Table: verified_answer_keys
-- Stores the FINAL, teacher-verified correct answer for every
-- question of an exam (whether it came from OCR extraction or
-- Gemini generation). This is the only answer key used during
-- evaluation.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verified_answer_keys (
    key_id INT AUTO_INCREMENT PRIMARY KEY,
    exam_id INT NOT NULL,
    question_number INT NOT NULL,
    correct_option VARCHAR(5) NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE,
    UNIQUE KEY unique_exam_question (exam_id, question_number)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Table: student_answer_sheets  (the "Student Sheets" table)
-- Stores metadata about each uploaded student answer sheet.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS student_answer_sheets (
    sheet_id INT AUTO_INCREMENT PRIMARY KEY,
    exam_id INT NOT NULL,
    student_name VARCHAR(255) DEFAULT NULL,
    roll_number VARCHAR(100) DEFAULT NULL,
    image_path VARCHAR(500) NOT NULL,
    sheet_type ENUM('OMR', 'NORMAL', 'UNKNOWN') DEFAULT 'UNKNOWN',
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Table: student_responses
-- Stores the detected answer for every question of a student
-- sheet (before final scoring).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS student_responses (
    response_id INT AUTO_INCREMENT PRIMARY KEY,
    sheet_id INT NOT NULL,
    question_number INT NOT NULL,
    selected_option VARCHAR(20) DEFAULT NULL, -- can hold "B" or "B,C" for invalid multi-mark
    detection_status ENUM('DETECTED', 'BLANK', 'INVALID') NOT NULL DEFAULT 'BLANK',
    confidence FLOAT DEFAULT NULL,
    FOREIGN KEY (sheet_id) REFERENCES student_answer_sheets(sheet_id) ON DELETE CASCADE,
    UNIQUE KEY unique_sheet_question (sheet_id, question_number)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Table: evaluation_results
-- Stores the final computed result summary for a student sheet,
-- including percentage and an optional AI-generated performance
-- analysis.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evaluation_results (
    result_id INT AUTO_INCREMENT PRIMARY KEY,
    sheet_id INT NOT NULL,
    exam_id INT NOT NULL,
    correct_count INT NOT NULL DEFAULT 0,
    wrong_count INT NOT NULL DEFAULT 0,
    blank_count INT NOT NULL DEFAULT 0,
    invalid_count INT NOT NULL DEFAULT 0,
    final_marks FLOAT NOT NULL DEFAULT 0,
    max_marks FLOAT NOT NULL DEFAULT 0,
    percentage FLOAT NOT NULL DEFAULT 0,
    ai_analysis TEXT DEFAULT NULL,
    evaluated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sheet_id) REFERENCES student_answer_sheets(sheet_id) ON DELETE CASCADE,
    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Table: reports
-- Metadata about generated PDF reports (student report, exam
-- report, highest/lowest/average marks summary) so previously
-- generated reports can be listed and re-downloaded.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
    report_id INT AUTO_INCREMENT PRIMARY KEY,
    exam_id INT DEFAULT NULL,
    sheet_id INT DEFAULT NULL,
    report_type ENUM('STUDENT', 'EXAM', 'HIGHEST', 'LOWEST', 'AVERAGE') NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE,
    FOREIGN KEY (sheet_id) REFERENCES student_answer_sheets(sheet_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Table: activity_logs
-- General-purpose audit trail of notable actions (exam created,
-- answer key verified, sheet evaluated, report generated, AI
-- assistant used, etc.).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    action VARCHAR(255) NOT NULL,
    description TEXT DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Helpful indexes for faster lookups
-- ------------------------------------------------------------
CREATE INDEX idx_question_papers_exam ON question_papers(exam_id);
CREATE INDEX idx_questions_exam ON questions(exam_id);
CREATE INDEX idx_ai_responses_exam ON ai_responses(exam_id);
CREATE INDEX idx_answer_key_exam ON verified_answer_keys(exam_id);
CREATE INDEX idx_sheet_exam ON student_answer_sheets(exam_id);
CREATE INDEX idx_response_sheet ON student_responses(sheet_id);
CREATE INDEX idx_reports_exam ON reports(exam_id);
