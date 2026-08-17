from bench.normalize import (
    format_ok,
    normalize_date,
    normalize_number,
    normalize_text,
    normalize_value,
    values_match,
)

DATE = {"type": "string", "format": "date"}
MONEY = {"type": "number", "format": "currency"}
TEXT = {"type": "string"}


def test_dates_parse_to_iso():
    assert normalize_date("25/12/2018") == "2018-12-25"
    assert normalize_date("21-05-17") == "2017-05-21"
    assert normalize_date("2018-12-25") == "2018-12-25"
    assert normalize_date("25 Dec 2018") == "2018-12-25"
    assert normalize_date("not a date") is None


def test_numbers_strip_currency():
    assert normalize_number("RM33.90") == "33.90"
    assert normalize_number("$1,234.5") == "1234.50"
    assert normalize_number(42) == "42.00"
    assert normalize_number("free") is None


def test_text_collapses_case_and_spacing():
    assert normalize_text("  Acme  Sdn , Bhd ") == "ACME SDN,BHD"


def test_values_match_is_schema_aware():
    assert values_match("RM42.00", 42.0, MONEY)
    assert values_match("25/12/2018", "2018-12-25", DATE)
    assert values_match("Acme Store", "ACME  STORE", TEXT)
    assert not values_match("42.00", "43.00", MONEY)
    assert values_match(None, None, TEXT)
    assert not values_match(None, "x", TEXT)


def test_format_ok():
    assert format_ok("42.00", MONEY)
    assert not format_ok("unknown", MONEY)
    assert format_ok("25/12/2018", DATE)
    assert not format_ok("someday", DATE)
    assert not format_ok(None, TEXT)
    assert not format_ok("   ", TEXT)


def test_normalize_value_fallback():
    assert normalize_value("hello  world", TEXT) == "HELLO WORLD"
    assert normalize_value(None, TEXT) is None
    assert normalize_value("", TEXT) is None
