import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import os
from datetime import datetime


class EmailInput(BaseModel):
    recipient: str = Field(description="The email address of the recipient")
    subject: str = Field(description="The subject line of the email")
    body: str = Field(description="The body content of the email")


class EmailTool(BaseTool):
    name: str = "send_email"
    description: str = "Sends a professionally formatted HTML email"
    args_schema: Type[BaseModel] = EmailInput

    def _run(self, recipient: str, subject: str, body: str) -> str:
        try:
            sender_email = os.getenv("EMAIL_ADDRESS")
            sender_password = os.getenv("EMAIL_PASSWORD")
            
            if not sender_email or not sender_password:
                return "Error: EMAIL_ADDRESS and EMAIL_PASSWORD must be set in .env file"
            
            html_body = self._format_as_html(body)
            
            msg = MIMEMultipart('alternative')
            msg['From'] = sender_email
            msg['To'] = recipient
            msg['Subject'] = subject
            
            part1 = MIMEText(body, 'plain')
            part2 = MIMEText(html_body, 'html')
            
            msg.attach(part1)
            msg.attach(part2)
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            server.quit()
            
            return f"Email sent successfully to {recipient}"
            
        except Exception as e:
            return f"Failed to send email: {str(e)}"

    def _build_table(self, rows):
        """Build a mobile-friendly HTML table from rows"""
        if not rows:
            return ''
        
        header_row = rows[0] if rows else []
        
        html = '<div style="overflow-x:auto;margin:12px 0;border-radius:6px;border:1px solid #e2e8f0;">'
        html += '<table style="width:100%;border-collapse:collapse;font-size:14px;min-width:280px;">'
        
        if header_row:
            html += '<thead><tr style="background-color:#f1f5f9;border-bottom:2px solid #2563eb;">'
            for cell in header_row:
                html += f'<th style="padding:8px 10px;text-align:left;font-weight:600;color:#1e293b;font-size:13px;">{cell}</th>'
            html += '</tr></thead>'
            rows = rows[1:]
        
        if rows:
            html += '<tbody>'
            for i, row in enumerate(rows):
                bg_color = '#f8fafc' if i % 2 == 0 else '#ffffff'
                html += f'<tr style="border-bottom:1px solid #e2e8f0;background-color:{bg_color};">'
                for j, cell in enumerate(row):
                    style = 'padding:6px 10px;text-align:left;color:#334155;font-size:13px;'
                    if j == 0:
                        style += 'font-weight:500;'
                    html += f'<td style="{style}">{cell}</td>'
                html += '</tr>'
            html += '</tbody>'
        
        html += '</table></div>'
        return html

    def _format_as_html(self, body: str) -> str:
        lines = body.split('\n')
        html_lines = []
        in_table = False
        table_rows = []
        
        for line in lines:
            line_stripped = line.strip()
            
            if not line_stripped:
                if in_table and table_rows:
                    html_lines.append(self._build_table(table_rows))
                    table_rows = []
                    in_table = False
                html_lines.append('<br>')
                continue
            
            if line_stripped.startswith('# '):
                if in_table and table_rows:
                    html_lines.append(self._build_table(table_rows))
                    table_rows = []
                    in_table = False
                html_lines.append(f'<h1 style="color:#0f172a;font-size:24px;margin:20px 0 10px 0;border-bottom:2px solid #2563eb;padding-bottom:8px;">{line_stripped[2:]}</h1>')
            elif line_stripped.startswith('## '):
                if in_table and table_rows:
                    html_lines.append(self._build_table(table_rows))
                    table_rows = []
                    in_table = False
                html_lines.append(f'<h2 style="color:#1e293b;font-size:20px;margin:16px 0 8px 0;">{line_stripped[3:]}</h2>')
            elif line_stripped.startswith('### '):
                if in_table and table_rows:
                    html_lines.append(self._build_table(table_rows))
                    table_rows = []
                    in_table = False
                html_lines.append(f'<h3 style="color:#334155;font-size:17px;margin:12px 0 6px 0;">{line_stripped[4:]}</h3>')
            
            elif '|' in line_stripped:
                if '---' in line_stripped and '|' in line_stripped:
                    continue
                cells = [c.strip() for c in line_stripped.split('|') if c.strip()]
                if cells:
                    if not in_table:
                        in_table = True
                        table_rows = []
                    table_rows.append(cells)
            
            elif line_stripped.startswith('**') and line_stripped.endswith('**'):
                if in_table and table_rows:
                    html_lines.append(self._build_table(table_rows))
                    table_rows = []
                    in_table = False
                html_lines.append(f'<p style="margin:6px 0;line-height:1.6;color:#1e293b;"><strong>{line_stripped[2:-2]}</strong></p>')
            
            elif line_stripped.startswith('- '):
                if in_table and table_rows:
                    html_lines.append(self._build_table(table_rows))
                    table_rows = []
                    in_table = False
                html_lines.append(f'<li style="margin:4px 0;padding-left:8px;">{line_stripped[2:]}</li>')
            
            else:
                if in_table and table_rows:
                    html_lines.append(self._build_table(table_rows))
                    table_rows = []
                    in_table = False
                html_lines.append(f'<p style="margin:6px 0;line-height:1.6;color:#334155;">{line_stripped}</p>')
        
        if in_table and table_rows:
            html_lines.append(self._build_table(table_rows))
        
        html_content = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Report</title>
</head>
<body style="font-family:-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif;background-color:#f8fafc;margin:0;padding:10px;">
    <div style="max-width:600px;margin:0 auto;background-color:#ffffff;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,0.08);padding:20px;">
        <div style="border-bottom:3px solid #2563eb;padding-bottom:12px;margin-bottom:16px;">
            <h1 style="color:#0f172a;font-size:20px;font-weight:700;margin:0;">AI Research Agent</h1>
            <p style="color:#64748b;font-size:12px;margin:2px 0 0 0;">Professional Research Report</p>
        </div>
        <div style="font-size:14px;line-height:1.6;color:#1e293b;">
            {''.join(html_lines)}
        </div>
        <div style="border-top:2px solid #f1f5f9;padding-top:12px;margin-top:16px;text-align:center;">
            <p style="color:#94a3b8;font-size:11px;margin:0;">Generated by AI Research Agent Pro</p>
            <p style="color:#94a3b8;font-size:11px;margin:2px 0 0 0;">© {datetime.now().year} All Rights Reserved</p>
        </div>
    </div>
</body>
</html>
'''
        return html_content