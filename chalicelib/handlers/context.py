"""Route-template cache: collapses concrete paths (/greet/alice) into their
declared template (/greet/{name}) so Prometheus label cardinality stays
bounded regardless of user input."""

from __future__ import annotations


class RouteTemplateCache:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._patterns: list[tuple[str, list[str]]] = []

    def add_pattern(self, pattern: str) -> None:
        if pattern not in {p for p, _ in self._patterns}:
            self._patterns.append((pattern, pattern.strip("/").split("/")))

    def route_for(self, path: str) -> str:
        if path in self._cache:
            return self._cache[path]
        parts = path.strip("/").split("/")
        for pattern, pat_parts in self._patterns:
            if len(pat_parts) != len(parts):
                continue
            if all(
                seg == actual or (seg.startswith("{") and seg.endswith("}"))
                for seg, actual in zip(pat_parts, parts)
            ):
                self._cache[path] = pattern
                return pattern
        # Unknown paths (404 probes, scanners): keep cardinality bounded.
        if len(self._cache) >= 64:
            return "unmatched"
        self._cache[path] = path
        return path


route_template_cache = RouteTemplateCache()
