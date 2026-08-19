# WaveSpeed

**Author**: WaveSpeedAI
**Version**: 0.0.1
**Type**: tool
**Source**: https://github.com/WaveSpeedAI/dify-wavespeed-plugin
**Contact**: market@wavespeed.ai

Generate images and videos in Dify with [WaveSpeed AI](https://wavespeed.ai) — a fast inference platform serving state-of-the-art media generation models such as ByteDance Seedream (image) and Seedance (video), plus hundreds of other models.

## Setup

1. Create an account at [wavespeed.ai](https://wavespeed.ai).
2. Get your API key from the [API Keys page](https://wavespeed.ai/dashboard/apikeys) of the dashboard.
3. Install this plugin in Dify, open its authorization settings, and paste the key into **WaveSpeed API Key**. The plugin validates the key with a lightweight authenticated call when you save.

## Connection requirements

The plugin makes outbound HTTPS requests to a single fixed endpoint: `https://api.wavespeed.ai`. Authentication uses your API key as a Bearer token. No other network destinations are contacted, and no inbound connections are needed.

## Tools

### Generate Image

Generate an image from a text prompt.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | yes | — | Text description of the image |
| `model` | string | no | `bytedance/seedream-v5.0-pro` | WaveSpeed model id |
| `size` | string | no | model default | Resolution as `width*height`, e.g. `2048*2048` |
| `seed` | number | no | random | Seed for reproducible results |

Returns the generated image(s) plus a JSON payload with the task id and output URLs.

### Generate Video

Generate a video from a text prompt.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | yes | — | Text description of the video |
| `model` | string | no | `bytedance/seedance-2.5/text-to-video` | WaveSpeed model id |
| `duration` | number | no | model default | Video duration in seconds (supported values depend on the model) |

Returns the generated video URL as a link and text message, plus a JSON payload with the task id and output URLs.

## Usage

Use either tool in an Agent, Chatflow, or Workflow application. In a workflow, add the tool node, wire the `prompt` from an upstream variable, and optionally set `model`, `size`/`duration`, or `seed`. Browse the full model catalog at [wavespeed.ai/models](https://wavespeed.ai/models) — any compatible image or video model id can be passed in `model`.

Generation is synchronous from Dify's point of view: the tool submits the task and polls the WaveSpeed API (every second, up to 10 minutes) until the media is ready.

## Privacy

See [PRIVACY.md](PRIVACY.md). The plugin stores nothing; prompts and parameters are sent only to the WaveSpeed API.

## Support

- Email: market@wavespeed.ai
- Website: https://wavespeed.ai
- Source repository: https://github.com/WaveSpeedAI/dify-wavespeed-plugin
