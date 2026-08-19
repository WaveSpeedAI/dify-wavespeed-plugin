from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.client import WaveSpeedClient, WaveSpeedError

DEFAULT_MODEL = "bytedance/seedream-v5.0-pro"


class GenerateImageTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        prompt = (tool_parameters.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Please provide a prompt describing the image.")

        model = (tool_parameters.get("model") or DEFAULT_MODEL).strip()
        inputs: dict[str, Any] = {"prompt": prompt}

        size = (tool_parameters.get("size") or "").strip()
        if size:
            inputs["size"] = size

        seed = tool_parameters.get("seed")
        if seed is not None and str(seed).strip() != "":
            inputs["seed"] = int(seed)

        client = WaveSpeedClient(self.runtime.credentials["wavespeed_api_key"])
        try:
            task_id = client.submit(model, inputs)
            prediction = client.wait(task_id)
        except WaveSpeedError as e:
            raise ValueError(str(e)) from e

        urls = client.output_urls(prediction)
        if not urls:
            raise ValueError(
                f"Generation completed but returned no image URL (task id: {task_id})."
            )

        for url in urls:
            yield self.create_image_message(url)
        yield self.create_json_message(
            {
                "task_id": task_id,
                "model": model,
                "outputs": urls,
            }
        )
