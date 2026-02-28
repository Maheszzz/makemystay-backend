import os
import urllib.parse
from datetime import datetime
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from typing import List
from app.schemas.demo import DemoBookingCreate
from loguru import logger
import pytz
from dotenv import load_dotenv

# Ensure environment variables are loaded when this module is imported
load_dotenv()

class EmailService:
    def __init__(self):
        self.conf = ConnectionConfig(
            MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
            MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
            MAIL_FROM=os.getenv("MAIL_FROM"),
            MAIL_PORT=int(os.getenv("MAIL_PORT", 465)),
            MAIL_SERVER=os.getenv("MAIL_SERVER"),
            MAIL_FROM_NAME=os.getenv("MAIL_FROM_NAME"),
            MAIL_STARTTLS=False,
            MAIL_SSL_TLS=True,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True
        )

    def _format_datetime_ist(self, dt: datetime) -> tuple[str, str]:
        """Formats a datetime object to IST and returns (date_str, time_str)"""
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        ist_tz = pytz.timezone('Asia/Kolkata')
        dt_ist = dt.astimezone(ist_tz)
        
        date_str = dt_ist.strftime("%d %B %Y")
        time_str = dt_ist.strftime("%I:%M %p IST")
        return date_str, time_str

    def _generate_google_calendar_link(self, title: str, start_dt: datetime, end_dt: datetime, details: str, location: str) -> str:
        """Generates a Google Calendar event link"""
        # Google calendar expects UTC format with 'Z' appended
        if start_dt.tzinfo is None:
            start_dt = pytz.utc.localize(start_dt)
        if end_dt.tzinfo is None:
            end_dt = pytz.utc.localize(end_dt)
            
        start_utc = start_dt.astimezone(pytz.utc).strftime("%Y%m%dT%H%M%SZ")
        end_utc = end_dt.astimezone(pytz.utc).strftime("%Y%m%dT%H%M%SZ")
        
        base_url = "https://calendar.google.com/calendar/render?action=TEMPLATE"
        params = {
            "text": title,
            "dates": f"{start_utc}/{end_utc}",
            "details": details,
            "location": location
        }
        return base_url + "&" + urllib.parse.urlencode(params)
    
    def _generate_outlook_calendar_link(self, title: str, start_dt: datetime, end_dt: datetime, details: str, location: str) -> str:
        """Generates an Outlook Calendar event link"""
        if start_dt.tzinfo is None:
            start_dt = pytz.utc.localize(start_dt)
        if end_dt.tzinfo is None:
            end_dt = pytz.utc.localize(end_dt)
            
        start_utc = start_dt.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = end_dt.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        base_url = "https://outlook.live.com/calendar/0/deeplink/compose"
        params = {
            "path": "/calendar/action/compose",
            "rru": "addevent",
            "startdt": start_utc,
            "enddt": end_utc,
            "subject": title,
            "body": details,
            "location": location
        }
        return base_url + "?" + urllib.parse.urlencode(params)

    async def send_booking_confirmation(self, booking_data: DemoBookingCreate, meet_link: str):
        """Send confirmation email to the user and notification to admin."""
        
        # Format date and time
        start_time = booking_data.selected_slot
        # Assuming demo is 30 mins
        import datetime as dt_mod
        end_time = start_time + dt_mod.timedelta(minutes=30)
        
        date_str, time_str = self._format_datetime_ist(start_time)
        
        # Details for calendar
        cal_title = "MakeMyStay Platform Demo"
        cal_details = f"Demo session with the MakeMyStay team.\\n\\nName: {booking_data.name}\\nCompany: {booking_data.company}\\n\\nMeeting Link: {meet_link}"
        
        gcal_link = self._generate_google_calendar_link(cal_title, start_time, end_time, cal_details, meet_link)
        outlook_link = self._generate_outlook_calendar_link(cal_title, start_time, end_time, cal_details, meet_link)

        # 1. Email to User
        user_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #334155; margin: 0; padding: 0; background-color: #f8fafc; }}
                .container {{ max-width: 600px; margin: 40px auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); }}
                .header {{ background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 32px 40px; text-align: center; color: white; }}
                .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; letter-spacing: -0.025em; }}
                .header p {{ margin: 8px 0 0 0; font-size: 15px; opacity: 0.9; }}
                .content {{ padding: 40px; }}
                .greeting {{ font-size: 18px; font-weight: 600; color: #0f172a; margin-top: 0; }}
                .details-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; margin: 32px 0; }}
                .detail-row {{ display: flex; align-items: flex-start; margin-bottom: 16px; }}
                .detail-row:last-child {{ margin-bottom: 0; }}
                .detail-icon {{ font-size: 20px; margin-right: 12px; line-height: 1.2; }}
                .detail-text {{ margin: 0; font-size: 15px; color: #334155; }}
                .detail-label {{ display: block; font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }}
                .detail-value {{ font-size: 16px; font-weight: 500; color: #0f172a; }}
                .btn {{ display: inline-block; background: #ef4444; color: #ffffff !important; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600; font-size: 15px; text-align: center; margin-top: 8px; box-shadow: 0 4px 6px -1px rgba(239, 68, 68, 0.2); transition: all 0.2s; }}
                .btn:hover {{ background: #dc2626; }}
                .btn-secondary {{ display: inline-block; background: #ffffff; color: #475569 !important; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-weight: 500; font-size: 14px; text-align: center; border: 1px solid #cbd5e1; margin-right: 8px; margin-bottom: 8px; }}
                .calendar-section {{ margin-top: 24px; padding-top: 24px; border-top: 1px dashed #e2e8f0; }}
                .expectations {{ margin: 32px 0; }}
                .expectations h3 {{ font-size: 16px; color: #0f172a; margin-bottom: 16px; }}
                .expectations ul {{ padding-left: 20px; margin: 0; color: #475569; }}
                .expectations li {{ margin-bottom: 8px; font-size: 15px; }}
                .footer {{ background: #0f172a; color: #94a3b8; padding: 32px 40px; text-align: center; font-size: 14px; }}
                .footer h4 {{ color: white; margin: 0 0 8px 0; font-size: 16px; }}
                .footer p {{ margin: 0 0 16px 0; }}
                .footer-links {{ margin-top: 16px; padding-top: 16px; border-top: 1px solid #1e293b; }}
                .footer-links a {{ color: #e2e8f0; text-decoration: none; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>MakeMyStay.ai</h1>
                    <p>Demo Scheduled Successfully 🎉</p>
                </div>
                
                <div class="content">
                    <p class="greeting">Hi {booking_data.name},</p>
                    <p>Thank you for scheduling a demo with MakeMyStay. We're excited to show you how our platform can transform your rental business.</p>
                    
                    <div class="details-card">
                        <div class="detail-row">
                            <span class="detail-icon">📅</span>
                            <div class="detail-text">
                                <span class="detail-label">Date</span>
                                <span class="detail-value">{date_str}</span>
                            </div>
                        </div>
                        <div class="detail-row">
                            <span class="detail-icon">🕒</span>
                            <div class="detail-text">
                                <span class="detail-label">Time</span>
                                <span class="detail-value">{time_str} ({booking_data.selected_slot.strftime("%Z")} / UTC)</span>
                            </div>
                        </div>
                        <div style="margin-top: 24px; text-align: center;">
                            <a href="{meet_link}" class="btn">🎥 Join Google Meet</a>
                        </div>
                        
                        <div class="calendar-section">
                            <p style="font-size: 14px; font-weight: 500; color: #64748b; margin-top: 0; margin-bottom: 12px;">Add to your calendar:</p>
                            <a href="{gcal_link}" class="btn-secondary">🇬 Google Calendar</a>
                            <a href="{outlook_link}" class="btn-secondary">📧 Outlook</a>
                        </div>
                    </div>
                    
                    <div class="expectations">
                        <h3>In this demo, we'll show you:</h3>
                        <ul>
                            <li>How to automate entire booking workflows</li>
                            <li>Strategies to reduce broker dependency</li>
                            <li>Tools to increase occupancy and streamline operations</li>
                            <li>Our comprehensive revenue analytics dashboard</li>
                        </ul>
                    </div>
                    
                    <p>If you need to reschedule or have any questions beforehand, please reply directly to this email.</p>
                </div>
                
                <div class="footer">
                    <h4>Need help before the demo?</h4>
                    <p>💬 Contact Support: connect@makemystay.ai</p>
                    <div class="footer-links">
                        <p>© 2026 MakeMyStay.ai - Premium Rental Automation Platform</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        user_message = MessageSchema(
            subject=f"Your MakeMyStay Demo is Confirmed – {date_str} at {dt_mod.datetime.strptime(time_str, '%I:%M %p IST').strftime('%I %p')}",
            recipients=[booking_data.email],
            body=user_html,
            subtype=MessageType.html
        )

        # 2. Email to Admin (Internal notification - keeping it functional but clean)
        admin_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 20px auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 8px; }}
                .header {{ border-bottom: 2px solid #ef4444; padding-bottom: 10px; margin-bottom: 20px; }}
                .header h2 {{ margin: 0; color: #111827; }}
                .data-row {{ margin-bottom: 10px; }}
                .label {{ font-weight: 600; color: #4b5563; display: inline-block; width: 120px; }}
                .value {{ color: #111827; }}
                .meet-link {{ display: inline-block; margin-top: 20px; padding: 10px 20px; background-color: #f3f4f6; border: 1px solid #d1d5db; border-radius: 6px; text-decoration: none; color: #374151; font-weight: 500; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🚨 New Demo Scheduled</h2>
                </div>
                
                <div class="data-row"><span class="label">Name:</span> <span class="value">{booking_data.name}</span></div>
                <div class="data-row"><span class="label">Email:</span> <span class="value"><a href="mailto:{booking_data.email}">{booking_data.email}</a></span></div>
                <div class="data-row"><span class="label">Phone:</span> <span class="value">{booking_data.phone}</span></div>
                <div class="data-row"><span class="label">Company:</span> <span class="value">{booking_data.company or 'N/A'}</span></div>
                <div class="data-row"><span class="label">Units:</span> <span class="value">{booking_data.units or 'N/A'}</span></div>
                <div class="data-row"><span class="label">Date:</span> <span class="value">{date_str}</span></div>
                <div class="data-row"><span class="label">Time:</span> <span class="value">{time_str} ({booking_data.selected_slot.strftime("%Z")} / UTC)</span></div>
                
                <a href="{meet_link}" class="meet-link">Open Google Meet</a>
            </div>
        </body>
        </html>
        """

        admin_message = MessageSchema(
            subject=f"New Demo Booking: {booking_data.company or booking_data.name} - {date_str}",
            recipients=[os.getenv("MAIL_FROM")], # Sending to company email
            body=admin_html,
            subtype=MessageType.html
        )

        fm = FastMail(self.conf)
        
        try:
            await fm.send_message(user_message)
            logger.info(f"Confirmation email sent to {booking_data.email}")
            await fm.send_message(admin_message)
            logger.info(f"Admin notification sent for {booking_data.name}")
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")

email_service = EmailService()

