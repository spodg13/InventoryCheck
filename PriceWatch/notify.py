"""Send a text through this Mac's Messages app (iMessage, falling back to SMS relay).

SMS fallback works when your iPhone has Settings > Messages > Text Message Forwarding
enabled for this Mac, so the text goes out over your AT&T line.
"""
from __future__ import annotations

import os
import subprocess

SCRIPT = """
on run argv
    set msg to item 1 of argv
    set phone to item 2 of argv
    tell application "Messages"
        try
            set svc to 1st account whose service type = iMessage
            send msg to participant phone of svc
        on error
            set svc to 1st account whose service type = SMS
            send msg to participant phone of svc
        end try
    end tell
end run
"""


DEFAULT_LABEL = "🧪 SpodgLabs PriceWatch"


def send_text(message: str, dry_run: bool = False) -> bool:
    phone = os.getenv("ALERT_PHONE", "").strip()
    # First line of every text, so alerts stand out in your own Messages thread.
    # Set ALERT_LABEL in .env to change it, or ALERT_LABEL= (empty) to turn it off.
    label = os.getenv("ALERT_LABEL", DEFAULT_LABEL).strip()
    if label:
        message = f"{label}\n{message}"
    if dry_run or not phone:
        if not phone and not dry_run:
            print("⚠️  ALERT_PHONE not set in .env - printing instead of texting.")
        print(f"[text] {message}")
        return False
    try:
        subprocess.run(["osascript", "-e", SCRIPT, message, phone],
                       check=True, capture_output=True, text=True, timeout=30)
        print(f"📱 Texted {phone}: {message}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Messages send failed: {e.stderr.strip()}")
    except subprocess.TimeoutExpired:
        print("❌ Messages send timed out")
    return False
