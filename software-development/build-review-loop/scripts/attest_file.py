#!/usr/bin/env python3
"""Attest and verify files by SHA-256 (build-review-loop port of the
planning-with-files attestation concept).

Two uses:
1. Briefs — hash the brief before dispatching a builder; verify after the
   build. A changed hash means the builder edited its own instructions
   (pitfall #20: warp the spec until tests pass).
2. Loop plans — hash task_plan.md in gated loops so a mid-loop edit to
   phase statuses is visible instead of silent.

The sidecar lives next to the file as <name>.attest (JSON). Loop-plan files
are gitignored working state, never committed; the sidecar follows the file.
"""
import argparse
import datetime
import hashlib
import json
import os
import sys


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sidecar_path(path):
    return path + ".attest"


def cmd_attest(args):
    digest = sha256_file(args.path)
    record = {
        "schema": "btl-attest.v1",
        "file": os.path.basename(args.path),
        "sha256": digest,
        "attestedAt": datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds"),
        "note": args.note,
    }
    with open(sidecar_path(args.path), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")
    print(f"attested {args.path} -> {sidecar_path(args.path)}")
    print(digest)


def cmd_verify(args):
    sc = sidecar_path(args.path)
    if not os.path.isfile(sc):
        print(f"NO ATTESTATION: {sc} missing", file=sys.stderr)
        return 2
    with open(sc, encoding="utf-8") as fh:
        record = json.load(fh)
    actual = sha256_file(args.path)
    if actual == record.get("sha256"):
        print(f"OK {args.path} matches attestation {record['attestedAt']}")
        return 0
    print(f"TAMPERED {args.path}: sha256 {actual} != attested "
          f"{record.get('sha256')} (attested {record['attestedAt']})",
          file=sys.stderr)
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("attest", help="write <path>.attest with the SHA-256")
    a.add_argument("path")
    a.add_argument("--note", default=None)
    v = sub.add_parser("verify", help="verify <path> against <path>.attest")
    v.add_argument("path")
    args = ap.parse_args()
    if not os.path.isfile(args.path):
        print(f"file not found: {args.path}", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(cmd_attest(args) if args.cmd == "attest" else cmd_verify(args))


if __name__ == "__main__":
    main()
