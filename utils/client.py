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
# Per-request timeouts by request type (no overall cap on the wait itself).
# Result queries / read-only GETs are fast; a submit timeout is an ambiguous
# outcome, so it gets more headroom.
GET_TIMEOUT_SECONDS = 30
SUBMIT_TIMEOUT_SECONDS = 60

POLL_MAX_RETRIES = 5
TRANSIENT_HTTP_STATUSES = (429, 500, 502, 503, 504)

TERMINAL_FAILURE_STATUSES = ("failed", "cancelled", "timeout", "deleted")


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
            f"{BASE_URL}{path}", timeout=GET_TIMEOUT_SECONDS
        )
        return self._unwrap(response, context)

    def check_credentials(self) -> None:
        """Cheap authenticated call; raises WaveSpeedError on a bad key."""
        self._get("/api/v3/balance", "Credential check")

    def submit(self, model_id: str, inputs: dict[str, Any]) -> str:
        """Submit a prediction and return its task id."""
        # Submit is single-shot and never retried: on an ambiguous failure the
        # task may already exist (and be billed).
        ambiguous = (
            "The task may already exist. Do not retry blindly; check your"
            " recent predictions first."
        )
        context = f"Submitting to model '{model_id}'"
        try:
            response = self.session.post(
                f"{BASE_URL}/api/v3/{model_id}",
                json=inputs,
                timeout=SUBMIT_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            raise WaveSpeedError(
                f"{context} failed with no confirmed response"
                f" ({type(e).__name__}). {ambiguous}"
            ) from e
        try:
            data = self._unwrap(response, context)
        except WaveSpeedError as e:
            if response.status_code >= 500:
                raise WaveSpeedError(f"{e} {ambiguous}") from e
            raise
        task_id = (data or {}).get("id")
        if not task_id:
            raise WaveSpeedError("The API did not return a prediction id.")
        return task_id

    def _poll_result(self, task_id: str) -> Any:
        """GET the prediction result, tolerating transient errors.

        Retries 429/500/502/503/504 and network errors up to POLL_MAX_RETRIES
        times (delay 1s * (n + 1)). Polling is read-only: never re-submits.
        """
        path = f"/api/v3/predictions/{task_id}/result"
        context = "Fetching prediction result"
        last = ""
        for attempt in range(POLL_MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    f"{BASE_URL}{path}", timeout=GET_TIMEOUT_SECONDS
                )
                if response.status_code not in TRANSIENT_HTTP_STATUSES:
                    return self._unwrap(response, context)
                last = f"HTTP {response.status_code}"
            except requests.RequestException as e:
                last = type(e).__name__
            if attempt < POLL_MAX_RETRIES:
                time.sleep(POLL_INTERVAL_SECONDS * (attempt + 1))
        raise WaveSpeedError(
            f"Could not fetch the prediction result after {POLL_MAX_RETRIES}"
            f" retries ({last}) (task id: {task_id}). The task may still be"
            " running; check it later on the WaveSpeed dashboard."
        )

    def wait(self, task_id: str, timeout: Optional[float] = None) -> dict[str, Any]:
        """Poll until the prediction reaches a terminal status.

        Returns the prediction data on success. Raises WaveSpeedError on
        failed/cancelled/timeout/deleted statuses, or when an explicit ``timeout``
        (seconds) is passed and exceeded. By default there is no overall cap:
        tasks can run for hours, so we wait until a terminal status.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            data = self._poll_result(task_id)
            status = (data or {}).get("status")
            if status == "completed":
                return data
            if status in TERMINAL_FAILURE_STATUSES:
                error = (data or {}).get("error")
                raise WaveSpeedError(
                    f"Prediction {status}{': ' + error if error else ''}"
                    f" (task id: {task_id})"
                )
            if deadline is not None and time.monotonic() > deadline:
                raise WaveSpeedError(
                    f"Prediction still '{status}' after {int(timeout)}s"
                    f" (task id: {task_id}). The task keeps running server-side;"
                    " check it later on the WaveSpeed dashboard."
                )
            time.sleep(POLL_INTERVAL_SECONDS)

    @staticmethod
    def output_urls(prediction: dict[str, Any]) -> list[str]:
        outputs = prediction.get("outputs") or []
        return [item for item in outputs if isinstance(item, str)]
