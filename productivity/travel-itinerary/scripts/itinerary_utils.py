#!/usr/bin/env python3
"""Small utility helpers for the travel-itinerary skill.

This is intentionally lightweight and stdlib-only. It is not a full itinerary
app. Use it for deterministic formatting/validation chores that are annoying or
error-prone for an LLM to do by hand:

- Build Google Maps direction URLs.
- Escape and fold iCalendar text lines.
- Sanity-check .ics structure.

Examples:
  python3 itinerary_utils.py maps-url --origin "HND" --destination "Hotel The Celestine Tokyo Shiba" --mode transit
  python3 itinerary_utils.py ics-check /path/to/trip.ics
  python3 itinerary_utils.py ics-escape "Line 1, with comma; and newline\nLine 2"
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from urllib.parse import quote_plus


GMAPS_MODE = {
    "driving": "driving",
    "taxi": "driving",
    "ride_hail": "driving",
    "private_car": "driving",
    "shuttle": "driving",
    "transit": "transit",
    "walking": "walking",
    "bicycling": "bicycling",
    "cycling": "bicycling",
    "unknown": "driving",
    "": "driving",
}

TZID_RE = re.compile(r"(?:^|;)TZID=([^:;]+)")


def _endpoint(value: str) -> str:
    """Encode a Maps endpoint.

    Keep valid WGS-84 coordinate pairs readable ("35.1,139.1"), otherwise
    URL-encode the value as a place name/address.
    """
    value = (value or "").strip()
    if not value:
        raise ValueError("origin/destination cannot be empty")

    compact = value.replace(" ", "")
    parts = compact.split(",")
    if len(parts) == 2:
        try:
            lat = float(parts[0])
            lon = float(parts[1])
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return compact
        except ValueError:
            pass

    return quote_plus(value)


def maps_url(origin: str, destination: str, mode: str = "driving") -> str:
    travelmode = GMAPS_MODE.get((mode or "").strip().lower(), "driving")
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={_endpoint(origin)}"
        f"&destination={_endpoint(destination)}"
        f"&travelmode={travelmode}"
    )


def ics_escape(text: str) -> str:
    """Escape TEXT per RFC 5545 text value rules."""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def ics_fold_line(line: str, limit: int = 75) -> str:
    """Fold one iCalendar content line at <= limit UTF-8 octets.

    Continuation lines start with one space. The function avoids splitting a
    UTF-8 character by accumulating character-by-character.
    """
    if len(line.encode("utf-8")) <= limit:
        return line

    out: list[str] = []
    current = ""
    current_limit = limit
    for ch in line:
        candidate = current + ch
        if len(candidate.encode("utf-8")) > current_limit:
            out.append(current)
            current = " " + ch
            current_limit = limit
        else:
            current = candidate
    if current:
        out.append(current)
    return "\r\n".join(out)


def _unfold_ics_lines(text: str) -> list[str]:
    """Return unfolded non-empty iCalendar content lines."""
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded: list[str] = []
    for raw in raw_lines:
        if not raw:
            continue
        if raw.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += raw[1:]
        else:
            unfolded.append(raw)
    return unfolded


def _line_name(line: str) -> str:
    """Return the iCalendar property name before any parameters."""
    return line.split(":", 1)[0].split(";", 1)[0].upper()


def ics_check(path: str) -> tuple[bool, list[str]]:
    """Perform lightweight sanity checks for a generated .ics file.

    This is not a complete RFC 5545 validator. It catches common mistakes made
    by hand-written or LLM-rendered calendar files: unbalanced blocks, missing
    required VEVENT fields, missing VTIMEZONE blocks for TZID references, and
    unfolded lines over 75 octets.
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    errors: list[str] = []

    physical_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i, line in enumerate(physical_lines, start=1):
        if line and not line.startswith((" ", "\t")) and len(line.encode("utf-8")) > 75:
            errors.append(f"Line {i}: unfolded content line exceeds 75 octets")

    lines = _unfold_ics_lines(text)
    if not lines or lines[0].strip() != "BEGIN:VCALENDAR":
        errors.append("First non-empty line must be BEGIN:VCALENDAR")
    if not lines or lines[-1].strip() != "END:VCALENDAR":
        errors.append("Last non-empty line must be END:VCALENDAR")

    stack: list[str] = []
    component_stack: list[tuple[str, int, set[str]]] = []
    vtimezones: set[str] = set()
    used_tzids: set[str] = set()

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("BEGIN:"):
            name = stripped.split(":", 1)[1].upper()
            stack.append(name)
            if name in {"VEVENT", "VTODO", "VTIMEZONE"}:
                component_stack.append((name, i, set()))
            continue

        if stripped.startswith("END:"):
            name = stripped.split(":", 1)[1].upper()
            if not stack:
                errors.append(f"Line {i}: END:{name} without matching BEGIN")
            else:
                start = stack.pop()
                if start != name:
                    errors.append(f"Line {i}: END:{name} closes BEGIN:{start}")

            if name in {"VEVENT", "VTODO", "VTIMEZONE"}:
                if not component_stack:
                    errors.append(f"Line {i}: END:{name} without component state")
                else:
                    component_name, start_line, props = component_stack.pop()
                    if component_name != name:
                        errors.append(
                            f"Line {i}: END:{name} closes component BEGIN:{component_name}"
                        )
                    if name == "VEVENT":
                        required = {"UID", "DTSTAMP", "DTSTART", "SUMMARY"}
                        missing = sorted(required - props)
                        if missing:
                            errors.append(
                                f"VEVENT beginning line {start_line} missing: {', '.join(missing)}"
                            )
                    if name == "VTODO":
                        required = {"UID", "DTSTAMP", "SUMMARY"}
                        missing = sorted(required - props)
                        if missing:
                            errors.append(
                                f"VTODO beginning line {start_line} missing: {', '.join(missing)}"
                            )
            continue

        if component_stack:
            component_name, start_line, props = component_stack[-1]
            prop_name = _line_name(stripped)
            props.add(prop_name)
            component_stack[-1] = (component_name, start_line, props)
            if component_name == "VTIMEZONE" and prop_name == "TZID" and ":" in stripped:
                vtimezones.add(stripped.split(":", 1)[1].strip())

        match = TZID_RE.search(stripped)
        if match:
            used_tzids.add(match.group(1).strip())

    if stack:
        errors.append("Unclosed blocks: " + ", ".join(stack))

    missing_tzids = sorted(tzid for tzid in used_tzids if tzid not in vtimezones)
    if missing_tzids:
        errors.append("Missing VTIMEZONE for TZID(s): " + ", ".join(missing_tzids))

    return not errors, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_url = sub.add_parser("maps-url", help="Build a Google Maps directions URL")
    p_url.add_argument("--origin", required=True)
    p_url.add_argument("--destination", required=True)
    p_url.add_argument("--mode", default="driving")

    p_escape = sub.add_parser("ics-escape", help="Escape an iCalendar text value")
    p_escape.add_argument("text")

    p_fold = sub.add_parser("ics-fold", help="Fold an iCalendar content line")
    p_fold.add_argument("line")

    p_check = sub.add_parser("ics-check", help="Sanity-check .ics structure")
    p_check.add_argument("path")

    args = parser.parse_args(argv)
    if args.cmd == "maps-url":
        print(maps_url(args.origin, args.destination, args.mode))
        return 0
    if args.cmd == "ics-escape":
        print(ics_escape(args.text))
        return 0
    if args.cmd == "ics-fold":
        print(ics_fold_line(args.line))
        return 0
    if args.cmd == "ics-check":
        ok, errors = ics_check(args.path)
        if ok:
            print("OK")
            return 0
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
