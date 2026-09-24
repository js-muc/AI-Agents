"""
Calendar Tool for CrewAI Agents
================================
This tool allows AI agents to create calendar events/schedule meetings.
It demonstrates the pattern of scheduling and can be extended to use
Google Calendar API or Outlook API.

Usage:
    agent uses "create_calendar_event" tool with:
    - summary: "Client Follow-up Meeting"
    - date: "2026-09-10"
    - time: "14:30"
    - duration: 60
    - attendees: "client@company.com, manager@company.com"
"""

from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import datetime
import os


class CalendarInput(BaseModel):
    """
    Input schema for the CalendarTool.
    
    All times are in 24-hour format for consistency.
    """
    summary: str = Field(
        description=(
            "The title/name of the event. "
            "Example: 'Client Follow-up Meeting' or 'Project Review Session'"
        )
    )
    date: str = Field(
        description=(
            "The date of the event in YYYY-MM-DD format. "
            "Example: '2026-09-15' for September 15, 2026"
        )
    )
    time: str = Field(
        description=(
            "The start time in HH:MM format (24-hour). "
            "Example: '14:30' for 2:30 PM"
        )
    )
    duration: int = Field(
        default=60,
        description=(
            "The duration of the event in minutes. "
            "Default is 60 minutes. Example: 30, 45, 60, 90"
        )
    )
    attendees: str = Field(
        default="",
        description=(
            "Comma-separated list of attendee email addresses. "
            "Example: 'client@company.com, manager@company.com'"
        )
    )


class CalendarTool(BaseTool):
    """
    Calendar Scheduling Tool for CrewAI Agents.
    
    This tool allows agents to create calendar events and schedule meetings.
    It handles the formatting and timing logic.
    
    For production use, this can be extended to connect to:
    - Google Calendar API
    - Microsoft Outlook API
    - Calendly API
    """
    name: str = "create_calendar_event"
    description: str = (
        "Creates a calendar event for scheduling meetings. "
        "Use this tool when you need to: "
        "1. Schedule follow-up meetings with clients\n"
        "2. Set up team sync sessions\n"
        "3. Create deadlines or reminders\n"
        "4. Plan project milestones"
    )
    args_schema: Type[BaseModel] = CalendarInput

    def _run(self, summary: str, date: str, time: str, 
             duration: int = 60, attendees: str = "") -> str:
        """
        Create a calendar event.
        
        Args:
            summary: Event title
            date: Event date (YYYY-MM-DD)
            time: Event start time (HH:MM)
            duration: Duration in minutes
            attendees: Comma-separated email addresses
            
        Returns:
            Success or error message
        """
        try:
            # === STEP 1: Parse and validate the date/time ===
            try:
                start_time = datetime.datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            except ValueError as e:
                return f"❌ Invalid date/time format. Please use YYYY-MM-DD and HH:MM. Error: {str(e)}"
            
            # === STEP 2: Calculate the end time ===
            end_time = start_time + datetime.timedelta(minutes=duration)
            
            # === STEP 3: Format the event details for display ===
            # This creates a nice visual representation
            event_details = f"""
┌────────────────────────────────────────────────────────────────┐
│  📅 CALENDAR EVENT CREATED                                   │
├────────────────────────────────────────────────────────────────┤
│  Event Title:  {summary}                                      │
│  Date:         {date}                                        │
│  Start Time:   {time}                                        │
│  End Time:     {end_time.strftime('%H:%M')}                   │
│  Duration:     {duration} minutes                            │
│  Attendees:    {attendees if attendees else 'None'}           │
└────────────────────────────────────────────────────────────────┘
"""
            print(event_details)
            
            # === STEP 4: In production, this would create a real calendar event ===
            # For now, we simulate success
            # To implement real calendar integration:
            # 1. Google Calendar: Use google-api-python-client
            # 2. Outlook: Use Microsoft Graph API
            
            return (
                f"✅ Calendar event created successfully!\n"
                f"   Event: '{summary}'\n"
                f"   When: {date} at {time}\n"
                f"   Duration: {duration} minutes\n"
                f"   Attendees: {attendees if attendees else 'None'}"
            )
            
        except Exception as e:
            return f"❌ Failed to create calendar event: {str(e)}"