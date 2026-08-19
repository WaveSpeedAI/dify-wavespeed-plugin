from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.client import WaveSpeedClient, WaveSpeedError

DEFAULT_MODEL = "bytedance/seedance-2.5/text-to-video"


class GenerateVideoTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        prompt = (tool_parameters.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Please provide a prompt describing the video.")

        model = (tool_parameters.get("model") or DEFAULT_MODEL).strip()
        inputs: dict[str, Any] = {"prompt": prompt}

        duration = tool_parameters.get("duration")
        if duration is not None and str(duration).strip() != "":
            inputs["duration"] = int(duration)

        client = WaveSpeedClient(self.runtime.credentials["wavespeed_api_key"])
        try:
            task_id = client.submit(model, inputs)
            prediction = client.wait(task_id)
        except WaveSpeedError as e:
            raise ValueError(str(e)) from e

        urls = client.output_urls(prediction)
        if not urls:
            raise ValueError(
                f"Generation completed but returned no video URL (task id: {task_id})."
            )

        for url in urls:
            yield self.create_link_message(url)
        yield self.create_text_message("\n".join(urls))
        yield self.create_json_message(
            {
                "task_id": task_id,
                "model": model,
                "outputs": urls,
            }
        )
