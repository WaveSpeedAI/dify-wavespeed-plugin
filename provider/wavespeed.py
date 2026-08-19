from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from utils.client import WaveSpeedClient, WaveSpeedError


class WavespeedProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = credentials.get("wavespeed_api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError(
                "WaveSpeed API key is required."
            )
        try:
            WaveSpeedClient(api_key).check_credentials()
        except WaveSpeedError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to validate the WaveSpeed API key: {e}"
            ) from e
