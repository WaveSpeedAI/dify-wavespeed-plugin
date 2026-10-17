from dify_plugin import Plugin, DifyPluginEnv

# In serverless mode the SDK closes a tool invocation that streams nothing for
# MAX_REQUEST_TIMEOUT seconds. The tools only reply once the task finishes, and
# tasks can run for hours, so the idle limit must be far longer than the default.
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=86400))

if __name__ == '__main__':
    plugin.run()
