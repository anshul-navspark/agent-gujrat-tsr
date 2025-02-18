from langchain_openai import AzureChatOpenAI
from browser_use import Agent, Browser  # Remove BrowserConfig if it's not available
from dotenv import load_dotenv
import asyncio
import os
from pydantic import SecretStr
from mlx_use.mac.tree import MacUITreeBuilder
from mlx_use.controller.service import Controller
from objc import *
from Cocoa import NSWorkspace, NSApplicationActivateIgnoringOtherApps

load_dotenv()

async def main():
    browser = None  # Initialize browser as None
    try:
        # Create browser without config since timeout isn't supported
        browser = Browser()
        
        # --- User-defined parameters ---
        district_name = "પાટણ"  # Change this to your desired District
        taluka_name = "પાટણ"    # Change this to your desired Taluka
        village_name = "અનાવાડા - 091" # Change this to your desired Village
        survey_block_number = "029" # Change this to your desired Survey Number

        task_description = f"""
        Objective: Download the land record from AnyRoR website as a PDF.
        Using the following details:
        District: {district_name}
        Taluka: {taluka_name}
        Village: {village_name}
        Survey/Block Number: {survey_block_number}

        Steps:
        1. Go to the website https://anyror.gujarat.gov.in/LandRecordRural.aspx.
        2. On the "RURAL LAND RECORD" page, find and click the dropdown with id="ContentPlaceHolder1_drpLandRecord".
        3. Select the option with value="8" from the dropdown (this is for "INTEGRATED SURVEY NO DETAILS").
        4. For District, find dropdown with id="ContentPlaceHolder1_ddlDistrict" and select "{district_name}".
        5. For Taluka, find dropdown with id="ContentPlaceHolder1_ddlTaluka" and select "{taluka_name}".
        6. For Village, find dropdown with id="ContentPlaceHolder1_ddlVillage" and select "{village_name}".
        7. For "Survey/ Block Number", enter "{survey_block_number}" in the appropriate field that appears.
        8. Find the captcha input field with id="ContentPlaceHolder1_txt_captcha_1". The captcha is always 6 digits long. You need to manually read all 6 digits from the captcha image and provide it to the agent. If you can't read all 6 digits clearly, ask for human help.
        9. Click the submit button with id="ContentPlaceHolder1_btnGo".
        10. Wait for the record details to load.
        11. Initiate printing the page (e.g., by using browser's print function, usually Ctrl+P or Cmd+P).
        12. In the print dialog, select "Save as PDF" as the destination.
        13. Click "Save" and save the PDF file with the name "land_record.pdf" in the Downloads folder.
        """

        # Initialize Azure OpenAI with a lower temperature for more precise selection
        llm = AzureChatOpenAI(
            model="gpt-4o",
            api_version='2024-02-15-preview',
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
            api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
            temperature=0.2
        )

        agent = Agent(
            llm=llm,
            browser=browser,
            task=task_description,
            save_conversation_path="logs/conversation",
            use_vision=True
        )

        # Run the agent to perform the task
        await agent.run()

        # Use MacOSAgent to handle the print dialog
        controller = Controller()
        builder = MacUITreeBuilder()

        # Open the Preview application
        workspace = NSWorkspace.sharedWorkspace()
        success = workspace.launchApplication_("Preview")
        if not success:
            print("❌ Failed to launch Preview app")
            return

        await asyncio.sleep(1)  # Give the app a moment to launch

        # Find the app's PID
        app_pid = None
        for app in workspace.runningApplications():
            if app.bundleIdentifier() and "com.apple.Preview" in app.bundleIdentifier():
                app_pid = app.processIdentifier()
                break

        if not app_pid:
            print("❌ Could not find Preview app")
            return

        # Activate the app
        for app in workspace.runningApplications():
            if app.processIdentifier() == app_pid:
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                break

        await asyncio.sleep(1)  # Give it a moment to activate

        # Build and print the UI tree
        root = await builder.build_tree(app_pid)
        if root:
            print(f"✅ Successfully built UI tree for Preview!")
        else:
            print("❌ Failed to build UI tree for Preview")

        # Verify if file was downloaded
        expected_file_path = os.path.join(os.path.expanduser("~"), "Downloads", "land_record.pdf")
        if os.path.exists(expected_file_path):
            print(f"Land record successfully downloaded to: {expected_file_path}")
        else:
            print("Warning: Land record PDF was not found in Downloads folder")

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise  # Re-raise the exception to see the full traceback
    finally:
        if browser:  # Only try to close if browser was created
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())