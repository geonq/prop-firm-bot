"""Run/export the current TradingView Strategy Tester report through CDP.

This script automates the repeatable part of the TradingView workflow:

1. connect to a TradingView desktop/web chart opened with remote debugging;
2. choose a local Pine file and paste it into the Pine Editor;
3. add the pasted strategy to the current chart;
4. set the backtest start date to 2000-01-01 when the input is visible;
5. wait for TradingView to calculate;
6. click the current Strategy Report CSV export;
7. convert the CSV export to XLSX for the local replay pipeline;
8. optionally refresh the strategy registry.

It does not save Pine source in TradingView. Load the intended chart, symbol,
timeframe, and default Strategy Tester layout first, then run:

    .venv/bin/python Analysis/scripts/run_tradingview_backtest.py --launch \
        --output-prefix geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_MNQ1_2026-05-28
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Any

import websocket
from openpyxl import Workbook

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TV_APP_BUNDLE = Path("/Applications/TradingView.app")
TV_APP_BINARY = TV_APP_BUNDLE / "Contents/MacOS/TradingView"
DEFAULT_PORT = 9222
DEFAULT_DOWNLOAD_DIR = PROJECT_ROOT / "TVExports"
DEFAULT_PINE_DIR = PROJECT_ROOT / "PineScripts"
DEFAULT_FROM_DATE = "2000-01-01"
DEFAULT_WAIT_SECONDS = 120
DEFAULT_POST_ADD_WAIT_SECONDS = 60
DEFAULT_UI_TIMEOUT = 90
PARTIAL_SUFFIXES = (".crdownload", ".download", ".tmp")
META_MODIFIER = 4
DEFAULT_GUI_PINE_TAB = (160, 850)
DEFAULT_GUI_EDITOR = (600, 650)
DEFAULT_GUI_STRATEGY_TESTER_TAB = (300, 850)
DEFAULT_CDP_PINE_TAB = (160, 850)
DEFAULT_CDP_EDITOR = (600, 650)
DEFAULT_CDP_STRATEGY_TESTER_TAB = (300, 850)
DEFAULT_CDP_ADD_TO_CHART = (1280, 525)


class TradingViewAutomationError(RuntimeError):
    """Raised when TradingView cannot be controlled safely."""


@dataclass(frozen=True)
class ExportResult:
    csv_path: Path
    xlsx_path: Path | None
    click_result: dict[str, Any]


class CdpClient:
    def __init__(self, websocket_url: str, *, timeout: int = 30) -> None:
        self._ws = websocket.create_connection(websocket_url, timeout=timeout)
        self._ids = count(1)

    def close(self) -> None:
        self._ws.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = next(self._ids)
        self._ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            response = json.loads(self._ws.recv())
            if response.get("id") == request_id:
                if "error" in response:
                    raise TradingViewAutomationError(f"CDP {method} failed: {response['error']}")
                return response


def cdp_json(path: str, *, port: int = DEFAULT_PORT, timeout: float = 2.0) -> Any:
    url = f"http://127.0.0.1:{port}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def cdp_available(*, port: int = DEFAULT_PORT) -> bool:
    try:
        cdp_json("/json/version", port=port)
        return True
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def launch_tradingview(*, port: int = DEFAULT_PORT) -> subprocess.Popen[str]:
    """Launch TradingView the macOS-native way.

    Starting the inner Electron binary directly can leave TradingView on a grey
    shell. `open -na ... --args` lets LaunchServices bootstrap the app bundle
    while still passing the CDP flags.
    """
    if not TV_APP_BUNDLE.exists():
        raise TradingViewAutomationError(f"TradingView app not found: {TV_APP_BUNDLE}")
    return subprocess.Popen(
        [
            "open",
            "-na",
            str(TV_APP_BUNDLE),
            "--args",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def launch_tradingview_binary(*, port: int = DEFAULT_PORT) -> subprocess.Popen[str]:
    if not TV_APP_BINARY.exists():
        raise TradingViewAutomationError(f"TradingView binary not found: {TV_APP_BINARY}")
    return subprocess.Popen(
        [
            str(TV_APP_BINARY),
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def tradingview_running() -> bool:
    result = subprocess.run(["pgrep", "-f", "TradingView"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def quit_tradingview() -> None:
    subprocess.run(
        ["osascript", "-e", 'tell application "TradingView" to quit'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def wait_for_tradingview_exit(*, timeout_seconds: int = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not tradingview_running():
            return
        time.sleep(0.5)
    raise TradingViewAutomationError("TradingView did not exit before relaunch timeout")


def run_osascript(lines: list[str]) -> str:
    command: list[str] = ["osascript"]
    for line in lines:
        command.extend(["-e", line])
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise TradingViewAutomationError(result.stderr.strip() or result.stdout.strip() or "osascript failed")
    return result.stdout.strip()


def activate_tradingview() -> None:
    run_osascript(['tell application "TradingView" to activate'])


def gui_click(x: int, y: int) -> None:
    run_osascript(
        [
            'tell application "System Events"',
            'tell process "TradingView"',
            f"click at {{{x}, {y}}}",
            "end tell",
            "end tell",
        ]
    )


def gui_keystroke(key: str, *, command: bool = False, option: bool = False, control: bool = False) -> None:
    modifiers: list[str] = []
    if command:
        modifiers.append("command down")
    if option:
        modifiers.append("option down")
    if control:
        modifiers.append("control down")
    using = f" using {{{', '.join(modifiers)}}}" if modifiers else ""
    run_osascript(
        [
            'tell application "System Events"',
            'tell process "TradingView"',
            f'keystroke "{key}"{using}',
            "end tell",
            "end tell",
        ]
    )


def gui_key_code(code: int, *, command: bool = False, option: bool = False, control: bool = False) -> None:
    modifiers: list[str] = []
    if command:
        modifiers.append("command down")
    if option:
        modifiers.append("option down")
    if control:
        modifiers.append("control down")
    using = f" using {{{', '.join(modifiers)}}}" if modifiers else ""
    run_osascript(
        [
            'tell application "System Events"',
            'tell process "TradingView"',
            f"key code {code}{using}",
            "end tell",
            "end tell",
        ]
    )


def parse_xy(value: str) -> tuple[int, int]:
    try:
        left, right = value.split(",", 1)
        return int(left), int(right)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected X,Y") from exc


def wait_for_cdp(*, port: int = DEFAULT_PORT, timeout_seconds: int = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if cdp_available(port=port):
            return
        time.sleep(0.5)
    raise TradingViewAutomationError(f"CDP did not become available on port {port}")


def open_chart_url(chart_url: str, *, port: int = DEFAULT_PORT) -> None:
    version = cdp_json("/json/version", port=port)
    browser_ws = version.get("webSocketDebuggerUrl")
    if not browser_ws:
        encoded = urllib.parse.quote(chart_url, safe="")
        cdp_json(f"/json/new?{encoded}", port=port)
        return

    client = CdpClient(browser_ws)
    try:
        client.call("Target.createTarget", {"url": chart_url})
    finally:
        client.close()


def find_chart_page(*, port: int = DEFAULT_PORT, timeout_seconds: int = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_pages: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        pages = cdp_json("/json/list", port=port)
        last_pages = pages
        for page in pages:
            url = page.get("url", "")
            if "tradingview.com/chart" in url and page.get("webSocketDebuggerUrl"):
                return page
        time.sleep(1)
    urls = [page.get("url", "") for page in last_pages]
    raise TradingViewAutomationError(f"No TradingView chart page found on CDP port {port}. Seen URLs: {urls}")


def get_ui_probe(client: CdpClient) -> dict[str, Any]:
    script = r"""
(() => {
  const nodes = [...document.querySelectorAll('*')];
  const visible = nodes.filter((node) => {
    const rect = node.getBoundingClientRect?.();
    const style = window.getComputedStyle?.(node);
    return rect && rect.width > 0 && rect.height > 0 && style && style.visibility !== 'hidden';
  });
  const text = document.body?.innerText || '';
  return {
    title: document.title,
    url: location.href,
    readyState: document.readyState,
    nodeCount: nodes.length,
    visibleCount: visible.length,
    hasPine: /pine editor|pine-editor|pine-editor/i.test(text + ' ' + document.documentElement.innerHTML),
    hasTester: /strategy tester|strategietester|backtesting/i.test(text + ' ' + document.documentElement.innerHTML),
  };
})()
"""
    result = evaluate(client, script)
    return result if isinstance(result, dict) else {"result": result}


def wait_for_chart_ui(client: CdpClient, *, timeout_seconds: int = DEFAULT_UI_TIMEOUT) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    reloaded = False
    last_probe: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_probe = get_ui_probe(client)
        node_count = int(last_probe.get("nodeCount") or 0)
        visible_count = int(last_probe.get("visibleCount") or 0)
        if node_count > 500 and visible_count > 20:
            return last_probe
        if not reloaded and time.monotonic() + 20 < deadline and node_count <= 50:
            client.call("Page.reload", {"ignoreCache": True})
            reloaded = True
        time.sleep(2)
    raise TradingViewAutomationError(
        "TradingView chart UI did not finish loading; still looks like a grey/shell page. "
        f"Last probe: {json.dumps(last_probe, ensure_ascii=False)}"
    )


def evaluate(client: CdpClient, expression: str) -> Any:
    response = client.call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        },
    )
    result = response["result"]["result"]
    if "exceptionDetails" in response["result"]:
        raise TradingViewAutomationError(str(response["result"]["exceptionDetails"]))
    return result.get("value")


def dispatch_shortcut(client: CdpClient, key: str, code: str) -> None:
    params = {"key": key, "code": code, "modifiers": META_MODIFIER}
    client.call("Input.dispatchKeyEvent", {"type": "keyDown", **params})
    client.call("Input.dispatchKeyEvent", {"type": "keyUp", **params})


def dispatch_key(client: CdpClient, key: str, code: str) -> None:
    params = {"key": key, "code": code}
    client.call("Input.dispatchKeyEvent", {"type": "keyDown", **params})
    client.call("Input.dispatchKeyEvent", {"type": "keyUp", **params})


def cdp_click(client: CdpClient, x: int, y: int) -> None:
    client.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    client.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    client.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})


def set_macos_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=True)


def query_click_script(needles: list[str]) -> str:
    needles_json = json.dumps([needle.lower() for needle in needles])
    return f"""
(() => {{
  const needles = {needles_json};
  const nodes = [];
  const visit = (root) => {{
    if (!root) return;
    if (root.querySelectorAll) {{
      for (const node of root.querySelectorAll('*')) {{
        nodes.push(node);
        if (node.shadowRoot) visit(node.shadowRoot);
      }}
    }}
  }};
  visit(document);
  const textOf = (node) => (
    node.innerText ||
    node.textContent ||
    node.getAttribute?.('aria-label') ||
    node.getAttribute?.('title') ||
    node.getAttribute?.('data-name') ||
    ''
  ).trim();
  const visible = (node) => {{
    const rect = node.getBoundingClientRect?.();
    const style = window.getComputedStyle?.(node);
    return rect && rect.width > 0 && rect.height > 0 && style && style.visibility !== 'hidden';
  }};
  const matches = nodes.filter((node) => {{
    if (['HTML', 'BODY'].includes(node.tagName)) return false;
    if (!visible(node)) return false;
    const haystack = textOf(node).toLowerCase();
    return needles.some((needle) => haystack.includes(needle));
  }});
  matches.sort((a, b) => {{
    const ar = a.getBoundingClientRect();
    const br = b.getBoundingClientRect();
    return (ar.width * ar.height) - (br.width * br.height);
  }});
  const el = matches[0];
  if (!el) return {{ok: false, needles}};
  const rect = el.getBoundingClientRect();
  el.click();
  return {{
    ok: true,
    text: textOf(el).slice(0, 200),
    tag: el.tagName,
    rect: [rect.x, rect.y, rect.width, rect.height],
  }};
}})()
"""


def click_by_text(client: CdpClient, needles: list[str]) -> dict[str, Any]:
    result = evaluate(client, query_click_script(needles))
    return result if isinstance(result, dict) else {"ok": False, "result": result}


def close_date_picker_overlay(client: CdpClient) -> dict[str, Any]:
    script = r"""
(() => {
  const nodes = [];
  const visit = (root) => {
    if (!root) return;
    if (root.querySelectorAll) {
      for (const node of root.querySelectorAll('button,[role=button],[data-name],div')) {
        nodes.push(node);
        if (node.shadowRoot) visit(node.shadowRoot);
      }
    }
  };
  visit(document);
  const textOf = (node) => (
    node.innerText ||
    node.textContent ||
    node.getAttribute?.('aria-label') ||
    node.getAttribute?.('title') ||
    node.getAttribute?.('data-name') ||
    ''
  ).trim();
  const visible = (node) => {
    const rect = node.getBoundingClientRect?.();
    const style = window.getComputedStyle?.(node);
    return rect && rect.width > 0 && rect.height > 0 && style && style.visibility !== 'hidden';
  };
  const matches = nodes
    .filter(visible)
    .map((node) => ({node, text: textOf(node), rect: node.getBoundingClientRect()}))
    .filter((item) => item.text.toLowerCase() === 'menü schließen' || item.text.toLowerCase() === 'close menu');
  matches.sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
  const picked = matches[0];
  if (!picked) return {ok: true, stage: 'not_present'};
  picked.node.click();
  return {ok: true, stage: 'closed', text: picked.text, rect: [picked.rect.x, picked.rect.y, picked.rect.width, picked.rect.height]};
})()
"""
    result = evaluate(client, script)
    time.sleep(0.5)
    return result if isinstance(result, dict) else {"ok": False, "result": result}


def focus_pine_editor(client: CdpClient) -> dict[str, Any]:
    click_by_text(client, ["pine editor", "pine-editor", "pine-editor-tab"])
    time.sleep(0.5)
    script = r"""
(() => {
  const nodes = [];
  const visit = (root) => {
    if (!root) return;
    if (root.querySelectorAll) {
      for (const node of root.querySelectorAll('*')) {
        nodes.push(node);
        if (node.shadowRoot) visit(node.shadowRoot);
      }
    }
  };
  visit(document);
  const candidates = [
    '.cm-content',
    '.monaco-editor textarea',
    '.ace_text-input',
    '[contenteditable="true"]',
    'textarea'
  ];
  for (const selector of candidates) {
    const node = nodes.find((candidate) => candidate.matches?.(selector));
    if (!node) continue;
    const rect = node.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) continue;
    node.focus?.();
    node.click?.();
    return {ok: true, selector, rect: [rect.x, rect.y, rect.width, rect.height]};
  }
  return {
    ok: false,
    editors: nodes
      .map((node) => node.className || node.getAttribute?.('data-name') || node.tagName)
      .filter(Boolean)
      .slice(-120),
  };
})()
"""
    result = evaluate(client, script)
    return result if isinstance(result, dict) else {"ok": False, "result": result}


def paste_pine_source(client: CdpClient, pine_path: Path, *, pine_tab: tuple[int, int], editor: tuple[int, int]) -> dict[str, Any]:
    pine_source = pine_path.read_text(encoding="utf-8")
    set_macos_clipboard(pine_source)
    focus_result = focus_pine_editor(client)
    if not focus_result.get("ok"):
        cdp_click(client, *pine_tab)
        time.sleep(0.5)
        cdp_click(client, *editor)
        focus_result = {"ok": True, "selector": "coordinate_fallback", "pine_tab": pine_tab, "editor": editor}
    time.sleep(0.5)
    dispatch_shortcut(client, "a", "KeyA")
    time.sleep(0.2)
    dispatch_shortcut(client, "v", "KeyV")
    time.sleep(1)
    return {"ok": True, "pine": str(pine_path), "chars": len(pine_source), "focus": focus_result}


def add_strategy_to_chart(client: CdpClient, *, timeout_seconds: int = 30, add_button: tuple[int, int]) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    needles = [
        "add to chart",
        "update on chart",
        "auf dem chart aktualisieren",
        "zum chart hinzufügen",
        "auf chart anwenden",
        "add strategy",
        "hinzufügen",
    ]
    last_result: dict[str, Any] = {"ok": False}
    while time.monotonic() < deadline:
        last_result = click_by_text(client, needles)
        if last_result.get("ok"):
            return last_result
        dispatch_shortcut(client, "Enter", "Enter")
        time.sleep(2)
    cdp_click(client, *add_button)
    time.sleep(5)
    return {"ok": True, "stage": "coordinate_fallback", "add_button": add_button, "last_dom_result": last_result}


def open_strategy_report(client: CdpClient, *, timeout_seconds: int = 60) -> dict[str, Any]:
    script = r"""
(() => {
  const textOf = (node) => (
    node.innerText ||
    node.textContent ||
    node.getAttribute?.('aria-label') ||
    node.getAttribute?.('title') ||
    ''
  ).trim();
  const visible = (node) => {
    const rect = node.getBoundingClientRect?.();
    const style = window.getComputedStyle?.(node);
    return rect && rect.width > 0 && rect.height > 0 && style && style.visibility !== 'hidden';
  };
  const buttons = [...document.querySelectorAll('button,[role=button],a,[data-name]')].filter(visible);
  const reportOpen = buttons.find((node) => {
    const text = textOf(node).toLowerCase();
    return (
      text.includes('strategiebericht schließen') ||
      text.includes('strategy report close') ||
      /[0-9]{4}.*[—-].*[0-9]{4}/.test(text) ||
      /[0-9]{1,2}\..*[0-9]{4}/.test(text)
    );
  });
  if (reportOpen) return {ok: true, stage: 'already_open', text: textOf(reportOpen).slice(0, 160)};
  const reportButton = buttons.find((node) => {
    const text = textOf(node).toLowerCase();
    return (
      text.includes('bericht generieren') ||
      text.includes('strategy report') ||
      text.includes('generate report')
    );
  });
  if (!reportButton) {
    return {
      ok: false,
      stage: 'report_button_not_found',
      controls: buttons.map((node) => textOf(node).slice(0, 100)).filter(Boolean).slice(-100),
    };
  }
  const rect = reportButton.getBoundingClientRect();
  reportButton.click();
  return {ok: false, stage: 'clicked_report_button', text: textOf(reportButton), rect: [rect.x, rect.y, rect.width, rect.height]};
})()
"""
    deadline = time.monotonic() + timeout_seconds
    last_result: Any = None
    while time.monotonic() < deadline:
        last_result = evaluate(client, script)
        if isinstance(last_result, dict) and last_result.get("ok"):
            return last_result
        time.sleep(2)
    raise TradingViewAutomationError(f"Could not open Strategy Report: {json.dumps(last_result, ensure_ascii=False)[:3000]}")


def open_date_range_picker(client: CdpClient, *, timeout_seconds: int = 30) -> dict[str, Any]:
    script = r"""
(() => {
  const textOf = (node) => (
    node.innerText ||
    node.textContent ||
    node.getAttribute?.('aria-label') ||
    node.getAttribute?.('title') ||
    ''
  ).trim();
  const visible = (node) => {
    const rect = node.getBoundingClientRect?.();
    const style = window.getComputedStyle?.(node);
    return rect && rect.width > 0 && rect.height > 0 && style && style.visibility !== 'hidden';
  };
  const buttons = [...document.querySelectorAll('button,[role=button],a,[data-name]')].filter(visible);
  const button = buttons.find((node) => {
    const text = textOf(node);
    return /[0-9]{4}.*[—-].*[0-9]{4}/.test(text) || /[0-9]{1,2}\..*[0-9]{4}/.test(text);
  });
  if (!button) {
    return {
      ok: false,
      stage: 'date_range_button_not_found',
      controls: buttons.map((node) => textOf(node).slice(0, 120)).filter(Boolean).slice(-120),
    };
  }
  const rect = button.getBoundingClientRect();
  button.click();
  return {ok: true, text: textOf(button), rect: [rect.x, rect.y, rect.width, rect.height]};
})()
"""
    deadline = time.monotonic() + timeout_seconds
    last_result: Any = None
    while time.monotonic() < deadline:
        last_result = evaluate(client, script)
        if isinstance(last_result, dict) and last_result.get("ok"):
            time.sleep(1)
            return last_result
        time.sleep(1)
    raise TradingViewAutomationError(f"Could not open date range picker: {json.dumps(last_result, ensure_ascii=False)[:3000]}")


def set_backtest_start_date(client: CdpClient, from_date: str) -> dict[str, Any]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", from_date):
        raise ValueError("from_date must be YYYY-MM-DD")
    click_by_text(client, ["strategy tester", "strategietester", "backtesting"])
    time.sleep(0.5)
    open_strategy_report(client)
    open_date_range_picker(client)
    custom_result = click_by_text(client, ["benutzerdefinierter datumsbereich", "custom date range"])
    time.sleep(0.8)
    script = f"""
(() => {{
  const wanted = {json.dumps(from_date)};
  const nodes = [];
  const visit = (root) => {{
    if (!root) return;
    if (root.querySelectorAll) {{
      for (const node of root.querySelectorAll('input')) {{
        nodes.push(node);
        if (node.shadowRoot) visit(node.shadowRoot);
      }}
    }}
  }};
  visit(document);
  const visible = (node) => {{
    const rect = node.getBoundingClientRect?.();
    const style = window.getComputedStyle?.(node);
    return rect && rect.width > 0 && rect.height > 0 && style && style.visibility !== 'hidden';
  }};
  const dateLike = (node) => {{
    const attrs = [
      node.type,
      node.value,
      node.placeholder,
      node.getAttribute('aria-label'),
      node.getAttribute('title'),
      node.getAttribute('inputmode'),
    ].filter(Boolean).join(' ').toLowerCase();
    return attrs.includes('date') || attrs.includes('datum') || /\\d{{4}}-\\d{{2}}-\\d{{2}}/.test(node.value || '');
  }};
  const candidates = nodes.filter((node) => visible(node) && dateLike(node));
  if (!candidates.length) {{
    return {{
      ok: false,
      reason: 'no_visible_date_input',
      visibleInputs: nodes
        .filter(visible)
        .map((node) => ({{
          type: node.type,
          value: node.value,
          placeholder: node.placeholder,
          aria: node.getAttribute('aria-label'),
          title: node.getAttribute('title'),
        }}))
        .slice(0, 50),
    }};
  }}
  candidates.sort((a, b) => {{
    const ar = a.getBoundingClientRect();
    const br = b.getBoundingClientRect();
    const score = (rect) => (
      (rect.x > 450 && rect.x < 1000 ? 0 : 1000) +
      (rect.y > 120 && rect.y < 420 ? 0 : 1000) +
      rect.y
    );
    return score(ar) - score(br);
  }});
  const input = candidates[0];
  const rect = input.getBoundingClientRect();
  input.focus();
  input.select?.();
  const valueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  if (valueSetter) valueSetter.call(input, wanted);
  else input.value = wanted;
  input.dispatchEvent(new Event('input', {{bubbles: true}}));
  input.dispatchEvent(new Event('change', {{bubbles: true}}));
  return {{
    ok: true,
    set: wanted,
    value: input.value,
    rect: [rect.x, rect.y, rect.width, rect.height],
    matched: {{
      type: input.type,
      value: input.value,
      placeholder: input.placeholder,
      aria: input.getAttribute('aria-label'),
      title: input.getAttribute('title'),
      className: String(input.className || '').slice(0, 120),
    }},
    candidates: candidates.length,
  }};
}})()
"""
    result = evaluate(client, script)
    if not isinstance(result, dict) or not result.get("ok"):
        raise TradingViewAutomationError(
            "Could not set Strategy Tester start date. Open the Properties/date-range controls, "
            f"then retry. Details: {json.dumps(result, ensure_ascii=False)[:3000]}"
        )
    # The JS React-prototype setter already fired input/change events. Give React time to
    # re-render before confirming — do not also paste via clipboard; double-setting conflicts
    # when TV reformats on change (e.g. German locale shows "01.01.2000", not "2000-01-01").
    time.sleep(0.4)
    confirm_script = """
(() => {
  const active = document.activeElement;
  return {
    ok: !!active,
    tag: active?.tagName,
    type: active?.type,
    value: active?.value,
    aria: active?.getAttribute?.('aria-label'),
    className: String(active?.className || '').slice(0, 120),
  };
})()
"""
    input_confirm = evaluate(client, confirm_script)
    actual_value = input_confirm.get("value", "") if isinstance(input_confirm, dict) else ""
    print(f"date_input_value={actual_value!r}  (requested {from_date})")
    if not actual_value:
        # Empty means the setter had no effect — raise before submitting garbage
        raise TradingViewAutomationError(
            f"Date input is empty after setting start date to {from_date}. "
            f"Details: {json.dumps(input_confirm, ensure_ascii=False)[:2000]}"
        )

    submit_script = r"""
(() => {
  const nodes = [];
  const visit = (root) => {
    if (!root) return;
    if (root.querySelectorAll) {
      for (const node of root.querySelectorAll('button,[role=button],[data-name],div')) {
        nodes.push(node);
        if (node.shadowRoot) visit(node.shadowRoot);
      }
    }
  };
  visit(document);
  const textOf = (node) => (
    node.innerText ||
    node.textContent ||
    node.getAttribute?.('aria-label') ||
    node.getAttribute?.('title') ||
    node.getAttribute?.('data-name') ||
    ''
  ).trim();
  const visible = (node) => {
    const rect = node.getBoundingClientRect?.();
    const style = window.getComputedStyle?.(node);
    return rect && rect.width > 0 && rect.height > 0 && style && style.visibility !== 'hidden';
  };
  const candidates = nodes
    .filter(visible)
    .map((node) => ({node, text: textOf(node), rect: node.getBoundingClientRect()}))
    .filter((item) => {
      const text = item.text.toLowerCase();
      const dataName = (item.node.getAttribute?.('data-name') || '').toLowerCase();
      return dataName === 'submit-button' || text === 'auswählen' || text === 'select' || text === 'apply';
    });
  candidates.sort((a, b) => {
    const ad = (a.node.getAttribute?.('data-name') || '').toLowerCase() === 'submit-button' ? 0 : 1;
    const bd = (b.node.getAttribute?.('data-name') || '').toLowerCase() === 'submit-button' ? 0 : 1;
    if (ad !== bd) return ad - bd;
    return (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height);
  });
  const picked = candidates[0];
  if (!picked) {
    return {
      ok: false,
      reason: 'submit_not_found',
      controls: nodes.filter(visible).map((node) => textOf(node).slice(0, 80)).filter(Boolean).slice(-80),
    };
  }
  picked.node.click();
  return {ok: true, text: picked.text, rect: [picked.rect.x, picked.rect.y, picked.rect.width, picked.rect.height]};
})()
"""
    submit_result = evaluate(client, submit_script)
    if not isinstance(submit_result, dict) or not submit_result.get("ok"):
        raise TradingViewAutomationError(
            "Could not submit TradingView custom date range after setting the start date. "
            f"Details: {json.dumps(submit_result, ensure_ascii=False)[:3000]}"
        )
    time.sleep(1)
    close_result = close_date_picker_overlay(client)
    time.sleep(2)
    return {
        "ok": True,
        "requested": from_date,
        "custom_range": custom_result,
        "input": result,
        "confirm": input_confirm,
        "submit": submit_result,
        "close": close_result,
    }


def open_strategy_tester(client: CdpClient, tester_tab: tuple[int, int]) -> None:
    click_result = click_by_text(client, ["strategy tester", "strategietester", "backtesting"])
    if not click_result.get("ok"):
        cdp_click(client, *tester_tab)
    time.sleep(0.5)


def inspect_visible_ui(client: CdpClient) -> dict[str, Any]:
    script = r"""
(() => {
  const nodes = [];
  const visit = (root) => {
    if (!root) return;
    if (root.querySelectorAll) {
      for (const node of root.querySelectorAll('*')) {
        nodes.push(node);
        if (node.shadowRoot) visit(node.shadowRoot);
      }
    }
  };
  visit(document);
  const visible = (node) => {
    const rect = node.getBoundingClientRect?.();
    const style = window.getComputedStyle?.(node);
    return rect && rect.width > 0 && rect.height > 0 && style && style.visibility !== 'hidden';
  };
  const textOf = (node) => (
    node.innerText ||
    node.textContent ||
    node.getAttribute?.('aria-label') ||
    node.getAttribute?.('title') ||
    node.getAttribute?.('data-name') ||
    ''
  ).trim();
  const visibleNodes = nodes.filter(visible);
  return {
    title: document.title,
    url: location.href,
    nodeCount: nodes.length,
    visibleCount: visibleNodes.length,
    controls: visibleNodes
      .filter((node) => ['BUTTON', 'A'].includes(node.tagName) || node.getAttribute?.('role') === 'button')
      .map((node) => ({
        tag: node.tagName,
        role: node.getAttribute?.('role'),
        dataName: node.getAttribute?.('data-name'),
        aria: node.getAttribute?.('aria-label'),
        title: node.getAttribute?.('title'),
        text: textOf(node).slice(0, 160),
      }))
      .filter((item) => item.text || item.aria || item.title || item.dataName)
      .slice(-120),
    inputs: visibleNodes
      .filter((node) => node.tagName === 'INPUT' || node.tagName === 'TEXTAREA' || node.getAttribute?.('contenteditable') === 'true')
      .map((node) => ({
        tag: node.tagName,
        type: node.type,
        value: node.value,
        placeholder: node.placeholder,
        aria: node.getAttribute?.('aria-label'),
        title: node.getAttribute?.('title'),
        className: String(node.className || '').slice(0, 120),
      }))
      .slice(-80),
    editorCandidates: visibleNodes
      .filter((node) => (
        node.matches?.('.cm-content') ||
        node.matches?.('.monaco-editor textarea') ||
        node.matches?.('.ace_text-input') ||
        node.getAttribute?.('contenteditable') === 'true' ||
        node.tagName === 'TEXTAREA'
      ))
      .map((node) => ({
        tag: node.tagName,
        className: String(node.className || '').slice(0, 120),
        aria: node.getAttribute?.('aria-label'),
        text: textOf(node).slice(0, 80),
      }))
      .slice(-40),
  };
})()
"""
    result = evaluate(client, script)
    return result if isinstance(result, dict) else {"result": result}


def set_download_behavior(client: CdpClient, download_dir: Path) -> None:
    params = {
        "behavior": "allow",
        "downloadPath": str(download_dir),
        "eventsEnabled": True,
    }
    try:
        client.call("Browser.setDownloadBehavior", params)
    except TradingViewAutomationError:
        client.call("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(download_dir)})


def click_report_export(client: CdpClient, *, timeout_seconds: int = 60) -> dict[str, Any]:
    dispatch_key(client, "Escape", "Escape")
    time.sleep(0.5)
    close_date_picker_overlay(client)
    open_strategy_report(client, timeout_seconds=min(timeout_seconds, 30))
    script = r"""
(() => {
  const textOf = (node) => (
    node.innerText ||
    node.textContent ||
    node.getAttribute('aria-label') ||
    node.getAttribute('title') ||
    node.getAttribute('data-name') ||
    ''
  ).trim();
  const visible = (node) => {
    const rect = node.getBoundingClientRect?.();
    const style = window.getComputedStyle?.(node);
    return rect && rect.width > 0 && rect.height > 0 && style && style.visibility !== 'hidden';
  };
  const candidates = [...document.querySelectorAll('button,[role=button],a,[data-name],div')].filter(visible);
  const clickFirst = (needles) => {
    const matches = candidates.filter((node) => {
      const text = textOf(node).toLowerCase();
      const dataName = (node.getAttribute('data-name') || '').toLowerCase();
      return needles.some((needle) => text.includes(needle) || dataName.includes(needle));
    });
    matches.sort((a, b) => {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      return (ar.width * ar.height) - (br.width * br.height);
    });
    const el = matches[0];
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    el.click();
    return {
      text: textOf(el),
      dataName: el.getAttribute('data-name'),
      rect: [rect.x, rect.y, rect.width, rect.height],
    };
  };

  const exportButton = clickFirst([
    'daten als xlsx herunterladen',
    'xlsx herunterladen',
    'download xlsx',
    'export xlsx',
    'excel',
    'download csv',
    'csv herunterladen',
    'export csv',
    'exportieren',
    'export',
    'csv'
  ]);
  if (exportButton) {
    return {ok: true, stage: 'export_clicked', exportButton};
  }

  // First pass: popup-menu triggers that look report/export related
  let reportMenus = candidates.filter((node) => {
    if (node.getAttribute('aria-haspopup') !== 'menu') return false;
    const rect = node.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    const dn = (node.getAttribute('data-name') || '').toLowerCase();
    const al = (node.getAttribute('aria-label') || '').toLowerCase();
    return dn.includes('report') || dn.includes('export') || dn.includes('more') ||
           al.includes('report') || al.includes('export') || al.includes('more');
  });
  // Broader fallback: any visible popup-menu trigger (no hardcoded coordinates)
  if (!reportMenus.length) {
    reportMenus = candidates.filter((node) => {
      const rect = node.getBoundingClientRect();
      return node.getAttribute('aria-haspopup') === 'menu' && rect.width > 0 && rect.height > 0;
    });
  }
  reportMenus.sort((a, b) => {
    const ar = a.getBoundingClientRect();
    const br = b.getBoundingClientRect();
    return (ar.width * ar.height) - (br.width * br.height);
  });
  const reportMenu = reportMenus[0];
  if (reportMenu) {
    const rect = reportMenu.getBoundingClientRect();
    reportMenu.click();
    return {
      ok: false,
      stage: 'report_context_menu_clicked',
      menu: {
        text: textOf(reportMenu),
        rect: [rect.x, rect.y, rect.width, rect.height],
      },
    };
  }

  return {
    ok: false,
    stage: 'not_found',
    visibleControls: candidates
      .map((node) => textOf(node) || node.getAttribute('data-name') || '')
      .filter(Boolean)
      .slice(-150),
  };
})()
"""
    deadline = time.monotonic() + timeout_seconds
    last_result: Any = None
    while time.monotonic() < deadline:
        last_result = evaluate(client, script)
        if isinstance(last_result, dict) and last_result.get("ok"):
            return last_result
        time.sleep(1)
    if not isinstance(last_result, dict) or not last_result.get("ok"):
        raise TradingViewAutomationError(
            "Could not find TradingView's CSV export control. "
            f"Last UI state: {json.dumps(last_result, ensure_ascii=False)[:4000]}"
        )
    return last_result


def snapshot_downloads(download_dir: Path) -> set[Path]:
    download_dir.mkdir(parents=True, exist_ok=True)
    return {path.resolve() for path in download_dir.iterdir() if path.is_file()}


def wait_for_new_download(
    download_dir: Path,
    before: set[Path],
    *,
    timeout_seconds: int = 120,
) -> Path:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        after = {path.resolve() for path in download_dir.iterdir() if path.is_file()}
        new_files = after - before
        partials = [path for path in new_files if path.suffix in PARTIAL_SUFFIXES]
        complete = [
            path
            for path in new_files
            if path.suffix.lower() in {".csv", ".xlsx"} and not any(path.name.endswith(s) for s in PARTIAL_SUFFIXES)
        ]
        if complete and not partials:
            return max(complete, key=lambda path: path.stat().st_mtime)
        time.sleep(0.5)
    raise TradingViewAutomationError(f"No completed CSV/XLSX download appeared in {download_dir}")


def safe_output_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in count(2):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise AssertionError("unreachable")


def rename_download(path: Path, *, output_prefix: str | None) -> Path:
    if not output_prefix:
        return path
    suffix = path.suffix.lower()
    target = safe_output_path(path.with_name(f"{output_prefix}{suffix}"))
    if path.resolve() == target.resolve():
        return path
    path.rename(target)
    return target


def csv_to_xlsx(csv_path: Path, *, output_path: Path | None = None) -> Path:
    output = output_path or csv_path.with_suffix(".xlsx")
    output = safe_output_path(output)
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = "Liste der Trades"
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            worksheet.append(row)
    workbook.save(output)
    return output


def validate_xlsx(xlsx_path: Path) -> tuple[int, str | None, str | None]:
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.data.tv_trade_audit import load_tv_trade_records_xlsx

    records = load_tv_trade_records_xlsx(xlsx_path)
    if not records:
        return 0, None, None
    return len(records), records[0].entry_time.isoformat(" "), records[-1].exit_time.isoformat(" ")


def list_pine_files(pine_dir: Path) -> list[Path]:
    return sorted(path for path in pine_dir.glob("*.pine") if path.is_file())


def select_pine_file(pine_dir: Path, requested: str | None) -> Path:
    files = list_pine_files(pine_dir)
    if not files:
        raise TradingViewAutomationError(f"No .pine files found in {pine_dir}")
    if requested:
        candidate = Path(requested)
        if not candidate.is_absolute():
            candidate = pine_dir / requested
        if candidate.exists():
            return candidate
        matches = [path for path in files if path.name == requested or path.stem == requested]
        if len(matches) == 1:
            return matches[0]
        raise TradingViewAutomationError(f"Pine file not found or ambiguous: {requested}")
    if len(files) == 1:
        return files[0]

    print("Choose Pine script:")
    for index, path in enumerate(files, start=1):
        print(f"  {index}. {path.name}")
    while True:
        raw = input("Pine #> ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(files):
            return files[int(raw) - 1]
        print(f"Enter a number from 1 to {len(files)}.")


def run_gui_workflow(args: argparse.Namespace) -> ExportResult:
    if not tradingview_running():
        launch_tradingview(port=args.port)
        time.sleep(5)
    activate_tradingview()
    time.sleep(0.8)

    if args.dry_run:
        title = run_osascript(
            [
                'tell application "System Events"',
                'tell process "TradingView" to get {name, position, size} of every window',
                "end tell",
            ]
        )
        print(f"gui_window={title}")
        raise SystemExit(0)

    if args.export_only:
        raise TradingViewAutomationError("GUI fallback does not support --export-only yet. Use CDP mode for export-only.")

    pine_path = select_pine_file(args.pine_dir, args.pine)
    pine_source = pine_path.read_text(encoding="utf-8")
    set_macos_clipboard(pine_source)

    gui_click(*args.gui_pine_tab)
    time.sleep(0.5)
    gui_click(*args.gui_editor)
    time.sleep(0.2)
    gui_keystroke("a", command=True)
    time.sleep(0.2)
    gui_keystroke("v", command=True)
    time.sleep(1)

    # TradingView Pine Editor normally maps Command+Enter to Add to chart.
    gui_key_code(36, command=True)
    time.sleep(2)

    if not args.skip_date:
        gui_click(*args.gui_strategy_tester_tab)
        time.sleep(0.5)
        print(
            "gui_warning=start date cannot be set safely through the opaque default app UI yet; "
            "open date properties manually or run CDP mode."
        )

    if args.wait_seconds > 0:
        print(f"waiting_seconds={args.wait_seconds}")
        time.sleep(args.wait_seconds)

    raise TradingViewAutomationError(
        "GUI fallback pasted/added the Pine, but export still needs CDP or a tested coordinate path. "
        "Rerun with TradingView launched via --force-relaunch for automated export."
    )


def run_registry(*, tv_dir: Path, skip_mc: bool, only_pass: bool) -> dict[str, Any]:
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.pipeline.strategy_registry import build_registry

    return build_registry(
        tv_dir=tv_dir,
        skip_mc=skip_mc,
        only_screened_pass=only_pass,
    )


def export_current_report(args: argparse.Namespace) -> ExportResult:
    has_cdp = cdp_available(port=args.port)
    has_tv = tradingview_running()
    if args.gui or (args.auto_gui and not has_cdp and has_tv):
        return run_gui_workflow(args)

    if args.force_relaunch:
        quit_tradingview()
        wait_for_tradingview_exit()
        launch_tradingview_binary(port=args.port) if args.launch_method == "binary" else launch_tradingview(port=args.port)
    elif args.launch and not has_cdp:
        if has_tv:
            raise TradingViewAutomationError(
                "TradingView is already running without CDP. Quit it first or rerun with --force-relaunch."
            )
        launch_tradingview_binary(port=args.port) if args.launch_method == "binary" else launch_tradingview(port=args.port)
    elif not has_cdp and has_tv:
        raise TradingViewAutomationError(
            "TradingView is open but not controllable through CDP. Use --force-relaunch for full automation, "
            "or --gui for the partial keyboard/clipboard fallback."
        )
    wait_for_cdp(port=args.port, timeout_seconds=args.cdp_timeout)

    if args.chart_url:
        open_chart_url(args.chart_url, port=args.port)

    page = find_chart_page(port=args.port, timeout_seconds=args.page_timeout)
    client = CdpClient(page["webSocketDebuggerUrl"], timeout=args.cdp_timeout)
    try:
        client.call("Runtime.enable")
        client.call("Page.enable")
        ui_probe = wait_for_chart_ui(client, timeout_seconds=args.ui_timeout)
        print(json.dumps({"ui_ready": ui_probe}, ensure_ascii=False, indent=2))
        set_download_behavior(client, args.download_dir)
        if args.dry_run:
            print(json.dumps(inspect_visible_ui(client), ensure_ascii=False, indent=2))
            raise SystemExit(0)

        if not args.export_only:
            pine_path = select_pine_file(args.pine_dir, args.pine)
            paste_result = paste_pine_source(
                client,
                pine_path,
                pine_tab=args.cdp_pine_tab,
                editor=args.cdp_editor,
            )
            print(json.dumps(paste_result, ensure_ascii=False, indent=2))
            add_result = add_strategy_to_chart(
                client,
                timeout_seconds=args.add_timeout,
                add_button=args.cdp_add_to_chart,
            )
            print(json.dumps({"add_to_chart": add_result}, ensure_ascii=False, indent=2))
            if args.post_add_wait_seconds > 0:
                print(f"post_add_wait_seconds={args.post_add_wait_seconds}")
                time.sleep(args.post_add_wait_seconds)
            if not args.skip_date:
                open_strategy_tester(client, args.cdp_strategy_tester_tab)
                date_result = set_backtest_start_date(client, args.from_date)
                print(json.dumps({"start_date": date_result}, ensure_ascii=False, indent=2))
            if args.setup_only:
                raise SystemExit(0)
            if args.wait_seconds > 0:
                print(f"waiting_seconds={args.wait_seconds}")
                time.sleep(args.wait_seconds)

        before = snapshot_downloads(args.download_dir)
        click_result = click_report_export(client, timeout_seconds=args.report_timeout)
        downloaded = wait_for_new_download(args.download_dir, before, timeout_seconds=args.download_timeout)
    finally:
        client.close()

    csv_or_xlsx = rename_download(downloaded, output_prefix=args.output_prefix)
    if csv_or_xlsx.suffix.lower() == ".csv" and not args.no_xlsx:
        xlsx_path = csv_to_xlsx(csv_or_xlsx)
    elif csv_or_xlsx.suffix.lower() == ".xlsx":
        xlsx_path = csv_or_xlsx
    else:
        xlsx_path = None

    return ExportResult(
        csv_path=csv_or_xlsx,
        xlsx_path=xlsx_path,
        click_result=click_result,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--launch", action="store_true", help="Launch TradingView with CDP if it is not already running")
    parser.add_argument("--force-relaunch", action="store_true", help="Quit TradingView first, then relaunch it with CDP")
    parser.add_argument("--launch-method", choices=("open", "binary"), default="open")
    parser.add_argument("--gui", action="store_true", help="Use macOS GUI automation instead of CDP")
    parser.add_argument(
        "--auto-gui",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Fall back to GUI automation when TradingView is already open without CDP",
    )
    parser.add_argument("--chart-url", help="Optional TradingView chart URL to open before exporting")
    parser.add_argument("--download-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument("--pine-dir", type=Path, default=DEFAULT_PINE_DIR)
    parser.add_argument("--pine", help="Pine filename/stem/path. Omit to choose interactively from PineScripts/")
    parser.add_argument("--export-only", action="store_true", help="Only export the current report; do not paste Pine or set dates")
    parser.add_argument("--setup-only", action="store_true", help="Paste/add/date setup, then stop before waiting/exporting")
    parser.add_argument("--from-date", default=DEFAULT_FROM_DATE)
    parser.add_argument("--skip-date", action="store_true", help="Do not try to set the Strategy Tester start date")
    parser.add_argument(
        "--post-add-wait-seconds",
        type=int,
        default=DEFAULT_POST_ADD_WAIT_SECONDS,
        help="Wait after updating the strategy on chart before touching Strategy Tester dates",
    )
    parser.add_argument("--wait-seconds", type=int, default=DEFAULT_WAIT_SECONDS)
    parser.add_argument("--output-prefix", help="Rename the downloaded report to this stem before conversion")
    parser.add_argument("--no-xlsx", action="store_true", help="Do not convert CSV exports to XLSX")
    parser.add_argument("--build-registry", action=argparse.BooleanOptionalAction, default=True, help="Run build_strategy_registry after export")
    parser.add_argument("--skip-mc", action="store_true", help="When building registry, skip Monte Carlo")
    parser.add_argument("--only-pass", action="store_true", help="When building registry, run MC only for pre-MC passes")
    parser.add_argument("--dry-run", action="store_true", help="Print visible controls without clicking export")
    parser.add_argument("--cdp-timeout", type=int, default=30)
    parser.add_argument("--page-timeout", type=int, default=60)
    parser.add_argument("--ui-timeout", type=int, default=DEFAULT_UI_TIMEOUT)
    parser.add_argument("--add-timeout", type=int, default=30)
    parser.add_argument("--report-timeout", type=int, default=60)
    parser.add_argument("--download-timeout", type=int, default=180)
    parser.add_argument("--cdp-pine-tab", type=parse_xy, default=DEFAULT_CDP_PINE_TAB, help="Viewport coordinate X,Y for Pine Editor tab")
    parser.add_argument("--cdp-editor", type=parse_xy, default=DEFAULT_CDP_EDITOR, help="Viewport coordinate X,Y inside Pine Editor text area")
    parser.add_argument("--cdp-add-to-chart", type=parse_xy, default=DEFAULT_CDP_ADD_TO_CHART, help="Viewport coordinate X,Y for Pine Editor Add/Update on chart button")
    parser.add_argument(
        "--cdp-strategy-tester-tab",
        type=parse_xy,
        default=DEFAULT_CDP_STRATEGY_TESTER_TAB,
        help="Viewport coordinate X,Y for Strategy Tester tab",
    )
    parser.add_argument("--gui-pine-tab", type=parse_xy, default=DEFAULT_GUI_PINE_TAB, help="Screen coordinate X,Y for the Pine Editor tab")
    parser.add_argument("--gui-editor", type=parse_xy, default=DEFAULT_GUI_EDITOR, help="Screen coordinate X,Y inside the Pine Editor text area")
    parser.add_argument(
        "--gui-strategy-tester-tab",
        type=parse_xy,
        default=DEFAULT_GUI_STRATEGY_TESTER_TAB,
        help="Screen coordinate X,Y for the Strategy Tester tab",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.download_dir = args.download_dir.resolve()
    args.pine_dir = args.pine_dir.resolve()
    try:
        result = export_current_report(args)
        print(json.dumps(result.click_result, ensure_ascii=False, indent=2))
        print(f"download={result.csv_path}")
        if result.xlsx_path:
            count_, first, last = validate_xlsx(result.xlsx_path)
            print(f"xlsx={result.xlsx_path}")
            print(f"validated_trades={count_} first_entry={first} last_exit={last}")
        if args.build_registry:
            summary = run_registry(tv_dir=args.download_dir, skip_mc=args.skip_mc, only_pass=args.only_pass)
            print(json.dumps(summary, indent=2))
    except TradingViewAutomationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
