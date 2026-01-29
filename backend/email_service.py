"""
Email Service for PSV Calculator
Sends PDF reports to customers using SMTP
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Optional
from datetime import datetime


# Email configuration from environment variables
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "reports@franceng.com")
FROM_NAME = os.getenv("FROM_NAME", "Franc Engineering")


def send_report_email(
    to_email: str,
    pdf_bytes: bytes,
    device_tag: str,
    report_type: str = "standard",
    customer_name: Optional[str] = None,
    is_admin_copy: bool = False,
    customer_email: Optional[str] = None,
) -> bool:
    """
    Send a PSV report via email
    
    Args:
        to_email: Recipient email address
        pdf_bytes: PDF report as bytes
        device_tag: PSV tag for the filename
        report_type: 'standard', 'pe_reviewed', or display name like 'Professional Report'
        customer_name: Optional customer name for personalization
        is_admin_copy: If True, this is an admin notification copy
        customer_email: Customer's email (used in admin copy)
        
    Returns:
        True if email sent successfully, False otherwise
    """
    
    if not SMTP_USER or not SMTP_PASSWORD:
        print("Warning: Email not configured. Set SMTP_USER and SMTP_PASSWORD environment variables.")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg['To'] = to_email
        
        # Different subject/body for admin copy vs customer
        if is_admin_copy:
            msg['Subject'] = f"[SALE] {report_type} - {device_tag}"
            body = f"""
NEW REPORT SALE

Report Details:
- Device Tag: {device_tag}
- Report Type: {report_type}
- Customer Email: {customer_email or 'Not provided'}
- Date: {datetime.now().strftime('%B %d, %Y %I:%M %p')}

The customer's report is attached.

---
Automated notification from PSV Calculator
"""
        else:
            msg['Subject'] = f"Your PSV Sizing Report - {device_tag}"
            greeting = f"Dear {customer_name}," if customer_name else "Hello,"
            
            is_pe_reviewed = "pe" in report_type.lower() or "reviewed" in report_type.lower()
            
            if is_pe_reviewed:
                body = f"""
{greeting}

Thank you for purchasing a PE-Reviewed PSV Sizing Report from Franc Engineering.

Your report for {device_tag} is attached to this email. This report has been reviewed and stamped by a licensed Professional Engineer (PE) in Texas and Colorado.

Report Details:
- Device Tag: {device_tag}
- Report Type: PE-Reviewed Report
- Date Generated: {datetime.now().strftime('%B %d, %Y')}

If you have any questions about this report or need additional engineering services, please don't hesitate to contact us.

Best regards,
Franc Engineering
https://franceng.com
info@franceng.com

---
This report is provided for professional use. Please review all inputs and verify results are appropriate for your specific application.
"""
            else:
                body = f"""
{greeting}

Thank you for purchasing a PSV Sizing Report from Franc Engineering!

Your report for {device_tag} is attached to this email.

Report Details:
- Device Tag: {device_tag}
- Report Type: Professional Report
- Date Generated: {datetime.now().strftime('%B %d, %Y')}

If you have any questions or need a PE-stamped report, please contact us.

Best regards,
Franc Engineering
https://franceng.com
info@franceng.com

---
This report is for screening purposes. Final PSV sizing should be verified by a qualified engineer.
"""

        msg.attach(MIMEText(body, 'plain'))
        
        # Attach PDF
        filename = f"{device_tag}_Deliverable_{datetime.now().strftime('%Y%m%d')}.pdf"
        pdf_attachment = MIMEApplication(pdf_bytes, _subtype='pdf')
        pdf_attachment.add_header('Content-Disposition', 'attachment', filename=filename)
        msg.attach(pdf_attachment)
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"Report email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

Questions? Contact us at info@franceng.com

Best regards,
Franc Engineering
https://franceng.com
"""

        msg.attach(MIMEText(body, 'plain'))
        
        # Attach PDF
        filename = f"PSV_Report_{device_tag}_{datetime.now().strftime('%Y%m%d')}.pdf"
        pdf_attachment = MIMEApplication(pdf_bytes, _subtype='pdf')
        pdf_attachment.add_header('Content-Disposition', 'attachment', filename=filename)
        msg.attach(pdf_attachment)
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"Report email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def send_pe_review_notification(
    customer_email: str,
    device_tag: str,
    customer_name: Optional[str] = None,
    customer_notes: Optional[str] = None,
    report_data: Optional[dict] = None,
) -> bool:
    """
    Send notification to Franc Engineering about a PE review request
    
    Args:
        customer_email: Customer's email address
        device_tag: PSV device tag
        customer_name: Customer's name
        customer_notes: Any notes from the customer
        report_data: The full report data for review
        
    Returns:
        True if notification sent successfully
    """
    
    if not SMTP_USER or not SMTP_PASSWORD:
        print("Warning: Email not configured.")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg['To'] = "info@franceng.com"  # Your notification email
        msg['Subject'] = f"🔔 New PE Review Request - {device_tag}"
        
        body = f"""
NEW PE-REVIEWED REPORT REQUEST

Customer Information:
- Email: {customer_email}
- Name: {customer_name or 'Not provided'}
- Device Tag: {device_tag}
- Date: {datetime.now().strftime('%B %d, %Y %I:%M %p')}

Customer Notes:
{customer_notes or 'None provided'}

Report Data Summary:
{_format_report_summary(report_data) if report_data else 'See attached'}

Action Required:
1. Review the calculation inputs and results
2. Generate PE-stamped report
3. Send to customer within 48-72 hours

---
This is an automated notification from the PSV Calculator system.
"""
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send notification
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"PE review notification sent for {device_tag}")
        return True
        
    except Exception as e:
        print(f"Error sending notification: {e}")
        return False


def _format_report_summary(report_data: dict) -> str:
    """Format report data as a readable summary"""
    if not report_data:
        return "No data available"
    
    lines = []
    
    device = report_data.get('device_info', {})
    if device:
        lines.append(f"Device: {device.get('tag', 'N/A')}")
        lines.append(f"Facility: {device.get('facility_name', 'N/A')}")
        lines.append(f"Set Pressure: {device.get('set_pressure_psig', 'N/A')} psig")
    
    results = report_data.get('calculation_results', {})
    if results:
        lines.append(f"Scenario: {results.get('scenario', 'N/A')}")
        lines.append(f"Required Area: {results.get('required_area_in2', 'N/A')} in²")
        lines.append(f"Selected Orifice: {results.get('selected_orifice', 'N/A')}")
        lines.append(f"Utilization: {results.get('percent_utilization', 'N/A')}%")
    
    return '\n'.join(lines) if lines else "No summary available"
