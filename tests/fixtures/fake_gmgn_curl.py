"""Stand-in for curl.exe. It writes a JSON envelope and records its argv."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    argv_path = os.environ.get("CYVORA_FAKE_CURL_ARGV")
    if argv_path:
        Path(argv_path).write_text("\n".join(sys.argv), encoding="utf-8")
    if "--config" not in sys.argv:
        sys.stderr.write("missing config\n")
        return 2
    config = Path(sys.argv[sys.argv.index("--config") + 1]).read_text(encoding="utf-8")
    if os.environ.get("CYVORA_FAKE_CURL_FAIL") == "1":
        sys.stderr.write("forced failure\n")
        return 28
    values: dict[str, str] = {}
    saw_key = False
    for line in config.splitlines():
        if line.startswith("header = "):
            if "x-apikey:" in line.lower():
                saw_key = True
            continue
        if " = " not in line:
            continue
        key, value = line.split(" = ", 1)
        values[key.strip()] = value.strip().strip('"')
    if not saw_key:
        sys.stderr.write("missing api key header\n")
        return 3
    Path(values["output"]).write_bytes(b'{"code":0,"data":{"rank":[]}}')
    Path(values["dump-header"]).write_text(
        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
