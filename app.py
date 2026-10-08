"""AWS Chalice application entrypoint.

Local:  chalice local --port 8000
AWS:    chalice deploy --stage prod
"""

from __future__ import annotations

from chalice import Chalice

from chalicelib.config import get_config
from chalicelib.handlers.context import route_template_cache
from chalicelib.handlers.core import core_routes
from chalicelib.handlers.demo import demo_routes
from chalicelib.logging import configure_logging
from chalicelib.observability.pipeline import middleware

_cfg = get_config()
configure_logging(_cfg.log_level)

app = Chalice(app_name=_cfg.service_name)
app.register_blueprint(core_routes)
app.register_blueprint(demo_routes)

for _pattern in app.routes:
    route_template_cache.add_pattern(_pattern)


@app.middleware("http")
def observability_middleware(request, get_response):
    return middleware(request, get_response)
