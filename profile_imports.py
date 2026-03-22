import time

start_all = time.time()
start = time.time()
import os
import sys
print(f"Built-ins: {time.time() - start:.3f}s")

start = time.time()
import webview
print(f"webview: {time.time() - start:.3f}s")

start = time.time()
import el_sbobinator.app_webview
print(f"el_sbobinator.app_webview: {time.time() - start:.3f}s")

print(f"Total time to start: {time.time() - start_all:.3f}s")
