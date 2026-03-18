from tsr_generator.extractors.findings import generate_findings_table

def test_cross_reference_with_map():
    entries = [
        {"entry_number": "4477", "type": "LOAN", "entry_status": "certified"},
        {"entry_number": "4736", "type": "RELEASE", "entry_status": "certified",
         "description": "Entry No. 4477"},
        {"entry_number": "5647", "type": "LOAN", "entry_status": "certified"},
    ]
    land_details = {"taluka_name": "Dhanera", "tsr_profile": "final_sample_v1"}
    entry_to_row_map = {"4477": 20, "4736": 21, "5647": 33}

    findings = generate_findings_table("", entries, land_details, entry_to_row_map)

    # Row 5 (index 8) should cross-reference point 33
    row5 = findings[8]
    assert "point 33 in table no. 3 above" in row5['observation']

    # Row 18 (index 21) should also cross-reference
    row18 = findings[21]
    assert "point 33 in table no. 3 above" in row18['observation']

def test_cross_reference_without_map_fallback():
    entries = [
        {"entry_number": "100", "type": "LOAN", "entry_status": "certified"},
    ]
    land_details = {"taluka_name": "Dhanera", "tsr_profile": "final_sample_v1"}

    findings = generate_findings_table("", entries, land_details)
    row5 = findings[8]
    # Without map, should fall back to generic text
    assert "clear and marketable" in row5['observation']

def test_no_encumbrances():
    entries = [
        {"entry_number": "100", "type": "SALE", "entry_status": "certified"},
    ]
    land_details = {"taluka_name": "Dhanera", "tsr_profile": "final_sample_v1"}

    findings = generate_findings_table("", entries, land_details, {})
    row5 = findings[8]
    assert row5['observation'] == "The title of the land is clear and marketable."

def test_sn_has_periods():
    entries = []
    land_details = {"taluka_name": "Dhanera"}
    findings = generate_findings_table("", entries, land_details)
    # Check that non-empty SN values have periods
    for f in findings:
        if f['sn']:
            assert f['sn'].endswith('.'), f"SN '{f['sn']}' missing period"
