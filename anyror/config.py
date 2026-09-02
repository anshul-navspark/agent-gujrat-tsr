"""
Configuration for AnyRoR Gujarat Land Record Automation
"""

# Configuration for AnyRoR website
CONFIG = {
    'LAND_RECORD_TYPE_ID': 'ContentPlaceHolder1_drpLandRecord',
    'LAND_RECORD_TYPE_VALUE': '8',  # Value for "INTEGRATED SURVEY NO DETAILS"
    'DISTRICT_DROPDOWN_ID': 'ContentPlaceHolder1_ddlDistrict',
    'TALUKA_DROPDOWN_ID': 'ContentPlaceHolder1_ddlTaluka',
    'VILLAGE_DROPDOWN_ID': 'ContentPlaceHolder1_ddlVillage',
    'SURVEY_DROPDOWN_ID': 'ContentPlaceHolder1_ddlSurveyNo',
    'CAPTCHA_IMG_ID': 'ContentPlaceHolder1_i_captcha_1',
    # CAPTCHA_INPUT_ID removed 2026-09-02: it read 'txt_captcha1' while the
    # real field is 'txt_captcha_1' (underscore before the 1), and posting
    # the wrong name silently yields "Capcha is not matched". No code read
    # it, and it was documented as wrong in CLAUDE.md and the journal -- but
    # a documented trap is still a trap, and the next person to wire the
    # config in reintroduces the bug. The real name lives in http_fetch.py.
    'SUBMIT_BUTTON_ID': 'ContentPlaceHolder1_btnGo',
    'WAIT_TIMEOUT': 20,
    'CAPTCHA_WAIT_TIMEOUT': 2,
    'MAX_RETRIES': 3,
    'DROPDOWN_WAIT_TIMEOUT': 3,
    'PAGE_LOAD_WAIT': 3,
    'URL': 'https://anyror.gujarat.gov.in/LandRecordRural.aspx'
}
