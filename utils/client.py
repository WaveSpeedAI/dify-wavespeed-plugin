"""Minimal WaveSpeed AI REST client.

Uses only documented v3 endpoints:
- POST /api/v3/{model_id}                 submit a prediction
- GET  /api/v3/predictions/{id}/result    poll a prediction
- GET  /api/v3/balance                    lightweight authenticated call for
                                          credential validation

Every response carries the platform envelope {"code": 200, "message": ...,
"data": ...}; any other code is surfaced as an error with the platform's
message so users see actionable text instead of bare HTTP statuses.
"""

import os
import platform
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

BASE_URL = "https://api.wavespeed.ai"
DEFAULT_CLIENT_NAME = "dify-wavespeed-plugin"
POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 30

TERMINAL_FAILURE_STATUSES = ("failed", "cancelled", "timeout")


class WaveSpeedError(Exception):
    """Raised when the WaveSpeed API reports an error."""


def _plugin_version() -> str:
    """Read the plugin version from manifest.yaml."""
    try:
        manifest = Path(__file__).resolve().parent.parent / "manifest.yaml"
        match = re.search(
            r"^version:\s*(\S+)", manifest.read_text(encoding="utf-8"), re.MULTILINE
        )
        if match:
            return match.group(1)
    except OSError:
        pass
    return "unknown"


def _client_os() -> str:
    """OS identifier using the desktop client's vocabulary (darwin/linux/win32)."""
    system = platform.system().lower()
    return "win32" if system == "windows" else (system or "unknown")


def _attribution_headers() -> dict[str, str]:
    """Channel-attribution headers sent with every API request.

    WAVESPEED_CLIENT_NAME overrides the default name so wrapper channels can
    brand themselves without code changes.
    """
    return {
        "X-Client-Name": os.environ.get("WAVESPEED_CLIENT_NAME") or DEFAULT_CLIENT_NAME,
        "X-Client-Version": _plugin_version(),
        "X-Client-OS": _client_os(),
    }


class WaveSpeedClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise WaveSpeedError("WaveSpeed API key is required.")
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {api_key}", **_attribution_headers()}
        )

    def _unwrap(self, response: requests.Response, context: str) -> Any:
        try:
            body = response.json()
        except ValueError:
            body = None
        if not response.ok:
            detail = ""
            if isinstance(body, dict) and body.get("message"):
                code = body.get("error_code")
                detail = f"{body['message']} [{code}]" if code else str(body["message"])
            raise WaveSpeedError(
                detail or f"{context} failed: HTTP {response.status_code}"
            )
        if not isinstance(body, dict):
            raise WaveSpeedError(f"{context} returned an unexpected response.")
        if body.get("code") != 200:
            raise WaveSpeedError(
                body.get("message") or f"{context} returned code {body.get('code')}"
            )
        return body.get("data")

    def _get(self, path: str, context: str) -> Any:
        response = self.session.get(
            f"{BASE_URL}{path}", timeout=REQUEST_TIMEOUT_SECONDS
        )
        return self._unwrap(response, context)

    def check_credentials(self) -> None:
        """Cheap authenticated call; raises WaveSpeedError on a bad key."""
        self._get("/api/v3/balance", "Credential check")

    def submit(self, model_id: str, inputs: dict[str, Any]) -> str:
        """Submit a prediction and return its task id."""
        response = self.session.post(
            f"{BASE_URL}/api/v3/{model_id}",
            json=inputs,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        data = self._unwrap(response, f"Submitting to model '{model_id}'")
        task_id = (data or {}).get("id")
        if not task_id:
            raise WaveSpeedError("The API did not return a prediction id.")
        return task_id

    def wait(self, task_id: str, timeout: Optional[float] = None) -> dict[str, Any]:
        """Poll until the prediction reaches a terminal status.

        Returns the prediction data on success. Raises WaveSpeedError on
        failed/cancelled/timeout statuses or when the wait limit is hit.
        """
        deadline = time.monotonic() + (timeout or POLL_TIMEOUT_SECONDS)
        while True:
            data = self._get(
                f"/api/v3/predictions/{task_id}/result", "Fetching prediction result"
            )
            status = (data or {}).get("status")
            if status == "completed":
                return data
            if status in TERMINAL_FAILURE_STATUSES:
                error = (data or {}).get("error")
                raise WaveSpeedError(
                    f"Prediction {status}{': ' + error if error else ''}"
                    f" (task id: {task_id})"
                )
            if time.monotonic() > deadline:
                raise WaveSpeedError(
                    f"Prediction still '{status}' after {int(timeout or POLL_TIMEOUT_SECONDS)}s"
                    f" (task id: {task_id}). The task keeps running server-side;"
                    " check it later on the WaveSpeed dashboard."
                )
            time.sleep(POLL_INTERVAL_SECONDS)

    @staticmethod
    def output_urls(prediction: dict[str, Any]) -> list[str]:
        outputs = prediction.get("outputs") or []
        return [item for item in outputs if isinstance(item, str)]
