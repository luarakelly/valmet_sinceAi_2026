"""Automated engineering verification and ROI report generation."""

from datetime import datetime

from app.three_d.config import (
    DEFAULT_REPORT_JOB_ID,
    DEFAULT_REPORT_MATERIAL,
    DELAMINATION_RISK_LOW,
    SUPPORT_MODE_CANTILEVER,
)


def _format_css():
    return (
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;"
        "margin:0;padding:24px;background:#0f172a;color:#f8fafc;line-height:1.5}"
        ".card{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:20px;margin-bottom:20px}"
        "h1,h2,h3{margin-top:0;color:#38bdf8}table{width:100%;border-collapse:collapse;margin:12px 0}"
        "th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #334155}"
        "th{background:#0f172a;color:#94a3b8}.badge-pass{background:#065f46;color:#34d399;padding:4px 8px;border-radius:4px}"
        ".badge-fail{background:#7f1d1d;color:#f87171;padding:4px 8px;border-radius:4px}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}"
        ".metric{background:#0f172a;padding:12px;border-radius:6px;border:1px solid #334155}"
        ".metric-val{font-size:24px;font-weight:700;color:#38bdf8}"
    )


def _format_status_badge(is_safe):
    if is_safe:
        return '<span class="badge-pass">VERIFIED SAFE</span>'
    return '<span class="badge-fail">SAFETY TARGET UNMET</span>'


def _build_html_metrics_grid(summary):
    reduction = summary.get("reduction_pct", 0.0)
    mass_saved = summary.get("mass_saved_g", 0.0)
    cost_saved = summary.get("cost_saved_eur", 0.0)
    time_saved = summary.get("print_time_saved_hours", 0.0)
    return (
        f'<div class="grid">'
        f'<div class="metric"><div>Weight Reduction</div><div class="metric-val">{reduction}%</div></div>'
        f'<div class="metric"><div>Mass Saved</div><div class="metric-val">{mass_saved} g</div></div>'
        f'<div class="metric"><div>Cost Saved</div><div class="metric-val">€{cost_saved}</div></div>'
        f'<div class="metric"><div>Print Time Saved</div><div class="metric-val">{time_saved} h</div></div>'
        f'</div>'
    )


def _build_html_tables(summary, material_name):
    fos = summary.get("factor_of_safety", 0.0)
    fos_z = summary.get("anisotropic_fos_z", 0.0)
    max_stress = summary.get("max_stress_mpa", 0.0)
    max_sz = summary.get("max_tensile_z_mpa", 0.0)
    risk = summary.get("delamination_risk", DELAMINATION_RISK_LOW).upper()
    support = summary.get("support_mode", SUPPORT_MODE_CANTILEVER)

    return (
        f'<table><tr><th>Metric</th><th>Value</th><th>Status</th></tr>'
        f'<tr><td>Material</td><td>{material_name}</td><td>Specified</td></tr>'
        f'<tr><td>Support Boundary</td><td>{support}</td><td>Active</td></tr>'
        f'<tr><td>Peak Von Mises Stress</td><td>{max_stress} MPa</td><td>Evaluated</td></tr>'
        f'<tr><td>Factor of Safety (Bulk)</td><td>{fos}</td><td>Target ≥ 1.5</td></tr>'
        f'<tr><td>Peak Inter-layer Tensile (σzz)</td><td>{max_sz} MPa</td><td>Evaluated</td></tr>'
        f'<tr><td>Anisotropic FOS (Z-axis)</td><td>{fos_z}</td><td>Target ≥ 1.5</td></tr>'
        f'<tr><td>FDM Delamination Risk</td><td>{risk}</td><td>Assessed</td></tr>'
        f'</table>'
    )


def generate_html_report(summary, job_id=DEFAULT_REPORT_JOB_ID, material_name=DEFAULT_REPORT_MATERIAL):
    css = _format_css()
    is_safe = summary.get("is_safe", False)
    badge = _format_status_badge(is_safe)
    grid = _build_html_metrics_grid(summary)
    table = _build_html_tables(summary, material_name)
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    return (
        f'<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<title>Engineering Verification Report - {job_id}</title>'
        f'<style>{css}</style></head><body>'
        f'<div class="card"><h1>OptiShape 3D — Verification Report</h1>'
        f'<p>Job ID: <b>{job_id}</b> | Generated: {now} | Status: {badge}</p>'
        f'<h2>Executive ROI Summary</h2>{grid}</div>'
        f'<div class="card"><h2>Structural Safety & FEA Verification</h2>{table}</div>'
        f'</body></html>'
    )


def _build_markdown_roi_section(summary):
    reduction = summary.get("reduction_pct", 0.0)
    mass_saved = summary.get("mass_saved_g", 0.0)
    cost_saved = summary.get("cost_saved_eur", 0.0)
    time_saved = summary.get("print_time_saved_hours", 0.0)
    return (
        f"## Executive ROI Summary\n\n"
        f"- **Weight Reduction**: {reduction}%\n"
        f"- **Mass Saved**: {mass_saved} g\n"
        f"- **Cost Saved**: €{cost_saved}\n"
        f"- **Print Time Saved**: {time_saved} hours\n\n"
    )


def _build_markdown_fea_table(summary, material_name):
    fos = summary.get("factor_of_safety", 0.0)
    fos_z = summary.get("anisotropic_fos_z", 0.0)
    max_stress = summary.get("max_stress_mpa", 0.0)
    support = summary.get("support_mode", SUPPORT_MODE_CANTILEVER)
    risk = summary.get("delamination_risk", DELAMINATION_RISK_LOW).upper()

    return (
        f"## Structural Safety & FEA\n\n"
        f"| Parameter | Value |\n"
        f"| :--- | :--- |\n"
        f"| Material | {material_name} |\n"
        f"| Support Boundary | {support} |\n"
        f"| Max Von Mises Stress | {max_stress} MPa |\n"
        f"| Factor of Safety (Bulk) | {fos} |\n"
        f"| Anisotropic FOS (Z-axis) | {fos_z} |\n"
        f"| Delamination Risk | {risk} |\n"
    )


def generate_markdown_report(summary, job_id=DEFAULT_REPORT_JOB_ID, material_name=DEFAULT_REPORT_MATERIAL):
    status_label = "VERIFIED SAFE"
    if not summary.get("is_safe", False):
        status_label = "SAFETY TARGET UNMET"

    header = f"# OptiShape 3D — Engineering Verification Report\n\n**Job ID**: {job_id} | **Status**: {status_label}\n\n"
    roi_section = _build_markdown_roi_section(summary)
    fea_table = _build_markdown_fea_table(summary, material_name)
    return header + roi_section + fea_table
