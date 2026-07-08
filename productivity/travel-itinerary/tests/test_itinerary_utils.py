from pathlib import Path
import importlib.util


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "itinerary_utils.py"
SPEC = importlib.util.spec_from_file_location("itinerary_utils", SCRIPT_PATH)
itinerary_utils = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(itinerary_utils)


def test_maps_url_normalises_mode_case_and_encodes_addresses():
    url = itinerary_utils.maps_url(
        "HND",
        "Hotel The Celestine Tokyo Shiba",
        "Transit",
    )
    assert "origin=HND" in url
    assert "destination=Hotel+The+Celestine+Tokyo+Shiba" in url
    assert "travelmode=transit" in url


def test_maps_url_preserves_valid_coordinates_and_rejects_invalid_ranges():
    url = itinerary_utils.maps_url("35.5494,139.7798", "35.6510,139.7470", "Taxi")
    assert "origin=35.5494,139.7798" in url
    assert "destination=35.6510,139.7470" in url
    assert "travelmode=driving" in url

    invalid = itinerary_utils.maps_url("999,999", "HND", "walking")
    assert "origin=999%2C999" in invalid
    assert "travelmode=walking" in invalid


def test_ics_escape_and_fold():
    escaped = itinerary_utils.ics_escape("Line 1, with comma; and \\ slash\nLine 2")
    assert escaped == "Line 1\\, with comma\\; and \\\\ slash\\nLine 2"

    folded = itinerary_utils.ics_fold_line("SUMMARY:" + "東京" * 40)
    assert "\r\n " in folded
    for line in folded.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75


def test_ics_check_accepts_valid_calendar(tmp_path):
    path = tmp_path / "trip.ics"
    path.write_text(
        "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//travel-itinerary skill//EN",
                "BEGIN:VTIMEZONE",
                "TZID:Asia/Tokyo",
                "END:VTIMEZONE",
                "BEGIN:VEVENT",
                "UID:flight-001@travel-itinerary",
                "DTSTAMP:20260610T120000Z",
                "DTSTART;TZID=Asia/Tokyo:20260612T081000",
                "SUMMARY:CX548 HKG to HND",
                "END:VEVENT",
                "END:VCALENDAR",
                "",
            ]
        ),
        encoding="utf-8",
    )

    ok, errors = itinerary_utils.ics_check(str(path))
    assert ok, errors


def test_ics_check_catches_missing_event_fields_and_timezone(tmp_path):
    path = tmp_path / "bad.ics"
    path.write_text(
        "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "BEGIN:VEVENT",
                "UID:flight-001@travel-itinerary",
                "DTSTART;TZID=Asia/Tokyo:20260612T081000",
                "SUMMARY:CX548 HKG to HND",
                "END:VEVENT",
                "END:VCALENDAR",
                "",
            ]
        ),
        encoding="utf-8",
    )

    ok, errors = itinerary_utils.ics_check(str(path))
    assert not ok
    assert any("missing: DTSTAMP" in error for error in errors)
    assert any("Missing VTIMEZONE for TZID(s): Asia/Tokyo" in error for error in errors)
