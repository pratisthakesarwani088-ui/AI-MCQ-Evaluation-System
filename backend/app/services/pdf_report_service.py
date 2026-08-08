"""
pdf_report_service.py
------------------------
Generates professional PDF reports (Student Report, Exam Report)
using reportlab. Both PDFs share a consistent header/footer style
so they look like they belong to the same system.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

PROJECT_NAME = "AI Assistant for MCQ Evaluation System"
PROJECT_TAGLINE = "Evaluate Smarter with AI"

PRIMARY_COLOR = colors.HexColor("#2f5fdc")
SUCCESS_COLOR = colors.HexColor("#1f9d55")
DANGER_COLOR = colors.HexColor("#d33d3d")
MUTED_COLOR = colors.HexColor("#6b7280")
LIGHT_BG = colors.HexColor("#f7f9fd")

_styles = getSampleStyleSheet()
_styles.add(ParagraphStyle(name="ReportTitle", fontSize=18, leading=22, textColor=PRIMARY_COLOR, spaceAfter=2))
_styles.add(ParagraphStyle(name="ReportTagline", fontSize=10, textColor=MUTED_COLOR, spaceAfter=14))
_styles.add(ParagraphStyle(name="SectionHeading", fontSize=13, leading=16, textColor=colors.HexColor("#202531"), spaceBefore=14, spaceAfter=6))
_styles.add(ParagraphStyle(name="BodyMuted", fontSize=9.5, textColor=MUTED_COLOR))
_styles.add(ParagraphStyle(name="BodyNormal", parent=_styles["Normal"], fontSize=10.5, leading=15))


def _build_header(subtitle: str):
    """Returns the shared title block flowables used by both report types."""
    elements = [
        Paragraph(PROJECT_NAME, _styles["ReportTitle"]),
        Paragraph(PROJECT_TAGLINE, _styles["ReportTagline"]),
        Paragraph(subtitle, _styles["SectionHeading"]),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e1e5ee"), spaceAfter=10),
    ]
    return elements


def _key_value_table(rows: list, col_widths=(5.5 * cm, 9.5 * cm)):
    """
    Builds a simple two-column "label: value" table, used for exam
    details / student details blocks.
    """
    table = Table(rows, colWidths=list(col_widths))
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#111827")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _stats_grid_table(cells: list):
    """
    Builds a small statistics grid (label above value), styled like
    the app's dashboard stat cards, laid out as a Table for the PDF.
    """
    header_row = [c["label"] for c in cells]
    value_row = [c["value"] for c in cells]
    table = Table([header_row, value_row], colWidths=[(17 * cm) / len(cells)] * len(cells))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("FONTSIZE", (0, 1), (-1, 1), 14),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED_COLOR),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e1e5ee")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e1e5ee")),
    ]))
    return table


def generate_student_report_pdf(data: dict, output_path: str):
    """
    Generates the Student Report PDF.

    Expected `data` keys:
        exam_name, subject, student_name, roll_number,
        correct_count, wrong_count, blank_count, invalid_count,
        final_marks, max_marks, percentage, evaluated_at,
        ai_analysis (optional, str or None)
    """
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    elements = _build_header("Student Report")

    elements.append(_key_value_table([
        ["Student Name", data.get("student_name") or "Not provided"],
        ["Roll Number", data.get("roll_number") or "Not provided"],
        ["Exam Name", data.get("exam_name")],
        ["Subject", data.get("subject") or "Not specified"],
        ["Evaluation Date", data.get("evaluated_at") or "—"],
    ]))

    elements.append(Paragraph("Result Summary", _styles["SectionHeading"]))
    elements.append(_stats_grid_table([
        {"label": "Correct", "value": str(data.get("correct_count", 0))},
        {"label": "Wrong", "value": str(data.get("wrong_count", 0))},
        {"label": "Blank", "value": str(data.get("blank_count", 0))},
        {"label": "Invalid", "value": str(data.get("invalid_count", 0))},
    ]))
    elements.append(Spacer(1, 10))
    elements.append(_key_value_table([
        ["Final Marks", f"{data.get('final_marks', 0)} / {data.get('max_marks', 0)}"],
        ["Percentage", f"{data.get('percentage', 0)}%"],
    ]))

    if data.get("ai_analysis"):
        elements.append(Paragraph("AI Performance Analysis", _styles["SectionHeading"]))
        for line in str(data["ai_analysis"]).split("\n"):
            if line.strip():
                elements.append(Paragraph(line.strip(), _styles["BodyNormal"]))
            else:
                elements.append(Spacer(1, 4))

    doc.build(elements)


def generate_exam_report_pdf(data: dict, output_path: str):
    """
    Generates the Exam Report PDF.

    Expected `data` keys:
        exam_name, subject, exam_type, total_students, highest_marks,
        lowest_marks, average_marks, max_marks, pass_count,
        fail_count, pass_percentage, average_percentage
    """
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    elements = _build_header("Exam Report")

    exam_type_label = "AI-Based Evaluation" if data.get("exam_type") == "AI" else "OMR Evaluation"
    elements.append(_key_value_table([
        ["Exam Name", data.get("exam_name")],
        ["Subject", data.get("subject") or "Not specified"],
        ["Exam Type", exam_type_label],
        ["Total Students Evaluated", str(data.get("total_students", 0))],
    ]))

    elements.append(Paragraph("Statistics", _styles["SectionHeading"]))
    elements.append(_stats_grid_table([
        {"label": "Highest Marks", "value": f"{data.get('highest_marks', 0)}"},
        {"label": "Lowest Marks", "value": f"{data.get('lowest_marks', 0)}"},
        {"label": "Average Marks", "value": f"{data.get('average_marks', 0)}"},
        {"label": "Max Marks", "value": f"{data.get('max_marks', 0)}"},
    ]))
    elements.append(Spacer(1, 10))
    elements.append(_stats_grid_table([
        {"label": "Pass Count", "value": str(data.get("pass_count", 0))},
        {"label": "Fail Count", "value": str(data.get("fail_count", 0))},
        {"label": "Pass %", "value": f"{data.get('pass_percentage', 0)}%"},
        {"label": "Average %", "value": f"{data.get('average_percentage', 0)}%"},
    ]))

    elements.append(Paragraph(
        "Note: a student is counted as \"Pass\" if their percentage is 40% or higher.",
        _styles["BodyMuted"],
    ))

    doc.build(elements)
