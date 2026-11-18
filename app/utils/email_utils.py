import urllib.parse
from datetime import datetime

import pytz
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from loguru import logger

from app.core.config import settings
from app.schemas.demo import DemoBookingCreate
from app.schemas.realty import ContactCreate


class EmailService:
    def __init__(self):
        self.conf = ConnectionConfig(
            MAIL_USERNAME=settings.MAIL_USERNAME,
            MAIL_PASSWORD=settings.MAIL_PASSWORD,
            MAIL_FROM=settings.MAIL_FROM,
            MAIL_PORT=settings.MAIL_PORT,
            MAIL_SERVER=settings.MAIL_SERVER,
            MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
            MAIL_STARTTLS=False,
            MAIL_SSL_TLS=True,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True,
        )

    def _format_datetime_ist(self, dt: datetime) -> tuple[str, str]:
        """Formats a datetime object to IST and returns (date_str, time_str)"""
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        ist_tz = pytz.timezone("Asia/Kolkata")
        dt_ist = dt.astimezone(ist_tz)

        date_str = dt_ist.strftime("%d %B %Y")
        time_str = dt_ist.strftime("%I:%M %p IST")
        return date_str, time_str

    def _generate_google_calendar_link(
        self,
        title: str,
        start_dt: datetime,
        end_dt: datetime,
        details: str,
        location: str,
    ) -> str:
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
            "location": location,
        }
        return base_url + "&" + urllib.parse.urlencode(params)

    def _generate_outlook_calendar_link(
        self,
        title: str,
        start_dt: datetime,
        end_dt: datetime,
        details: str,
        location: str,
    ) -> str:
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
            "location": location,
        }
        return base_url + "?" + urllib.parse.urlencode(params)

    async def send_booking_confirmation(
        self, booking_data: DemoBookingCreate, meet_link: str
    ):
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

        gcal_link = self._generate_google_calendar_link(
            cal_title, start_time, end_time, cal_details, meet_link
        )
        outlook_link = self._generate_outlook_calendar_link(
            cal_title, start_time, end_time, cal_details, meet_link
        )

        # 1. Email to User
        user_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f5f7; margin: 0; padding: 0; color: #333333; }}
                .container {{ max-width: 600px; margin: 30px auto; background-color: #ffffff; border: 1px solid #e5e7eb; border-top: 4px solid #ef4444; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
                .header {{ padding: 20px 30px; border-bottom: 1px solid #f0f0f0; }}
                .brand-logo {{ font-size: 18px; font-weight: bold; color: #111827; margin: 0; letter-spacing: -0.5px; }}
                .content {{ padding: 30px; line-height: 1.6; font-size: 14px; color: #4b5563; }}
                .greeting {{ font-size: 16px; color: #111827; margin-top: 0; margin-bottom: 15px; }}
                h2.title {{ font-size: 20px; color: #111827; margin-top: 0; margin-bottom: 25px; font-weight: 500; }}
                
                .meeting-box {{ background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 20px; margin-bottom: 25px; }}
                .meeting-table {{ width: 100%; border-collapse: collapse; }}
                .meeting-table td {{ padding: 8px 0; vertical-align: top; font-size: 14px; }}
                .label-cell {{ width: 100px; color: #6b7280; font-weight: 500; }}
                .value-cell {{ color: #111827; font-weight: 500; }}
                
                .btn-primary {{ display: inline-block; background-color: #ef4444; color: #ffffff !important; text-decoration: none; padding: 10px 24px; border-radius: 4px; font-weight: bold; font-size: 14px; margin-top: 15px; border: 1px solid #dc2626; }}
                .btn-secondary {{ display: inline-block; background-color: #ffffff; color: #4b5563 !important; text-decoration: none; padding: 8px 16px; border-radius: 4px; font-weight: 500; font-size: 13px; margin-top: 10px; margin-right: 10px; border: 1px solid #d1d5db; }}
                
                .agenda-section {{ margin-top: 25px; }}
                .agenda-title {{ font-weight: bold; color: #374151; margin-bottom: 10px; font-size: 14px; }}
                .agenda-list {{ margin: 0; padding-left: 20px; color: #4b5563; }}
                .agenda-list li {{ margin-bottom: 5px; }}
                
                .footer {{ background-color: #f9fafb; padding: 20px 30px; border-top: 1px solid #e5e7eb; text-align: center; color: #6b7280; font-size: 12px; border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; }}
                .footer a {{ color: #ef4444; text-decoration: none; }}
                .footer p {{ margin: 5px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <p class="brand-logo">MakeMyStay.ai</p>
                </div>
                
                <div class="content">
                    <h2 class="title">Demo Meeting Confirmed</h2>
                    <p class="greeting">Hello {booking_data.name.split(' ')[0]},</p>
                    <p style="margin-bottom: 25px;">Your requested product demo has been successfully scheduled. Please find the meeting details below.</p>
                    
                    <div class="meeting-box">
                        <table class="meeting-table">
                            <tr>
                                <td class="label-cell">Date:</td>
                                <td class="value-cell">{date_str}</td>
                            </tr>
                            <tr>
                                <td class="label-cell">Time:</td>
                                <td class="value-cell">{time_str}</td>
                            </tr>
                            <tr>
                                <td class="label-cell">Host:</td>
                                <td class="value-cell">MakeMyStay.ai Growth Team</td>
                            </tr>
                        </table>
                        
                        <a href="{meet_link}" class="btn-primary">Join Meeting</a>
                        
                        <div style="margin-top: 20px; border-top: 1px solid #e5e7eb; padding-top: 15px;">
                            <span style="font-size: 13px; color: #6b7280; display: block; margin-bottom: 5px;">Save to calendar:</span>
                            <a href="{gcal_link}" class="btn-secondary">Google Calendar</a>
                            <a href="{outlook_link}" class="btn-secondary">Outlook Calendar</a>
                        </div>
                    </div>
                    
                    <div class="agenda-section">
                        <p class="agenda-title">Agenda:</p>
                        <ul class="agenda-list">
                            <li>Platform overview and feature walkthrough.</li>
                            <li>Automating your booking and tenant management workflows.</li>
                            <li>Effective strategies for reducing broker dependency.</li>
                            <li>Q&A session.</li>
                        </ul>
                    </div>
                    
                    <p style="margin-top: 25px; color: #6b7280; font-size: 13px;">If you need to cancel or propose a new time, please reply to this email.</p>
                </div>
                
                <div class="footer">
                    <p>This is an automated message from MakeMyStay.ai. For assistance, contact <a href="mailto:connect@makemystay.ai">connect@makemystay.ai</a>.</p>
                    <p>&copy; {datetime.now().year} MakeMyStay.ai. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        user_message = MessageSchema(
            subject=f"Your MakeMyStay Demo is Confirmed – {date_str} at {dt_mod.datetime.strptime(time_str, '%I:%M %p IST').strftime('%I %p')}",
            recipients=[booking_data.email],
            body=user_html,
            subtype=MessageType.html,
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
            recipients=[settings.MAIL_FROM],  # Sending to company email
            body=admin_html,
            subtype=MessageType.html,
        )

        fm = FastMail(self.conf)

        try:
            await fm.send_message(user_message)
            logger.info(f"Confirmation email sent to {booking_data.email}")
            await fm.send_message(admin_message)
            logger.info(f"Admin notification sent for {booking_data.name}")
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")

    async def send_contact_notification(self, contact_data: ContactCreate):
        """Send notification to admin when someone contacts through the website."""

        # Email to Admin
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
                .message-box {{ margin-top: 15px; padding: 15px; background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>📨 New Website Contact</h2>
                </div>
                
                <div class="data-row"><span class="label">Name:</span> <span class="value">{contact_data.name_}</span></div>
                <div class="data-row"><span class="label">Email:</span> <span class="value"><a href="mailto:{contact_data.email}">{contact_data.email}</a></span></div>
                <div class="data-row"><span class="label">Phone:</span> <span class="value">{contact_data.phone}</span></div>
                <div class="data-row"><span class="label">Location:</span> <span class="value">{contact_data.location or 'N/A'}</span></div>
                <div class="data-row"><span class="label">Property Type:</span> <span class="value">{contact_data.property_type or 'N/A'}</span></div>
                
                <div class="data-row" style="margin-top: 20px;"><span class="label">Message:</span></div>
                <div class="message-box">
                    {contact_data.message}
                </div>
            </div>
        </body>
        </html>
        """

        admin_message = MessageSchema(
            subject=f"New Website Contact: {contact_data.name_}",
            recipients=[self.conf.MAIL_FROM],  # Sending to company email
            body=admin_html,
            subtype=MessageType.html,
        )

        fm = FastMail(self.conf)

        try:
            await fm.send_message(admin_message)
            logger.info(
                f"Admin notification sent for new contact: {contact_data.name_}"
            )
        except Exception as e:
            logger.error(f"Failed to send contact email: {str(e)}")


    async def send_sync_error_alert(self, source: str, error_msg: str):
        """Send urgent notification to admin if a high-priority sync job fails."""

        admin_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 20px auto; padding: 20px; border: 2px solid #ef4444; border-radius: 8px; }}
                .header {{ background-color: #fef2f2; padding: 10px; margin-bottom: 20px; text-align: center; border-radius: 4px; }}
                .header h2 {{ margin: 0; color: #991b1b; }}
                .content {{ font-size: 15px; }}
                .error-box {{ margin-top: 15px; padding: 15px; background-color: #fff1f2; border: 1px solid #fecdd3; border-radius: 6px; color: #9f1239; font-family: monospace; }}
                .footer {{ margin-top: 20px; font-size: 12px; color: #6b7280; border-top: 1px solid #e5e7eb; padding-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>⚠️ Critical Sync Failure: {source.title()}</h2>
                </div>
                
                <div class="content">
                    <p>The background lead sync job for <strong>{source}</strong> has encountered a failure and has been paused or is reporting errors.</p>
                    
                    <div class="error-box">
                        {error_msg}
                    </div>
                    
                    <p><strong>Action Required:</strong> Please check the server logs or the <code>sync_metadata</code> table for details. This could be due to an expired API key or a network issue.</p>
                </div>
                
                <div class="footer">
                    Sent automatically by MakeMyStay.ai Monitoring System.
                </div>
            </div>
        </body>
        </html>
        """

        message = MessageSchema(
            subject=f"🚨 ALERT: {source.title()} Sync Job Failed",
            recipients=[self.conf.MAIL_FROM],
            body=admin_html,
            subtype=MessageType.html,
        )

        fm = FastMail(self.conf)
        try:
            await fm.send_message(message)
            logger.warning(f"Sync error alert sent for {source}")
        except Exception as e:
            logger.error(f"Failed to send sync error alert: {str(e)}")


email_service = EmailService()
