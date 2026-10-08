"""Minimal in-process Prometheus-style metrics registry (stdlib only).

Why not prometheus_client: we keep runtime dependencies to chalice alone and
stay compatible with AWS Lambda. On Lambda these counters live per execution
environment; the supported path for aggregating them is OpenTelemetry /
CloudWatch (see docs/observability.md). Locally, `chalice local` keeps a
single long-lived process so /metrics is scrapeable by Prometheus.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _fmt_labels(label_names: tuple[str, ...], label_values: tuple[str, ...]) -> str:
    pairs = ",".join(f'{n}="{v}"' for n, v in zip(label_names, label_values))
    return "{" + pairs + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Counter:
    def __init__(self, name: str, help_text: str, label_names: tuple[str, ...]):
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, labels: tuple[str, ...], amount: float = 1.0) -> None:
        with self._lock:
            self._values[labels] += amount

    def render(self, out: list[str]) -> None:
        out.append(f"# HELP {self.name} {self.help_text}")
        out.append(f"# TYPE {self.name} counter")
        with self._lock:
            items = sorted(self._values.items())
        for label_values, value in items:
            escaped = tuple(_escape(v) for v in label_values)
            out.append(f"{self.name}{_fmt_labels(self.label_names, escaped)} {value}")


class Histogram:
    def __init__(self, name: str, help_text: str, label_names: tuple[str, ...], buckets: tuple[float, ...]):
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self.buckets = buckets
        self._counts: dict[tuple[str, ...], list[int]] = {}
        self._sums: dict[tuple[str, ...], float] = defaultdict(float)
        self._totals: dict[tuple[str, ...], int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, labels: tuple[str, ...], value: float) -> None:
        with self._lock:
            if labels not in self._counts:
                self._counts[labels] = [0] * len(self.buckets)
            counts = self._counts[labels]
            for i, upper in enumerate(self.buckets):
                if value <= upper:
                    counts[i] += 1
            self._sums[labels] += value
            self._totals[labels] += 1

    def render(self, out: list[str]) -> None:
        out.append(f"# HELP {self.name} {self.help_text}")
        out.append(f"# TYPE {self.name} histogram")
        with self._lock:
            items = sorted(self._counts.items())
            sums = dict(self._sums)
            totals = dict(self._totals)
        for label_values, cumulative in items:
            for upper, count in zip(self.buckets, cumulative):
                le = f"{upper:g}"
                out.append(
                    f"{self.name}_bucket"
                    f'{_fmt_labels(self.label_names + ("le",), label_values + (le,))} {count}'
                )
            escaped = tuple(_escape(v) for v in label_values)
            out.append(
                f"{self.name}_count{_fmt_labels(self.label_names, escaped)} {totals[label_values]}"
            )
            out.append(f"{self.name}_sum{_fmt_labels(self.label_names, escaped)} {sums[label_values]:g}")


class MetricsRegistry:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.requests_total = Counter(
            "chalice_http_requests_total",
            "HTTP requests processed, labeled by normalized route, method and status class.",
            ("route", "method", "status"),
        )
        self.request_duration = Histogram(
            "chalice_http_request_duration_seconds",
            "HTTP request duration in seconds.",
            ("route", "method"),
            DURATION_BUCKETS,
        )
        self.errors_total = Counter(
            "chalice_http_errors_total",
            "Unhandled application errors (HTTP 5xx).",
            ("route",),
        )

    def observe_request(self, route: str, method: str, status: int, duration: float) -> None:
        status_class = f"{status // 100}xx"
        self.requests_total.inc((route, method, status_class))
        self.request_duration.observe((route, method), duration)
        if status >= 500:
            self.errors_total.inc((route,))

    def render(self) -> str:
        out: list[str] = [
            "# HELP chalice_uptime_seconds Seconds since this process started.",
            "# TYPE chalice_uptime_seconds gauge",
            f"chalice_uptime_seconds {time.time() - self.started_at:g}",
        ]
        self.requests_total.render(out)
        self.request_duration.render(out)
        self.errors_total.render(out)
        return "\n".join(out) + "\n"


REGISTRY = MetricsRegistry()
