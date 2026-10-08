#!/usr/bin/env python3
"""Regenera CHANGELOG.md desde el historial Git (Conventional Commits).
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict

_SKIP_CHANGELOG_CHURN = re.compile(r"^chore\(changelog\):", re.IGNORECASE)


def _skip_subject(subject: str) -> bool:
    return bool(_SKIP_CHANGELOG_CHURN.match(subject.strip()))


def main() -> int:
    output = subprocess.check_output(
        ["git", "log", "--pretty=format:%h%x09%cs%x09%s", "--reverse"],
        text=True,
    ).strip()
    lines = [line for line in output.splitlines() if line.strip()]

    pattern = re.compile(r"^([a-zA-Z]+)(\([^)]+\))?(!)?:\s+(.+)$")
    title = {
        "feat": "Features",
        "fix": "Fixes",
        "perf": "Performance",
        "refactor": "Refactors",
        "docs": "Documentation",
        "test": "Tests",
        "chore": "Chores",
        "ci": "CI",
        "build": "Build",
        "revert": "Reverts",
    }
    ordered_types = ["feat", "fix", "perf", "refactor", "docs", "test", "chore", "ci", "build", "revert"]

    by_date: dict = defaultdict(lambda: defaultdict(list))

    for line in lines:
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        short_sha, cdate, subject = parts
        if _skip_subject(subject):
            continue
        match = pattern.match(subject)
        if not match:
            by_date[cdate]["other"].append((subject, short_sha))
            continue
        commit_type = match.group(1).lower()
        description = match.group(4).strip()
        if commit_type not in title:
            by_date[cdate]["other"].append((subject, short_sha))
            continue
        by_date[cdate][commit_type].append((description, short_sha))

    out: list[str] = []
    out.append("# Changelog")
    out.append("")
    out.append(
        "_Conventional Commits, orden **cronológico por día** (más reciente arriba); "
        "dentro de cada día: Features, Fixes, Chores, etc. "
        "Omite commits `chore(changelog):` (regeneración automática). "
        "Generador: **`scripts/generate_changelog.py`**._"
    )
    out.append("")

    tag_lines = (
        subprocess.check_output(
            ["git", "tag", "-l", "v*", "--sort=-v:refname"],
            text=True,
        )
        .strip()
        .splitlines()
    )
    if tag_lines:
        out.append("## Releases (git tags)")
        out.append("")
        out.append(
            "Cada **`v*`** es una versión **semver** en Git; la fecha es la del **commit** al que apunta el tag."
        )
        out.append("")
        for t in tag_lines[:100]:
            try:
                d = subprocess.check_output(
                    ["git", "log", "-1", "--format=%cs", t, "--"],
                    text=True,
                ).strip()
            except subprocess.CalledProcessError:
                d = "—"
            out.append(f"- **`{t}`** — {d}")
        out.append("")

    tags_by_calendar_date: dict[str, list[str]] = defaultdict(list)
    for t in tag_lines:
        try:
            td = subprocess.check_output(
                ["git", "log", "-1", "--format=%cs", t, "--"],
                text=True,
            ).strip()
            tags_by_calendar_date[td].append(t)
        except subprocess.CalledProcessError:
            continue

    def tag_sort_key(tag: str) -> tuple[int, int, int]:
        m = re.match(r"^v(\d+)\.(\d+)\.(\d+)", tag)
        if m:
            return tuple(int(x) for x in m.groups())
        return (0, 0, 0)

    commit_dates = set(by_date.keys())
    tag_dates = set(tags_by_calendar_date.keys())
    all_dates = sorted(commit_dates | tag_dates, reverse=True)

    for cdate in all_dates:
        day = by_date.get(cdate)
        if day is None:
            day = defaultdict(list)

        has_sections = any(day.get(k) for k in ordered_types) or bool(day.get("other"))
        has_tag_note = cdate in tags_by_calendar_date
        if not has_sections and not has_tag_note:
            continue

        out.append(f"## {cdate}")
        out.append("")
        if has_tag_note:
            day_tags = sorted(tags_by_calendar_date[cdate], key=tag_sort_key, reverse=True)
            joined = ", ".join(f"`{x}`" for x in day_tags)
            out.append(
                f"_**Versión(es) semver** etiquetada(s) con commit en esta fecha: {joined}_"
            )
            out.append("")
        if not has_sections:
            continue
        for key in ordered_types:
            items = day.get(key)
            if not items:
                continue
            out.append(f"### {title[key]}")
            for description, short_sha in items:
                out.append(f"- {description} (`{short_sha}`)")
            out.append("")
        if day.get("other"):
            out.append("### Other")
            for description, short_sha in day["other"]:
                out.append(f"- {description} (`{short_sha}`)")
            out.append("")

    with open("CHANGELOG.md", "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())