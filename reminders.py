"""
reminders.py

Lets you set daily diagnosis reminders by texting the Telegram bot --
no need to touch the Pi. Runs a long-polling thread in the background
(thread-safe, same pattern as PresenceDetector/FallDetector) and
persists reminders to disk so they survive a reboot.

You can drive everything with typed commands, or tap inline buttons
(sent as part of the bot's replies) instead:

    /remind 14:30        -- add a daily reminder at 14:30
    /remind list          -- show all active reminders
    /remind cancel 14:30  -- remove that one
    /remind clear          -- remove all
    /diagnose               -- run a check-in right now, no reminder needed
    /help or /start          -- usage + main menu buttons
"""

import json
import os
import re
import threading
import time
from datetime import datetime

import requests

from alarm.notifier import BOT_TOKEN, CHAT_ID

import config

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

HELP_TEXT = (
    "VitalBot reminders:\n"
    "/remind HH:MM - add a daily reminder (e.g. /remind 14:30)\n"
    "/remind list - show active reminders\n"
    "/remind cancel HH:MM - remove one\n"
    "/remind clear - remove all\n"
    "/diagnose - run a check-in right now\n\n"
    "Or just tap a button below 👇"
)

# Preset times offered on the "add reminder" keyboard. Custom times are
# still available via typed /remind HH:MM.
TIME_PRESETS = ["07:00", "08:00", "09:00", "12:00", "18:00", "21:00"]


# =========================
# Keyboard builders
# =========================

def _main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🩺 Diagnose now", "callback_data": "diagnose"}],
            [{"text": "⏰ Add reminder", "callback_data": "remind_add"}],
            [{"text": "📋 List reminders", "callback_data": "remind_list"}],
            [{"text": "🗑️ Clear all", "callback_data": "remind_clear"}],
            [{"text": "🌐 Language", "callback_data": "language"}],
        ]
    }


def _time_preset_keyboard():
    def button(t):
        return {"text": t, "callback_data": f"remind_time_{t}"}

    rows = [
        [button(t) for t in TIME_PRESETS[i:i + 3]]
        for i in range(0, len(TIME_PRESETS), 3)
    ]
    rows.append([{"text": "⬅️ Back", "callback_data": "menu"}])
    return {"inline_keyboard": rows}


def _cancel_keyboard(times):
    """Built dynamically from currently active reminders so it always
    matches what's actually on disk."""
    rows = [
        [{"text": f"❌ {t}", "callback_data": f"remind_cancel_{t}"}]
        for t in times
    ]
    rows.append([{"text": "⬅️ Back", "callback_data": "menu"}])
    return {"inline_keyboard": rows}


class ReminderBot:
    def __init__(self, storage_path=None):
        self._lock = threading.Lock()
        self._storage_path = storage_path or config.REMINDERS_FILE
        # {"14:30": {"last_fired_date": "2026-07-15" or None}}
        self._reminders = self._load()
        self._offset = None
        self._running = False
        self._manual_requested = False
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)

    def start(self):
        self._running = True
        self._thread.start()
        print("Reminder bot listening for Telegram commands.")

    def stop(self):
        self._running = False

    # =========================
    # Persistence
    # =========================

    def _load(self):
        if os.path.exists(self._storage_path):
            try:
                with open(self._storage_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                print("[reminders] could not read reminders file, starting empty")
        return {}

    def _save(self):
        try:
            with open(self._storage_path, "w") as f:
                json.dump(self._reminders, f, indent=2)
        except OSError as e:
            print(f"[reminders] failed to save: {e}")

    # =========================
    # Due-reminder check (called from the idle loop)
    # =========================

    def get_due_reminder(self):
        """
        Returns a time string like "14:30" if a reminder is due right now
        and hasn't already fired today, else None. Call mark_fired() once
        the diagnosis for it actually runs.
        """
        now = datetime.now()
        current_hhmm = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        with self._lock:
            entry = self._reminders.get(current_hhmm)
            if entry is not None and entry.get("last_fired_date") != today:
                return current_hhmm
        return None

    def mark_fired(self, hhmm):
        today = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            if hhmm in self._reminders:
                self._reminders[hhmm]["last_fired_date"] = today
                self._save()

    def pop_manual_request(self):
        """
        Returns True once if /diagnose was texted (or tapped) since the
        last check, then clears the flag -- same one-shot pattern as a
        due reminder, so main.py's loop can treat "due" and "on-demand"
        the same way.
        """
        with self._lock:
            if self._manual_requested:
                self._manual_requested = False
                return True
        return False

    # =========================
    # Sending results back
    # =========================

    def send_message(self, text, reply_markup=None):
        data = {"chat_id": CHAT_ID, "text": text}
        if reply_markup is not None:
            data["reply_markup"] = json.dumps(reply_markup)
        try:
            requests.post(
                f"{API_BASE}/sendMessage",
                data=data,
                timeout=10,
            )
        except requests.exceptions.RequestException as e:
            print(f"[reminders] send_message failed: {e}")

    def _answer_callback(self, callback_id, text=None):
        """Stops the button's loading spinner. Best-effort -- a failure
        here shouldn't block handling the tap itself."""
        data = {"callback_query_id": callback_id}
        if text is not None:
            data["text"] = text
        try:
            requests.post(f"{API_BASE}/answerCallbackQuery", data=data, timeout=10)
        except requests.exceptions.RequestException as e:
            print(f"[reminders] answerCallbackQuery failed: {e}")

    # =========================
    # Telegram long-polling
    # =========================

    def _poll_loop(self):
        while self._running:
            try:
                params = {"timeout": config.TELEGRAM_POLL_TIMEOUT_SECONDS}
                if self._offset is not None:
                    params["offset"] = self._offset

                resp = requests.get(
                    f"{API_BASE}/getUpdates",
                    params=params,
                    timeout=config.TELEGRAM_POLL_TIMEOUT_SECONDS + 10,
                )
                resp.raise_for_status()
                updates = resp.json().get("result", [])

                for update in updates:
                    self._offset = update["update_id"] + 1
                    try:
                        self._handle_update(update)
                    except Exception as e:
                        print(f"[reminders] error handling update: {e}")

            except requests.exceptions.RequestException as e:
                print(f"[reminders] poll error: {e}")
                time.sleep(5)  # back off before retrying so a network drop doesn't spin the CPU

    def _handle_update(self, update):
        # Button taps arrive as callback_query updates, not message updates.
        if "callback_query" in update:
            self._handle_callback(update["callback_query"])
            return

        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        if not text:
            return

        # Only accept commands from the configured chat -- otherwise anyone
        # who finds the bot could add/clear reminders on your device.
        if chat_id != str(CHAT_ID):
            print(f"[reminders] ignoring message from unrecognized chat_id={chat_id}")
            return

        self._handle_command(text)

    # =========================
    # Button taps
    # =========================

    def _handle_callback(self, callback_query):
        chat_id = str(
            callback_query.get("message", {}).get("chat", {}).get("id", "")
        )
        data = callback_query.get("data", "")
        callback_id = callback_query.get("id")

        # Ack immediately so the tapped button stops spinning, regardless
        # of whether the chat_id check below passes.
        self._answer_callback(callback_id)

        if chat_id != str(CHAT_ID):
            print(f"[reminders] ignoring callback from unrecognized chat_id={chat_id}")
            return

        if data == "menu":
            self.send_message(HELP_TEXT, reply_markup=_main_menu_keyboard())

        elif data == "diagnose":
            with self._lock:
                self._manual_requested = True
            self.send_message("On it -- starting a check-in now.")

        elif data == "remind_list":
            self._cmd_list()

        elif data == "remind_clear":
            self._cmd_clear()

        elif data == "remind_add":
            self.send_message(
                "Tap a preset time, or send a custom one as /remind HH:MM:",
                reply_markup=_time_preset_keyboard(),
            )

        elif data == "remind_cancel_menu":
            with self._lock:
                times = sorted(self._reminders.keys())
            if not times:
                self.send_message("No reminders set.")
            else:
                self.send_message(
                    "Tap a reminder to remove it:",
                    reply_markup=_cancel_keyboard(times),
                )

        elif data.startswith("remind_time_"):
            self._cmd_add(data.replace("remind_time_", "", 1))

        elif data.startswith("remind_cancel_"):
            self._cmd_cancel(data.replace("remind_cancel_", "", 1))

        elif data == "language":

            self.send_message(

                "Choose a language",

                reply_markup={
                    "inline_keyboard":[

                        [
                            {
                                "text":"🇬🇧 English",
                                "callback_data":"lang_en"
                            }
                        ],

                        [
                            {
                                "text":"🇩🇿 العربية",
                                "callback_data":"lang_ar"
                            }
                        ]
                    ]
                }
            )
        elif data == "lang_en":

            from language import set_language

            set_language("en")

            self.send_message(
                "Language changed to English."
            )
        elif data == "lang_ar":

            from language import set_language

            set_language("ar")

            self.send_message(
                "تم تغيير اللغة إلى العربية."
            )
        else:
            print(f"[reminders] unknown callback_data: {data}")

    # =========================
    # Typed commands
    # =========================

    def _handle_command(self, text):
        parts = text.split(maxsplit=2)
        cmd = parts[0].lower() if parts else ""

        if cmd == "/help" or cmd == "/start":
            self.send_message(HELP_TEXT, reply_markup=_main_menu_keyboard())
            return

        if cmd == "/diagnose":
            with self._lock:
                self._manual_requested = True
            self.send_message("On it -- starting a check-in now.")
            return

        if cmd != "/remind":
            return

        if len(parts) < 2:
            self.send_message(HELP_TEXT, reply_markup=_main_menu_keyboard())
            return

        sub = parts[1].lower()

        if sub == "list":
            self._cmd_list()
        elif sub == "clear":
            self._cmd_clear()
        elif sub == "cancel" and len(parts) >= 3 and TIME_RE.match(parts[2].strip()):
            self._cmd_cancel(parts[2].strip())
        elif TIME_RE.match(sub):
            self._cmd_add(sub)
        else:
            self.send_message(
                f"Didn't understand \"{text}\".\n\n{HELP_TEXT}"
            )

    def _cmd_add(self, hhmm):
        hh, mm = hhmm.split(":")
        hhmm = f"{int(hh):02d}:{mm}"  # normalize e.g. "9:00" -> "09:00" so it can
                                       # actually match strftime's zero-padded output
        with self._lock:
            self._reminders[hhmm] = {"last_fired_date": None}
            self._save()
        self.send_message(f"Reminder set for {hhmm} every day.")

    def _cmd_list(self):
        with self._lock:
            times = sorted(self._reminders.keys())
        if not times:
            self.send_message("No reminders set.")
        else:
            self.send_message(
                "Reminders:\n" + "\n".join(times),
                reply_markup=_cancel_keyboard(times),
            )

    def _cmd_cancel(self, hhmm):
        hh, mm = hhmm.split(":")
        hhmm = f"{int(hh):02d}:{mm}"
        with self._lock:
            existed = self._reminders.pop(hhmm, None) is not None
            if existed:
                self._save()
        self.send_message(f"Removed {hhmm}." if existed else f"No reminder at {hhmm}.")

    def _cmd_clear(self):
        with self._lock:
            self._reminders = {}
            self._save()
        self.send_message("All reminders cleared.")