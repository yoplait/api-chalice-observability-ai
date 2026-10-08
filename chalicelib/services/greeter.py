"""Hello World business logic, decoupled from the HTTP layer."""

from __future__ import annotations


def build_greeting(name: str) -> dict:
    return {"message": f"Hello, {name}!", "name": name}
