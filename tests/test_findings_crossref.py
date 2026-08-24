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

    # The cross-reference is emitted as a {{XREF:<entry>:<row>}} marker, which
    # the DOCX writer turns into a Word REF field bound to that chain row's
    # bookmark. Static numbers went stale when the lawyer inserted a chain row
    # (2026-07-28), so the marker must carry BOTH the entry and its row.
    row5 = findings[8]
    assert "{{XREF:5647:33}} in table no. 3 above" in row5['observation']

    # Row 18 (index 21) should also cross-reference
    row18 = findings[21]
    assert "{{XREF:5647:33}} in table no. 3 above" in row18['observation']

    # The released charge (4477, released by 4736) must NOT be referenced.
    assert "4477" not in row5['observation']

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


def test_xref_marker_becomes_a_word_ref_field(tmp_path):
    """The marker must render as a REF field bound to the chain row's bookmark.

    Static numbers went stale twice in the 2026-07-28 Bodki batch when the
    lawyer inserted a chain row - in 57p1 the reference ended up pointing at a
    charge RELEASE instead of a charge. A REF field follows Word's renumbering.
    """
    import re, zipfile
    from docx import Document
    from tsr_generator.document.docx_generator import (
        add_findings_table, chain_bookmark_name,
    )

    doc = Document()
    findings = [{
        'sn': '5.',
        'particular': 'Additional suggestions',
        'observation': ('The title of the land is clear and marketable subject to '
                        'point {{XREF:539:2}} and {{XREF:622:5}} in table no. 3 above.'),
    }]
    add_findings_table(doc, findings)
    out = tmp_path / "x.docx"
    doc.save(out)

    xml = zipfile.ZipFile(out).read('word/document.xml').decode()
    assert "{{XREF" not in xml, "marker leaked into the document as literal text"
    refs = re.findall(r'REF\s+(chainEntry\d+)\s+\\r', xml)
    assert refs == ['chainEntry539', 'chainEntry622']
    # cached values keep the document readable before fields are refreshed
    assert '>2<' in xml and '>5<' in xml


def test_chain_bookmark_name_is_word_safe():
    from tsr_generator.document.docx_generator import chain_bookmark_name
    # Word bookmark names allow only letters, digits and underscore
    for raw in ["539", "44/p1", "45/4p2", "208p2"]:
        name = chain_bookmark_name(raw)
        assert name.replace("_", "").isalnum(), name
        assert name.startswith("chainEntry")
