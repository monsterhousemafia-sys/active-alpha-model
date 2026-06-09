"""Redirect validation for Trading 212 demo read-only HTTP client."""
from __future__ import annotations

import urllib.error
import urllib.request

from integrations.trading212.t212_environment_guard import validate_redirect_target
from integrations.trading212.t212_request_allowlist import validate_method


class T212RedirectBlockedError(urllib.error.HTTPError):
    pass


class T212RedirectGuardHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_redirect_target(newurl)
        validate_method(req.get_method(), newurl)
        return urllib.request.HTTPRedirectHandler.redirect_request(
            self, req, fp, code, msg, headers, newurl
        )


class T212NoRedirectHandler(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):
        if 300 <= response.status < 400:
            location = response.headers.get("Location", "")
            validate_redirect_target(location)
            raise T212RedirectBlockedError(
                response.url,
                response.status,
                f"Redirect requires revalidation: {location}",
                response.headers,
                None,
            )
        return response
