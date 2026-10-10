#!/usr/bin/env python3
"""Generate one image through Atlas Cloud without retrying the paid POST."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


CATALOG_URL = "https://api.atlascloud.ai/api/v1/models"
DEFAULT_API_BASE = "https://api.atlascloud.ai/api/v1"
DEFAULT_MODEL = "google/nano-banana-pro/text-to-image-developer"
SUCCESS_STATUSES = {"completed", "succeeded", "success"}
FAILURE_STATUSES = {"failed", "canceled", "cancelled"}
USER_AGENT = "agent-skills-atlas-image/1.0"


def read_json(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    attempts: int = 3,
    timeout: float = 30,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
        request = urllib.request.Request(url, headers=request_headers)
        try:
            return read_json(request, timeout)
        except (RuntimeError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"GET failed after {attempts} attempts: {url}") from last_error


def validate_live_model(model_id: str, requested_fields: set[str]) -> None:
    catalog = get_json(CATALOG_URL)
    models = catalog.get("data") or []
    model = next((item for item in models if item.get("model") == model_id), None)
    if not model:
        raise RuntimeError(f"Model is not present in the live catalog: {model_id}")
    if model.get("display_console") is not True:
        raise RuntimeError(f"Model is not public: {model_id}")
    if model.get("type") != "Image":
        raise RuntimeError(f"Model is not an image model: {model_id}")

    schema_url = model.get("schema")
    if not schema_url:
        raise RuntimeError(f"Model has no live schema: {model_id}")
    schema = get_json(str(schema_url))
    properties = (
        schema.get("components", {}).get("schemas", {}).get("Input", {}).get("properties", {})
    )
    missing = sorted(requested_fields - set(properties))
    if missing:
        raise RuntimeError(f"Live model schema does not support: {', '.join(missing)}")


def first_output_url(data: dict[str, Any]) -> str:
    outputs = data.get("outputs") or data.get("output") or []
    if isinstance(outputs, str):
        return outputs
    if isinstance(outputs, list) and outputs:
        first = outputs[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            for key in ("url", "image_url"):
                if isinstance(first.get(key), str):
                    return first[key]
    raise RuntimeError("Atlas prediction completed without an output URL")


def generate(
    *,
    api_key: str,
    payload: dict[str, Any],
    api_base: str,
    poll_interval: float,
    wait_timeout: float,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/model/generateImage",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    # This POST may be billable and is intentionally never retried.
    submission = read_json(request, timeout=300)
    if submission.get("code") not in (None, 200, "200"):
        raise RuntimeError(str(submission.get("msg") or submission.get("message") or submission))
    prediction_id = (submission.get("data") or {}).get("id")
    if not prediction_id:
        raise RuntimeError("Atlas submission did not return data.id")

    poll_url = (
        f"{api_base.rstrip('/')}/model/prediction/"
        f"{urllib.parse.quote(str(prediction_id), safe='')}"
    )
    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        prediction = get_json(
            poll_url,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        data = prediction.get("data") or {}
        status = str(data.get("status") or "").lower()
        if status in SUCCESS_STATUSES:
            return first_output_url(data)
        if status in FAILURE_STATUSES:
            reason = data.get("error") or data.get("message") or status
            raise RuntimeError(f"Atlas image generation failed: {reason}")
        time.sleep(poll_interval)
    raise RuntimeError(f"Timed out waiting for Atlas prediction {prediction_id}")


def detect_image(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WebP"
    raise RuntimeError("Downloaded Atlas output is not a PNG, JPEG, or WebP image")


def download_image(url: str, output: Path) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Image download failed: {exc}") from exc
    image_type = detect_image(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    return image_type


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate one image through Atlas Cloud.")
    parser.add_argument("prompt", help="Text prompt sent to the selected image model")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--aspect-ratio",
        choices=("1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"),
    )
    parser.add_argument("--resolution", choices=("1k", "2k", "4k"))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output", type=Path, default=Path("atlas-image.png"))
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--dry-run", action="store_true", help="Print the payload; do not use the network")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload: dict[str, Any] = {"model": args.model, "prompt": args.prompt}
    optional = {
        "aspect_ratio": args.aspect_ratio,
        "resolution": args.resolution,
        "seed": args.seed,
    }
    payload.update({key: value for key, value in optional.items() if value is not None})

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    api_key = os.environ.get("ATLASCLOUD_API_KEY", "").strip()
    if not api_key:
        print("Missing ATLASCLOUD_API_KEY", file=sys.stderr)
        return 2

    validate_live_model(args.model, set(payload))
    output_url = generate(
        api_key=api_key,
        payload=payload,
        api_base=os.environ.get("ATLASCLOUD_API_BASE_URL", DEFAULT_API_BASE),
        poll_interval=args.poll_interval,
        wait_timeout=args.timeout,
    )
    image_type = download_image(output_url, args.output)
    print(f"{args.output} ({image_type})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
