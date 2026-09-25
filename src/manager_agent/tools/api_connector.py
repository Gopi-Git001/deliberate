"""Generic HTTP API connector. Auth via env — never hardcode secrets."""

from __future__ import annotations

import os

import httpx
from langchain_core.tools import tool

from manager_agent.config import get_settings

_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


@tool
def api_connector(
    method: str,
    url: str,
    body: str = "",
    auth_env_var: str = "",
    header_name: str = "Authorization",
    header_prefix: str = "Bearer ",
) -> str:
    """Call an external HTTP API.

    For auth, pass the NAME of an env var that holds the token (never the token
    itself). Only env vars listed in API_CONNECTOR_ALLOWED_ENV_VARS may be used.
    """
    method = method.upper()
    if method not in _METHODS:
        return f"Unsupported method {method!r}; use one of {sorted(_METHODS)}."
    if not url.lower().startswith(("http://", "https://")):
        return "URL must start with http:// or https://"
    headers: dict[str, str] = {"Accept": "application/json"}
    if auth_env_var:
        if auth_env_var not in get_settings().allowed_env_vars():
            return (
                f"Env var {auth_env_var!r} is not in API_CONNECTOR_ALLOWED_ENV_VARS; "
                "refusing to send it."
            )
        token = os.environ.get(auth_env_var, "")
        if not token:
            return f"Env var {auth_env_var!r} is empty or unset."
        headers[header_name] = f"{header_prefix}{token}"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(
                method,
                url,
                content=body.encode() if body else None,
                headers=headers,
            )
        return f"status={resp.status_code}\n{resp.text[:4000]}"
    except Exception as exc:  # noqa: BLE001
        return f"api_connector error: {exc}"
