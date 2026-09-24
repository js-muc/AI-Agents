"""
Data Logger Tool for CrewAI Agents
==================================
This tool allows AI agents to store structured data in CSV files.
It's a lightweight alternative to Google Sheets or databases.

Usage:
    agent uses "add_to_sheet" tool with:
    - data: "Kenya, AI Agents, 47M, 40+ startups"
    - filename: "research_data.csv"
"""

from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import csv
import os
from datetime import datetime


class SheetsInput(BaseModel):
    """
    Input schema for the Data Logger Tool.
    
    Each row gets a timestamp automatically so you can track when data was added.
    """
    data: str = Field(
        description=(
            "The data to store. Use comma-separated values for structured data. "
            "Example: 'Kenya, AI Market, 47M, 40 startups, 2026'"
        )
    )
    filename: str = Field(
        default="research_data.csv",
        description=(
            "The name of the CSV file to store data in. "
            "Default is 'research_data.csv'"
        )
    )


class SheetsTool(BaseTool):
    """
    Data Logger Tool for CrewAI Agents.
    
    This tool allows agents to store data in a simple CSV format.
    It automatically adds timestamps to each entry.
    
    Benefits:
    1. No external dependencies
    2. Can be opened in Excel, Google Sheets, or any spreadsheet
    3. Append-only (preserves history)
    """
    name: str = "add_to_sheet"
    description: str = (
        "Adds a row of data to a CSV file for logging and tracking. "
        "Use this tool when you need to: "
        "1. Log research findings\n"
        "2. Track metrics or KPIs\n"
        "3. Build datasets for analysis\n"
        "4. Maintain audit trails\n"
        "5. Create structured records"
    )
    args_schema: Type[BaseModel] = SheetsInput

    def _run(self, data: str, filename: str = "research_data.csv") -> str:
        """
        Add data to a CSV file.
        
        Args:
            data: Comma-separated data to store
            filename: Name of the CSV file
            
        Returns:
            Success or error message
        """
        try:
            # === STEP 1: Ensure the data directory exists ===
            os.makedirs("data", exist_ok=True)
            
            # === STEP 2: Build the full file path ===
            filepath = os.path.join("data", filename)
            
            # === STEP 3: Check if the file already exists ===
            file_exists = os.path.exists(filepath)
            
            # === STEP 4: Write the data ===
            with open(filepath, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # If file is new, add headers
                if not file_exists:
                    writer.writerow(["timestamp", "data"])
                    header_msg = "Created new file with headers."
                else:
                    header_msg = "Appended to existing file."
                
                # Add the data row with timestamp
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([timestamp, data])
            
            # === STEP 5: Return success ===
            return (
                f"✅ Data added to {filename}\n"
                f"   {header_msg}\n"
                f"   Data: {data}\n"
                f"   Timestamp: {timestamp}"
            )
            
        except PermissionError:
            return f"❌ Permission denied: Could not write to {filename}. Please check file permissions."
        except Exception as e:
            return f"❌ Failed to add data: {str(e)}"