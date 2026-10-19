"""Report generation: single-file HTML and machine-readable JSON."""

from skytrace.report.html import render_html, write_html
from skytrace.report.json_report import report_dict, write_json

__all__ = ["render_html", "report_dict", "write_html", "write_json"]
