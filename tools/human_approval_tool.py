from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import time
import sys
import select

class ApprovalInput(BaseModel):
    message: str = Field(description="The message to show the human")
    options: str = Field(default="", description="Optional options to choose from")
    timeout: int = Field(default=60, description="Timeout in seconds to wait for response")

class HumanApprovalTool(BaseTool):
    name: str = "request_human_approval"
    description: str = (
        "Requests human approval before taking action. "
        "Use this for critical decisions like sending emails, "
        "finalizing reports, or making important changes."
    )
    args_schema: Type[BaseModel] = ApprovalInput

    def _run(self, message: str, options: str = "", timeout: int = 60) -> str:
        """Request human approval and wait for response"""
        
        print("\n" + "="*60)
        print("🔴 HUMAN APPROVAL REQUIRED")
        print("="*60)
        print(f"📝 Message: {message}")
        if options:
            print(f"📋 Options: {options}")
        print("\nPlease respond with:")
        print("  'yes' or 'y' - to approve")
        print("  'no' or 'n' - to reject")
        if options:
            options_list = options.split(',')
            for i, opt in enumerate(options_list, 1):
                print(f"  {i} - {opt.strip()}")
        
        print(f"\n⏳ Waiting up to {timeout} seconds...")
        
        # Wait for input with timeout
        start_time = time.time()
        response = None
        while time.time() - start_time < timeout:
            try:
                # Check if input is available
                import sys
                if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                    response = input("\nYour response: ").strip().lower()
                    break
            except:
                pass
        
        if response is None:
            return "⏰ TIMEOUT: No response received within the time limit. Action will not proceed."
        
        # Process response
        if response in ['yes', 'y']:
            return "✅ APPROVED: Proceeding with action"
        elif response in ['no', 'n']:
            return "❌ REJECTED: Action will not proceed"
        elif options and response.isdigit():
            option_num = int(response)
            options_list = [opt.strip() for opt in options.split(',')]
            if 1 <= option_num <= len(options_list):
                return f"✅ OPTION SELECTED: {options_list[option_num-1]}"
        
        return f"⚠️ UNCLEAR: '{response}' not recognized. Action will not proceed."