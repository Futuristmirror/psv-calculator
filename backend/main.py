# Force redeploy v4
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
        "name": "PSV Calculator - Professional Report",
        "description": "Full PDF calculation package with all inputs documented",
        "price_cents": 9900,  # $99.00
    },
    "pe_reviewed": {
        "name": "PSV Calculator - PE-Reviewed Report", 
        "description": "Engineer certified report with PE (TX/CO) review, 48-72hr delivery",
        "price_cents": 49900,  # $299.00
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
# PDF MERGE - Takes frontend-generated PDF and appends uploaded attachments
# ============================================================================

@app.post("/merge-pdfs")
async def merge_pdfs_endpoint(
    main_pdf: UploadFile = File(..., description="The main PDF report generated by frontend"),
    pid_file_id: Optional[str] = Form(None, description="File ID of uploaded P&ID"),
    misc_file_id: Optional[str] = Form(None, description="File ID of uploaded misc document"),
    device_tag: Optional[str] = Form("PSV", description="Device tag for filename"),
    email: Optional[str] = Form(None, description="Customer email"),
):
    """
    Merge the frontend-generated PDF with uploaded attachments.
    
    This endpoint:
    1. Takes the PDF generated by the frontend (jsPDF)
    2. Appends any uploaded P&ID and misc documents
    3. Returns the combined PDF
    
    First report per user is FREE, subsequent reports require payment.
    """
    from pypdf import PdfReader, PdfWriter
    
    # Check free report eligibility
    user_identifier = email or "anonymous"
    has_used_free = free_report_users.get(user_identifier, False)
    
    try:
        # Read the main PDF from frontend
        main_pdf_content = await main_pdf.read()
        
        # Create PDF writer
        writer = PdfWriter()
        
        # Add main report pages
        main_reader = PdfReader(io.BytesIO(main_pdf_content))
        for page in main_reader.pages:
            writer.add_page(page)
        
        # Add P&ID attachment if provided
        if pid_file_id and pid_file_id in uploaded_files:
            try:
                pid_reader = PdfReader(io.BytesIO(uploaded_files[pid_file_id]))
                for page in pid_reader.pages:
                    writer.add_page(page)
            except Exception as e:
                print(f"Warning: Could not add P&ID attachment: {e}")
        
        # Add misc attachment if provided  
        if misc_file_id and misc_file_id in uploaded_files:
            try:
                misc_reader = PdfReader(io.BytesIO(uploaded_files[misc_file_id]))
                for page in misc_reader.pages:
                    writer.add_page(page)
            except Exception as e:
                print(f"Warning: Could not add misc attachment: {e}")
        
        # Write merged PDF
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        merged_pdf = output.getvalue()
        
        # Mark free report as used
        if not has_used_free and email:
            free_report_users[user_identifier] = True
        
        # Send email if provided
        if email:
            try:
                send_report_email(
                    to_email=email,
                    pdf_bytes=merged_pdf,
                    device_tag=device_tag,
                    report_type="standard",
                )
            except Exception as email_error:
                print(f"Warning: Could not send email: {email_error}")
        
        # Return merged PDF
        return StreamingResponse(
            io.BytesIO(merged_pdf),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=PSV_Report_{device_tag}.pdf"
            }
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error merging PDFs: {str(e)}")


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
        
        if request.product == "pe_reviewed":
            checkout_params["billing_address_collection"] = "required"
        
        checkout_session = stripe.checkout.Session.create(**checkout_params)
        
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
        
        if session_id in payment_sessions:
            payment_sessions[session_id]["status"] = "completed"
            payment_sessions[session_id]["customer_email"] = session.get("customer_email")
            
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
