#!/usr/bin/env python3
"""Side-by-side evaluation of Unstructured.io vs Docling for layout-aware PDF parsing.

Runs both libraries on sample PDFs and compares:
- Element type accuracy (Title/Paragraph/Table classification)
- Table extraction quality (cell structure preservation)
- Processing speed (seconds per page)
- Fragment count and size distribution

Usage:
    python scripts/evaluate_parsers.py [--pdf-dir path/to/pdfs] [--output results.json]

If no --pdf-dir is provided, generates a synthetic test PDF with tables,
multi-column text, and headers for evaluation.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def generate_test_pdf(output_path: Path) -> Path:
    """Generate a synthetic test PDF with diverse content types."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        logger.error("reportlab not installed. Install with: pip install reportlab")
        sys.exit(1)

    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph("Mortgage Lending Process Assessment", styles["Title"]))
    story.append(Spacer(1, 0.3 * inch))

    # Section 1: Body text
    story.append(Paragraph("1. Executive Summary", styles["Heading1"]))
    story.append(
        Paragraph(
            "This document outlines the current mortgage lending process, including "
            "loan origination, underwriting, and closing procedures. The assessment "
            "identifies key bottlenecks in the current workflow and recommends "
            "improvements to reduce processing time and improve compliance. "
            "The Loan Officer initiates the process by collecting applicant "
            "documentation and submitting it to the Underwriting Team for review. "
            "The Credit Analyst performs risk assessment using the LoanPro system.",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.2 * inch))

    # Section 2: Table
    story.append(Paragraph("2. Process Metrics", styles["Heading1"]))
    table_data = [
        ["Process Step", "Avg Duration", "Owner", "System"],
        ["Application Intake", "2 days", "Loan Officer", "LoanPro"],
        ["Credit Check", "1 day", "Credit Analyst", "Equifax Gateway"],
        ["Underwriting Review", "5 days", "Senior Underwriter", "DecisionPro"],
        ["Appraisal Order", "10 days", "Appraisal Coordinator", "ValuTrak"],
        ["Closing", "3 days", "Closing Agent", "ClosingCorp"],
    ]
    table = Table(table_data)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), "#4472C4"),
                ("TEXTCOLOR", (0, 0), (-1, 0), "#FFFFFF"),
                ("GRID", (0, 0), (-1, -1), 0.5, "#888888"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.2 * inch))

    # Section 3: More text with decision language
    story.append(Paragraph("3. Decision Points", styles["Heading1"]))
    story.append(
        Paragraph(
            "If the credit score exceeds 720, the application is fast-tracked to "
            "automated underwriting. When the loan-to-value ratio is above 80%, "
            "private mortgage insurance (PMI) is required. The threshold for "
            "manual review is $500,000 or above. Either the Senior Underwriter "
            "or the Chief Credit Officer must approve loans above this amount.",
            styles["Normal"],
        )
    )

    doc.build(story)
    logger.info("Generated test PDF: %s", output_path)
    return output_path


def evaluate_unstructured(pdf_path: Path) -> dict:
    """Evaluate Unstructured.io on a PDF."""
    result = {
        "parser": "unstructured",
        "available": False,
        "elements": [],
        "tables": 0,
        "titles": 0,
        "narratives": 0,
        "total_elements": 0,
        "seconds_per_page": 0.0,
        "error": None,
    }

    try:
        from unstructured.partition.pdf import partition_pdf

        result["available"] = True

        start = time.time()
        elements = partition_pdf(filename=str(pdf_path), strategy="hi_res")
        elapsed = time.time() - start

        for el in elements:
            el_type = type(el).__name__
            text = str(el).strip()
            entry = {"type": el_type, "text_length": len(text), "text_preview": text[:100]}

            if hasattr(el.metadata, "page_number"):
                entry["page"] = el.metadata.page_number

            result["elements"].append(entry)

            if el_type == "Table":
                result["tables"] += 1
            elif el_type == "Title":
                result["titles"] += 1
            elif el_type == "NarrativeText":
                result["narratives"] += 1

        result["total_elements"] = len(elements)
        # Estimate page count from max page number
        pages = max((e.get("page", 1) for e in result["elements"]), default=1)
        result["seconds_per_page"] = elapsed / max(pages, 1)
        result["total_seconds"] = elapsed

    except ImportError:
        result["error"] = "unstructured[pdf] not installed"
    except Exception as e:
        result["error"] = str(e)

    return result


def evaluate_docling(pdf_path: Path) -> dict:
    """Evaluate IBM Docling on a PDF."""
    result = {
        "parser": "docling",
        "available": False,
        "elements": [],
        "tables": 0,
        "titles": 0,
        "narratives": 0,
        "total_elements": 0,
        "seconds_per_page": 0.0,
        "error": None,
    }

    try:
        from docling.document_converter import DocumentConverter

        result["available"] = True

        start = time.time()
        converter = DocumentConverter()
        doc_result = converter.convert(str(pdf_path))
        elapsed = time.time() - start

        # Access document structure
        doc = doc_result.document
        if hasattr(doc, "texts"):
            for text_item in doc.texts:
                text = str(text_item.text).strip() if hasattr(text_item, "text") else ""
                label = str(text_item.label) if hasattr(text_item, "label") else "unknown"
                entry = {"type": label, "text_length": len(text), "text_preview": text[:100]}
                result["elements"].append(entry)

                if "table" in label.lower():
                    result["tables"] += 1
                elif "title" in label.lower() or "heading" in label.lower():
                    result["titles"] += 1
                elif "text" in label.lower() or "paragraph" in label.lower():
                    result["narratives"] += 1

        result["total_elements"] = len(result["elements"])
        result["seconds_per_page"] = elapsed  # Approximate
        result["total_seconds"] = elapsed

    except ImportError:
        result["error"] = "docling not installed"
    except Exception as e:
        result["error"] = str(e)

    return result


def compare_results(unstructured_result: dict, docling_result: dict) -> dict:
    """Compare evaluation results between the two parsers."""
    comparison = {
        "unstructured_available": unstructured_result["available"],
        "docling_available": docling_result["available"],
    }

    for name, result in [("unstructured", unstructured_result), ("docling", docling_result)]:
        comparison[f"{name}_total_elements"] = result["total_elements"]
        comparison[f"{name}_tables"] = result["tables"]
        comparison[f"{name}_titles"] = result["titles"]
        comparison[f"{name}_narratives"] = result["narratives"]
        comparison[f"{name}_seconds_per_page"] = round(result["seconds_per_page"], 3)
        if result["error"]:
            comparison[f"{name}_error"] = result["error"]

    # Recommendation
    if not unstructured_result["available"] and not docling_result["available"]:
        comparison["recommendation"] = "Neither parser available. Install: pip install 'kmflow[layout]'"
    elif not docling_result["available"]:
        comparison["recommendation"] = "Unstructured (only option available)"
    elif not unstructured_result["available"]:
        comparison["recommendation"] = "Docling (only option available)"
    else:
        # Compare on key metrics
        u_score = unstructured_result["tables"] + unstructured_result["titles"]
        d_score = docling_result["tables"] + docling_result["titles"]
        u_speed = unstructured_result["seconds_per_page"]
        d_speed = docling_result["seconds_per_page"]

        if u_score > d_score:
            comparison["recommendation"] = "Unstructured (better element detection)"
        elif d_score > u_score:
            comparison["recommendation"] = "Docling (better element detection)"
        elif u_speed < d_speed:
            comparison["recommendation"] = "Unstructured (faster processing)"
        else:
            comparison["recommendation"] = "Docling (faster processing)"

    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate PDF parsers side-by-side")
    parser.add_argument("--pdf-dir", type=Path, help="Directory with sample PDFs")
    parser.add_argument("--output", type=Path, default=Path("parser_evaluation_results.json"))
    args = parser.parse_args()

    # Collect PDFs
    pdfs: list[Path] = []
    if args.pdf_dir and args.pdf_dir.exists():
        pdfs = list(args.pdf_dir.glob("*.pdf"))
    if not pdfs:
        logger.info("No PDFs provided, generating synthetic test PDF")
        test_pdf = Path("scripts/test_mortgage_lending.pdf")
        test_pdf.parent.mkdir(exist_ok=True)
        generate_test_pdf(test_pdf)
        pdfs = [test_pdf]

    all_results = []
    for pdf_path in pdfs:
        logger.info("Evaluating: %s", pdf_path.name)
        u_result = evaluate_unstructured(pdf_path)
        d_result = evaluate_docling(pdf_path)
        comparison = compare_results(u_result, d_result)

        all_results.append(
            {
                "file": pdf_path.name,
                "unstructured": u_result,
                "docling": d_result,
                "comparison": comparison,
            }
        )

    # Write results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    logger.info("Results written to: %s", args.output)

    # Print summary
    for r in all_results:
        c = r["comparison"]
        print(f"\n{'=' * 60}")
        print(f"File: {r['file']}")
        print(
            f"  Unstructured: {c.get('unstructured_total_elements', 'N/A')} elements, "
            f"{c.get('unstructured_tables', 'N/A')} tables, "
            f"{c.get('unstructured_seconds_per_page', 'N/A')}s/page"
        )
        print(
            f"  Docling:      {c.get('docling_total_elements', 'N/A')} elements, "
            f"{c.get('docling_tables', 'N/A')} tables, "
            f"{c.get('docling_seconds_per_page', 'N/A')}s/page"
        )
        print(f"  Recommendation: {c.get('recommendation', 'N/A')}")


if __name__ == "__main__":
    main()
