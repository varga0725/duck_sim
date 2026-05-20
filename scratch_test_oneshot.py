import sys
import time

sys.path.insert(0, '/Users/vargaferenc/.hermes/hermes-agent/venv/lib/python3.11/site-packages')
sys.path.insert(0, '/Users/vargaferenc/.hermes/hermes-agent')

import os
os.environ["HERMES_ENABLE_PROJECT_PLUGINS"] = "1"
os.environ["HERMES_PLUGINS_DEBUG"] = "1"

from hermes_cli.oneshot import run_oneshot
from hermes_cli.plugins import discover_plugins, get_plugin_manager

print("Testing plugin discovery:")
discover_plugins(force=True)
manager = get_plugin_manager()
print(f"Loaded plugins: {list(manager._plugins.keys())}")
print(f"Discovered tools: {list(manager._plugin_tool_names)}")

prompt = "Mondd azt hogy 'Szia kacsacska!'"

# First run: will pay import and initialization cost
print("\n--- FIRST RUN ---")
start_time = time.time()
code = run_oneshot(
    prompt=prompt,
    toolsets="duck-robot"
)
elapsed = time.time() - start_time
print(f"First run finished in {elapsed:.3f} seconds with exit code {code}")

# Second run: everything is cached in memory
print("\n--- SECOND RUN ---")
start_time = time.time()
code = run_oneshot(
    prompt=prompt,
    toolsets="duck-robot"
)
elapsed = time.time() - start_time
print(f"Second run finished in {elapsed:.3f} seconds with exit code {code}")
