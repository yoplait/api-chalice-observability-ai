#!/usr/bin/env python3
"""HTTP traffic generator (stdlib only).

Environment variables:
  TRAFFIC_MODE:   normal | errors | latency
  TRAFFIC_RPS:    float, default 5.0
  TRAFFIC_DURATION: seconds, default 60
  TRAFFIC_BASE_URL: http://chalice-api:8000
"""
from __future__ import annotations

import json
import random
import sys
import time
import urllib.request
import urllib.error

BASE = f"http://{sys.argv[1]}/" if len(sys.argv) > 1 else "http://chalice-api:8000/"
MODE = sys.argv[2] if len(sys.argv) > 2 else "normal"
RPS = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
DURATION = int(sys.argv[4]) if len(sys.argv) > 4 else 60

ENDPOINTS_NORMAL = ["/hello", "/hello?name=Ops", "/health", "/ready", "/version"]
ENDPOINTS_ERRORS = ["/demo/error?kind=bad_request", "/demo/error?kind=unavailable", "/demo/error?kind=nope"]
ENDPOINTS_LATENCY = ["/demo/slow?delay=0.8", "/demo/slow?delay=1.5", "/demo/slow?delay=2.0"]


def _req(path: str) -> tuple[int, str]:
    try:
        req = urllib.request.Request(f"{BASE}{path.lstrip('/')}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return 0, str(e)


def _sleep_interval() -> float:
    return 1.0 / RPS


if __name__ == "__main__":
    random.seed(42)
    mode_endpoints = {
        "normal": ENDPOINTS_NORMAL,
        "errors": ENDPOINTS_ERRORS,
        "latency": ENDPOINTS_LATENCY,
    }.get(MODE, ENDPOINTS_NORMAL)

    deadline = time.monotonic() + DURATION
    total = 0
    errors_expected = 0
    errors_actual = 0
    failed = 0

    print(f"[traffic] MODE={MODE} RPS={RPS} DURATION={DURATION}s TARGET={BASE}")
    while time.monotonic() < deadline:
        path = random.choice(mode_endpoints)
        status, _body = _req(path)
        total += 1
        is_error = status >= 400

        if MODE == "errors":
            if is_error:
                errors_actual += 1
                errors_expected += 1
        elif MODE == "normal":
            if is_error:
                failed += 1
        elif MODE == "latency":
            pass  # all ok within timeout

        time.sleep(_sleep_interval() * random.uniform(0.5, 1.5))

    print(f"\n[traffic] DONE — total={total} errors={errors_actual if MODE=='errors' else failed} status=ok")
    sys.exit(0)