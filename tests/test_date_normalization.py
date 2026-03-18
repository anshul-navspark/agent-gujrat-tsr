from tsr_generator.extractors.unified_extractor import _normalize_date_str

def test_2digit_year_modern():
    assert _normalize_date_str("08/03/04") == "08/03/2004"
    assert _normalize_date_str("15/06/00") == "15/06/2000"
    assert _normalize_date_str("01/01/30") == "01/01/2030"

def test_2digit_year_old():
    assert _normalize_date_str("22/08/96") == "22/08/1996"
    assert _normalize_date_str("10/05/31") == "10/05/1931"
    assert _normalize_date_str("01/01/99") == "01/01/1999"

def test_4digit_year_preserved():
    assert _normalize_date_str("08/03/2004") == "08/03/2004"
    assert _normalize_date_str("22/08/1996") == "22/08/1996"

def test_empty_and_invalid():
    assert _normalize_date_str("") == ""
    assert _normalize_date_str("not a date") == "not a date"

def test_dash_separator():
    assert _normalize_date_str("08-03-04") == "08/03/2004"

def test_single_digit_padding():
    assert _normalize_date_str("8/3/04") == "08/03/2004"
