# Privacy Policy — WaveSpeed Dify Plugin

This plugin connects Dify to the WaveSpeed AI API (https://api.wavespeed.ai) to generate images and videos.

## What data is sent to WaveSpeed

- Your WaveSpeed API key, sent as an `Authorization: Bearer` header to authenticate requests.
- The generation inputs you provide in a tool call (prompt text and optional parameters such as model id, size, seed, and duration). These are sent to the WaveSpeed API to run the generation and are handled according to the WaveSpeed privacy policy: https://wavespeed.ai/privacy

## What the plugin collects or stores

- The plugin itself does not collect, store, log, or retain any user data. It keeps no state: inputs are forwarded to the WaveSpeed API, results (media URLs) are returned to Dify, and nothing is persisted by the plugin.
- The plugin does not send any data to third parties other than the WaveSpeed API endpoint above.
- The API key is stored by Dify's credential storage, not by this plugin.

## Contact

Questions about privacy: support@wavespeed.ai

Full WaveSpeed privacy policy: https://wavespeed.ai/privacy
