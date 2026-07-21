#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import urlopen


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "automation_config.json"
STATE_PATH = BASE_DIR / ".automation_state.json"
CACHE_DIR = BASE_DIR / ".automation_cache"


DEFAULT_TARGET_CHATS = [
    "oc_4f5979586c9fbb62e57da5cbf1b6dc06",
    "oc_faff39e61d6f6f61117e5c7c47e350b9",
    "oc_feea11a61c042d4938dc2bfbc368ecaa",
    "oc_72fd177739021fa79490191476ec52f3",
    "oc_f8b87db17911b7e088a0115bd803396b",
    "oc_80e57dbda4baa5f9470e6517cef84ac4",
    "oc_f194d9459b56af6cef4e1074bfb10faa",
    "oc_845f65876a01f56fabf931edd6424d1a",
]


def default_state() -> dict[str, Any]:
    return {
        "running": False,
        "active_action": None,
        "cancel_requested": False,
        "cancel_reason": None,
        "last_scan_at": None,
        "last_morning_date": None,
        "last_morning_dry_run_date": None,
        "last_evening_date": None,
        "last_evening_dry_run_date": None,
        "chat_hashes": {},
        "chat_contents": {},
        "discord_last_message_ids": {},
        "last_sent_messages": {},
        "last_provider_run_at": None,
        "provider_runs": [],
        "recent_prompt_hashes": {},
        "initialized_chats": False,
        "last_match": None,
        "codex_running": False,
        "codex_started_at": None,
        "codex_project_path": None,
        "codex_last_status": None,
        "codex_last_finished_at": None,
        "codex_output": [],
        "codex_trigger_text": None,
        "codex_prompt": None,
        "codex_result_summary": None,
    }


def normalize_cli_command(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        return shlex.split(text)[0]
    except ValueError:
        parts = text.split()
        return parts[0] if parts else ""


def discover_codex_path(configured_value: str = "") -> str:
    normalized = normalize_cli_command(configured_value)
    candidate_names = [normalized, "codex"]
    candidate_names = [candidate for candidate in candidate_names if candidate]
    for candidate in candidate_names:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        candidate_path = Path(candidate).expanduser()
        if candidate_path.is_file() and os.access(candidate_path, os.X_OK):
            return str(candidate_path)
    fallback_paths = [
        Path("/Users/mac/.vscode/extensions/openai.chatgpt-26.623.42026-darwin-arm64/bin/macos-aarch64/codex"),
        Path.home() / ".vscode/extensions/openai.chatgpt-26.623.42026-darwin-arm64/bin/macos-aarch64/codex",
    ]
    fallback_paths.extend(
        sorted(
            Path.home().glob(".vscode/extensions/openai.chatgpt-*/bin/macos-aarch64/codex"),
            reverse=True,
        )
    )
    for fallback in fallback_paths:
        if fallback.is_file() and os.access(fallback, os.X_OK):
            return str(fallback)
    return normalized


def discover_gemini_path(configured_value: str = "") -> str:
    normalized = normalize_cli_command(configured_value)
    candidate_names = [normalized, "gemini"]
    candidate_names = [candidate for candidate in candidate_names if candidate]
    for candidate in candidate_names:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        candidate_path = Path(candidate).expanduser()
        if candidate_path.is_file() and os.access(candidate_path, os.X_OK):
            return str(candidate_path)
    fallback_paths = [
        Path("/opt/homebrew/bin/gemini"),
        Path.home() / ".npm-global/bin/gemini",
    ]
    for fallback in fallback_paths:
        if fallback.is_file() and os.access(fallback, os.X_OK):
            return str(fallback)
    return normalized


def discover_cursor_path(configured_value: str = "") -> str:
    normalized = normalize_cli_command(configured_value)
    candidate_names = [normalized, "cursor-agent", "agent", "cursor"]
    candidate_names = [candidate for candidate in candidate_names if candidate]
    for candidate in candidate_names:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        candidate_path = Path(candidate).expanduser()
        if candidate_path.is_file() and os.access(candidate_path, os.X_OK):
            return str(candidate_path)
    fallback_paths = [
        Path.home() / ".local/share/cursor-agent/versions",
        Path("/Applications/Cursor.app/Contents/Resources/app/bin/cursor"),
    ]
    versions_dir = fallback_paths[0]
    if versions_dir.is_dir():
        version_bins = sorted(versions_dir.glob("*/cursor-agent"), reverse=True)
        for candidate in version_bins:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    app_bin = fallback_paths[1]
    if app_bin.is_file() and os.access(app_bin, os.X_OK):
        return str(app_bin)
    return normalized


@dataclass
class AutomationConfig:
    project_path: str = "/Users/mac/Desktop/waansaung/delivery-app-backend"
    report_chat_id: str = "oc_9163bbd749c0fb104770e12f6f46ca94"
    codex_result_chat_id: str = "oc_86aa16e264f9c03ce99ec7ad7e0c8867"
    evening_report_chat_id: str = ""
    target_chats: list[str] = field(default_factory=lambda: DEFAULT_TARGET_CHATS.copy())
    dm_target_id: str = ""
    keywords: list[str] = field(
        default_factory=lambda: ["backend", "api", "query", "fix", "bug", "@williams kositt"]
    )
    work_start: str = "08:10"
    work_end: str = "16:30"
    morning_report_time: str = "08:10"
    evening_report_time: str = "16:30"
    scan_interval_seconds: int = 300
    morning_message: str = "Ready to work"
    dry_run: bool = True
    auto_push: bool = False
    ignore_first_scan: bool = True
    read_source: str = "ui"
    send_source: str = "ui"
    lark_api_host: str = "https://open.larksuite.com"
    lark_applink_host: str = "https://applink.larksuite.com"
    lark_app_id: str = field(default_factory=lambda: os.environ.get("LARK_APP_ID", ""))
    lark_app_secret: str = field(default_factory=lambda: os.environ.get("LARK_APP_SECRET", ""))
    lark_api_page_size: int = 20
    discord_bot_token: str = field(default_factory=lambda: os.environ.get("DISCORD_BOT_TOKEN", ""))
    discord_prompt_channel_id: str = ""
    discord_api_host: str = "https://discord.com/api/v10"
    discord_read_limit: int = 25
    discord_latest_message_only: bool = True
    codex_timeout_seconds: int = 600
    stop_hotkey: str = "control+option+s"
    provider: str = "codex"
    cursor_path: str = "cursor-agent"
    cursor_model: str = ""
    gemini_path: str = "gemini"
    gemini_model: str = "gemini-3.5-flash"
    auto_switch_to_gemini_on_codex_limit: bool = True
    min_run_interval_seconds: int = 1200
    max_runs_per_day: int = 6
    prompt_dedup_window_seconds: int = 43200
    max_prompt_chars: int = 3500
    codex_prompt_prefix: str = (
        "Review these Lark messages and do only the backend/API/logic work requested. "
        "Keep the change scoped and run relevant checks. "
        "If you make changes, prepare them clearly for git commit/push. "
        "Write the final result in concise Myanmar language using a Codex-UI style answer. "
        "Rules for the final answer: "
        "start with the direct answer first; "
        "use short sections only when needed such as 'Code အရ:' and 'ဆိုလိုတာက:'; "
        "keep identifiers like table names, fields, routes, and files in backticks; "
        "use flat bullet points; "
        "do not include logs, timestamps, tokens used, internal notes, or repeated text."
    )
    commit_message: str = "auto(backend): implement from lark trigger"
    codex_path: str = "codex"


class LogBuffer:
    def __init__(self, limit: int = 500) -> None:
        self._items: deque[dict[str, str]] = deque(maxlen=limit)
        self._lock = threading.Lock()

    def add(self, message: str, level: str = "info") -> None:
        entry = {
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": message,
        }
        with self._lock:
            self._items.append(entry)
        print(f"[{entry['at']}] {level.upper()}: {message}", flush=True)

    def list(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self._items)


class AutomationState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not STATE_PATH.exists():
            return default_state()
        try:
            state = default_state()
            state.update(json.loads(STATE_PATH.read_text()))
            return state
        except (OSError, json.JSONDecodeError):
            return default_state()

    def save(self) -> None:
        with self._lock:
            STATE_PATH.write_text(json.dumps(self.data, indent=2, sort_keys=True))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self.data))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self.data[key] = value
        self.save()

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self.data.update(values)
        self.save()


def load_config() -> AutomationConfig:
    if not CONFIG_PATH.exists():
        config = AutomationConfig()
        config.codex_path = discover_codex_path(config.codex_path) or "codex"
        config.cursor_path = discover_cursor_path(config.cursor_path) or "cursor-agent"
        config.gemini_path = discover_gemini_path(config.gemini_path) or "gemini"
        save_config(config)
        return config

    raw = json.loads(CONFIG_PATH.read_text())
    if "message_source" in raw and "read_source" not in raw:
        raw["read_source"] = raw.pop("message_source")
    if "dm_target_id" not in raw:
        raw["dm_target_id"] = ""
    if "send_source" not in raw:
        raw["send_source"] = "ui"
    if raw.get("read_source") == "api_dm" and raw.get("dm_target_id"):
        raw["read_source"] = "ui"
        raw["target_chats"] = [raw["dm_target_id"]]
    defaults = asdict(AutomationConfig())
    defaults.update(raw)
    config = AutomationConfig(**defaults)
    config.codex_path = discover_codex_path(config.codex_path) or "codex"
    config.cursor_path = discover_cursor_path(config.cursor_path) or "cursor-agent"
    config.gemini_path = discover_gemini_path(config.gemini_path) or "gemini"
    return config


def save_config(config: AutomationConfig) -> None:
    CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2, sort_keys=True))


def parse_hhmm(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Invalid time: {value}")
    return hour, minute


def is_after_or_equal(now: datetime, hhmm: str) -> bool:
    hour, minute = parse_hhmm(hhmm)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now >= target


def is_before(now: datetime, hhmm: str) -> bool:
    hour, minute = parse_hhmm(hhmm)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now < target


class LarkAutomation:
    def __init__(self, config: AutomationConfig, state: AutomationState, logs: LogBuffer) -> None:
        self.config = config
        self.state = state
        self.logs = logs
        self._action_lock = threading.Lock()
        self._tenant_token: str | None = None
        self._tenant_token_expires_at = 0.0

    def refresh_config(self, config: AutomationConfig) -> None:
        self.config = config

    def clear_cancel(self) -> None:
        self.state.update({"cancel_requested": False, "cancel_reason": None})

    def should_skip_duplicate_send(self, destination_id: str, message: str, window_seconds: int = 900) -> bool:
        normalized = "\n".join(line.rstrip() for line in message.strip().splitlines()).strip()
        if not normalized:
            return False
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        now = time.time()
        snapshot = self.state.snapshot()
        sent_map = dict(snapshot.get("last_sent_messages", {}))
        entry = sent_map.get(destination_id)
        if isinstance(entry, dict):
            sent_at = float(entry.get("at", 0) or 0)
            if entry.get("hash") == digest and now - sent_at <= window_seconds:
                self.logs.add(
                    f"Skipped duplicate outbound message to {destination_id} within {window_seconds}s window.",
                    "warn",
                )
                return True
        sent_map[destination_id] = {"hash": digest, "at": now}
        self.state.set("last_sent_messages", sent_map)
        return False

    def should_skip_provider_run(self, trigger_text: str) -> tuple[bool, str]:
        now = time.time()
        snapshot = self.state.snapshot()

        normalized = "\n".join(line.strip() for line in trigger_text.splitlines() if line.strip()).strip()
        if not normalized:
            return True, "empty_prompt"
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        dedup_window = max(300, int(self.config.prompt_dedup_window_seconds))
        recent_hashes = {
            key: float(value)
            for key, value in dict(snapshot.get("recent_prompt_hashes", {})).items()
            if now - float(value) <= dedup_window
        }
        if digest in recent_hashes:
            return True, f"duplicate_within_{dedup_window}s"

        min_interval = max(0, int(self.config.min_run_interval_seconds))
        last_run_at = snapshot.get("last_provider_run_at")
        if min_interval > 0 and last_run_at:
            try:
                last_run_ts = datetime.fromisoformat(str(last_run_at)).timestamp()
            except ValueError:
                last_run_ts = 0
            if last_run_ts and now - last_run_ts < min_interval:
                return True, f"cooldown_{min_interval}s"

        run_window_seconds = 86400
        max_runs = max(1, int(self.config.max_runs_per_day))
        recent_runs = [
            str(item)
            for item in list(snapshot.get("provider_runs", []))
            if item
            and (
                now - datetime.fromisoformat(str(item)).timestamp() <= run_window_seconds
                if "T" in str(item)
                else False
            )
        ]
        if len(recent_runs) >= max_runs:
            return True, f"daily_limit_{max_runs}"

        recent_hashes[digest] = now
        recent_runs.append(datetime.now().isoformat(timespec="seconds"))
        self.state.update(
            {
                "recent_prompt_hashes": recent_hashes,
                "provider_runs": recent_runs[-100:],
                "last_provider_run_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return False, ""

    def request_cancel(self, reason: str) -> None:
        snapshot = self.state.snapshot()
        if snapshot.get("cancel_requested") and snapshot.get("cancel_reason") == reason:
            return
        self.state.update({"running": False, "cancel_requested": True, "cancel_reason": reason})
        self.logs.add(reason, "warn")

    def is_cancel_requested(self) -> bool:
        return bool(self.state.snapshot().get("cancel_requested"))

    def sleep_cancelable(self, seconds: float, interval: float = 0.1) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self.is_cancel_requested():
                return False
            time.sleep(min(interval, max(0, deadline - time.time())))
        return not self.is_cancel_requested()

    def send_morning_report(self) -> None:
        if self.is_cancel_requested():
            self.logs.add("Morning report skipped because stop was requested.", "warn")
            return
        if not self.config.report_chat_id.strip():
            self.logs.add("Morning report chat is empty; skipping morning report.", "warn")
            return
        self.send_message(self.config.report_chat_id, self.config.morning_message)
        today = datetime.now().date().isoformat()
        if self.config.dry_run:
            self.state.set("last_morning_dry_run_date", today)
        else:
            self.state.set("last_morning_date", today)
        self.logs.add("Morning report action completed.")

    def scan_messages(self) -> dict[str, Any]:
        with self._action_lock:
            previous_active = self.state.snapshot().get("active_action")
            self.state.set("active_action", "scan")
            if self.config.read_source == "discord":
                self.logs.add("Scanning Discord channels.")
            else:
                self.logs.add("Scanning Lark chats.")
            changed_chunks: list[str] = []
            snapshot = self.state.snapshot()
            previous_hashes = snapshot.get("chat_hashes", {})
            previous_contents = snapshot.get("chat_contents", {})
            previous_discord_message_ids = snapshot.get("discord_last_message_ids", {})
            next_hashes = dict(previous_hashes)
            next_contents = dict(previous_contents)
            next_discord_message_ids = dict(previous_discord_message_ids)
            copied_digests: dict[str, str] = {}

            try:
                target_ids = self.get_target_ids()
                if not target_ids:
                    self.logs.add("No target IDs configured for the current read source.", "error")
                    return {"matched": False, "reason": "no_targets"}

                for chat_id in target_ids:
                    if self.is_cancel_requested():
                        self.logs.add("Scan cancelled before reading next chat.", "warn")
                        return {"matched": False, "reason": "cancelled"}

                    if self.config.read_source == "discord":
                        content, latest_message_id = self.read_discord_channel_delta(
                            chat_id,
                            str(previous_discord_message_ids.get(chat_id, "") or ""),
                        )
                        if latest_message_id:
                            next_discord_message_ids[chat_id] = latest_message_id
                    else:
                        content = self.clean_source_text(self.read_source_chat(chat_id))
                        latest_message_id = ""
                    if self.is_cancel_requested():
                        self.logs.add("Scan cancelled after reading chat.", "warn")
                        return {"matched": False, "reason": "cancelled"}
                    if self.config.read_source == "ui" and content.strip():
                        self.focus_web_app()

                    if self.config.read_source == "discord":
                        if content.strip():
                            changed_chunks.append(f"--- CHAT ID: {chat_id} ---\n{content}")
                            self.logs.add(f"Detected new Discord messages in channel {chat_id}.")
                        else:
                            self.logs.add(f"No new Discord messages in channel {chat_id}.")
                        self.sleep_cancelable(0.2)
                        continue

                    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    if self.config.read_source == "ui" and content.strip():
                        first_chat = copied_digests.get(digest)
                        if first_chat and first_chat != chat_id:
                            self.logs.add(
                                f"Same copied text appeared for {first_chat} and {chat_id}; Lark may not have switched chats.",
                                "warn",
                            )
                        else:
                            copied_digests[digest] = chat_id

                    if previous_hashes.get(chat_id) != digest:
                        delta_text = self.extract_changed_text(previous_contents.get(chat_id, ""), content)
                        next_contents[chat_id] = content
                        next_hashes[chat_id] = digest
                        if delta_text.strip():
                            changed_chunks.append(f"--- CHAT ID: {chat_id} ---\n{delta_text}")
                            self.logs.add(f"Detected changed content in chat {chat_id}.")
                        else:
                            self.logs.add(f"Content changed in chat {chat_id}, but no new lines were isolated.")
                    else:
                        self.logs.add(f"No content change in chat {chat_id}.")
                    self.sleep_cancelable(0.2)

                initialized = bool(self.state.snapshot().get("initialized_chats"))
                self.state.update(
                    {
                        "chat_hashes": next_hashes,
                        "chat_contents": next_contents,
                        "discord_last_message_ids": next_discord_message_ids,
                        "initialized_chats": True,
                        "last_scan_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )

                if self.config.ignore_first_scan and not initialized:
                    self.logs.add("First scan baseline saved; triggers ignored for this scan.")
                    return {"matched": False, "reason": "baseline"}

                changed_text = "\n".join(changed_chunks)
                if self.config.read_source == "discord":
                    matched_keywords = ["discord_prompt"] if changed_text.strip() else []
                else:
                    matched_keywords = [
                        keyword
                        for keyword in self.config.keywords
                        if keyword.lower() in changed_text.lower()
                    ]

                if not matched_keywords:
                    self.logs.add("No configured backend/API keywords found.")
                    return {"matched": False, "reason": "no_keywords"}

                if self.config.read_source == "discord":
                    self.logs.add("Detected new Discord prompt content.", "warn")
                else:
                    self.logs.add(f"Matched keywords: {', '.join(matched_keywords)}", "warn")
                trigger_text = self.build_trigger_text(changed_text, matched_keywords)
                skip_run, skip_reason = self.should_skip_provider_run(trigger_text)
                if skip_run:
                    self.logs.add(f"Provider run skipped to control usage: {skip_reason}.", "warn")
                    return {"matched": False, "reason": skip_reason}
                self.state.set(
                    "last_match",
                    {
                        "at": datetime.now().isoformat(timespec="seconds"),
                        "keywords": matched_keywords,
                        "text": trigger_text,
                        "raw_text": changed_text,
                    },
                )
                self.execute_codex_and_maybe_push(trigger_text)
                return {"matched": True, "keywords": matched_keywords}
            finally:
                self.state.set("active_action", previous_active)

    def clean_source_text(self, content: str) -> str:
        if self.config.read_source == "discord":
            return self.clean_discord_text(content)
        return self.clean_lark_text(content)

    def clean_lark_text(self, content: str) -> str:
        stop_markers = (
            "Shift + Enter to add a new line",
            "Message ",
        )
        lines = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if any(marker in line for marker in stop_markers):
                break
            if line:
                lines.append(line)
        return "\n".join(lines)

    def extract_changed_text(self, previous_content: str, current_content: str) -> str:
        current_lines = [line.strip() for line in current_content.splitlines() if line.strip()]
        previous_set = {line.strip() for line in previous_content.splitlines() if line.strip()}
        changed_lines = [line for line in current_lines if line not in previous_set]

        if not changed_lines and current_lines != [line.strip() for line in previous_content.splitlines() if line.strip()]:
            changed_lines = current_lines[-8:]

        return "\n".join(changed_lines)

    def build_trigger_text(self, changed_text: str, matched_keywords: list[str]) -> str:
        lines = [line.strip() for line in changed_text.splitlines() if line.strip()]
        if not lines:
            return changed_text

        keyword_terms = [keyword.lower() for keyword in matched_keywords if keyword.strip()]
        matched_indexes: set[int] = set()
        for index, line in enumerate(lines):
            lowered = line.lower()
            if any(term in lowered for term in keyword_terms):
                for neighbor in range(max(0, index - 1), min(len(lines), index + 3)):
                    matched_indexes.add(neighbor)

        recent_indexes = {
            index
            for index in range(max(0, len(lines) - 8), len(lines))
        }
        selected_indexes = sorted(matched_indexes | recent_indexes)

        filtered: list[str] = []
        for index in selected_indexes:
            line = lines[index]
            if line.startswith("oc_"):
                continue
            if line in {"Today Tasks", "- No report output captured.", "Open Figma"}:
                continue
            filtered.append(line)

        if not filtered:
            filtered = lines[-8:]
        text = "\n".join(filtered[:16])
        max_chars = max(500, int(self.config.max_prompt_chars))
        if len(text) > max_chars:
            self.logs.add(f"Prompt truncated to {max_chars} chars to reduce usage.", "warn")
            text = text[:max_chars].rstrip() + "\n...[truncated]"
        return text

    def detect_local_git_command(self, tasks_text: str) -> list[str] | None:
        normalized_lines = [line.strip() for line in tasks_text.splitlines() if line.strip()]
        command_lines = [
            line for line in normalized_lines
            if not line.startswith("--- CHAT ID:")
            and not line.lower().startswith("williams kositt")
            and not line.lower().startswith("james")
        ]
        if len(command_lines) != 1:
            return None
        command_text = command_lines[0]
        lowered = command_text.lower()
        if lowered == "git pull origin develop":
            return ["git", "pull", "origin", "develop"]
        return None

    def extract_codex_result_summary(self, output: str) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        lowered_output = output.lower()

        if "usage limit" in lowered_output or "purchase more credits" in lowered_output:
            return "Codex usage limit ပြည့်နေပါတယ်။ Usage reset time ရောက်မှ ပြန် run နိုင်ပါမယ်။"

        if "outside the writable workspace" in lowered_output or "writing outside of the project" in lowered_output:
            return (
                "Codex က backend repo ကိုဖတ်နိုင်ပေမယ့် write permission မရှိလို့ file မပြင်နိုင်ခဲ့ပါ။ "
                "Writable workspace ကို target project နဲ့ကိုက်အောင်ပြန်သတ်မှတ်ရပါမယ်။"
            )

        changes: list[str] = []
        checks: list[str] = []
        current_section: str | None = None
        for line in lines:
            if line == "Changes:":
                current_section = "changes"
                continue
            if line == "Checks passed:":
                current_section = "checks"
                continue
            if line.startswith("[automation]"):
                current_section = None
            if current_section == "changes" and line.startswith("- "):
                changes.append(line[2:].strip())
                continue
            if current_section == "checks" and line.startswith("- "):
                checks.append(line[2:].strip())
                continue

        if changes or checks:
            parts: list[str] = []
            if changes:
                parts.append("ပြင်ဆင်မှုများ:")
                for item in changes:
                    parts.append(f"- {item}")
            if checks:
                parts.append("စစ်ဆေးပြီး အောင်မြင်ထားတာများ:")
                for item in checks:
                    parts.append(f"- {item}")
            return "\n".join(parts)

        skip_prefixes = (
            "Reading additional input from stdin",
            "OpenAI Codex",
            "--------",
            "workdir:",
            "model:",
            "provider:",
            "approval:",
            "sandbox:",
            "reasoning effort:",
            "reasoning summaries:",
            "session id:",
            "user",
            "codex",
            "exec",
            "[automation]",
        )
        summary_lines: list[str] = []
        skip_next_numeric = False
        for line in lines:
            if not line:
                continue
            if line.startswith("2026-") or line.startswith("2027-"):
                continue
            if line.startswith("WARN ") or line.startswith("ERROR "):
                continue
            if line.startswith("$ "):
                continue
            if any(line.startswith(prefix) for prefix in skip_prefixes):
                continue
            if "ignoring interface." in line:
                continue
            lowered = line.lower()
            if lowered == "tokens used":
                skip_next_numeric = True
                continue
            if skip_next_numeric and line.replace(",", "").isdigit():
                skip_next_numeric = False
                continue
            skip_next_numeric = False
            if line == "Today Tasks" and summary_lines:
                break
            summary_lines.append(line)

        if not summary_lines:
            return "Myanmar summary မရခဲ့ပါ။ Codex terminal output ကိုစစ်ပါ။"

        deduped_lines: list[str] = []
        seen_recent: set[str] = set()
        for line in summary_lines:
            normalized = line.strip()
            if not normalized:
                continue
            if normalized in seen_recent:
                continue
            deduped_lines.append(line)
            seen_recent.add(normalized)

        text = "\n".join(deduped_lines[-12:]).strip()
        return text or "Myanmar summary မရခဲ့ပါ။ Codex terminal output ကိုစစ်ပါ။"

    def generate_evening_report(self) -> None:
        if self.is_cancel_requested():
            self.logs.add("Evening report skipped because stop was requested.", "warn")
            return
        prompt = (
            "Generate today's work report in a Codex UI style format:\n"
            "Today Tasks\n"
            "[task area title]\n"
            "- [clear completed point]\n"
            "- [clear completed point]\n"
            "[repeat title + bullet blocks if there are multiple workstreams]\n"
            "\n"
            "2. Short Version\n"
            "- [short condensed point]\n"
            "- [short condensed point]\n"
            "\n"
            "3. Client Update Format\n"
            "- [client-friendly point in simpler wording]\n"
            "- [client-friendly point in simpler wording]\n"
            "\n"
            "Rules:\n"
            "- Return plain text only.\n"
            "- Do not include code fences.\n"
            "- Do not include tokens used, logs, timestamps, or internal notes.\n"
            "- Do not duplicate the same points twice.\n"
            "- Do not add suggestions or next steps unless they are necessary deployment notes.\n"
            "- Keep the wording concise and concrete like Codex UI summaries.\n"
            "- Start directly with 'Today Tasks'."
        )
        if self.config.dry_run:
            self.logs.add("Dry-run: evening report would be generated and posted.")
            self.state.set("last_evening_dry_run_date", datetime.now().date().isoformat())
            return

        self.logs.add("Generating evening report with provider chain.")
        report_completed, report_output, _, report_provider = self.run_provider_chain(
            prompt,
            cwd=self.config.project_path,
            preferred_provider=self.config.provider,
            post_summary=False,
        )
        if not report_completed:
            report_text = "Today Tasks\n- Evening report ထုတ်ရာမှာ Codex run မအောင်မြင်ပါ။"
        else:
            report_text = self.extract_evening_report_text(report_output)
            self.logs.add(f"Evening report generated by {report_provider}.")
        evening_chat_id = self.config.evening_report_chat_id.strip()
        if not evening_chat_id:
            self.logs.add("Evening report destination is empty; skipping evening report post.", "error")
            self.state.set("last_evening_date", datetime.now().date().isoformat())
            return
        self.send_message(evening_chat_id, report_text)
        self.state.set("last_evening_date", datetime.now().date().isoformat())
        self.logs.add(f"Evening report posted to {evening_chat_id}.")

    def extract_evening_report_text(self, output: str) -> str:
        lines = [line.rstrip() for line in output.splitlines()]
        start_index: int | None = None
        for index, line in enumerate(lines):
            if line.strip() == "Today Tasks":
                start_index = index

        if start_index is not None:
            report_lines: list[str] = []
            for line in lines[start_index:]:
                stripped = line.strip()
                if not stripped:
                    if report_lines:
                        report_lines.append("")
                    continue
                if stripped.startswith("[automation]") or stripped.startswith("$ "):
                    break
                if stripped.startswith("2026-") or stripped.startswith("2027-"):
                    break
                if stripped.startswith("OpenAI Codex") or stripped.startswith("workdir:"):
                    continue
                report_lines.append(stripped)
            report_text = "\n".join(report_lines).strip()
            if report_text:
                return report_text

        summary = self.extract_codex_result_summary(output).strip()
        if summary:
            return summary
        return "Today Tasks\n- No report output captured."

    def read_source_chat(self, chat_id: str) -> str:
        if self.config.read_source == "discord":
            return self.read_discord_channel(chat_id)
        return self.read_lark_chat(chat_id)

    def read_lark_chat(self, chat_id: str) -> str:
        if self.config.read_source in {"api", "api_dm"}:
            return self.read_lark_chat_api(chat_id)
        if self.config.read_source != "ui":
            self.logs.add(f"Unknown read source: {self.config.read_source}", "error")
            return ""

        if self.config.dry_run:
            self.logs.add(
                f"Dry-run: reading Lark chat {chat_id}; post, Codex, and git push remain disabled."
            )

        pyautogui, pyperclip = self.import_ui_modules()
        previous_clipboard = pyperclip.paste()
        self.open_lark_chat(chat_id)
        if not self.sleep_cancelable(3.5):
            pyperclip.copy(previous_clipboard)
            return ""

        screen_width, screen_height = pyautogui.size()
        content = self.copy_visible_message_text(pyautogui, pyperclip, screen_width, screen_height)
        pyperclip.copy(previous_clipboard)

        if content.strip():
            preview = " ".join(content.split())[:160]
            self.logs.add(f"Read {len(content)} chars from {chat_id}: {preview}")
        else:
            self.logs.add(
                f"No text copied from {chat_id}. Check Lark focus, screen position, or copy-menu order.",
                "warn",
            )
        return content

    def copy_visible_message_text(
        self,
        pyautogui: Any,
        pyperclip: Any,
        screen_width: int,
        screen_height: int,
    ) -> str:
        full_copy = self.copy_message_pane_text(pyautogui, pyperclip, screen_width, screen_height)
        if full_copy.strip():
            return full_copy

        message_x_positions = [
            screen_width // 2 + 15,
            screen_width // 2 + 190,
            screen_width // 2 + 330,
        ]
        message_y_positions = [
            int(screen_height * 0.51),
            int(screen_height * 0.62),
            int(screen_height * 0.72),
            int(screen_height * 0.42),
            int(screen_height * 0.80),
        ]

        for y in message_y_positions:
            for x in message_x_positions:
                if self.is_cancel_requested():
                    return ""
                pyperclip.copy("")
                pyautogui.rightClick(x, y)
                if not self.sleep_cancelable(0.35):
                    return ""
                pyautogui.click(x + 50, y + 20)
                if not self.sleep_cancelable(0.55):
                    return ""
                content = pyperclip.paste()
                if content.strip():
                    return content
        return ""

    def copy_message_pane_text(
        self,
        pyautogui: Any,
        pyperclip: Any,
        screen_width: int,
        screen_height: int,
    ) -> str:
        message_area_x = int(screen_width * 0.58)
        message_area_y = int(screen_height * 0.50)
        pyperclip.copy("")
        pyautogui.press("escape")
        if not self.sleep_cancelable(0.15):
            return ""
        pyautogui.click(message_area_x, message_area_y)
        if not self.sleep_cancelable(0.25):
            return ""
        pyautogui.hotkey("command", "a")
        if not self.sleep_cancelable(0.2):
            return ""
        pyautogui.hotkey("command", "c")
        if not self.sleep_cancelable(0.45):
            return ""
        content = pyperclip.paste().strip()
        if len(content) > 20:
            return content
        return ""

    def read_lark_chat_api(self, chat_id: str) -> str:
        if not self.config.lark_app_id or not self.config.lark_app_secret:
            self.logs.add(
                "Lark API mode requires LARK_APP_ID and LARK_APP_SECRET or Config values.",
                "error",
            )
            return ""

        token = self.get_lark_tenant_token()
        if not token:
            return ""

        container_type = "chat"
        params = urlencode(
            {
                "container_id_type": container_type,
                "container_id": chat_id,
                "sort_type": "ByCreateTimeDesc",
                "page_size": self.config.lark_api_page_size,
            }
        )
        url = f"{self.config.lark_api_host}/open-apis/im/v1/messages?{params}"
        response = self.request_json(
            url,
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
        )
        if not response:
            return ""
        if response.get("code") not in (0, None):
            self.logs.add(f"Lark message API failed for {chat_id}: {response}", "error")
            return ""

        items = response.get("data", {}).get("items", [])
        texts = []
        for item in items:
            text = self.extract_lark_message_text(item)
            if text:
                create_time = item.get("create_time", "")
                message_id = item.get("message_id", "")
                texts.append(f"[{create_time}] {message_id}\n{text}")

        combined = "\n\n".join(texts)
        self.logs.add(
            f"Lark API read {len(items)} messages / {len(combined)} chars from {chat_id} "
            f"using {self.config.read_source}."
        )
        return combined

    def read_discord_channel(self, channel_id: str) -> str:
        token = self.config.discord_bot_token.strip()
        if not token:
            self.logs.add("Discord read mode requires discord_bot_token.", "error")
            return ""
        url = (
            f"{self.config.discord_api_host.rstrip('/')}/channels/{channel_id}/messages?"
            f"limit={self.config.discord_read_limit}"
        )
        response = self.request_json_any(
            url,
            method="GET",
            headers={"Authorization": f"Bot {token}"},
        )
        if not isinstance(response, list):
            self.logs.add(f"Discord message read failed for {channel_id}.", "error")
            return ""

        texts: list[str] = []
        for item in reversed(response):
            if not isinstance(item, dict):
                continue
            author = item.get("author", {}) or {}
            if author.get("bot"):
                continue
            author_name = author.get("global_name") or author.get("username") or "Unknown"
            text = self.extract_discord_message_text(item)
            if text:
                texts.append(f"{author_name}\n{text}")

        combined = "\n\n".join(texts)
        self.logs.add(
            f"Discord read {len(response)} messages / {len(combined)} chars from channel {channel_id}."
        )
        return combined

    def read_discord_channel_delta(self, channel_id: str, last_message_id: str) -> tuple[str, str]:
        token = self.config.discord_bot_token.strip()
        if not token:
            self.logs.add("Discord read mode requires discord_bot_token.", "error")
            return "", last_message_id
        url = (
            f"{self.config.discord_api_host.rstrip('/')}/channels/{channel_id}/messages?"
            f"limit={self.config.discord_read_limit}"
        )
        response = self.request_json_any(
            url,
            method="GET",
            headers={"Authorization": f"Bot {token}"},
        )
        if not isinstance(response, list):
            self.logs.add(f"Discord message read failed for {channel_id}.", "error")
            return "", last_message_id

        latest_seen_id = last_message_id
        texts: list[str] = []
        for item in reversed(response):
            if not isinstance(item, dict):
                continue
            author = item.get("author", {}) or {}
            if author.get("bot"):
                continue
            message_id = str(item.get("id", "") or "")
            if message_id and (not latest_seen_id or int(message_id) > int(latest_seen_id)):
                latest_seen_id = message_id
            if last_message_id and message_id and int(message_id) <= int(last_message_id):
                continue
            author_name = author.get("global_name") or author.get("username") or "Unknown"
            text = self.extract_discord_message_text(item)
            if text:
                texts.append(f"{author_name}\n{text}")

        if self.config.discord_latest_message_only and texts:
            texts = [texts[-1]]
        combined = self.clean_discord_text("\n\n".join(texts))
        self.logs.add(
            f"Discord read {len(response)} messages / {len(combined)} chars from channel {channel_id} "
            f"(last seen: {latest_seen_id or '-'})"
        )
        return combined, latest_seen_id

    def clean_discord_text(self, content: str) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        filtered = [line for line in lines if line not in {"Prompts", "AI Result", "Daily Report"}]
        return "\n".join(filtered)

    def get_target_ids(self) -> list[str]:
        if self.config.read_source == "discord":
            channel_id = self.config.discord_prompt_channel_id.strip()
            return [channel_id] if channel_id else []
        if self.config.read_source == "api_dm":
            dm_target_id = self.config.dm_target_id.strip()
            return [dm_target_id] if dm_target_id else []
        return [chat_id for chat_id in self.config.target_chats if chat_id.strip()]

    def get_lark_tenant_token(self) -> str:
        now = time.time()
        if self._tenant_token and now < self._tenant_token_expires_at - 60:
            return self._tenant_token

        url = f"{self.config.lark_api_host}/open-apis/auth/v3/tenant_access_token/internal"
        response = self.request_json(
            url,
            method="POST",
            payload={
                "app_id": self.config.lark_app_id,
                "app_secret": self.config.lark_app_secret,
            },
        )
        if not response:
            return ""
        if response.get("code") != 0:
            self.logs.add(f"Lark token request failed: {response}", "error")
            return ""

        self._tenant_token = response.get("tenant_access_token", "")
        self._tenant_token_expires_at = now + int(response.get("expire", 7200))
        self.logs.add("Lark tenant token refreshed.")
        return self._tenant_token

    def request_json(
        self,
        url: str,
        method: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "LarkCodexAutomation/1.0 Python-urllib/3",
        }
        request_headers.update(headers or {})
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8")
            except Exception:
                error_body = ""
            if error_body:
                self.logs.add(f"Lark API error body: {error_body}", "error")
            self.logs.add(f"Lark API request failed: HTTP {exc.code} {exc.reason}", "error")
            return {}
        except Exception as exc:
            self.logs.add(f"Lark API request failed: {exc}", "error")
            return {}

    def request_json_any(
        self,
        url: str,
        method: str,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        request_headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "LarkCodexAutomation/1.0 Python-urllib/3",
        }
        request_headers.update(headers or {})
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8")
            except Exception:
                error_body = ""
            if error_body:
                self.logs.add(f"API error body: {error_body}", "error")
            self.logs.add(f"API request failed: HTTP {exc.code} {exc.reason}", "error")
            return {}
        except Exception as exc:
            self.logs.add(f"API request failed: {exc}", "error")
            return {}

    def request_bytes(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict[str, str]]:
        request_headers = {
            "User-Agent": "LarkCodexAutomation/1.0 Python-urllib/3",
        }
        request_headers.update(headers or {})
        request = Request(url, headers=request_headers, method="GET")
        try:
            with urlopen(request, timeout=20) as response:
                return response.read(), dict(response.headers.items())
        except HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                error_body = ""
            if error_body:
                self.logs.add(f"Asset fetch error body: {error_body}", "error")
            self.logs.add(f"Asset fetch failed: HTTP {exc.code} {exc.reason}", "error")
            return b"", {}
        except Exception as exc:
            self.logs.add(f"Asset fetch failed: {exc}", "error")
            return b"", {}

    def cache_discord_asset(
        self,
        url: str,
        *,
        filename: str = "",
        message_id: str = "",
    ) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        raw_name = filename.strip() or Path(parsed.path).name or "asset"
        safe_name = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in raw_name)
        if not safe_name:
            safe_name = "asset"
        asset_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        prefix = message_id.strip() or "message"
        destination = CACHE_DIR / "discord_attachments" / f"{prefix}_{asset_hash}_{safe_name}"
        if destination.exists():
            return str(destination)

        headers: dict[str, str] = {}
        if "discord" in parsed.netloc:
            token = self.config.discord_bot_token.strip()
            if token:
                headers["Authorization"] = f"Bot {token}"
        payload, _ = self.request_bytes(url, headers=headers)
        if not payload:
            return ""

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        self.logs.add(f"Cached Discord asset: {destination}")
        return str(destination)

    def extract_lark_message_text(self, item: Any) -> str:
        parts: list[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, str):
                stripped = value.strip()
                if not stripped:
                    return
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    parts.append(stripped)
                else:
                    walk(parsed)
                return
            if isinstance(value, list):
                for child in value:
                    walk(child)
                return
            if isinstance(value, dict):
                for key in ("text", "user_name", "name", "content"):
                    if key in value:
                        walk(value[key])
                for key, child in value.items():
                    if key not in {"text", "user_name", "name", "content"}:
                        walk(child)

        walk(item.get("content", item))
        return " ".join(dict.fromkeys(parts))

    def extract_discord_message_text(self, item: Any) -> str:
        content = str(item.get("content", "") or "").strip()
        message_id = str(item.get("id", "") or "").strip()
        attachment_lines: list[str] = []
        for attachment in item.get("attachments", []) or []:
            if not isinstance(attachment, dict):
                continue
            filename = str(attachment.get("filename", "") or "").strip()
            url = str(attachment.get("url", "") or "").strip()
            content_type = str(attachment.get("content_type", "") or "").strip()
            prefix = "Image attachment" if content_type.startswith("image/") else "Attachment"
            detail_parts = [part for part in [filename, content_type] if part]
            if detail_parts:
                attachment_lines.append(f"{prefix}: {' | '.join(detail_parts)}")
            if url:
                attachment_lines.append(f"{prefix} URL: {url}")
            if content_type.startswith("image/") and url:
                cached_path = self.cache_discord_asset(url, filename=filename, message_id=message_id)
                if cached_path:
                    attachment_lines.append(f"{prefix} local path: {cached_path}")

        embed_lines: list[str] = []
        for embed in item.get("embeds", []) or []:
            if not isinstance(embed, dict):
                continue
            title = str(embed.get("title", "") or "").strip()
            description = str(embed.get("description", "") or "").strip()
            image = embed.get("image", {}) if isinstance(embed.get("image"), dict) else {}
            image_url = str(image.get("url", "") or "").strip()
            if title:
                embed_lines.append(f"Embed title: {title}")
            if description:
                embed_lines.append(f"Embed description: {description}")
            if image_url:
                embed_lines.append(f"Embed image URL: {image_url}")
                cached_path = self.cache_discord_asset(image_url, filename=f"{message_id or 'embed'}_embed_image", message_id=message_id)
                if cached_path:
                    embed_lines.append(f"Embed image local path: {cached_path}")

        parts = [part for part in [content, *attachment_lines, *embed_lines] if part]
        return "\n".join(parts)

    def send_message(self, chat_id: str, message: str) -> None:
        if self.should_skip_duplicate_send(chat_id, message):
            return
        if self.config.send_source == "discord":
            self.send_discord_message(chat_id, message)
            return
        self.send_lark_message(chat_id, message)

    def send_lark_message(self, chat_id: str, message: str) -> None:
        if self.is_cancel_requested():
            self.logs.add("Send skipped because stop was requested.", "warn")
            return
        if self.config.send_source != "ui":
            self.logs.add(f"Unknown send source: {self.config.send_source}. Using UI send fallback.", "warn")
        if self.config.dry_run:
            preview = message.replace("\n", " ")[:140]
            self.logs.add(f"Dry-run: would post to {chat_id}: {preview}")
            return

        pyautogui, pyperclip = self.import_ui_modules()
        self.open_lark_chat(chat_id)
        if not self.sleep_cancelable(4):
            return
        screen_width, screen_height = pyautogui.size()
        input_x = int(screen_width * 0.66)
        input_y = int(screen_height * 0.94)
        pyautogui.press("escape")
        if not self.sleep_cancelable(0.15):
            return
        pyautogui.click(input_x, input_y)
        if not self.sleep_cancelable(0.35):
            return
        pyperclip.copy(message)
        paste_result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "v" using command down',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if paste_result.returncode != 0:
            self.logs.add(
                f"Paste to Lark failed: {paste_result.stderr.strip() or paste_result.stdout.strip()}",
                "error",
            )
            return
        if not self.sleep_cancelable(0.8):
            return
        send_result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to key code 36',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if send_result.returncode != 0:
            self.logs.add(
                f"Send to Lark failed: {send_result.stderr.strip() or send_result.stdout.strip()}",
                "error",
            )
            return
        self.logs.add(f"Posted message to Lark chat {chat_id}.")

    def send_discord_message(self, channel_id: str, message: str) -> None:
        if self.is_cancel_requested():
            self.logs.add("Discord send skipped because stop was requested.", "warn")
            return
        token = self.config.discord_bot_token.strip()
        if not token:
            self.logs.add("Discord send requires discord_bot_token.", "error")
            return
        if not channel_id.strip():
            self.logs.add("Discord send target is empty.", "error")
            return
        if self.config.dry_run:
            preview = message.replace("\n", " ")[:140]
            self.logs.add(f"Dry-run: would post to Discord channel {channel_id}: {preview}")
            return

        url = f"{self.config.discord_api_host.rstrip('/')}/channels/{channel_id}/messages"
        for chunk in self.split_discord_message(message):
            response = self.request_json_any(
                url,
                method="POST",
                payload={"content": chunk},
                headers={"Authorization": f"Bot {token}"},
            )
            if not isinstance(response, dict) or not response.get("id"):
                self.logs.add(f"Discord send failed for channel {channel_id}.", "error")
                return
        self.logs.add(f"Posted message to Discord channel {channel_id}.")

    def split_discord_message(self, message: str, limit: int = 1900) -> list[str]:
        text = message.strip()
        if not text:
            return [""]
        chunks: list[str] = []
        current = ""
        for line in text.splitlines():
            candidate = line if not current else f"{current}\n{line}"
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                chunks.append(current)
                current = ""
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current = line
        if current:
            chunks.append(current)
        return chunks or [text[:limit]]

    def send_codex_result_summary(self, summary: str) -> None:
        chat_id = self.config.codex_result_chat_id.strip()
        if not chat_id:
            self.logs.add("Codex result chat ID is empty; skipping result post.", "warn")
            return
        message = f"Codex result\n{self.strip_evening_report_from_summary(summary)}"
        self.send_message(chat_id, message)
        self.logs.add(f"Codex result summary sent to {chat_id}.")

    def strip_evening_report_from_summary(self, summary: str) -> str:
        lines = [line.rstrip() for line in summary.splitlines()]
        result_lines: list[str] = []
        for line in lines:
            if line.strip() == "Today Tasks":
                break
            result_lines.append(line)
        cleaned = "\n".join(result_lines).strip()
        return cleaned or summary.strip()

    def resolve_codex_path(self) -> str:
        return discover_codex_path(self.config.codex_path)

    def resolve_cursor_path(self) -> str:
        return discover_cursor_path(self.config.cursor_path)

    def resolve_gemini_path(self) -> str:
        return discover_gemini_path(self.config.gemini_path)

    def build_cursor_history_context(self, cwd: str, limit: int = 8) -> str:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-n{limit}"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ""
        history = result.stdout.strip()
        if not history:
            return ""
        return f"\n\nRecent git commit history:\n{history}"

    def run_provider(self, provider: str, prompt: str, cwd: str, post_summary: bool = True) -> tuple[bool, str, str]:
        provider_name = (provider or "codex").strip().lower()
        if provider_name == "cursor":
            return self.run_cursor_prompt(prompt, cwd=cwd, post_summary=post_summary)
        if provider_name == "gemini":
            return self.run_gemini_prompt(prompt, cwd=cwd, post_summary=post_summary)
        return self.run_codex_prompt(prompt, cwd=cwd, post_summary=post_summary)

    def run_provider_chain(
        self,
        prompt: str,
        cwd: str,
        *,
        preferred_provider: str,
        post_summary: bool = True,
    ) -> tuple[bool, str, str, str]:
        provider = (preferred_provider or "codex").strip().lower()
        order_map = {
            "codex": ["codex", "cursor", "gemini"],
            "cursor": ["cursor", "gemini", "codex"],
            "gemini": ["gemini", "cursor", "codex"],
        }
        providers = order_map.get(provider, ["codex", "cursor", "gemini"])
        final_output = ""
        final_status = "failed"
        final_provider = providers[0]

        for index, candidate in enumerate(providers):
            self.logs.add(f"Trying provider: {candidate}.")
            run_prompt = prompt
            if candidate == "cursor":
                run_prompt += self.build_cursor_history_context(cwd)
            completed, output, status = self.run_provider(
                candidate,
                run_prompt,
                cwd=cwd,
                post_summary=False,
            )
            final_output = output
            final_status = status
            final_provider = candidate
            if completed:
                summary = str(self.state.snapshot().get("codex_result_summary") or "").strip()
                if post_summary and summary:
                    self.send_codex_result_summary(summary)
                return True, output, status, candidate
            if index < len(providers) - 1:
                self.logs.add(f"{candidate} run did not complete successfully ({status}). Falling back.", "warn")

        summary = str(self.state.snapshot().get("codex_result_summary") or "").strip()
        if post_summary and summary:
            self.send_codex_result_summary(summary)
        return False, final_output, final_status, final_provider

    def execute_codex_and_maybe_push(self, tasks_text: str) -> None:
        project_path = Path(self.config.project_path).expanduser()
        if not project_path.exists():
            self.logs.add(f"Project path does not exist: {project_path}", "error")
            return

        local_command = self.detect_local_git_command(tasks_text)
        if local_command:
            self.execute_local_git_command(local_command, str(project_path), tasks_text)
            return

        extra_instruction = ""
        lowered_tasks = tasks_text.lower()
        if any(marker in lowered_tasks for marker in ("image attachment:", "image attachment url:", "embed image url:")):
            extra_instruction = (
                "\n\nIf image attachments, image URLs, or local image paths are included in the prompt, inspect them and infer the "
                "user's intended backend/API request from both the text and the visuals before making changes."
            )

        prompt = f"{self.config.codex_prompt_prefix}{extra_instruction}\n\nLark messages:\n{tasks_text}"
        if self.config.dry_run:
            self.state.update(
                {
                    "codex_trigger_text": tasks_text,
                    "codex_prompt": prompt,
                    "codex_last_status": "Dry-run preview",
                    "codex_result_summary": "Dry-run mode ဖြစ်လို့ Codex summary မထွက်သေးပါ။",
                    "codex_output": [
                        "[DRY-RUN]",
                        "[TRIGGER TEXT]",
                        tasks_text,
                        "",
                        "[PROMPT]",
                        prompt,
                    ],
                    "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            self.logs.add("Dry-run: Codex would run for matched messages. Triggering text:")
            self.logs.add(f"---\n{tasks_text}\n---")
            return
        if self.is_cancel_requested():
            self.logs.add("Codex skipped because stop was requested.", "warn")
            return

        self.state.update(
            {
                "codex_trigger_text": tasks_text,
                "codex_prompt": prompt,
                "codex_result_summary": None,
            }
        )
        self.logs.add(f"Codex triggered by text:\n---\n{tasks_text}\n---")
        self.focus_web_app()
        provider = self.config.provider.strip() or "codex"
        completed, _, status, used_provider = self.run_provider_chain(
            prompt,
            cwd=str(project_path),
            preferred_provider=provider,
            post_summary=True,
        )

        if self.config.auto_push and completed:
            self.commit_and_push(str(project_path))
        elif self.config.auto_push:
            self.logs.add("Auto-push skipped because provider run did not complete successfully.", "warn")
        else:
            self.logs.add(f"Auto-push is disabled; leaving {used_provider} changes for review.")
        if self.config.read_source == "ui" or self.config.send_source == "ui":
            self.focus_lark_app()

    def execute_local_git_command(self, command: list[str], cwd: str, tasks_text: str) -> None:
        self.logs.add(f"Running local command from prompt: {' '.join(command)}")
        if self.config.dry_run:
            self.state.update(
                {
                    "codex_trigger_text": tasks_text,
                    "codex_prompt": " ".join(command),
                    "codex_last_status": "Dry-run local command",
                    "codex_result_summary": f"Dry-run mode ဖြစ်လို့ `{' '.join(command)}` ကို မrunသေးပါ။",
                    "codex_output": ["[DRY-RUN LOCAL COMMAND]", " ".join(command)],
                    "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            return

        completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
        output_parts = []
        if completed.stdout.strip():
            output_parts.append(completed.stdout.strip())
        if completed.stderr.strip():
            output_parts.append(completed.stderr.strip())
        output = "\n".join(output_parts).strip()

        if completed.returncode == 0:
            summary = f"Local command run ပြီးပါပြီ: `{' '.join(command)}`"
            if output:
                summary += f"\n{output}"
            status = "Local command completed"
            self.logs.add(status + ".")
        else:
            summary = (
                f"Local command မအောင်မြင်ပါ: `{' '.join(command)}`\n"
                f"{output or 'No output returned.'}"
            )
            status = f"Local command failed ({completed.returncode})"
            self.logs.add(status, "error")

        self.state.update(
            {
                "codex_trigger_text": tasks_text,
                "codex_prompt": " ".join(command),
                "codex_last_status": status,
                "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                "codex_result_summary": summary,
                "codex_output": [line for line in ["$ " + " ".join(command), output] if line],
            }
        )
        self.send_codex_result_summary(summary)

    def run_codex_prompt(self, prompt: str, cwd: str, post_summary: bool = True) -> tuple[bool, str, str]:
        codex_executable = self.config.codex_path
        codex_path = self.resolve_codex_path()
        if not codex_path:
            self.logs.add("Codex CLI was not found on PATH.", "error")
            self.logs.add(f"Codex CLI ('{codex_executable}') was not found on PATH or is not executable.", "error")
            self.state.update(
                {
                    "codex_running": False,
                    "codex_project_path": cwd,
                    "codex_last_status": "Codex CLI not found",
                    "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                    "codex_result_summary": "Codex CLI command မတွေ့လို့ run မလုပ်နိုင်ပါ။ Codex path ကိုစစ်ပါ။",
                }
            )
            return False, "", "cli_not_found"

        self.logs.add("Running Codex CLI.")
        timeout_seconds = max(60, int(self.config.codex_timeout_seconds))
        started_at = time.time()
        self.state.update(
                {
                    "codex_running": True,
                    "codex_started_at": datetime.now().isoformat(timespec="seconds"),
                    "codex_project_path": cwd,
                    "codex_last_status": "Running",
                    "codex_last_finished_at": None,
                    "codex_result_summary": None,
                    "codex_output": [
                    "$ " + " ".join([codex_path, "-a", "never", "exec", "--cd", cwd, "--sandbox", "workspace-write", "--skip-git-repo-check", "<prompt>"]),
                    "\n[PROMPT]",
                    prompt,
                ],
            }
        )
        output_parts: list[str] = []
        output_lock = threading.Lock()

        def append_output(line: str) -> None:
            clean_line = line.rstrip()
            if not clean_line:
                return
            with output_lock:
                output_parts.append(clean_line)
            snapshot = self.state.snapshot()
            existing = list(snapshot.get("codex_output", []))
            existing.append(clean_line)
            self.state.update({"codex_output": existing[-400:]})

        process = subprocess.Popen(
            [
                codex_path,
                "-a",
                "never",
                "exec",
                "--cd",
                cwd,
                "--sandbox",
                "workspace-write",
                "--skip-git-repo-check",
                prompt,
            ],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        def reader() -> None:
            if process.stdout is None:
                return
            for line in process.stdout:
                append_output(line)

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()
        while process.poll() is None:
            if time.time() - started_at > timeout_seconds:
                self.logs.add(f"Stopping Codex process after {timeout_seconds}s timeout.", "error")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                reader_thread.join(timeout=2)
                self.state.update(
                    {
                        "codex_running": False,
                        "codex_last_status": f"Timed out after {timeout_seconds}s",
                        "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                        "codex_result_summary": "Codex run အချိန်ကျော်လို့ ရပ်သွားပါတယ်။",
                    }
                )
                return False, "\n".join(output_parts), "timeout"
            if self.is_cancel_requested():
                self.logs.add("Stopping Codex process because stop was requested.", "warn")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                reader_thread.join(timeout=2)
                self.state.update(
                    {
                        "codex_running": False,
                        "codex_last_status": "Cancelled",
                        "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                        "codex_result_summary": "Codex run ကို stop လုပ်လိုက်ပါတယ်။",
                    }
                )
                return False, "\n".join(output_parts), "cancelled"
            time.sleep(0.5)
        reader_thread.join(timeout=2)
        output = "\n".join(output_parts)
        if process.returncode != 0:
            self.logs.add(f"Codex exited with code {process.returncode}.", "error")
            lowered_output = output.lower()
            if "usage limit" in lowered_output or "purchase more credits" in lowered_output:
                status = "Usage limit reached"
                result_summary = "Codex usage limit ပြည့်နေပါတယ်။ Usage reset time ရောက်မှ ပြန် run နိုင်ပါမယ်။"
            else:
                status = f"Failed with code {process.returncode}"
                result_summary = self.extract_codex_result_summary(output)
        else:
            self.logs.add("Codex CLI completed.")
            status = "Completed"
            result_summary = self.extract_codex_result_summary(output)
        append_output(f"[automation] Codex {status}.")
        self.state.update(
            {
                "codex_running": False,
                "codex_last_status": status,
                "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                "codex_result_summary": result_summary,
            }
        )
        if post_summary and result_summary.strip():
            self.send_codex_result_summary(result_summary)
        if output.strip():
            self.logs.add(output.strip()[-1000:])
        return process.returncode == 0, output, ("usage_limit" if status == "Usage limit reached" else ("completed" if process.returncode == 0 else "failed"))

    def run_gemini_prompt(self, prompt: str, cwd: str, post_summary: bool = True) -> tuple[bool, str, str]:
        gemini_executable = self.config.gemini_path
        gemini_path = self.resolve_gemini_path()
        gemini_model = (self.config.gemini_model or "").strip()
        if not gemini_path:
            summary = "Gemini CLI command မတွေ့လို့ fallback run မလုပ်နိုင်ပါ။"
            self.logs.add("Gemini CLI was not found on PATH.", "error")
            self.state.update(
                {
                    "codex_running": False,
                    "codex_project_path": cwd,
                    "codex_last_status": "Gemini CLI not found",
                    "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                    "codex_result_summary": summary,
                }
            )
            if post_summary:
                self.send_codex_result_summary(summary)
            return False, "", "cli_not_found"

        self.logs.add("Running Gemini CLI.")
        self.state.update(
            {
                "codex_running": True,
                "codex_started_at": datetime.now().isoformat(timespec="seconds"),
                "codex_project_path": cwd,
                "codex_last_status": "Running Gemini",
                "codex_last_finished_at": None,
                "codex_result_summary": None,
                "codex_output": [
                    "$ " + " ".join(
                        [part for part in [gemini_path, "-m", gemini_model, "-p", "<prompt>", "--yolo", "--output-format", "text"] if part]
                    ),
                    "\n[PROMPT]",
                    prompt,
                ],
            }
        )
        command = [
            gemini_path,
        ]
        if gemini_model:
            command.extend(["-m", gemini_model])
        command.extend(
            [
                "-p",
                prompt,
                "--yolo",
                "--output-format",
                "text",
                "--include-directories",
                cwd,
                "--skip-trust",
            ]
        )
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
        if completed.returncode == 0:
            status = "Gemini Completed"
            result_summary = self.extract_codex_result_summary(output)
            success = True
            reason = "completed"
            self.logs.add("Gemini CLI completed.")
        else:
            lowered = output.lower()
            if "user location is not supported" in lowered or "failed_precondition" in lowered:
                status = "Gemini location unsupported"
                result_summary = "Gemini CLI ကို ဒီ location/region ကနေ API use မလုပ်နိုင်ပါ။"
                reason = "location_unsupported"
            elif "quota exceeded" in lowered or "exceeded your current quota" in lowered:
                status = "Gemini quota exceeded"
                result_summary = "Gemini CLI quota ပြည့်နေပါတယ်။"
                reason = "quota_exceeded"
            else:
                status = f"Gemini failed ({completed.returncode})"
                result_summary = self.extract_codex_result_summary(output)
                reason = "failed"
            success = False
            self.logs.add(status + ".", "error")
        self.state.update(
            {
                "codex_running": False,
                "codex_last_status": status,
                "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                "codex_result_summary": result_summary,
                "codex_output": [line for line in self.state.snapshot().get("codex_output", []) + ([output] if output else [])][-400:],
            }
        )
        if post_summary and result_summary.strip():
            self.send_codex_result_summary(result_summary)
        if output:
            self.logs.add(output[-1000:])
        return success, output, reason

    def run_cursor_prompt(self, prompt: str, cwd: str, post_summary: bool = True) -> tuple[bool, str, str]:
        cursor_executable = self.config.cursor_path
        cursor_path = self.resolve_cursor_path()
        cursor_model = (self.config.cursor_model or "").strip()
        if not cursor_path:
            summary = "Cursor Agent CLI command မတွေ့လို့ fallback run မလုပ်နိုင်ပါ။"
            self.logs.add("Cursor Agent CLI was not found on PATH.", "error")
            self.state.update(
                {
                    "codex_running": False,
                    "codex_project_path": cwd,
                    "codex_last_status": "Cursor CLI not found",
                    "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                    "codex_result_summary": summary,
                }
            )
            if post_summary:
                self.send_codex_result_summary(summary)
            return False, "", "cli_not_found"

        self.logs.add("Running Cursor Agent CLI.")
        command_preview = [cursor_path]
        if Path(cursor_path).name != "cursor-agent":
            command_preview.append("agent")
        command_preview.extend(["--print", "--output-format", "text", "--force", "--trust", "--workspace", cwd])
        if cursor_model:
            command_preview.extend(["--model", cursor_model])
        command_preview.append("<prompt>")
        self.state.update(
            {
                "codex_running": True,
                "codex_started_at": datetime.now().isoformat(timespec="seconds"),
                "codex_project_path": cwd,
                "codex_last_status": "Running Cursor",
                "codex_last_finished_at": None,
                "codex_result_summary": None,
                "codex_output": [
                    "$ " + " ".join(command_preview),
                    "\n[PROMPT]",
                    prompt,
                ],
            }
        )

        command = [cursor_path]
        if Path(cursor_path).name != "cursor-agent":
            command.append("agent")
        command.extend(["--print", "--output-format", "text", "--force", "--trust", "--workspace", cwd])
        if cursor_model:
            command.extend(["--model", cursor_model])
        command.append(prompt)

        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
        if completed.returncode == 0:
            status = "Cursor Completed"
            result_summary = self.extract_codex_result_summary(output)
            success = True
            reason = "completed"
            self.logs.add("Cursor Agent CLI completed.")
        else:
            lowered = output.lower()
            if "not authenticated" in lowered or "login" in lowered:
                status = "Cursor authentication required"
                result_summary = "Cursor Agent CLI login မဝင်ရသေးလို့ run မလုပ်နိုင်ပါ။"
                reason = "auth_required"
            elif "rate limit" in lowered or "usage limit" in lowered:
                status = "Cursor usage limit reached"
                result_summary = "Cursor usage limit ပြည့်နေပါတယ်။"
                reason = "usage_limit"
            else:
                status = f"Cursor failed ({completed.returncode})"
                result_summary = self.extract_codex_result_summary(output)
                reason = "failed"
            success = False
            self.logs.add(status + ".", "error")
        self.state.update(
            {
                "codex_running": False,
                "codex_last_status": status,
                "codex_last_finished_at": datetime.now().isoformat(timespec="seconds"),
                "codex_result_summary": result_summary,
                "codex_output": [line for line in self.state.snapshot().get("codex_output", []) + ([output] if output else [])][-400:],
            }
        )
        if post_summary and result_summary.strip():
            self.send_codex_result_summary(result_summary)
        if output:
            self.logs.add(output[-1000:])
        return success, output, reason

    def commit_and_push(self, cwd: str) -> None:
        if self.is_cancel_requested():
            self.logs.add("Git push skipped because stop was requested.", "warn")
            return
        if self.config.dry_run:
            self.logs.add("Git push skipped because dry-run is enabled.", "warn")
            return
        self.logs.add("Preparing git commit and push.")

        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
        if branch_result.returncode != 0:
            self.logs.add(f"Unable to detect git branch: {branch_result.stderr.strip()}", "error")
            return
        branch = branch_result.stdout.strip()
        if not branch or branch == "HEAD":
            self.logs.add("Git branch is detached; auto-push skipped.", "error")
            return

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
        if status.returncode != 0:
            self.logs.add(f"Unable to read git status: {status.stderr.strip()}", "error")
            return

        upstream_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
        has_upstream = upstream_result.returncode == 0 and bool(upstream_result.stdout.strip())

        ahead_count = "0"
        if has_upstream:
            ahead_result = subprocess.run(
                ["git", "rev-list", "--count", "@{u}..HEAD"],
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
            )
            if ahead_result.returncode == 0:
                ahead_count = ahead_result.stdout.strip() or "0"

        has_working_changes = bool(status.stdout.strip())
        has_unpushed_commits = not has_upstream or ahead_count != "0"

        if has_working_changes:
            commands = [
                ["git", "add", "."],
                ["git", "commit", "-m", self.config.commit_message],
            ]
            for command in commands:
                if self.is_cancel_requested():
                    self.logs.add("Git push cancelled before next git command.", "warn")
                    return
                completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
                if completed.returncode != 0:
                    self.logs.add(
                        f"Command failed ({' '.join(command)}): {completed.stderr.strip() or completed.stdout.strip()}",
                        "error",
                    )
                    return
        else:
            self.logs.add("No new working tree changes to commit.")

        if not has_working_changes and not has_unpushed_commits:
            self.logs.add("No local changes or unpushed commits found.")
            return

        push_command = ["git", "push", "-u", "origin", branch] if not has_upstream else ["git", "push", "origin", branch]
        completed = subprocess.run(push_command, cwd=cwd, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            self.logs.add(
                f"Command failed ({' '.join(push_command)}): {completed.stderr.strip() or completed.stdout.strip()}",
                "error",
            )
            return
        output = (completed.stdout.strip() + "\n" + completed.stderr.strip()).strip()
        if output:
            self.logs.add(output)
        if not has_upstream:
            self.logs.add(f"Git upstream configured for {branch}.")
        self.logs.add(f"Git changes pushed to origin {branch}.")

    def focus_web_app(self) -> None:
        url = "http://127.0.0.1:8787"
        focused = False
        for app_name in ("Google Chrome", "Chrome", "Safari"):
            result = subprocess.run(
                ["osascript", "-e", f'tell application "{app_name}" to activate'],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                focused = True
                break
        if focused:
            self.logs.add("Focused web app for Codex run status.")
        else:
            subprocess.run(
                ["open", url],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.logs.add("Opened web app URL for Codex run status.")

    def focus_lark_app(self) -> None:
        focused = False
        for app_name in ("LarkSuite", "Lark"):
            result = subprocess.run(
                ["osascript", "-e", f'tell application "{app_name}" to activate'],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                focused = True
                break
        if focused:
            self.logs.add("Focused Lark after Codex run.")
        else:
            self.logs.add("Could not focus Lark after Codex run.", "warn")

    def open_lark_chat(self, chat_id: str) -> None:
        applink_host = self.config.lark_applink_host.rstrip("/")
        url = f"{applink_host}/client/chat/open?openChatId={chat_id}"
        self.logs.add(f"Opening Lark chat {chat_id}.")
        opened = False
        for app_name in ("LarkSuite", "Lark"):
            result = subprocess.run(
                ["open", "-a", app_name, url],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                opened = True
                break
        if not opened:
            subprocess.run(["open", url], check=False)
        self.sleep_cancelable(0.8)
        if self.is_cancel_requested():
            return
        subprocess.run(
            ["osascript", "-e", 'tell application "Lark" to activate'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["osascript", "-e", 'tell application "LarkSuite" to activate'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @staticmethod
    def import_ui_modules() -> tuple[Any, Any]:
        import pyautogui
        import pyperclip

        return pyautogui, pyperclip


class Scheduler:
    def __init__(self, automation: LarkAutomation, state: AutomationState, logs: LogBuffer) -> None:
        self.automation = automation
        self.state = state
        self.logs = logs
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start_thread(self) -> None:
        self._thread.start()

    def start(self) -> None:
        self.automation.clear_cancel()
        self.state.update({"running": True, "active_action": None})
        self.logs.add("Scheduler started.")

    def stop(self, reason: str = "Stop requested.") -> None:
        self.automation.request_cancel(reason)
        self.logs.add("Scheduler stopped.")

    def shutdown(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.state.snapshot().get("running"):
                    self._tick()
            except Exception as exc:
                self.logs.add(f"Scheduler error: {exc}", "error")
            self._stop.wait(1)

    def _tick(self) -> None:
        config = self.automation.config
        now = datetime.now()
        today = now.date().isoformat()
        snapshot = self.state.snapshot()

        if (
            snapshot.get("last_morning_date") != today
            and (not config.dry_run or snapshot.get("last_morning_dry_run_date") != today)
            and is_after_or_equal(now, config.morning_report_time)
            and is_before(now, config.work_end)
        ):
            self.automation.send_morning_report()
        if self.automation.is_cancel_requested():
            return

        if is_after_or_equal(now, config.work_start) and is_before(now, config.work_end):
            last_scan_at = snapshot.get("last_scan_at")
            due = True
            if last_scan_at:
                last_scan = datetime.fromisoformat(last_scan_at)
                due = (now - last_scan).total_seconds() >= config.scan_interval_seconds
            if due:
                self.automation.scan_messages()
        if self.automation.is_cancel_requested():
            return

        if (
            snapshot.get("last_evening_date") != today
            and (not config.dry_run or snapshot.get("last_evening_dry_run_date") != today)
            and is_after_or_equal(now, config.evening_report_time)
        ):
            self.automation.generate_evening_report()


class StopHotkeyMonitor:
    KEY_S = 1
    LEFT_CONTROL = 59
    RIGHT_CONTROL = 62
    LEFT_OPTION = 58
    RIGHT_OPTION = 61

    def __init__(self, scheduler: Scheduler, logs: LogBuffer, hotkey: str) -> None:
        self.scheduler = scheduler
        self.logs = logs
        self.hotkey = hotkey
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        try:
            import Quartz
        except Exception as exc:
            self.logs.add(f"Stop hotkey unavailable: {exc}", "warn")
            return

        self.logs.add("Stop hotkey active: Control+Option+S.")
        was_pressed = False
        while not self._stop.is_set():
            pressed = self._is_pressed(Quartz)
            if pressed and not was_pressed:
                self.scheduler.stop("Stop hotkey pressed: Control+Option+S.")
            was_pressed = pressed
            self._stop.wait(0.1)

    def _is_pressed(self, quartz: Any) -> bool:
        state = quartz.kCGEventSourceStateCombinedSessionState
        control = quartz.CGEventSourceKeyState(state, self.LEFT_CONTROL) or quartz.CGEventSourceKeyState(
            state, self.RIGHT_CONTROL
        )
        option = quartz.CGEventSourceKeyState(state, self.LEFT_OPTION) or quartz.CGEventSourceKeyState(
            state, self.RIGHT_OPTION
        )
        s_key = quartz.CGEventSourceKeyState(state, self.KEY_S)
        return bool(control and option and s_key)


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lark Codex Automation</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #657080;
      --line: #dce1e7;
      --accent: #0f766e;
      --accent-dark: #0b5f59;
      --danger: #b42318;
      --warn: #a15c07;
      --ok: #16704a;
      --shadow: 0 12px 30px rgba(20, 31, 45, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 24px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 3;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
      font-weight: 700;
    }
    main {
      display: grid;
      grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
      gap: 18px;
      padding: 18px;
      max-width: 1440px;
      margin: 0 auto;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .toolbar {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
    }
    .status-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--danger);
      display: inline-block;
    }
    .status-dot.running { background: var(--ok); }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      height: 34px;
      padding: 0 12px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      font-size: 13px;
      background: #fbfcfd;
    }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      height: 36px;
      border-radius: 6px;
      padding: 0 12px;
      font-weight: 650;
      cursor: pointer;
    }
    button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }
    button.primary:hover { background: var(--accent-dark); }
    button.danger {
      border-color: #e4aaa4;
      color: var(--danger);
    }
    button:disabled {
      opacity: .5;
      cursor: not-allowed;
    }
    .panel-head {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .panel-head h2 {
      margin: 0;
      font-size: 15px;
      line-height: 1.2;
    }
    .panel-body {
      padding: 16px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .field {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .hint {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
      margin-top: -2px;
    }
    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      color: var(--text);
      background: #fff;
      font: inherit;
      min-width: 0;
    }
    textarea {
      min-height: 84px;
      resize: vertical;
      line-height: 1.45;
    }
    .wide { grid-column: 1 / -1; }
    .checks {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 14px;
      margin-top: 12px;
    }
    .check {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--text);
      font-size: 14px;
    }
    .check input {
      width: 16px;
      height: 16px;
    }
    .actions {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }
    .status-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      min-height: 64px;
      background: #fbfcfd;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }
    .metric strong {
      font-size: 14px;
      overflow-wrap: anywhere;
    }
    .preview-stack {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
      margin-top: 12px;
    }
    .preview-box {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
      min-height: 110px;
      overflow: hidden;
    }
    .preview-box span {
      display: block;
      padding: 10px 10px 0;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .preview-content {
      margin: 0;
      padding: 10px;
      min-height: 82px;
      max-height: 180px;
      overflow: auto;
      white-space: pre-wrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
      color: #223041;
    }
    .output-grid {
      display: grid;
      grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
      gap: 18px;
      height: calc(100vh - 186px);
      min-height: 620px;
    }
    .output-grid section {
      min-height: 0;
      display: flex;
      flex-direction: column;
    }
    .logs,
    .terminal {
      flex: 1;
      min-height: 0;
      overflow: auto;
      background: #101820;
      color: #d7e0ea;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
      padding: 12px;
      border-radius: 0 0 8px 8px;
    }
    .terminal {
      white-space: pre-wrap;
      margin: 0;
    }
    .log {
      display: grid;
      grid-template-columns: 142px 54px minmax(0, 1fr);
      gap: 8px;
      padding: 2px 0;
      border-bottom: 1px solid rgba(255, 255, 255, .04);
    }
    .log .level-info { color: #8fc7ff; }
    .log .level-warn { color: #f4bf75; }
    .log .level-error { color: #ff9b93; }
    @media (max-width: 900px) {
      header, main { padding-left: 12px; padding-right: 12px; }
      main { grid-template-columns: 1fr; }
      .actions, .grid, .checks, .status-grid { grid-template-columns: 1fr; }
      .output-grid { height: auto; min-height: 0; }
      .logs, .terminal { min-height: 320px; }
      .log { grid-template-columns: 1fr; gap: 2px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Lark Codex Automation</h1>
    </div>
    <div class="toolbar">
      <span class="pill"><span id="statusDot" class="status-dot"></span><span id="runState">Stopped</span></span>
      <button id="startBtn" class="primary">Start</button>
      <button id="stopBtn" class="danger">Stop</button>
    </div>
  </header>
  <main>
    <div>
      <section>
        <div class="panel-head">
          <h2>Status</h2>
          <button id="refreshBtn">Refresh</button>
        </div>
        <div class="panel-body">
          <div class="status-grid">
            <div class="metric"><span>Last scan</span><strong id="lastScan">-</strong></div>
            <div class="metric"><span>Last match</span><strong id="lastMatch">-</strong></div>
            <div class="metric"><span>Codex CLI</span><strong id="codexStatus">-</strong></div>
            <div class="metric"><span>Codex project</span><strong id="codexProject">-</strong></div>
            <div class="metric"><span>Morning sent</span><strong id="morningSent">-</strong></div>
            <div class="metric"><span>Evening sent</span><strong id="eveningSent">-</strong></div>
          </div>
          <div class="actions">
            <button data-action="morning">Morning</button>
            <button data-action="scan">Scan now</button>
            <button data-action="evening">Evening</button>
          </div>
          <div class="preview-stack">
            <div class="preview-box">
              <span>Matched message</span>
              <pre id="matchedMessage" class="preview-content"></pre>
            </div>
            <div class="preview-box">
              <span>Prompt preview</span>
              <pre id="promptPreview" class="preview-content"></pre>
            </div>
            <div class="preview-box">
              <span>Result summary (Myanmar)</span>
              <pre id="resultSummary" class="preview-content"></pre>
            </div>
          </div>
        </div>
      </section>

      <section style="margin-top: 18px;">
        <div class="panel-head">
          <h2>Config</h2>
          <button id="saveBtn" class="primary">Save</button>
        </div>
        <div class="panel-body">
          <div class="grid">
            <div class="field wide">
              <label for="projectPath">Project path</label>
              <input id="projectPath">
            </div>
            <div class="field wide">
              <label for="reportChatId">Morning destination ID</label>
              <input id="reportChatId">
            </div>
            <div class="field wide">
              <label for="codexResultChatId">Discord AI Result channel ID</label>
              <input id="codexResultChatId">
              <div class="hint">Use the Discord channel ID for your `ai-result` channel.</div>
            </div>
            <div class="field wide">
              <label for="eveningReportChatId">Discord Daily Report channel ID</label>
              <input id="eveningReportChatId" placeholder="leave empty to reuse AI Result channel">
              <div class="hint">Use the Discord channel ID for your `daily-report` channel.</div>
            </div>
            <div class="field">
              <label for="workStart">Work start</label>
              <input id="workStart" placeholder="08:10">
            </div>
            <div class="field">
              <label for="workEnd">Work end</label>
              <input id="workEnd" placeholder="16:30">
            </div>
            <div class="field">
              <label for="morningTime">Morning time</label>
              <input id="morningTime" placeholder="08:10">
            </div>
            <div class="field">
              <label for="eveningTime">Evening time</label>
              <input id="eveningTime" placeholder="16:30">
            </div>
            <div class="field wide">
              <label for="scanInterval">Scan interval seconds</label>
              <input id="scanInterval" type="number" min="30" step="30">
            </div>
            <div class="field">
              <label for="codexTimeout">Codex timeout seconds</label>
              <input id="codexTimeout" type="number" min="60" step="60">
            </div>
            <div class="field">
              <label for="readSource">Read source</label>
              <input id="readSource" placeholder="ui">
            </div>
            <div class="field">
              <label for="sendSource">Send source</label>
              <input id="sendSource" placeholder="ui">
            </div>
            <div class="field">
              <label for="apiPageSize">API page size</label>
              <input id="apiPageSize" type="number" min="1" max="50" step="1">
            </div>
            <div class="field wide">
              <label for="apiHost">Lark API host</label>
              <input id="apiHost" placeholder="https://open.larksuite.com">
            </div>
            <div class="field wide">
              <label for="applinkHost">Lark AppLink host</label>
              <input id="applinkHost" placeholder="https://applink.larksuite.com">
            </div>
            <div class="field wide">
              <label for="codexPath">Codex path or command</label>
              <input id="codexPath" placeholder="codex">
            </div>
            <div class="field">
              <label for="provider">Default provider</label>
              <input id="provider" placeholder="codex">
            </div>
            <div class="field wide">
              <label for="cursorPath">Cursor path or command</label>
              <input id="cursorPath" placeholder="cursor-agent">
            </div>
            <div class="field">
              <label for="cursorModel">Cursor model</label>
              <input id="cursorModel" placeholder="optional">
            </div>
            <div class="field wide">
              <label for="geminiPath">Gemini path or command</label>
              <input id="geminiPath" placeholder="gemini">
            </div>
            <div class="field">
              <label for="geminiModel">Gemini model</label>
              <input id="geminiModel" placeholder="gemini-3.5-flash">
            </div>
            <div class="field wide">
              <label for="stopHotkey">Stop hotkey</label>
              <input id="stopHotkey" placeholder="control+option+s">
            </div>
            <div class="field wide">
              <label for="appId">Lark app ID</label>
              <input id="appId" autocomplete="off">
            </div>
            <div class="field wide">
              <label for="appSecret">Lark app secret</label>
              <input id="appSecret" type="password" autocomplete="off">
            </div>
            <div class="field wide">
              <label for="discordBotToken">Discord bot token</label>
              <input id="discordBotToken" type="password" autocomplete="off">
            </div>
            <div class="field wide">
              <label for="discordPromptChannelId">Discord prompt channel ID</label>
              <input id="discordPromptChannelId" placeholder="123456789012345678">
              <div class="hint">Use the Discord channel ID for your `prompts` channel.</div>
            </div>
            <div class="field wide">
              <label for="discordApiHost">Discord API host</label>
              <input id="discordApiHost" placeholder="https://discord.com/api/v10">
            </div>
            <div class="field">
              <label for="discordReadLimit">Discord read limit</label>
              <input id="discordReadLimit" type="number" min="1" max="100" step="1">
            </div>
            <div class="field">
              <label for="minRunInterval">Min run interval seconds</label>
              <input id="minRunInterval" type="number" min="0" step="60">
            </div>
            <div class="field">
              <label for="maxRunsPerDay">Max runs per day</label>
              <input id="maxRunsPerDay" type="number" min="1" step="1">
            </div>
            <div class="field">
              <label for="promptDedupWindow">Prompt dedup window seconds</label>
              <input id="promptDedupWindow" type="number" min="300" step="300">
            </div>
            <div class="field">
              <label for="maxPromptChars">Max prompt chars</label>
              <input id="maxPromptChars" type="number" min="500" step="100">
            </div>
            <div class="field wide">
              <label for="morningMessage">Morning message</label>
              <textarea id="morningMessage"></textarea>
            </div>
            <div class="field wide">
              <label for="keywords">Keywords, one per line</label>
              <textarea id="keywords"></textarea>
            </div>
            <div class="field wide" id="dmTargetRow">
              <label for="dmTargetId">DM target ID</label>
              <input id="dmTargetId" placeholder="Direct message thread id or user id">
            </div>
            <div class="field wide" id="groupTargetsRow">
              <label for="targetChats">Chat IDs, one per line</label>
              <textarea id="targetChats"></textarea>
            </div>
          </div>
          <div class="checks">
            <label class="check"><input id="dryRun" type="checkbox"> Dry run</label>
            <label class="check"><input id="autoPush" type="checkbox"> Auto push</label>
            <label class="check"><input id="ignoreFirstScan" type="checkbox"> Ignore first scan</label>
            <label class="check"><input id="autoSwitchGemini" type="checkbox"> Auto switch to Gemini on Codex limit</label>
            <label class="check"><input id="discordLatestOnly" type="checkbox"> Discord latest message only</label>
          </div>
        </div>
      </section>
    </div>

    <div class="output-grid">
      <section>
        <div class="panel-head">
          <h2>Logs</h2>
          <button id="clearLocalBtn">Clear view</button>
        </div>
        <div id="logs" class="logs"></div>
      </section>
      <section>
        <div class="panel-head">
          <h2>Codex CLI</h2>
          <span class="pill" id="codexTerminalState">Idle</span>
        </div>
        <pre id="codexTerminal" class="terminal"></pre>
      </section>
    </div>
  </main>

  <script>
    const $ = (id) => document.getElementById(id);
    let lastLogCount = 0;
    let lastCodexOutput = "";

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options
      });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }

    function lines(value) {
      return value.split("\n").map((item) => item.trim()).filter(Boolean);
    }

    function setConfig(config) {
      $("projectPath").value = config.project_path;
      $("reportChatId").value = config.report_chat_id;
      $("codexResultChatId").value = config.codex_result_chat_id;
      $("eveningReportChatId").value = config.evening_report_chat_id || "";
      $("workStart").value = config.work_start;
      $("workEnd").value = config.work_end;
      $("morningTime").value = config.morning_report_time;
      $("eveningTime").value = config.evening_report_time;
      $("scanInterval").value = config.scan_interval_seconds;
      $("codexTimeout").value = config.codex_timeout_seconds || 600;
      $("readSource").value = config.read_source;
      $("sendSource").value = config.send_source;
      $("apiPageSize").value = config.lark_api_page_size;
      $("apiHost").value = config.lark_api_host;
      $("applinkHost").value = config.lark_applink_host;
      $("codexPath").value = config.codex_path;
      $("provider").value = config.provider || "codex";
      $("cursorPath").value = config.cursor_path || "cursor-agent";
      $("cursorModel").value = config.cursor_model || "";
      $("geminiPath").value = config.gemini_path || "gemini";
      $("geminiModel").value = config.gemini_model || "gemini-3.5-flash";
      $("stopHotkey").value = config.stop_hotkey;
      $("appId").value = config.lark_app_id;
      $("appSecret").value = config.lark_app_secret;
      $("discordBotToken").value = config.discord_bot_token || "";
      $("discordPromptChannelId").value = config.discord_prompt_channel_id || "";
      $("discordApiHost").value = config.discord_api_host || "https://discord.com/api/v10";
      $("discordReadLimit").value = config.discord_read_limit || 25;
      $("minRunInterval").value = config.min_run_interval_seconds || 1200;
      $("maxRunsPerDay").value = config.max_runs_per_day || 6;
      $("promptDedupWindow").value = config.prompt_dedup_window_seconds || 43200;
      $("maxPromptChars").value = config.max_prompt_chars || 3500;
      $("morningMessage").value = config.morning_message;
      $("keywords").value = config.keywords.join("\n");
      $("dmTargetId").value = config.dm_target_id;
      $("targetChats").value = config.target_chats.join("\n");
      $("dryRun").checked = config.dry_run;
      $("autoPush").checked = config.auto_push;
      $("ignoreFirstScan").checked = config.ignore_first_scan;
      $("autoSwitchGemini").checked = config.auto_switch_to_gemini_on_codex_limit !== false;
      $("discordLatestOnly").checked = config.discord_latest_message_only !== false;
      toggleTargetFields(config.read_source);
    }

    function toggleTargetFields(readSource) {
      const dmRow = $("dmTargetRow");
      const groupRow = $("groupTargetsRow");
      const isDm = readSource === "api_dm";
      const isDiscord = readSource === "discord";
      dmRow.style.display = isDm ? "grid" : "none";
      groupRow.style.display = (isDm || isDiscord) ? "none" : "grid";
    }

    function collectConfig() {
      return {
        project_path: $("projectPath").value.trim(),
        report_chat_id: $("reportChatId").value.trim(),
        codex_result_chat_id: $("codexResultChatId").value.trim(),
        evening_report_chat_id: $("eveningReportChatId").value.trim(),
        work_start: $("workStart").value.trim(),
        work_end: $("workEnd").value.trim(),
        morning_report_time: $("morningTime").value.trim(),
        evening_report_time: $("eveningTime").value.trim(),
        scan_interval_seconds: Number($("scanInterval").value || 300),
        codex_timeout_seconds: Number($("codexTimeout").value || 600),
        read_source: $("readSource").value.trim() || "ui",
        send_source: $("sendSource").value.trim() || "ui",
        lark_api_page_size: Number($("apiPageSize").value || 20),
        lark_api_host: $("apiHost").value.trim() || "https://open.larksuite.com",
        lark_applink_host: $("applinkHost").value.trim() || "https://applink.larksuite.com",
        codex_path: $("codexPath").value.trim() || "codex",
        provider: $("provider").value.trim() || "codex",
        cursor_path: $("cursorPath").value.trim() || "cursor-agent",
        cursor_model: $("cursorModel").value.trim(),
        gemini_path: $("geminiPath").value.trim() || "gemini",
        gemini_model: $("geminiModel").value.trim() || "gemini-3.5-flash",
        stop_hotkey: $("stopHotkey").value.trim() || "control+option+s",
        lark_app_id: $("appId").value.trim(),
        lark_app_secret: $("appSecret").value,
        discord_bot_token: $("discordBotToken").value,
        discord_prompt_channel_id: $("discordPromptChannelId").value.trim(),
        discord_api_host: $("discordApiHost").value.trim() || "https://discord.com/api/v10",
        discord_read_limit: Number($("discordReadLimit").value || 25),
        min_run_interval_seconds: Number($("minRunInterval").value || 1200),
        max_runs_per_day: Number($("maxRunsPerDay").value || 6),
        prompt_dedup_window_seconds: Number($("promptDedupWindow").value || 43200),
        max_prompt_chars: Number($("maxPromptChars").value || 3500),
        morning_message: $("morningMessage").value,
        keywords: lines($("keywords").value),
        dm_target_id: $("dmTargetId").value.trim(),
        target_chats: lines($("targetChats").value),
        dry_run: $("dryRun").checked,
        auto_push: $("autoPush").checked,
        ignore_first_scan: $("ignoreFirstScan").checked,
        auto_switch_to_gemini_on_codex_limit: $("autoSwitchGemini").checked,
        discord_latest_message_only: $("discordLatestOnly").checked
      };
    }

    function updateStatus(data) {
      const running = Boolean(data.state.running);
      const activeAction = data.state.active_action;
      const cancelReason = data.state.cancel_reason;
      const busy = running || Boolean(activeAction);
      $("statusDot").classList.toggle("running", running);
      $("runState").textContent = activeAction ? `Working: ${activeAction}` : (running ? "Running" : "Stopped");
      $("startBtn").disabled = running;
      $("stopBtn").disabled = !busy;
      $("lastScan").textContent = data.state.last_scan_at || "-";
      const codexStartedAt = data.state.codex_started_at;
      const codexRunning = Boolean(data.state.codex_running);
      let codexStatus = data.state.codex_last_status || "-";
      if (codexRunning && codexStartedAt) {
        const elapsed = Math.max(0, Math.floor((Date.now() - Date.parse(codexStartedAt)) / 1000));
        codexStatus = `Running ${elapsed}s`;
      }
      $("codexStatus").textContent = codexStatus;
      $("codexProject").textContent = data.state.codex_project_path || "-";
      $("codexTerminalState").textContent = codexStatus;
      $("morningSent").textContent = data.state.last_morning_date
        || (data.state.last_morning_dry_run_date ? `dry-run ${data.state.last_morning_dry_run_date}` : "-");
      $("eveningSent").textContent = data.state.last_evening_date
        || (data.state.last_evening_dry_run_date ? `dry-run ${data.state.last_evening_dry_run_date}` : "-");
      const match = data.state.last_match;
      $("lastMatch").textContent = cancelReason || (match ? `${match.at} (${match.keywords.join(", ")})` : "-");
      $("matchedMessage").textContent = data.state.codex_trigger_text || (match ? match.text : "No matched message yet.");
      $("promptPreview").textContent = data.state.codex_prompt || "No prompt prepared yet.";
      $("resultSummary").textContent = data.state.codex_result_summary || "Myanmar summary မထွက်သေးပါ။";
    }

    function renderLogs(logs) {
      if (logs.length === lastLogCount) return;
      lastLogCount = logs.length;
      $("logs").innerHTML = logs.map((entry) => `
        <div class="log">
          <span>${entry.at}</span>
          <span class="level-${entry.level}">${entry.level}</span>
          <span>${escapeHtml(entry.message)}</span>
        </div>
      `).join("");
      $("logs").scrollTop = $("logs").scrollHeight;
    }

    function renderCodexTerminal(output) {
      const text = (output || []).join("\n");
      if (text === lastCodexOutput) return;
      lastCodexOutput = text;
      $("codexTerminal").innerHTML = escapeHtml(text || "No Codex output yet.");
      $("codexTerminal").scrollTop = $("codexTerminal").scrollHeight;
    }

    function escapeHtml(value) {
      return value.replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
      })[char]);
    }

    async function refresh() {
      const button = $("refreshBtn");
      const original = button.textContent;
      button.disabled = true;
      button.textContent = "Refreshing...";
      try {
        const data = await api("/api/status");
        updateStatus(data);
        setConfig(data.config);
        renderLogs(data.logs);
        renderCodexTerminal(data.state.codex_output);
      } catch (error) {
        console.error(error);
      } finally {
        button.disabled = false;
        button.textContent = original;
      }
    }

    async function refreshSoft() {
      try {
        const data = await api("/api/status");
        updateStatus(data);
        renderLogs(data.logs);
        renderCodexTerminal(data.state.codex_output);
      } catch (error) {
        console.error(error);
      }
    }

      $("startBtn").addEventListener("click", async () => {
      await api("/api/start", { method: "POST", body: "{}" });
      refreshSoft();
    });
    $("stopBtn").addEventListener("click", async () => {
      await api("/api/stop", { method: "POST", body: "{}" });
      refreshSoft();
    });
    $("refreshBtn").addEventListener("click", refresh);
    $("readSource").addEventListener("change", (event) => toggleTargetFields(event.target.value.trim() || "api_dm"));
    $("saveBtn").addEventListener("click", async () => {
      await api("/api/config", { method: "POST", body: JSON.stringify(collectConfig()) });
      refresh();
    });
    document.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        await api("/api/action", {
          method: "POST",
          body: JSON.stringify({ action: button.dataset.action })
        });
        refreshSoft();
      });
    });
    $("clearLocalBtn").addEventListener("click", () => {
      $("logs").innerHTML = "";
      lastLogCount = 0;
    });

    refresh();
    setInterval(refreshSoft, 2000);
  </script>
</body>
</html>
"""


class AppHandler(BaseHTTPRequestHandler):
    server_version = "LarkCodexAutomation/0.1"

    def do_GET(self) -> None:
        try:
            self.handle_get()
        except Exception as exc:
            self.send_json_error(500, str(exc))

    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return
        self.send_error(404)

    def do_POST(self) -> None:
        try:
            self.handle_post()
        except ValueError as exc:
            self.send_json_error(400, str(exc))
        except Exception as exc:
            self.send_json_error(500, str(exc))

    def handle_get(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self.send_html(HTML)
            return
        if path == "/api/status":
            self.send_json(
                {
                    "config": asdict(self.server.app_config),
                    "state": self.server.state.snapshot(),
                    "logs": self.server.logs.list(),
                }
            )
            return
        self.send_error(404)

    def handle_post(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/start":
            self.server.scheduler.start()
            self.send_json({"ok": True})
            return
        if path == "/api/stop":
            self.server.scheduler.stop("Stop requested from UI.")
            self.send_json({"ok": True})
            return
        if path == "/api/config":
            payload = self.read_json()
            config = self.build_config(payload)
            save_config(config)
            self.server.app_config = config
            self.server.automation.refresh_config(config)
            self.server.logs.add("Config saved.")
            self.send_json({"ok": True, "config": asdict(config)})
            return
        if path == "/api/action":
            payload = self.read_json()
            action = payload.get("action")
            self.run_manual_action(action)
            self.send_json({"ok": True})
            return
        self.send_error(404)

    def run_manual_action(self, action: str) -> None:
        actions = {
            "morning": self.server.automation.send_morning_report,
            "scan": self.server.automation.scan_messages,
            "evening": self.server.automation.generate_evening_report,
        }
        if action not in actions:
            raise ValueError(f"Unknown action: {action}")

        def runner() -> None:
            self.server.automation.clear_cancel()
            self.server.state.set("active_action", action)
            self.server.logs.add(f"Manual action started: {action}")
            try:
                actions[action]()
            except Exception as exc:
                self.server.logs.add(f"Manual action failed ({action}): {exc}", "error")
            finally:
                self.server.state.set("active_action", None)

        threading.Thread(target=runner, daemon=True).start()
        self.server.logs.add(f"Manual action queued: {action}")

    def build_config(self, payload: dict[str, Any]) -> AutomationConfig:
        current = asdict(self.server.app_config)
        current.update(payload)
        config = AutomationConfig(**current)
        parse_hhmm(config.work_start)
        parse_hhmm(config.work_end)
        parse_hhmm(config.morning_report_time)
        parse_hhmm(config.evening_report_time)
        if config.scan_interval_seconds < 30:
            raise ValueError("scan_interval_seconds must be at least 30")
        if config.codex_timeout_seconds < 60:
            raise ValueError("codex_timeout_seconds must be at least 60")
        if config.read_source not in {"ui", "api", "api_dm", "discord"}:
            raise ValueError("read_source must be ui, api, api_dm, or discord")
        if config.send_source not in {"ui", "discord"}:
            raise ValueError("send_source must be ui or discord")
        if config.lark_api_page_size < 1 or config.lark_api_page_size > 50:
            raise ValueError("lark_api_page_size must be between 1 and 50")
        if config.discord_read_limit < 1 or config.discord_read_limit > 100:
            raise ValueError("discord_read_limit must be between 1 and 100")
        if config.min_run_interval_seconds < 0:
            raise ValueError("min_run_interval_seconds must be 0 or more")
        if config.max_runs_per_day < 1:
            raise ValueError("max_runs_per_day must be at least 1")
        if config.prompt_dedup_window_seconds < 300:
            raise ValueError("prompt_dedup_window_seconds must be at least 300")
        if config.max_prompt_chars < 500:
            raise ValueError("max_prompt_chars must be at least 500")
        if not config.lark_api_host.startswith("https://"):
            raise ValueError("lark_api_host must start with https://")
        if not config.lark_applink_host.startswith("https://"):
            raise ValueError("lark_applink_host must start with https://")
        if not config.discord_api_host.startswith("https://"):
            raise ValueError("discord_api_host must start with https://")
        if config.stop_hotkey != "control+option+s":
            raise ValueError("Only control+option+s is supported as stop_hotkey right now")
        config.provider = (config.provider or "codex").strip().lower()
        if config.provider not in {"codex", "cursor", "gemini"}:
            raise ValueError("provider must be codex, cursor, or gemini")
        config.codex_path = discover_codex_path(config.codex_path) or "codex"
        config.cursor_path = discover_cursor_path(config.cursor_path) or "cursor-agent"
        config.gemini_path = discover_gemini_path(config.gemini_path) or "gemini"
        if not config.project_path:
            raise ValueError("project_path is required")
        if config.read_source == "ui" and not config.target_chats:
            raise ValueError("target_chats is required when read_source is ui")
        if config.read_source == "api_dm":
            if not config.dm_target_id:
                raise ValueError("dm_target_id is required when read_source is api_dm")
            if config.dm_target_id == config.report_chat_id:
                raise ValueError("dm_target_id must be different from report_chat_id in api_dm mode")
        if config.read_source == "discord":
            if not config.discord_bot_token:
                raise ValueError("discord_bot_token is required when read_source is discord")
            if not config.discord_prompt_channel_id:
                raise ValueError("discord_prompt_channel_id is required when read_source is discord")
        if config.send_source == "discord":
            if not config.discord_bot_token:
                raise ValueError("discord_bot_token is required when send_source is discord")
            if not config.codex_result_chat_id:
                raise ValueError("codex_result_chat_id is required when send_source is discord")
            if not config.evening_report_chat_id:
                raise ValueError("evening_report_chat_id is required when send_source is discord")
        if config.send_source == "ui" and not config.codex_result_chat_id:
            raise ValueError("codex_result_chat_id is required")
        return config

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json_error(self, status: int, message: str) -> None:
        body = json.dumps({"ok": False, "error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


class AutomationServer(ThreadingHTTPServer):
    allow_reuse_address = True
    app_config: AutomationConfig
    state: AutomationState
    logs: LogBuffer
    automation: LarkAutomation
    scheduler: Scheduler
    hotkey_monitor: StopHotkeyMonitor


def main() -> None:
    config = load_config()
    state = AutomationState()
    logs = LogBuffer()
    automation = LarkAutomation(config, state, logs)
    scheduler = Scheduler(automation, state, logs)
    scheduler.start_thread()
    hotkey_monitor = StopHotkeyMonitor(scheduler, logs, config.stop_hotkey)
    hotkey_monitor.start()

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8787"))
    server = AutomationServer((host, port), AppHandler)
    server.app_config = config
    server.state = state
    server.logs = logs
    server.automation = automation
    server.scheduler = scheduler
    server.hotkey_monitor = hotkey_monitor

    logs.add(f"Web app ready at http://{host}:{port}")
    logs.add("Dry-run is enabled by default. Disable it in Config for live actions.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logs.add("Shutting down.")
    finally:
        hotkey_monitor.shutdown()
        scheduler.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
