"""Click TradingView's current Strategy Report CSV export via CDP."""

from __future__ import annotations

import json
import time
import urllib.request
from itertools import count
from pathlib import Path

import websocket

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_DIR = PROJECT_ROOT / "TVExports"


def cdp_page() -> dict:
    with urllib.request.urlopen("http://127.0.0.1:9222/json/list") as response:
        pages = json.load(response)
    for page in pages:
        if "tradingview.com/chart" in page.get("url", ""):
            return page
    raise SystemExit("No TradingView chart page found on CDP port 9222")


def main() -> None:
    page = cdp_page()
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=10)
    ids = count(1)

    def call(method: str, params: dict | None = None) -> dict:
        request_id = next(ids)
        ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            response = json.loads(ws.recv())
            if response.get("id") == request_id:
                return response

    call("Runtime.enable")
    call(
        "Browser.setDownloadBehavior",
        {
            "behavior": "allow",
            "downloadPath": str(DOWNLOAD_DIR),
            "eventsEnabled": True,
        },
    )
    script = r"""
(() => {
  const els = [...document.querySelectorAll('button,[role=button]')];
  const e = els.find((node) => {
    const text = (
      node.innerText ||
      node.getAttribute('aria-label') ||
      node.getAttribute('title') ||
      ''
    ).toLowerCase();
    return text.includes('csv herunterladen') || text.includes('download csv');
  });
  if (!e) {
    return {
      ok: false,
      texts: els
        .map((node) => (
          node.innerText ||
          node.getAttribute('aria-label') ||
          node.getAttribute('title') ||
          ''
        ).trim())
        .filter(Boolean)
        .slice(-100),
    };
  }
  const rect = e.getBoundingClientRect();
  e.click();
  return {
    ok: true,
    text: e.innerText,
    aria: e.getAttribute('aria-label'),
    title: e.getAttribute('title'),
    rect: [rect.x, rect.y, rect.width, rect.height],
  };
})()
"""
    result = call("Runtime.evaluate", {"expression": script, "returnByValue": True})
    print(json.dumps(result["result"]["result"].get("value"), ensure_ascii=False, indent=2))
    time.sleep(3)
    ws.close()


if __name__ == "__main__":
    main()
