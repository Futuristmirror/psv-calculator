"""
PDF Report Generator for PSV Calculator
Generates professional PDF reports with calculation results and uploaded attachments
"""

import io
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    PageBreak, Image, HRFlowable
)
from reportlab.lib import colors
from pypdf import PdfReader, PdfWriter


# Franc Engineering branding colors
BRAND_BLUE = HexColor('#1e40af')
BRAND_ORANGE = HexColor('#f97316')
HEADER_BG = HexColor('#f1f5f9')


def create_styles():
    """Create custom paragraph styles for the report"""
    styles = getSampleStyleSheet()
    
    # Title style
    styles.add(ParagraphStyle(
        name='ReportTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=BRAND_BLUE,
        spaceAfter=20,
    ))
    
    # Section header
    styles.add(ParagraphStyle(
        name='SectionHeader',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=BRAND_BLUE,
        spaceBefore=20,
        spaceAfter=10,
        borderColor=BRAND_BLUE,
        borderWidth=1,
        borderPadding=5,
    ))
    
    # Subsection header
    styles.add(ParagraphStyle(
        name='SubsectionHeader',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=BRAND_BLUE,
        spaceBefore=15,
        spaceAfter=8,
    ))
    
    # Normal text
    styles.add(ParagraphStyle(
        name='ReportBody',
        parent=styles['Normal'],
        fontSize=10,
        spaceBefore=6,
        spaceAfter=6,
    ))
    
    # Footer style
    styles.add(ParagraphStyle(
        name='Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.gray,
    ))
    
    return styles


def create_header_footer(canvas, doc, report_data: Dict):
    """Add header and footer to each page"""
    canvas.saveState()
    
    # Header
    canvas.setFont('Helvetica-Bold', 10)
    canvas.setFillColor(BRAND_BLUE)
    canvas.drawString(inch, letter[1] - 0.5*inch, "FRANC ENGINEERING")
    
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.gray)
    canvas.drawString(inch, letter[1] - 0.7*inch, "PSV Sizing Report per API 520/521")
    
    # Right side - report info
    canvas.drawRightString(letter[0] - inch, letter[1] - 0.5*inch, 
                          f"Tag: {report_data.get('device_info', {}).get('tag', 'N/A')}")
    canvas.drawRightString(letter[0] - inch, letter[1] - 0.7*inch,
                          f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    
    # Header line
    canvas.setStrokeColor(BRAND_BLUE)
    canvas.setLineWidth(1)
    canvas.line(inch, letter[1] - 0.8*inch, letter[0] - inch, letter[1] - 0.8*inch)
    
    # Footer
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.gray)
    canvas.drawString(inch, 0.5*inch, "© Franc Engineering | franceng.com | For screening purposes only")
    canvas.drawRightString(letter[0] - inch, 0.5*inch, f"Page {doc.page}")
    
    # Footer line
    canvas.line(inch, 0.7*inch, letter[0] - inch, 0.7*inch)
    
    canvas.restoreState()


def create_info_table(data: Dict[str, str], styles) -> Table:
    """Create a formatted info table"""
    table_data = [[k, v] for k, v in data.items()]
    
    table = Table(table_data, colWidths=[2.5*inch, 4*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), HEADER_BG),
        ('TEXTCOLOR', (0, 0), (0, -1), BRAND_BLUE),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    return table


def create_results_table(results: Dict, styles) -> Table:
    """Create the calculation results table"""
    table_data = [
        ['Parameter', 'Value', 'Units'],
        ['Scenario', results.get('scenario', 'N/A'), '-'],
        ['Relief Rate', f"{results.get('relief_rate', 0):.2f}", results.get('relief_rate_units', 'lb/hr')],
        ['Relieving Pressure', f"{results.get('relieving_pressure_psia', 0):.1f}", 'psia'],
        ['Required Orifice Area', f"{results.get('required_area_in2', 0):.4f}", 'in²'],
        ['Selected Orifice', results.get('selected_orifice', 'N/A'), '-'],
        ['Orifice Area', f"{results.get('orifice_area_in2', 0):.4f}", 'in²'],
        ['Percent Utilization', f"{results.get('percent_utilization', 0):.1f}", '%'],
    ]
    
    # Add optional fields
    if results.get('heat_input_mmbtu_hr'):
        table_data.append(['Heat Input', f"{results['heat_input_mmbtu_hr']:.3f}", 'MMBTU/hr'])
    if results.get('wetted_area_ft2'):
        table_data.append(['Wetted Area', f"{results['wetted_area_ft2']:.1f}", 'ft²'])
    
    table = Table(table_data, colWidths=[2.5*inch, 2*inch, 1.5*inch])
    table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, HEADER_BG]),
    ]))
    
    return table


def create_fluid_properties_table(fluid_props: Dict, styles) -> Table:
    """Create fluid properties table"""
    table_data = [
        ['Property', 'Value', 'Units'],
        ['Molecular Weight', f"{fluid_props.get('mw', 0):.2f}", 'lb/lbmol'],
        ['Compressibility (Z)', f"{fluid_props.get('Z', 1):.4f}", '-'],
        ['Density', f"{fluid_props.get('density_kg_m3', 0):.2f}", 'kg/m³'],
        ['Cp/Cv (γ)', f"{fluid_props.get('gamma', 1):.3f}", '-'],
        ['Phase', fluid_props.get('phase', 'N/A'), '-'],
    ]
    
    if fluid_props.get('lfl_percent'):
        table_data.append(['LFL', f"{fluid_props['lfl_percent']:.2f}", '%'])
    if fluid_props.get('ufl_percent'):
        table_data.append(['UFL', f"{fluid_props['ufl_percent']:.2f}", '%'])
    
    table = Table(table_data, colWidths=[2.5*inch, 2*inch, 1.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, HEADER_BG]),
    ]))
    
    return table


def generate_psv_report(
    device_info: Dict,
    scenario_info: Dict,
    fluid_info: Dict,
    calculation_results: Dict,
    attachments: Optional[List[bytes]] = None,
    customer_email: Optional[str] = None,
) -> bytes:
    """
    Generate a complete PSV sizing report as PDF
    
    Args:
        device_info: Device information (tag, P&ID, facility, etc.)
        scenario_info: Relief scenario details
        fluid_info: Fluid composition and properties
        calculation_results: PSV sizing results
        attachments: List of PDF attachments (P&ID, misc docs) as bytes
        customer_email: Customer email for the report
        
    Returns:
        PDF file as bytes
    """
    
    # Create buffer for the main report
    buffer = io.BytesIO()
    
    # Create document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )
    
    styles = create_styles()
    story = []
    
    # Store report data for header/footer
    report_data = {'device_info': device_info}
    
    # ===== TITLE PAGE =====
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph("PSV SIZING REPORT", styles['ReportTitle']))
    story.append(Paragraph("Pressure Safety Valve Sizing per API 520/521", styles['ReportBody']))
    story.append(Spacer(1, 0.5*inch))
    
    # Device summary on title page
    title_info = {
        'Relief Device Tag': device_info.get('tag', 'N/A'),
        'P&ID Number': device_info.get('pid_number', 'N/A'),
        'Facility': device_info.get('facility_name', 'N/A'),
        'Protected System': device_info.get('protected_system', 'N/A'),
        'Report Date': datetime.now().strftime('%B %d, %Y'),
    }
    if customer_email:
        title_info['Prepared For'] = customer_email
        
    story.append(create_info_table(title_info, styles))
    
    story.append(Spacer(1, inch))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_BLUE))
    story.append(Spacer(1, 0.25*inch))
    story.append(Paragraph(
        "<b>DISCLAIMER:</b> This report is for screening purposes only. "
        "Final PSV sizing should be verified by a licensed professional engineer. "
        "Franc Engineering assumes no liability for the use of this information.",
        styles['Footer']
    ))
    
    story.append(PageBreak())
    
    # ===== DEVICE INFORMATION =====
    story.append(Paragraph("1. RELIEF DEVICE INFORMATION", styles['SectionHeader']))
    
    device_table_data = {
        'Relief Device Tag': device_info.get('tag', 'N/A'),
        'P&ID Number': device_info.get('pid_number', 'N/A'),
        'Facility Name': device_info.get('facility_name', 'N/A'),
        'Protected System': device_info.get('protected_system', 'N/A'),
        'System MAWP': f"{device_info.get('mawp_psig', 'N/A')} psig",
        'Selected Orifice Size': device_info.get('orifice_selection', 'Calculate Required'),
        'Installation Type': device_info.get('new_or_existing', 'New Installation'),
        'Discharge Location': device_info.get('discharge_location', 'Atmosphere'),
        'PSV Set Pressure': f"{device_info.get('set_pressure_psig', 'N/A')} psig",
        'PSV Type': device_info.get('psv_type', 'Conventional'),
    }
    story.append(create_info_table(device_table_data, styles))
    
    # ===== SCENARIO INFORMATION =====
    story.append(Paragraph("2. RELIEF SCENARIO", styles['SectionHeader']))
    
    scenario_table_data = {
        'Scenario Type': scenario_info.get('scenario_type', 'N/A'),
        'Description': scenario_info.get('description', 'N/A'),
        'Back Pressure': f"{scenario_info.get('back_pressure_psig', 0)} psig",
    }
    
    # Add scenario-specific fields
    if scenario_info.get('vessel_orientation'):
        scenario_table_data['Vessel Orientation'] = scenario_info['vessel_orientation']
    if scenario_info.get('vessel_diameter'):
        scenario_table_data['Vessel Diameter'] = f"{scenario_info['vessel_diameter']} ft"
    if scenario_info.get('vessel_length'):
        scenario_table_data['Vessel Length'] = f"{scenario_info['vessel_length']} ft"
    if scenario_info.get('liquid_level'):
        scenario_table_data['Liquid Level'] = f"{scenario_info['liquid_level']*100:.0f}%"
    if scenario_info.get('insulated') is not None:
        scenario_table_data['Insulated'] = 'Yes' if scenario_info['insulated'] else 'No'
    if scenario_info.get('flow_rate'):
        scenario_table_data['Input Flow Rate'] = f"{scenario_info['flow_rate']}"
        
    story.append(create_info_table(scenario_table_data, styles))
    
    # ===== FLUID INFORMATION =====
    story.append(Paragraph("3. FLUID PROPERTIES", styles['SectionHeader']))
    
    story.append(Paragraph("3.1 Composition", styles['SubsectionHeader']))
    
    # Composition table
    components = fluid_info.get('components', [])
    if components:
        comp_data = [['Component', 'Mole Fraction']]
        for comp in components:
            comp_data.append([comp.get('name', 'N/A'), f"{comp.get('mole_fraction', 0):.4f}"])
        
        comp_table = Table(comp_data, colWidths=[3*inch, 2*inch])
        comp_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ]))
        story.append(comp_table)
    
    story.append(Paragraph("3.2 Operating Conditions", styles['SubsectionHeader']))
    
    conditions = {
        'Temperature': f"{fluid_info.get('temperature_F', 'N/A')} °F",
        'Pressure': f"{fluid_info.get('pressure_psig', 'N/A')} psig",
    }
    story.append(create_info_table(conditions, styles))
    
    story.append(Paragraph("3.3 Calculated Properties", styles['SubsectionHeader']))
    
    fluid_props = calculation_results.get('fluid_properties', {})
    story.append(create_fluid_properties_table(fluid_props, styles))
    
    # ===== CALCULATION RESULTS =====
    story.append(PageBreak())
    story.append(Paragraph("4. CALCULATION RESULTS", styles['SectionHeader']))
    
    story.append(create_results_table(calculation_results, styles))
    
    story.append(Spacer(1, 0.5*inch))
    
    # Summary box
    summary_text = f"""
    <b>SIZING SUMMARY:</b><br/><br/>
    The relief device <b>{device_info.get('tag', 'N/A')}</b> requires a minimum orifice area of 
    <b>{calculation_results.get('required_area_in2', 0):.4f} in²</b>.<br/><br/>
    
    The selected <b>{calculation_results.get('selected_orifice', 'N/A')}</b> orifice 
    ({calculation_results.get('orifice_area_in2', 0):.4f} in²) provides 
    <b>{calculation_results.get('percent_utilization', 0):.1f}%</b> utilization.<br/><br/>
    
    {"✓ ADEQUATE - Orifice size is sufficient for the specified relief scenario." 
     if calculation_results.get('percent_utilization', 100) <= 100 
     else "⚠ WARNING - Selected orifice may be undersized. Review recommended."}
    """
    
    story.append(Paragraph(summary_text, styles['ReportBody']))
    
    # ===== METHODOLOGY =====
    story.append(Paragraph("5. METHODOLOGY & REFERENCES", styles['SectionHeader']))
    
    methodology_text = """
    This PSV sizing calculation follows the methodology outlined in:<br/><br/>
    • <b>API Standard 520 Part I</b> - Sizing, Selection, and Installation of 
      Pressure-relieving Devices<br/>
    • <b>API Standard 521</b> - Pressure-relieving and Depressuring Systems<br/><br/>
    
    Thermodynamic properties are calculated using the Peng-Robinson equation of state 
    with standard mixing rules for multicomponent systems.<br/><br/>
    
    Orifice designations and areas per <b>API Standard 526</b> - Flanged Steel 
    Pressure-relief Valves.
    """
    story.append(Paragraph(methodology_text, styles['ReportBody']))
    
    # Build the main report
    doc.build(
        story,
        onFirstPage=lambda c, d: create_header_footer(c, d, report_data),
        onLaterPages=lambda c, d: create_header_footer(c, d, report_data),
    )
    
    # Get the main report PDF
    buffer.seek(0)
    main_pdf = buffer.getvalue()
    
    # If there are attachments, merge them
    if attachments:
        return merge_pdfs(main_pdf, attachments)
    
    return main_pdf


def merge_pdfs(main_pdf: bytes, attachments: List[bytes]) -> bytes:
    """Merge the main report with uploaded attachments"""
    writer = PdfWriter()
    
    # Add main report pages
    main_reader = PdfReader(io.BytesIO(main_pdf))
    for page in main_reader.pages:
        writer.add_page(page)
    
    # Add attachment pages
    for attachment in attachments:
        try:
            attachment_reader = PdfReader(io.BytesIO(attachment))
            for page in attachment_reader.pages:
                writer.add_page(page)
        except Exception as e:
            print(f"Warning: Could not add attachment: {e}")
            continue
    
    # Write merged PDF
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    
    return output.getvalue()
