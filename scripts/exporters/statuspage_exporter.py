#!/usr/bin/env python3
"""External status-page incident exporter.

Polls public status pages (Atlassian Statuspage APIs and Okta's embedded
incident JSON) and exposes Prometheus metrics so dashboards can show RED when
a third-party provider has an active incident — not just when the status
page itself is unreachable.

Metrics per service:
  external_status_up{service}                 1 if the source could be fetched
  external_status_indicator{service}          0 none | 1 minor | 2 major | 3 critical | -1 unknown
  external_status_incidents_active{service}   number of non-resolved incidents
  external_status_incident_info{service,name,impact}  1 while incident is active

Stdlib only (runs inside python:3.12-slim).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("EXPORTER_PORT", "9118"))
INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "60"))
USER_AGENT = "Mozilla/5.0 (compatible; chalice-lab-status-exporter/1.0)"

INDICATOR_LEVELS = {"none": 0, "operational": 0, "minor": 1, "degraded": 1,
                    "partial": 2, "partial_outage": 2, "major": 2,
                    "major_outage": 3, "critical": 3, "outage": 3}

RESOLVED = {"resolved", "postmortem", "monitoring", "completed"}

log = logging.getLogger("statuspage-exporter")


def fetch(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ---------------------------------------------------------------- parsers
def parse_atlassian(raw: bytes) -> dict:
    """Atlassian Statuspage /api/v2/summary.json (twilio, github, stripe...)."""
    data = json.loads(raw)
    status = data.get("status", {})
    indicator = status.get("indicator", "unknown")
    incidents = [i for i in data.get("incidents", [])
                 if i.get("status", "").lower() not in RESOLVED]
    return {
        "indicator": indicator,
        "incidents": [
            {"name": i.get("name", "incident"),
             "impact": i.get("impact") or i.get("status", "unknown")}
            for i in incidents
        ],
    }


def parse_google(raw: bytes) -> dict:
    """Google Cloud status incidents.json (list of incident objects)."""
    data = json.loads(raw)
    active = [i for i in data if not i.get("end")]
    worst = 0
    incidents = []
    for i in active:
        sev = (i.get("status_impact") or i.get("severity") or "").lower()
        worst = max(worst, INDICATOR_LEVELS.get(sev, 1))
        incidents.append({"name": i.get("external_desc") or i.get("service_name", "incident"),
                          "impact": sev or "unknown"})
    return {
        "indicator": {0: "none", 1: "minor", 2: "major", 3: "critical"}.get(worst, "none"),
        "incidents": incidents,
    }


OKTA_RE = re.compile(r'data-id="incidents">\s*(\[.*?\])\s*</span>', re.S)


def parse_okta(raw: bytes) -> dict:
    """Okta embeds a Salesforce-style incident JSON array in the HTML page."""
    html = raw.decode("utf-8", errors="replace")
    m = OKTA_RE.search(html)
    if not m:
        raise ValueError("incidents payload not found in Okta status HTML")
    incidents_raw = json.loads(m.group(1))
    active = []
    for inc in incidents_raw:
        st = (inc.get("Status__c") or "").strip().lower()
        if st in RESOLVED or st == "":
            continue
        text = f'{inc.get("Name", "")} {inc.get("Log__c", "")} {inc.get("Category__c", "")}'
        impact = "major" if re.search(r"outage|down", text, re.I) else "minor"
        active.append({"name": inc.get("Log__c", inc.get("Name", "incident"))[:140],
                       "impact": impact})
    indicator = "none"
    if active:
        indicator = "major" if any(a["impact"] == "major" for a in active) else "minor"
    return {"indicator": indicator, "incidents": active}


SOURCES: dict[str, tuple[str, callable]] = {
    "okta": ("https://status.okta.com", parse_okta),
    "twilio": ("https://status.twilio.com/api/v2/summary.json", parse_atlassian),
    "github": ("https://www.githubstatus.com/api/v2/summary.json", parse_atlassian),
    "stripe": ("https://status.stripe.com/api/v2/summary.json", parse_atlassian),
    "google": ("https://status.cloud.google.com/incidents.json", parse_google),
}

STATE: dict[str, dict] = {}
_LOCK = threading.Lock()


def poll_all() -> None:
    for service, (url, parser) in SOURCES.items():
        result = {"up": 0, "indicator": -1, "incidents": []}
        try:
            parsed = parser(fetch(url))
            result["up"] = 1
            result["indicator"] = INDICATOR_LEVELS.get(
                parsed["indicator"].lower(), -1)
            result["incidents"] = parsed["incidents"]
            if result["incidents"]:
                log.warning("%s: %d ACTIVE incident(s) indicator=%s",
                            service, len(result["incidents"]), parsed["indicator"])
            else:
                log.info("%s: OK indicator=%s", service, parsed["indicator"])
        except Exception as exc:
            log.error("%s: fetch/parse failed: %s", service, exc)
        with _LOCK:
            STATE[service] = result


def render_metrics() -> bytes:
    lines = [
        "# HELP external_status_up Whether the status page source could be fetched.",
        "# TYPE external_status_up gauge",
        "# HELP external_status_indicator 0 none | 1 minor | 2 major | 3 critical | -1 unknown.",
        "# TYPE external_status_indicator gauge",
        "# HELP external_status_incidents_active Number of non-resolved incidents.",
        "# TYPE external_status_incidents_active gauge",
        "# HELP external_status_incident_info Active incident metadata.",
        "# TYPE external_status_incident_info gauge",
    ]
    with _LOCK:
        snapshot = dict(STATE)
    for service, st in sorted(snapshot.items()):
        lines.append(f'external_status_up{{service="{service}"}} {st["up"]}')
        lines.append(f'external_status_indicator{{service="{service}"}} {st["indicator"]}')
        lines.append(f'external_status_incidents_active{{service="{service}"}} {len(st["incidents"])}')
        for inc in st["incidents"]:
            name = inc["name"].replace("\\", "").replace('"', "'")
            impact = inc["impact"].replace('"', "'")
            lines.append(f'external_status_incident_info{{service="{service}",'
                         f'name="{name}",impact="{impact}"}} 1')
    return ("\n".join(lines) + "\n").encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/metrics"):
            body = render_metrics()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/healthz"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args) -> None:  # silence per-request logs
        return


def poller() -> None:
    while True:
        poll_all()
        time.sleep(INTERVAL)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    t = threading.Thread(target=poller, daemon=True)
    t.start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
