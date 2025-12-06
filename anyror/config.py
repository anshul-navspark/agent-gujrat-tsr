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
    'CAPTCHA_INPUT_ID': 'ContentPlaceHolder1_txt_captcha1',
    'SUBMIT_BUTTON_ID': 'ContentPlaceHolder1_btnGo',
    'WAIT_TIMEOUT': 20,
    'CAPTCHA_WAIT_TIMEOUT': 2,
    'MAX_RETRIES': 3,
    'DROPDOWN_WAIT_TIMEOUT': 3,
    'PAGE_LOAD_WAIT': 3,
    'URL': 'https://anyror.gujarat.gov.in/LandRecordRural.aspx'
}
