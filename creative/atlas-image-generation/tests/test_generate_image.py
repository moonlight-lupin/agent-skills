import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_image.py"
SPEC = importlib.util.spec_from_file_location("atlas_generate_image", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


def test_paid_submission_happens_once_then_poll_completes():
    responses = [
        FakeResponse({"code": 200, "data": {"id": "prediction-test"}}),
        FakeResponse({"code": 200, "data": {"status": "processing"}}),
        FakeResponse(
            {
                "code": 200,
                "data": {"status": "completed", "outputs": ["https://example.test/image.png"]},
            }
        ),
    ]
    with patch.object(MODULE.urllib.request, "urlopen", side_effect=responses) as urlopen:
        output = MODULE.generate(
            api_key="test-key",
            payload={"model": "example/image", "prompt": "red kite"},
            api_base="https://example.test/api/v1",
            poll_interval=0,
            wait_timeout=2,
        )

    assert output == "https://example.test/image.png"
    requests = [call.args[0] for call in urlopen.call_args_list]
    assert sum(request.get_method() == "POST" for request in requests) == 1
    for request in requests[1:]:
        assert request.get_header("Authorization") == "Bearer test-key"


def test_dry_run_uses_no_api_key_or_network():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "red kite",
            "--aspect-ratio",
            "16:9",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={},
    )
    payload = json.loads(result.stdout)
    assert payload["prompt"] == "red kite"
    assert payload["aspect_ratio"] == "16:9"


def test_detect_image_signatures():
    assert MODULE.detect_image(b"\x89PNG\r\n\x1a\nrest") == "PNG"
    assert MODULE.detect_image(b"\xff\xd8\xffrest") == "JPEG"
    assert MODULE.detect_image(b"RIFFxxxxWEBPrest") == "WebP"
