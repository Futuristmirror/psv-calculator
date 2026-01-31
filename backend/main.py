"""
PSV Calculator API - FastAPI Backend

REST API for PSV sizing calculations using Peng-Robinson EOS

Author: Franc Engineering
"""

import os
import stripe
import resend
import base64
import io
import tempfile
import uuid
from fastapi import FastAPI, HTTPException, Request, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import uvicorn
import hashlib
import time

from thermo_engine import get_properties, COMPONENTS, PRESETS
from psv_sizing import calculate_psv_size, wetted_area_horizontal_vessel, wetted_area_vertical_vessel

# Try to import PyPDF2 for PDF merging
try:
    from PyPDF2 import PdfMerger, PdfReader
    PDF_MERGE_AVAILABLE = True
except ImportError:
    PDF_MERGE_AVAILABLE = False

# Stripe Configuration
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Resend Email Configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
ADMIN_EMAIL = "caseym@franceng.com"
FROM_EMAIL = os.getenv("FROM_EMAIL", "reports@franceng.com")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# In-memory store for payment sessions (use Redis/DB in production)
# Maps session_id -> { status, email, created_at, product }
payment_sessions: Dict[str, Dict] = {}

# In-memory store for uploaded files (use cloud storage in production)
# Maps file_id -> { filename, content_base64, file_type, created_at }
uploaded_files: Dict[str, Dict] = {}

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


# Request/Response Models
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
    flow_rate: Optional[float] = Field(None, description="Flow rate for blocked outlet scenarios (lb/hr for vapor, gpm for liquid)")
    latent_heat_btu_lb: Optional[float] = Field(None, description="Latent heat for fire cases (BTU/lb)")


class ThermodynamicProperties(BaseModel):
    mw: float
    Z: float
    density_kg_m3: float
    gamma: float
    lfl_percent: Optional[float]
    ufl_percent: Optional[float]
    phase: str


class PSVSizingResult(BaseModel):
    scenario: str
    relief_rate: float
    relief_rate_units: str
    relieving_pressure_psia: float
    required_area_in2: float
    selected_orifice: str
    orifice_area_in2: float
    percent_utilization: float
    flow_type: Optional[str]
    heat_input_mmbtu_hr: Optional[float]
    wetted_area_ft2: Optional[float]
    fluid_properties: ThermodynamicProperties


# Endpoints
@app.get("/")
async def root():
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


@app.post("/properties")
async def calculate_properties(fluid: FluidInput) -> Dict:
    """Calculate thermodynamic properties for a fluid mixture"""
    try:
        # Convert to lists
        components = [c.name.lower() for c in fluid.components]
        mole_fractions = [c.mole_fraction for c in fluid.components]

        # Normalize mole fractions
        total = sum(mole_fractions)
        mole_fractions = [x / total for x in mole_fractions]

        # Convert units
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


@app.post("/size-psv")
async def size_psv(request: PSVSizingRequest) -> Dict:
    """Calculate PSV sizing for specified scenario"""
    try:
        # Get fluid properties
        components = [c.name.lower() for c in request.fluid.components]
        mole_fractions = [c.mole_fraction for c in request.fluid.components]

        # Normalize
        total = sum(mole_fractions)
        mole_fractions = [x / total for x in mole_fractions]

        # Convert units
        T_K = (request.fluid.temperature_F + 459.67) * 5/9
        P_Pa = (request.fluid.pressure_psig + 14.7) * 6894.76

        props = get_properties(components, mole_fractions, T_K, P_Pa)

        # Calculate wetted area if vessel provided
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
                "surface_area_ft2": wetted_area * 1.5,  # Approximate total
                "insulated": request.vessel.insulated,
                "F_env": 0.3 if request.vessel.insulated else 1.0
            }

        # Prepare fluid properties for sizing
        fluid_props = {
            "MW": props["mw"],
            "Z": props["Z"],
            "gamma": props["gamma"],
            "T_F": request.fluid.temperature_F,
            "latent_heat_btu_lb": request.latent_heat_btu_lb or 150,  # Default
            "specific_gravity": props["density"] / 1000  # Relative to water
        }

        # Calculate sizing
        result = calculate_psv_size(
            scenario=request.scenario,
            set_pressure_psig=request.set_pressure_psig,
            fluid_properties=fluid_props,
            vessel_properties=vessel_props if vessel_props else None,
            flow_rate=request.flow_rate,
            back_pressure_psig=request.back_pressure_psig
        )

        # Add fluid properties to result
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


# Stripe Payment Models
class CreateCheckoutRequest(BaseModel):
    product: str = Field(..., description="Product type: 'standard_report' or 'pe_reviewed'")
    email: Optional[str] = Field(None, description="Customer email for receipt")
    success_url: Optional[str] = Field(None, description="URL to redirect after successful payment")
    cancel_url: Optional[str] = Field(None, description="URL to redirect if payment cancelled")


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
        "description": "Full PDF calculation package with all inputs documented. Additionally, engineer certified report with PE (TX/CO) review in 48-72hr.",
        "price_cents": 29900,  # $299.00
    }
}


@app.post("/create-checkout-session")
async def create_checkout_session(request: CreateCheckoutRequest):
    """Create a Stripe Checkout session for payment"""
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured. Set STRIPE_SECRET_KEY environment variable.")

    product = PRODUCTS.get(request.product)
    if not product:
        raise HTTPException(status_code=400, detail=f"Invalid product. Choose from: {list(PRODUCTS.keys())}")

    try:
        # Build success/cancel URLs
        success_url = request.success_url or f"{FRONTEND_URL}?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = request.cancel_url or f"{FRONTEND_URL}?payment=cancelled"

        # Create Stripe Checkout Session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
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
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.email,
            metadata={
                "product": request.product,
            }
        )

        # Store session for verification
        payment_sessions[checkout_session.id] = {
            "status": "pending",
            "product": request.product,
            "email": request.email,
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
        # In development, accept all webhooks
        payload = await request.json()
        event = stripe.Event.construct_from(payload, stripe.api_key)
    else:
        # In production, verify webhook signature
        payload = await request.body()
        try:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session["id"]

        # Update payment status
        if session_id in payment_sessions:
            payment_sessions[session_id]["status"] = "completed"
            payment_sessions[session_id]["customer_email"] = session.get("customer_email")
        else:
            # Session wasn't tracked, add it now
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
    # First check our local cache
    if session_id in payment_sessions:
        session_data = payment_sessions[session_id]
        return {
            "valid": session_data["status"] == "completed",
            "status": session_data["status"],
            "product": session_data.get("product"),
            "email": session_data.get("email") or session_data.get("customer_email"),
        }

    # If not in cache, check with Stripe directly
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        is_paid = session.payment_status == "paid"

        # Cache the result
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
            "email": session.customer_email,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/payment-status")
async def payment_status():
    """Check if Stripe is configured (for frontend to know if payments are enabled)"""
    return {
        "stripe_configured": bool(stripe.api_key),
        "products": PRODUCTS if stripe.api_key else {},
    }


# ============ Report Generation & Email Endpoints ============

class GenerateReportRequest(BaseModel):
    email: str = Field(..., description="Customer email for report delivery")
    session_id: Optional[str] = Field(None, description="Stripe session ID for paid reports")
    report_pdf_base64: str = Field(..., description="Base64 encoded PDF report")
    device_tag: Optional[str] = Field("PSV", description="Device tag for filename")
    pid_file_id: Optional[str] = Field(None, description="ID of uploaded P&ID file")
    misc_file_id: Optional[str] = Field(None, description="ID of uploaded Misc file")


@app.post("/upload-file")
async def upload_file(
    file: UploadFile = File(...),
    file_type: str = Form(...)
):
    """Upload a file (P&ID or Misc) for report attachment"""
    try:
        content = await file.read()
        file_id = str(uuid.uuid4())

        uploaded_files[file_id] = {
            "filename": file.filename,
            "content": content,
            "content_type": file.content_type,
            "file_type": file_type,
            "created_at": time.time()
        }

        # Clean up old files (older than 1 hour)
        current_time = time.time()
        old_files = [fid for fid, fdata in uploaded_files.items()
                     if current_time - fdata["created_at"] > 3600]
        for fid in old_files:
            del uploaded_files[fid]

        return {"file_id": file_id, "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/check-free-report")
async def check_free_report(email: str):
    """Check if an email can still generate a free report"""
    # For now, always allow - tracking is done client-side via localStorage
    # In production, you'd check a database
    return {"can_generate_free": True, "email": email}


def merge_pdfs(main_pdf_bytes: bytes, pid_file_id: Optional[str], misc_file_id: Optional[str]) -> bytes:
    """Merge the main PDF with P&ID and Misc PDFs if available"""
    if not PDF_MERGE_AVAILABLE:
        return main_pdf_bytes

    merger = PdfMerger()

    # Add main report
    merger.append(io.BytesIO(main_pdf_bytes))

    # Add P&ID if it's a PDF
    if pid_file_id and pid_file_id in uploaded_files:
        pid_data = uploaded_files[pid_file_id]
        if pid_data.get("content_type") == "application/pdf":
            try:
                merger.append(io.BytesIO(pid_data["content"]))
            except Exception as e:
                print(f"Could not merge P&ID PDF: {e}")

    # Add Misc file if it's a PDF
    if misc_file_id and misc_file_id in uploaded_files:
        misc_data = uploaded_files[misc_file_id]
        if misc_data.get("content_type") == "application/pdf":
            try:
                merger.append(io.BytesIO(misc_data["content"]))
            except Exception as e:
                print(f"Could not merge Misc PDF: {e}")

    # Write merged PDF to bytes
    output = io.BytesIO()
    merger.write(output)
    merger.close()
    output.seek(0)

    return output.read()


def send_report_email(customer_email: str, report_bytes: bytes, device_tag: str,
                      pid_file_id: Optional[str] = None, misc_file_id: Optional[str] = None):
    """Send the report via email to customer and admin"""
    if not RESEND_API_KEY:
        print("Resend API key not configured, skipping email")
        return False

    filename = f"{device_tag}_PSV_Report_{time.strftime('%Y-%m-%d')}.pdf"

    # Build attachments list
    attachments = [
        {
            "filename": filename,
            "content": base64.b64encode(report_bytes).decode('utf-8'),
            "content_type": "application/pdf"
        }
    ]

    # Add P&ID attachment if it's not a PDF (PDFs are merged into main report)
    if pid_file_id and pid_file_id in uploaded_files:
        pid_data = uploaded_files[pid_file_id]
        if pid_data.get("content_type") != "application/pdf":
            attachments.append({
                "filename": f"PID_{pid_data['filename']}",
                "content": base64.b64encode(pid_data["content"]).decode('utf-8'),
                "content_type": pid_data.get("content_type", "application/octet-stream")
            })

    # Add Misc attachment if it's not a PDF (PDFs are merged into main report)
    if misc_file_id and misc_file_id in uploaded_files:
        misc_data = uploaded_files[misc_file_id]
        if misc_data.get("content_type") != "application/pdf":
            attachments.append({
                "filename": f"Misc_{misc_data['filename']}",
                "content": base64.b64encode(misc_data["content"]).decode('utf-8'),
                "content_type": misc_data.get("content_type", "application/octet-stream")
            })

    # Send to both customer and admin
    recipients = [customer_email]
    if ADMIN_EMAIL and ADMIN_EMAIL != customer_email:
        recipients.append(ADMIN_EMAIL)

    try:
        params = {
            "from": f"Franc Engineering <{FROM_EMAIL}>",
            "to": recipients,
            "subject": f"PSV Sizing Report - {device_tag}",
            "html": f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <div style="background-color: #1e40af; padding: 20px; text-align: center;">
                        <h1 style="color: white; margin: 0;">Franc Engineering</h1>
                    </div>
                    <div style="padding: 30px; background-color: #f8f9fa;">
                        <h2 style="color: #1e40af;">Your PSV Sizing Report</h2>
                        <p>Thank you for using the Franc Engineering PSV Calculator!</p>
                        <p>Your PSV sizing report for <strong>{device_tag}</strong> is attached to this email.</p>
                        <div style="background-color: #e8f4f8; padding: 15px; border-radius: 8px; margin: 20px 0;">
                            <p style="margin: 0;"><strong>Report Details:</strong></p>
                            <ul style="margin: 10px 0;">
                                <li>Device Tag: {device_tag}</li>
                                <li>Generated: {time.strftime('%Y-%m-%d %H:%M UTC')}</li>
                            </ul>
                        </div>
                        <p>If you have any questions about your report or need engineering services, please contact us.</p>
                        <p style="margin-top: 30px;">
                            Best regards,<br>
                            <strong>Franc Engineering Team</strong>
                        </p>
                    </div>
                    <div style="background-color: #1e40af; padding: 15px; text-align: center;">
                        <p style="color: white; margin: 0; font-size: 12px;">
                            <a href="https://franceng.com" style="color: #93c5fd;">franceng.com</a> |
                            <a href="mailto:caseym@franceng.com" style="color: #93c5fd;">caseym@franceng.com</a>
                        </p>
                    </div>
                </div>
            """,
            "attachments": attachments
        }

        response = resend.Emails.send(params)
        print(f"Email sent successfully: {response}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


@app.post("/generate-report")
async def generate_report(request: GenerateReportRequest):
    """Generate merged PDF report and send via email"""
    try:
        # Decode the base64 PDF
        try:
            main_pdf_bytes = base64.b64decode(request.report_pdf_base64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid PDF data: {str(e)}")

        # Merge PDFs if there are attachments
        merged_pdf = merge_pdfs(
            main_pdf_bytes,
            request.pid_file_id,
            request.misc_file_id
        )

        # Send email
        email_sent = send_report_email(
            customer_email=request.email,
            report_bytes=merged_pdf,
            device_tag=request.device_tag or "PSV",
            pid_file_id=request.pid_file_id,
            misc_file_id=request.misc_file_id
        )

        # Clean up uploaded files
        for file_id in [request.pid_file_id, request.misc_file_id]:
            if file_id and file_id in uploaded_files:
                del uploaded_files[file_id]

        # Return the merged PDF
        filename = f"{request.device_tag or 'PSV'}_PSV_Report_{time.strftime('%Y-%m-%d')}.pdf"
        return Response(
            content=merged_pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Email-Sent": str(email_sent).lower()
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "email_configured": bool(RESEND_API_KEY),
        "pdf_merge_available": PDF_MERGE_AVAILABLE
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
