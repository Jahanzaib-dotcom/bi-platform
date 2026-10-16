"""
Export utilities — CSV, Excel, and PDF generation.

Functions
---------
businesses_to_csv(businesses, output_path)   -> Path
    Write a list of Business ORM instances to a UTF-8 CSV file.
businesses_to_excel(businesses, output_path) -> Path
    Write a styled Excel workbook using openpyxl via pandas.
audit_to_pdf(audit, business, output_path)   -> Path
    Generate a single-audit PDF report using ReportLab.

All functions are async-friendly wrappers: the actual I/O is delegated to
``asyncio.get_event_loop().run_in_executor`` so they do not block the event
loop when called from async code.
"""
from __future__ import annotations

import asyncio
import io
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# businesses_to_csv
# ---------------------------------------------------------------------------

_BUSINESS_CSV_COLUMNS = [
    "id",
    "name",
    "slug",
    "industry",
    "category",
    "country",
    "state",
    "city",
    "zip_code",
    "address",
    "phone",
    "email",
    "website_url",
    "has_website",
    "website_status",
    "source",
    "overall_score",
    "opportunity_score",
    "priority_score",
    "revenue_potential",
    "audit_count",
    "discovered_at",
    "last_audited_at",
    "created_at",
    "updated_at",
]


def _business_to_row(biz: Any) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for col in _BUSINESS_CSV_COLUMNS:
        val = getattr(biz, col, None)
        if col == "website_status" and val is not None:
            val = val.value if hasattr(val, "value") else str(val)
        elif isinstance(val, datetime):
            val = val.isoformat()
        elif hasattr(val, "__str__"):
            val = str(val) if val is not None else ""
        row[col] = val if val is not None else ""
    return row


def businesses_to_csv(
    businesses: Sequence[Any],
    output_path: Optional[Path] = None,
) -> Path:
    """
    Write *businesses* to a CSV file and return the file :class:`Path`.

    Parameters
    ----------
    businesses:
        Iterable of :class:`~app.models.business.Business` ORM instances.
    output_path:
        Destination file path.  If ``None`` a temporary path is generated
        inside the configured export directory.

    Returns
    -------
    Path
        Absolute path to the written file.
    """
    import csv

    from app.core.config import settings

    if output_path is None:
        export_dir = settings.export_path
        output_path = export_dir / f"businesses_{_utcnow_str()}.csv"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [_business_to_row(b) for b in businesses]

    with output_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=_BUSINESS_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return output_path


async def businesses_to_csv_async(
    businesses: Sequence[Any],
    output_path: Optional[Path] = None,
) -> Path:
    """Async wrapper around :func:`businesses_to_csv`."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, businesses_to_csv, businesses, output_path
    )


# ---------------------------------------------------------------------------
# businesses_to_excel
# ---------------------------------------------------------------------------


def businesses_to_excel(
    businesses: Sequence[Any],
    output_path: Optional[Path] = None,
    sheet_name: str = "Businesses",
) -> Path:
    """
    Write *businesses* to a styled Excel workbook (.xlsx) and return the path.

    Requires ``pandas`` and ``openpyxl``.

    Parameters
    ----------
    businesses:
        Iterable of :class:`~app.models.business.Business` ORM instances.
    output_path:
        Destination file path.  Auto-generated if ``None``.
    sheet_name:
        Name for the main worksheet (default ``"Businesses"``).

    Returns
    -------
    Path
        Absolute path to the written file.
    """
    import pandas as pd
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from app.core.config import settings

    if output_path is None:
        export_dir = settings.export_path
        output_path = export_dir / f"businesses_{_utcnow_str()}.xlsx"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [_business_to_row(b) for b in businesses]
    df = pd.DataFrame(rows, columns=_BUSINESS_CSV_COLUMNS)

    # Human-readable column headers
    display_columns = {
        "id": "ID",
        "name": "Business Name",
        "slug": "Slug",
        "industry": "Industry",
        "category": "Category",
        "country": "Country",
        "state": "State",
        "city": "City",
        "zip_code": "ZIP Code",
        "address": "Address",
        "phone": "Phone",
        "email": "Email",
        "website_url": "Website URL",
        "has_website": "Has Website",
        "website_status": "Website Status",
        "source": "Source",
        "overall_score": "Overall Score",
        "opportunity_score": "Opportunity Score",
        "priority_score": "Priority Score",
        "revenue_potential": "Revenue Potential",
        "audit_count": "Audits",
        "discovered_at": "Discovered At",
        "last_audited_at": "Last Audited",
        "created_at": "Created At",
        "updated_at": "Updated At",
    }
    df.rename(columns=display_columns, inplace=True)

    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]

        # Style header row
        header_fill = PatternFill("solid", fgColor="2D6A9F")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Alternate row colouring
        even_fill = PatternFill("solid", fgColor="EBF3FB")
        for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
            if row_idx % 2 == 0:
                for cell in row:
                    cell.fill = even_fill

        # Auto-fit column widths (cap at 60)
        for col_idx, col_cells in enumerate(ws.columns, start=1):
            max_len = max(
                (len(str(cell.value or "")) for cell in col_cells),
                default=10,
            )
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 60)

        # Freeze top row
        ws.freeze_panes = "A2"

    return output_path


async def businesses_to_excel_async(
    businesses: Sequence[Any],
    output_path: Optional[Path] = None,
    sheet_name: str = "Businesses",
) -> Path:
    """Async wrapper around :func:`businesses_to_excel`."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, businesses_to_excel, businesses, output_path, sheet_name
    )


# ---------------------------------------------------------------------------
# audit_to_pdf
# ---------------------------------------------------------------------------


def audit_to_pdf(
    audit: Any,
    business: Any,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Generate a PDF audit report using ReportLab.

    Parameters
    ----------
    audit:
        :class:`~app.models.audit.AuditReport` ORM instance.
    business:
        :class:`~app.models.business.Business` ORM instance.
    output_path:
        Destination file path.  Auto-generated if ``None``.

    Returns
    -------
    Path
        Absolute path to the written PDF file.
    """
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
    from reportlab.lib.units import cm, mm  # type: ignore
    from reportlab.platypus import (  # type: ignore
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    from app.core.config import settings

    if output_path is None:
        export_dir = settings.export_path
        audit_id = str(getattr(audit, "id", "unknown"))
        output_path = export_dir / f"audit_{audit_id[:8]}_{_utcnow_str()}.pdf"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    # Custom styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        spaceAfter=8,
        textColor=colors.HexColor("#1A3C6E"),
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=14,
        spaceAfter=6,
        textColor=colors.HexColor("#2D6A9F"),
    )
    body_style = styles["BodyText"]
    body_style.fontSize = 10
    body_style.leading = 14

    brand_blue = colors.HexColor("#2D6A9F")
    light_blue = colors.HexColor("#EBF3FB")
    mid_grey = colors.HexColor("#CCCCCC")

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def _score_colour(score: Optional[float]) -> colors.Color:
        if score is None:
            return mid_grey
        if score >= 70:
            return colors.HexColor("#27AE60")
        if score >= 40:
            return colors.HexColor("#F39C12")
        return colors.HexColor("#E74C3C")

    def _fmt_score(score: Optional[float]) -> str:
        return f"{score:.1f}" if score is not None else "N/A"

    def _fmt_dt(dt: Optional[datetime]) -> str:
        if dt is None:
            return "N/A"
        return dt.strftime("%d %b %Y, %H:%M UTC")

    story: list[Any] = []

    # ---------------------------------------------------------------------------
    # Header
    # ---------------------------------------------------------------------------
    story.append(Paragraph("Website Audit Report", title_style))
    story.append(
        Paragraph(
            f"<b>{getattr(business, 'name', 'Unknown Business')}</b>",
            ParagraphStyle("BizName", parent=styles["Normal"], fontSize=16,
                           textColor=brand_blue, spaceAfter=4),
        )
    )
    story.append(
        Paragraph(
            f"Generated: {_fmt_dt(datetime.now(timezone.utc))}",
            ParagraphStyle("SubHead", parent=styles["Normal"], fontSize=9,
                           textColor=colors.grey, spaceAfter=10),
        )
    )
    story.append(HRFlowable(width="100%", thickness=2, color=brand_blue, spaceAfter=14))

    # ---------------------------------------------------------------------------
    # Business info
    # ---------------------------------------------------------------------------
    story.append(Paragraph("Business Details", h2_style))

    biz_data = [
        ["Field", "Value"],
        ["Name", getattr(business, "name", "") or ""],
        ["Industry", getattr(business, "industry", "") or ""],
        ["Location", ", ".join(filter(None, [
            getattr(business, "city", None),
            getattr(business, "state", None),
            getattr(business, "country", None),
        ]))],
        ["Phone", getattr(business, "phone", "") or ""],
        ["Email", getattr(business, "email", "") or ""],
        ["Website", getattr(business, "website_url", "") or ""],
        ["Discovered", _fmt_dt(getattr(business, "discovered_at", None))],
    ]
    biz_table = Table(biz_data, colWidths=[5 * cm, None])
    biz_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand_blue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("BACKGROUND", (0, 1), (-1, -1), light_blue),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light_blue]),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, mid_grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(biz_table)
    story.append(Spacer(1, 12))

    # ---------------------------------------------------------------------------
    # Score summary
    # ---------------------------------------------------------------------------
    story.append(Paragraph("Audit Scores", h2_style))

    score_fields = [
        ("Overall Score", "overall_score"),
        ("UI Score", "ui_score"),
        ("UX Score", "ux_score"),
        ("SEO Score", "seo_score"),
        ("Mobile Score", "mobile_score"),
        ("Accessibility", "accessibility_score"),
        ("Performance", "speed_score"),
        ("Security", "security_score"),
        ("Content", "content_score"),
        ("Conversion", "conversion_score"),
        ("Branding", "branding_score"),
    ]

    score_data = [["Category", "Score", "Status"]]
    for label, attr in score_fields:
        score = getattr(audit, attr, None)
        colour = _score_colour(score)
        status = "Good" if score and score >= 70 else ("Fair" if score and score >= 40 else "Poor")
        score_data.append([label, _fmt_score(score), status])

    score_table = Table(score_data, colWidths=[7 * cm, 3 * cm, 4 * cm])
    # Build row-level background colours based on score
    ts_cmds: list[Any] = [
        ("BACKGROUND", (0, 0), (-1, 0), brand_blue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, mid_grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
    ]
    for row_idx, (_, attr) in enumerate(score_fields, start=1):
        score = getattr(audit, attr, None)
        colour = _score_colour(score)
        ts_cmds.append(("TEXTCOLOR", (2, row_idx), (2, row_idx), colour))
        ts_cmds.append(("FONTNAME", (2, row_idx), (2, row_idx), "Helvetica-Bold"))
        if row_idx % 2 == 0:
            ts_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), light_blue))
    score_table.setStyle(TableStyle(ts_cmds))
    story.append(score_table)
    story.append(Spacer(1, 12))

    # ---------------------------------------------------------------------------
    # Recommendations
    # ---------------------------------------------------------------------------
    recs = getattr(audit, "recommendations", None) or []
    if recs:
        story.append(Paragraph("Recommendations", h2_style))
        for rec in recs[:15]:  # cap at 15 to avoid very long reports
            priority = str(rec.get("priority", "medium")).upper()
            title = rec.get("title", "")
            description = rec.get("description", "")
            priority_colour = (
                "#E74C3C" if priority == "HIGH"
                else "#F39C12" if priority == "MEDIUM"
                else "#27AE60"
            )
            story.append(
                Paragraph(
                    f'<font color="{priority_colour}"><b>[{priority}]</b></font> {title}',
                    ParagraphStyle(
                        "RecTitle",
                        parent=styles["Normal"],
                        fontSize=10,
                        spaceBefore=6,
                        spaceAfter=2,
                        leftIndent=10,
                    ),
                )
            )
            if description:
                story.append(
                    Paragraph(
                        description,
                        ParagraphStyle(
                            "RecBody",
                            parent=body_style,
                            leftIndent=20,
                            spaceAfter=4,
                        ),
                    )
                )
        story.append(Spacer(1, 8))

    # ---------------------------------------------------------------------------
    # AI analysis
    # ---------------------------------------------------------------------------
    ai = getattr(audit, "ai_analysis", None) or {}
    if ai:
        story.append(Paragraph("AI Analysis", h2_style))
        if ai.get("summary"):
            story.append(Paragraph(ai["summary"], body_style))
            story.append(Spacer(1, 6))

        for section, label in [("strengths", "Strengths"), ("weaknesses", "Weaknesses"),
                                ("opportunities", "Opportunities")]:
            items = ai.get(section) or []
            if items:
                story.append(
                    Paragraph(
                        label,
                        ParagraphStyle("AISection", parent=styles["Normal"],
                                       fontSize=11, fontName="Helvetica-Bold",
                                       spaceBefore=6, spaceAfter=3),
                    )
                )
                for item in items:
                    story.append(
                        Paragraph(
                            f"• {item}",
                            ParagraphStyle("AIBullet", parent=body_style,
                                           leftIndent=15, spaceAfter=2),
                        )
                    )
        story.append(Spacer(1, 8))

    # ---------------------------------------------------------------------------
    # Footer line
    # ---------------------------------------------------------------------------
    story.append(HRFlowable(width="100%", thickness=1, color=mid_grey, spaceBefore=16))
    story.append(
        Paragraph(
            f"Report generated by BI-Platform | {_fmt_dt(datetime.now(timezone.utc))}",
            ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8,
                           textColor=colors.grey, alignment=1),
        )
    )

    doc.build(story)
    return output_path


async def audit_to_pdf_async(
    audit: Any,
    business: Any,
    output_path: Optional[Path] = None,
) -> Path:
    """Async wrapper around :func:`audit_to_pdf`."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, audit_to_pdf, audit, business, output_path)
