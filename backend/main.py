# Force redeploy v3
"""
PSV Calculator API - FastAPI Backend
REST API for PSV sizing calculations using Peng-Robinson EOS
Author: Franc Engineering
"""

import os
import io
import stripe
import uuid
import base64
from fastapi import FastAPI, HTTPException, Request, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uvicorn
import time

from thermo_engine import get_properties, COMPONENTS, PRESETS
from psv_sizing import calculate_psv_size, wetted_area_horizontal_vessel, wetted_area_vertical_vessel
from pdf_generator import generate_psv_report
from email_service import send_report_email, send_pe_review_notification

# Stripe Configuration
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://psv-calculator-production.up.railway.app")

# In-memory stores (use Redis/DB in production)
payment_sessions: Dict[str, Dict] = {}  # session_id -> { status, email, product, ... }
free_report_users: Dict[str, bool] = {}  # email/fingerprint -> has_used_free_report
uploaded_files: Dict[str, bytes] = {}  # file_id -> file_bytes (temporary storage)

app = FastAPI(
    title="Franc Engineering PSV Calculator API",
    description="API for pressure safety valve sizing per API 520/521",
    version="1.0.0",
    contact={
        "name": "Franc Engineering",
        "url": "https://franceng.com",
        "email": "info@franceng.com"
    }
)

# CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ComponentInput(BaseModel):
    name: str = Field(..., description="Component name (e.g., 'methane', 'propane')")
    mole_fraction: float = Field(..., ge=0, le=1, description="Mole fraction (0-1)")

class FluidInput(BaseModel):
    components: List[ComponentInput] = Field(..., description="List of components with mole fractions")
    temperature_F: float = Field(..., description="Temperature in °F")
    pressure_psig: float = Field(..., description="Pressure in psig")

class VesselInput(BaseModel):
    orientation: str = Field("horizontal", description="'horizontal' or 'vertical'")
    diameter_ft: float = Field(..., gt=0, description="Vessel diameter in feet")
    length_ft: float = Field(..., gt=0, description="Vessel length/height in feet")
    liquid_level_fraction: float = Field(0.5, ge=0, le=1, description="Liquid level as fraction of diameter")
    insulated: bool = Field(False, description="Whether vessel is insulated")

class PSVSizingRequest(BaseModel):
    scenario: str = Field(..., description="Scenario: fire_wetted, fire_unwetted, blocked_vapor, blocked_liquid, cv_failure")
    set_pressure_psig: float = Field(..., gt=0, description="PSV set pressure in psig")
    back_pressure_psig: float = Field(0, ge=0, description="Back pressure in psig")
    fluid: FluidInput
    vessel: Optional[VesselInput] = None
    flow_rate: Optional[float] = Field(None, description="Flow rate for blocked outlet scenarios")
    latent_heat_btu_lb: Optional[float] = Field(None, description="Latent heat for fire cases (BTU/lb)")


# ============================================================================
# FLEXIBLE REPORT REQUEST MODEL (matches frontend)
# ============================================================================

class FrontendReportRequest(BaseModel):
    """
    Flexible model that accepts the frontend's data structure directly.
    This avoids having to transform data on the frontend.
    """
    email: str = Field(..., description="Customer email")
    device_info: Dict[str, Any] = Field(..., description="Device information from frontend")
    report_info: Optional[Dict[str, Any]] = Field(default={}, description="Report metadata")
    vessel_details: Optional[Dict[str, Any]] = Field(default={}, description="Vessel dimensions")
    scenario_selections: Optional[Dict[str, Any]] = Field(default={}, description="Which scenarios are applicable")
    scenario_conditions: Optional[Dict[str, Any]] = Field(default={}, description="Conditions for each scenario")
    compositions: Optional[Dict[str, Any]] = Field(default={}, description="Fluid compositions per scenario")
    results: Optional[Dict[str, Any]] = Field(default={}, description="Calculation results")
    pid_file_id: Optional[str] = Field(default=None, description="Uploaded P&ID file ID")
    misc_file_id: Optional[str] = Field(default=None, description="Uploaded misc file ID")


class CreateCheckoutRequest(BaseModel):
    product: str = Field(..., description="Product type: 'standard_report' or 'pe_reviewed'")
    email: Optional[str] = Field(None, description="Customer email for receipt")
    customer_name: Optional[str] = Field(None, description="Customer name")
    customer_notes: Optional[str] = Field(None, description="Additional notes for PE review")
    report_data: Optional[Dict[str, Any]] = Field(None, description="Full report data to store")
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


# Product pricing configuration
PRODUCTS = {
    "standard_report": {
        "name": "PSV Calculator - Standard Report",
        "description": "Full PDF calculation package with all inputs documented",
        "price_cents": 9900,  # $99.00
    },
    "pe_reviewed": {
        "name": "PSV Calculator - PE-Reviewed Report", 
        "description": "Engineer stamped report with PE (TX/CO) review, 48-72hr delivery",
        "price_cents": 49900,  # $499.00
    }
}


# ============================================================================
# SERVE FRONTEND
# ============================================================================

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the PSV Calculator frontend"""
    index_path = os.path.join(STATIC_DIR, "psv-calculator.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return HTMLResponse(
        content="<h1>Franc Engineering PSV Calculator API</h1><p>Frontend not found. API docs at <a href='/docs'>/docs</a></p>",
        status_code=200
    )


# ============================================================================
# API INFO & COMPONENTS
# ============================================================================

@app.get("/api")
async def api_info():
    """API info endpoint"""
    return {
        "message": "Franc Engineering PSV Calculator API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/components")
async def list_components():
    """Get list of available components"""
    return {
        "components": [
            {
                "id": name,
                "name": comp.name,
                "formula": comp.formula,
                "mw": comp.mw,
                "lfl": comp.lfl,
                "ufl": comp.ufl
            }
            for name, comp in COMPONENTS.items()
        ]
    }

@app.get("/presets")
async def list_presets():
    """Get list of fluid presets"""
    return {"presets": PRESETS}


# ============================================================================
# THERMODYNAMIC CALCULATIONS
# ============================================================================

@app.post("/properties")
async def calculate_properties(fluid: FluidInput) -> Dict:
    """Calculate thermodynamic properties for a fluid mixture"""
    try:
        components = [c.name.lower() for c in fluid.components]
        mole_fractions = [c.mole_fraction for c in fluid.components]
        
        total = sum(mole_fractions)
        mole_fractions = [x / total for x in mole_fractions]
        
        T_K = (fluid.temperature_F + 459.67) * 5/9
        P_Pa = (fluid.pressure_psig + 14.7) * 6894.76
        
        props = get_properties(components, mole_fractions, T_K, P_Pa)
        
        return {
            "molecular_weight": round(props["mw"], 2),
            "compressibility_Z": round(props["Z"], 4),
            "density_kg_m3": round(props["density"], 2),
            "density_lb_ft3": round(props["density"] * 0.0624, 2),
            "gamma_cp_cv": round(props["gamma"], 3),
            "lfl_percent": round(props["lfl"], 2) if props["lfl"] else None,
            "ufl_percent": round(props["ufl"], 2) if props["ufl"] else None,
            "phase": props["flash"]["phase"],
            "vapor_fraction": props["flash"]["vapor_fraction"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# PSV SIZING
# ============================================================================

@app.post("/size-psv")
async def size_psv(request: PSVSizingRequest) -> Dict:
    """Calculate PSV sizing for specified scenario"""
    try:
        components = [c.name.lower() for c in request.fluid.components]
        mole_fractions = [c.mole_fraction for c in request.fluid.components]
        
        total = sum(mole_fractions)
        mole_fractions = [x / total for x in mole_fractions]
        
        T_K = (request.fluid.temperature_F + 459.67) * 5/9
        P_Pa = (request.fluid.pressure_psig + 14.7) * 6894.76
        
        props = get_properties(components, mole_fractions, T_K, P_Pa)
        
        vessel_props = {}
        if request.vessel:
            if request.vessel.orientation == "horizontal":
                wetted_area = wetted_area_horizontal_vessel(
                    request.vessel.diameter_ft,
                    request.vessel.length_ft,
                    request.vessel.liquid_level_fraction
                )
            else:
                liquid_height = request.vessel.liquid_level_fraction * request.vessel.length_ft
                wetted_area = wetted_area_vertical_vessel(
                    request.vessel.diameter_ft,
                    request.vessel.length_ft,
                    liquid_height
                )
            vessel_props = {
                "wetted_area_ft2": wetted_area,
                "surface_area_ft2": wetted_area * 1.5,
                "insulated": request.vessel.insulated,
                "F_env": 0.3 if request.vessel.insulated else 1.0
            }
        
        fluid_props = {
            "MW": props["mw"],
            "Z": props["Z"],
            "gamma": props["gamma"],
            "T_F": request.fluid.temperature_F,
            "latent_heat_btu_lb": request.latent_heat_btu_lb or 150,
            "specific_gravity": props["density"] / 1000
        }
        
        result = calculate_psv_size(
            scenario=request.scenario,
            set_pressure_psig=request.set_pressure_psig,
            fluid_properties=fluid_props,
            vessel_properties=vessel_props if vessel_props else None,
            flow_rate=request.flow_rate,
            back_pressure_psig=request.back_pressure_psig
        )
        
        result["fluid_properties"] = {
            "mw": round(props["mw"], 2),
            "Z": round(props["Z"], 4),
            "density_kg_m3": round(props["density"], 2),
            "gamma": round(props["gamma"], 3),
            "lfl_percent": round(props["lfl"], 2) if props["lfl"] else None,
            "ufl_percent": round(props["ufl"], 2) if props["ufl"] else None,
            "phase": props["flash"]["phase"]
        }
        
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/orifices")
async def list_orifices():
    """Get API 526 standard orifice sizes"""
    from psv_sizing import API_526_ORIFICES
    return {
        "orifices": [
            {
                "letter": o.letter,
                "area_in2": o.area_in2,
                "area_mm2": o.area_mm2
            }
            for o in API_526_ORIFICES
        ]
    }


# ============================================================================
# FILE UPLOAD
# ============================================================================

@app.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a PDF file (P&ID or miscellaneous document)
    Returns a file_id to reference in report generation
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    
    # Read file content
    content = await file.read()
    
    # Limit file size (10MB)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
    
    # Generate unique ID
    file_id = str(uuid.uuid4())
    
    # Store file (in production, use S3 or similar)
    uploaded_files[file_id] = content
    
    return {
        "file_id": file_id,
        "filename": file.filename,
        "size_bytes": len(content)
    }


# ============================================================================
# PDF REPORT GENERATION (FLEXIBLE - matches frontend)
# ============================================================================

@app.post("/generate-report")
async def generate_report(request: FrontendReportRequest):
    """
    Generate a PDF report from frontend data.
    
    Accepts the exact data structure the frontend sends.
    First report per user is FREE, subsequent reports require payment.
    """
    user_identifier = request.email or "anonymous"
    
    # Check if user has already used free report
    has_used_free = free_report_users.get(user_identifier, False)
    
    # Collect any uploaded attachments
    attachments = []
    if request.pid_file_id and request.pid_file_id in uploaded_files:
        attachments.append(uploaded_files[request.pid_file_id])
    if request.misc_file_id and request.misc_file_id in uploaded_files:
        attachments.append(uploaded_files[request.misc_file_id])
    
    try:
        # Generate the PDF using the frontend's data structure
        pdf_bytes = generate_psv_report_from_frontend(
            device_info=request.device_info,
            report_info=request.report_info or {},
            vessel_details=request.vessel_details or {},
            scenario_selections=request.scenario_selections or {},
            scenario_conditions=request.scenario_conditions or {},
            compositions=request.compositions or {},
            results=request.results or {},
            attachments=attachments if attachments else None,
            customer_email=request.email,
        )
        
        # Mark that user has used their free report
        if not has_used_free and request.email:
            free_report_users[user_identifier] = True
        
        # Get device tag for filename
        device_tag = request.device_info.get("tag", "PSV") if request.device_info else "PSV"
        
        # Send email if provided
        if request.email:
            try:
                send_report_email(
                    to_email=request.email,
                    pdf_bytes=pdf_bytes,
                    device_tag=device_tag,
                    report_type="standard",
                )
            except Exception as email_error:
                print(f"Warning: Could not send email: {email_error}")
        
        # Return PDF as download
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=PSV_Report_{device_tag}.pdf"
            }
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")


def generate_psv_report_from_frontend(
    device_info: Dict[str, Any],
    report_info: Dict[str, Any],
    vessel_details: Dict[str, Any],
    scenario_selections: Dict[str, Any],
    scenario_conditions: Dict[str, Any],
    compositions: Dict[str, Any],
    results: Dict[str, Any],
    attachments: Optional[List[bytes]] = None,
    customer_email: Optional[str] = None,
) -> bytes:
    """
    Generate PDF report from the frontend's data structure.
    
    This function transforms the frontend data and calls the PDF generator.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from pypdf import PdfReader, PdfWriter
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=1*inch,
        bottomMargin=0.75*inch
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1e3a5f')
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceBefore=15,
        spaceAfter=8,
        textColor=colors.HexColor('#1e3a5f')
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6
    )
    
    story = []
    
    # ========== TITLE PAGE ==========
    story.append(Spacer(1, 1*inch))
    
    device_tag = device_info.get('tag', 'PSV')
    revision = report_info.get('revision', 'A') if report_info else 'A'
    
    story.append(Paragraph(f"<b>{device_tag} Deliverable Rev. {revision}</b>", title_style))
    story.append(Spacer(1, 0.5*inch))
    
    # Device info table
    device_data = []
    if device_info.get('facility_name'):
        device_data.append(['Facility:', device_info.get('facility_name', '')])
    if device_info.get('pid_number'):
        device_data.append(['P&ID Number:', device_info.get('pid_number', '')])
    if device_info.get('protected_system'):
        device_data.append(['Protected System:', device_info.get('protected_system', '')])
    if device_info.get('set_pressure'):
        device_data.append(['Set Pressure:', f"{device_info.get('set_pressure', '')} psig"])
    if device_info.get('selected_orifice'):
        device_data.append(['Selected Orifice:', device_info.get('selected_orifice', '')])
    
    if device_data:
        device_table = Table(device_data, colWidths=[2*inch, 4*inch])
        device_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(device_table)
    
    story.append(Spacer(1, 0.5*inch))
    
    # Revision history
    story.append(Paragraph("<b>Revision History</b>", heading_style))
    
    revision_history = report_info.get('revision_history', []) if report_info else []
    if not revision_history:
        revision_history = [{'rev': 'A', 'date': '', 'description': 'Issued for Review'}]
    
    rev_data = [['Rev', 'Date', 'Description']]
    for rev in revision_history:
        rev_data.append([
            rev.get('rev', ''),
            rev.get('date', ''),
            rev.get('description', '')
        ])
    
    rev_table = Table(rev_data, colWidths=[0.75*inch, 1.25*inch, 4*inch])
    rev_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8f4f8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(rev_table)
    
    story.append(PageBreak())
    
    # ========== RELIEF DEVICE SIZING SUMMARY ==========
    story.append(Paragraph("<b>Relief Device Sizing Summary</b>", title_style))
    story.append(Spacer(1, 0.25*inch))
    
    # Device details section
    story.append(Paragraph("<b>Relief Device & Protected System Details</b>", heading_style))
    
    details_data = [
        ['Relief Device Tag:', device_info.get('tag', '-'), 'P&ID Number:', device_info.get('pid_number', '-')],
        ['PSV Type:', device_info.get('psv_type', 'CONVENTIONAL').upper(), 'Discharge Location:', device_info.get('discharge_location', 'ATMOSPHERE').upper()],
        ['Set Pressure:', f"{device_info.get('set_pressure', '-')} psig", 'Selected Orifice:', device_info.get('selected_orifice', '-')],
    ]
    
    details_table = Table(details_data, colWidths=[1.5*inch, 1.75*inch, 1.5*inch, 1.75*inch])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f8f8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 0.25*inch))
    
    # ========== SCENARIO RESULTS TABLE ==========
    if results and results.get('scenarioResults'):
        story.append(Paragraph("<b>Summary of Potential Relieving Scenarios</b>", heading_style))
        
        scenario_results = results.get('scenarioResults', {})
        controlling = results.get('controllingScenario', '')
        
        # Table header
        table_data = [['Credible?', 'Scenario', 'Required Flow\n(lb/hr)', 'Rated Flow\n(lb/hr)', 'Required Area\n(in²)', 'Status']]
        
        scenario_names = {
            'fire_wetted': '1A - Fire-Wetted',
            'fire_unwetted': '1B - Fire-Unwetted',
            'blocked_vapor': '2A - Blocked Outlet',
            'cv_failure': '3 - CV Failure',
            'hydraulic_thermal': '4 - Hydraulic Thermal',
        }
        
        for scen_id, scen_name in scenario_names.items():
            sel = scenario_selections.get(scen_id, {}) if scenario_selections else {}
            sr = scenario_results.get(scen_id, {})
            
            is_applicable = sel.get('applicable', False) if isinstance(sel, dict) else False
            credible = 'YES' if is_applicable and sr.get('applicable') else 'NO'
            
            if sr.get('applicable'):
                req_flow = f"{sr.get('requiredFlow', 0):,.0f}" if sr.get('requiredFlow') else '-'
                rated_flow = f"{sr.get('ratedFlow', 0):,.0f}" if sr.get('ratedFlow') else '-'
                req_area = f"{sr.get('requiredArea', 0):.3f}" if sr.get('requiredArea') else '-'
                status = 'Adequate' if sr.get('adequate') else 'UNDERSIZED'
            else:
                req_flow = '-'
                rated_flow = '-'
                req_area = '-'
                status = '-'
            
            table_data.append([credible, scen_name, req_flow, rated_flow, req_area, status])
        
        scenario_table = Table(table_data, colWidths=[0.75*inch, 1.5*inch, 1*inch, 1*inch, 1*inch, 1*inch])
        scenario_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d0e8f0')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ]))
        
        # Highlight controlling scenario row
        for i, scen_id in enumerate(scenario_names.keys(), start=1):
            if scen_id == controlling:
                scenario_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fff3cd')),
                ]))
            # Color status cell
            sr = scenario_results.get(scen_id, {})
            if sr.get('applicable'):
                if sr.get('adequate'):
                    scenario_table.setStyle(TableStyle([
                        ('TEXTCOLOR', (5, i), (5, i), colors.HexColor('#28a745')),
                    ]))
                else:
                    scenario_table.setStyle(TableStyle([
                        ('TEXTCOLOR', (5, i), (5, i), colors.HexColor('#dc3545')),
                        ('FONTNAME', (5, i), (5, i), 'Helvetica-Bold'),
                    ]))
        
        story.append(scenario_table)
        story.append(Spacer(1, 0.25*inch))
        
        # Controlling scenario summary
        if controlling and scenario_results.get(controlling):
            sr = scenario_results[controlling]
            story.append(Paragraph("<b>Design Scenario Summary</b>", heading_style))
            
            summary_data = [
                ['Controlling Scenario:', scenario_names.get(controlling, controlling)],
                ['Required Orifice Area:', f"{results.get('maxRequiredArea', 0):.3f} in²"],
                ['System Status:', 'ADEQUATE' if not results.get('isUndersized') else 'UNDERSIZED - RECOMMEND LARGER ORIFICE'],
            ]
            
            summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
            summary_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(summary_table)
    
    story.append(PageBreak())
    
    # ========== VESSEL DETAILS ==========
    if vessel_details:
        story.append(Paragraph("<b>Vessel Details</b>", heading_style))
        
        vessel_data = []
        if vessel_details.get('equipment_tag'):
            vessel_data.append(['Equipment Tag:', vessel_details.get('equipment_tag', '-')])
        vessel_data.append(['Orientation:', vessel_details.get('orientation', 'horizontal').title()])
        vessel_data.append(['Head Type:', vessel_details.get('head_type', '2:1_elliptical').replace('_', ' ').title()])
        vessel_data.append(['Inner Diameter:', f"{vessel_details.get('inner_diameter', '-')} in"])
        vessel_data.append(['Seam-to-Seam Length:', f"{vessel_details.get('seam_to_seam', '-')} ft"])
        vessel_data.append(['Height Above Grade:', f"{vessel_details.get('height_above_grade', '-')} ft"])
        
        if vessel_data:
            vessel_table = Table(vessel_data, colWidths=[2*inch, 3*inch])
            vessel_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(vessel_table)
            story.append(Spacer(1, 0.25*inch))
    
    # ========== FLUID COMPOSITIONS ==========
    if compositions:
        story.append(Paragraph("<b>Fluid Compositions</b>", heading_style))
        
        for scen_id, comp in compositions.items():
            if comp and any(v > 0 for v in comp.values()):
                scen_name = scenario_names.get(scen_id, scen_id)
                story.append(Paragraph(f"<i>{scen_name}</i>", normal_style))
                
                comp_data = [['Component', 'Mol %']]
                for comp_name, mol_pct in comp.items():
                    if mol_pct > 0:
                        comp_data.append([comp_name.title(), f"{mol_pct:.2f}"])
                
                if len(comp_data) > 1:
                    comp_table = Table(comp_data, colWidths=[2*inch, 1*inch])
                    comp_table.setStyle(TableStyle([
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8f4f8')),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ]))
                    story.append(comp_table)
                    story.append(Spacer(1, 0.15*inch))
    
    # ========== FOOTER ON EACH PAGE ==========
    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(0.75*inch, 0.5*inch, f"{device_tag} | Rev. {revision}")
        canvas.drawCentredString(letter[0]/2, 0.5*inch, f"Page {doc.page}")
        canvas.drawRightString(letter[0] - 0.75*inch, 0.5*inch, "Franc Engineering")
        canvas.restoreState()
    
    # Build main PDF
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    
    # Get the main report PDF bytes
    buffer.seek(0)
    main_pdf_bytes = buffer.getvalue()
    
    # Merge with attachments if any
    if attachments:
        writer = PdfWriter()
        
        # Add main report pages
        main_reader = PdfReader(io.BytesIO(main_pdf_bytes))
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
    
    return main_pdf_bytes


@app.get("/check-free-report")
async def check_free_report(email: str):
    """Check if a user has already used their free report"""
    has_used = free_report_users.get(email, False)
    return {
        "email": email,
        "has_used_free_report": has_used,
        "can_generate_free": not has_used
    }


# ============================================================================
# STRIPE PAYMENT
# ============================================================================

@app.post("/create-checkout-session")
async def create_checkout_session(request: CreateCheckoutRequest):
    """Create a Stripe Checkout session for payment"""
    if not stripe.api_key:
        raise HTTPException(
            status_code=500, 
            detail="Stripe not configured. Set STRIPE_SECRET_KEY environment variable."
        )
    
    product = PRODUCTS.get(request.product)
    if not product:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid product. Choose from: {list(PRODUCTS.keys())}"
        )
    
    try:
        success_url = request.success_url or f"{FRONTEND_URL}?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = request.cancel_url or f"{FRONTEND_URL}?payment=cancelled"
        
        # For PE-reviewed, collect additional info
        checkout_params = {
            "payment_method_types": ["card"],
            "line_items": [{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": product["name"],
                        "description": product["description"],
                    },
                    "unit_amount": product["price_cents"],
                },
                "quantity": 1,
            }],
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "customer_email": request.email,
            "metadata": {
                "product": request.product,
                "customer_name": request.customer_name or "",
                "customer_notes": request.customer_notes or "",
            }
        }
        
        # For PE-reviewed, add billing address collection
        if request.product == "pe_reviewed":
            checkout_params["billing_address_collection"] = "required"
        
        checkout_session = stripe.checkout.Session.create(**checkout_params)
        
        # Store session with report data
        payment_sessions[checkout_session.id] = {
            "status": "pending",
            "product": request.product,
            "email": request.email,
            "customer_name": request.customer_name,
            "customer_notes": request.customer_notes,
            "report_data": request.report_data,
            "created_at": time.time(),
        }
        
        return CheckoutResponse(
            checkout_url=checkout_session.url,
            session_id=checkout_session.id
        )
        
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """Handle Stripe webhook events"""
    if not STRIPE_WEBHOOK_SECRET:
        payload = await request.json()
        event = stripe.Event.construct_from(payload, stripe.api_key)
    else:
        payload = await request.body()
        try:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")
    
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session["id"]
        
        # Update payment status
        if session_id in payment_sessions:
            payment_sessions[session_id]["status"] = "completed"
            payment_sessions[session_id]["customer_email"] = session.get("customer_email")
            
            # If PE-reviewed, send notification
            session_data = payment_sessions[session_id]
            if session_data.get("product") == "pe_reviewed":
                report_data = session_data.get("report_data", {})
                device_tag = report_data.get("device_info", {}).get("tag", "Unknown")
                
                send_pe_review_notification(
                    customer_email=session.get("customer_email"),
                    device_tag=device_tag,
                    customer_name=session_data.get("customer_name"),
                    customer_notes=session_data.get("customer_notes"),
                    report_data=report_data,
                )
        else:
            payment_sessions[session_id] = {
                "status": "completed",
                "product": session.get("metadata", {}).get("product", "standard_report"),
                "email": session.get("customer_email"),
                "created_at": time.time(),
            }
        
        print(f"Payment completed for session: {session_id}")
        
    elif event["type"] == "checkout.session.expired":
        session = event["data"]["object"]
        session_id = session["id"]
        if session_id in payment_sessions:
            payment_sessions[session_id]["status"] = "expired"
    
    return {"status": "ok"}


@app.get("/verify-payment/{session_id}")
async def verify_payment(session_id: str):
    """Verify if a payment session has been completed"""
    if session_id in payment_sessions:
        session_data = payment_sessions[session_id]
        return {
            "valid": session_data["status"] == "completed",
            "status": session_data["status"],
            "product": session_data.get("product"),
            "report_data": session_data.get("report_data"),
        }
    
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        is_paid = session.payment_status == "paid"
        
        payment_sessions[session_id] = {
            "status": "completed" if is_paid else session.status,
            "product": session.metadata.get("product", "standard_report"),
            "email": session.customer_email,
            "created_at": time.time(),
        }
        
        return {
            "valid": is_paid,
            "status": session.payment_status,
            "product": session.metadata.get("product"),
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/payment-status")
async def payment_status():
    """Check if Stripe is configured"""
    return {
        "stripe_configured": bool(stripe.api_key),
        "products": PRODUCTS if stripe.api_key else {},
    }


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
