"""Unit tests: route template cache (label cardinality control)."""

from __future__ import annotations

from chalicelib.handlers.context import RouteTemplateCache


def build_cache() -> RouteTemplateCache:
    cache = RouteTemplateCache()
    for pattern in ("/", "/hello", "/greet/{name}", "/demo/error"):
        cache.add_pattern(pattern)
    return cache


def test_exact_match():
    cache = build_cache()
    assert cache.route_for("/hello") == "/hello"
    assert cache.route_for("/") == "/"


def test_template_match_and_cache_hit():
    cache = build_cache()
    assert cache.route_for("/greet/alice") == "/greet/{name}"
    assert cache.route_for("/greet/alice") == "/greet/{name}"  # second: cache hit
    assert cache.route_for("/greet/bob") == "/greet/{name}"


def test_length_mismatch_and_segment_mismatch_are_unmatched():
    cache = build_cache()
    assert cache.route_for("/demo/error/extra") == "/demo/error/extra"
    assert cache.route_for("/other") == "/other"


def test_duplicate_patterns_ignored():
    cache = build_cache()
    before = len(cache._patterns)
    cache.add_pattern("/hello")
    assert len(cache._patterns) == before


def test_cardinality_guard_bounded_after_64_distinct_unmatched():
    cache = RouteTemplateCache()
    cache.add_pattern("/known")
    for i in range(64):
        cache.route_for(f"/unknown-{i}")
    assert cache.route_for("/unknown-64") == "unmatched"
    # known and already cached paths still resolve normally
    assert cache.route_for("/known") == "/known"
    assert cache.route_for("/unknown-0") == "/unknown-0"
