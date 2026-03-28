# ================================================================
#  PROJECT  : Self-Healing Network — Enterprise Edition
#  VERSION  : 2.0  (Audit Trail + Cisco Webex Alerting)
#  DEVICE   : Cisco Catalyst 8000v  (IOS-XE)
#  LIBRARIES: netmiko, requests (pip install netmiko requests)
#
#  NEW IN v2.0
#  ─────────────────────────────────────────────────────────────
#  ★ FEATURE 1 — AUTOMATED AUDIT TRAIL
#    Captures a full router state snapshot BEFORE and AFTER every
#    healing event and writes it to timestamped .txt files.
#    This satisfies compliance, change-management, and post-mortem
#    requirements that every real NOC team has.
#
#  ★ FEATURE 2 — CISCO WEBEX ALERTING
#    Sends real-time incident notifications and resolution alerts
#    to a Webex space via the Webex REST API.
#    This replaces "checking a terminal window" with push alerts
#    that reach engineers wherever they are — the same pattern
#    used in production SOC/NOC environments.
#
#  ARCHITECTURE PATTERN: Observe → Alert → Audit → Act → Audit → Verify → Alert
# ================================================================


# ── IMPORTS ──────────────────────────────────────────────────────

# netmiko — SSH automation for network devices (Cisco, Juniper, etc.)
from netmiko import ConnectHandler

# requests — Industry-standard HTTP library for REST API calls.
# We use it to POST messages to the Cisco Webex API endpoint.
import requests

# re — Regular expressions for parsing CLI show-command output.
import re

# time — Used to pause script execution during interface convergence.
import time

# datetime — Generates precise timestamps for log files and messages.
from datetime import datetime

# os — Used to build safe, OS-agnostic file paths for audit logs.
import os


# ════════════════════════════════════════════════════════════════
# SECTION 1: GLOBAL CONFIGURATION
# All credentials and settings live here. In production, these
# would be pulled from environment variables or a secrets vault
# (e.g., HashiCorp Vault, AWS Secrets Manager) — NEVER hardcoded.
# For this PoC, we use clearly labelled placeholders.
# ════════════════════════════════════════════════════════════════

# ── 1A: Network Device Profile ───────────────────────────────────
DEVICE = {
    "device_type" : "cisco_xe",
    "host"        : "devnetsandboxiosxec8k.cisco.com",
    "port"        : 22,
    "username"    : "lakshmanan.e1652",
    "password"    : "jR3H_Nl43Llv-D4u",
}

print("😈 CHAOS MONKEY INITIATED: Logging in to sabotage Loopback100...")
connection = ConnectHandler(**DEVICE)
connection.enable()

# Send the shutdown command
connection.send_config_set(["interface Loopback100", "shutdown"])
connection.disconnect()

print("💥 SABOTAGE COMPLETE: Loopback100 is now DOWN. Watch your monitor script!")

# ── 1B: Cisco Webex API Configuration ────────────────────────────
# Your Personal Access Token from developer.webex.com
# KEEP THIS SECRET — treat it like a password.
WEBEX_ACCESS_TOKEN = "MGRmZjliN2YtMzM3MS00ODI0LWJhMGYtOWFmOTFmNzJlNzFhMzMzODEwOGMtYjRl_P0A1_381a95f5-7349-4f5b-bc0d-1e1f574b419a"  # ← Replace

# The ID of the Webex Space (Room) where alerts will be posted.
# To find your Room ID:
#   1. Go to https://developer.webex.com/docs/api/v1/rooms/list-rooms
#   2. Click "Run" — find your space name and copy the 'id' field.
WEBEX_TARGET_EMAIL = "lakshmanan.e1652@gmail.com"# ← Replace

# The Webex Messages API endpoint — this never changes.
WEBEX_API_URL = "https://webexapis.com/v1/messages"

# ── 1C: Script Behaviour Settings ────────────────────────────────
TARGET_INTERFACE  = "Loopback100"   # The interface to monitor
CONVERGENCE_DELAY = 3               # Seconds to wait after a config change
AUDIT_LOG_DIR     = "audit_logs"    # Local folder where .txt files are saved


# ════════════════════════════════════════════════════════════════
# SECTION 2: LOGGING HELPER
# Centralised function for printing timestamped console messages.
# Every action the script takes is printed with:
#   [TIMESTAMP] [LEVEL]  Message
# Levels used: INFO, ALERT, AUDIT, WEBEX, ERROR, WARN
# ════════════════════════════════════════════════════════════════
def log(message, level="INFO"):
    """Prints a formatted, timestamped message to the console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # :<6 pads the level string to 6 characters for clean column alignment
    print(f"[{timestamp}] [{level:<6}] {message}")


# ════════════════════════════════════════════════════════════════
# SECTION 3: ★ FEATURE 1 — AUTOMATED AUDIT TRAIL
#
# WHY THIS MATTERS TO RECRUITERS:
# Every enterprise network change must be documented. Change
# Management frameworks (ITIL, ISO 27001) require proof of:
#   • What the network state was BEFORE a change
#   • What the network state was AFTER a change
#   • Who/what made the change and exactly when
# This function automates that requirement completely.
# ════════════════════════════════════════════════════════════════
def save_audit_log(content, filename_prefix, event_description):
    """
    Saves a snapshot of router CLI output to a timestamped .txt file.

    The file is saved to the AUDIT_LOG_DIR folder. The folder is
    created automatically if it does not already exist.

    Args:
        content          (str) : The raw CLI text output to save.
        filename_prefix  (str) : File label, e.g. 'pre_heal_audit'
                                 or 'post_heal_audit'.
        event_description(str) : Human-readable label for the log header.

    Returns:
        str : The full file path of the saved log (used in console output).
    """

    # ── Step 1: Ensure the audit log directory exists ─────────────
    # os.makedirs() creates the folder AND any missing parent folders.
    # exist_ok=True means it won't crash if the folder already exists.
    os.makedirs(AUDIT_LOG_DIR, exist_ok=True)

    # ── Step 2: Build the filename with a timestamp ────────────────
    # Example output: pre_heal_audit_2025-06-10_14-32-01.txt
    # The timestamp makes every file unique — no overwrites, full history.
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename      = f"{filename_prefix}_{timestamp_str}.txt"
    filepath      = os.path.join(AUDIT_LOG_DIR, filename)

    # ── Step 3: Build the file content with a structured header ───
    # The header makes the file self-documenting — anyone opening it
    # immediately knows what it is, when it was created, and why.
    file_header = (
        f"{'=' * 65}\n"
        f"  SELF-HEALING NETWORK — AUTOMATED AUDIT LOG\n"
        f"{'=' * 65}\n"
        f"  Event       : {event_description}\n"
        f"  Timestamp   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"  Device Host : {DEVICE['host']}\n"
        f"  Interface   : {TARGET_INTERFACE}\n"
        f"  Script      : self_healing_enterprise.py v2.0\n"
        f"{'=' * 65}\n\n"
        f"  --- RAW DEVICE OUTPUT BELOW ---\n\n"
    )

    # ── Step 4: Write the header + CLI content to disk ─────────────
    # 'w' mode creates the file if it doesn't exist, overwrites if it does.
    # encoding='utf-8' ensures special characters are handled correctly.
    with open(filepath, 'w', encoding='utf-8') as audit_file:
        audit_file.write(file_header)
        audit_file.write(content)

    log(f"Audit log saved → {filepath}", level="AUDIT")
    return filepath


# ════════════════════════════════════════════════════════════════
# SECTION 4: ★ FEATURE 2 — CISCO WEBEX ALERTING
#
# WHY THIS MATTERS TO RECRUITERS:
# Modern NOC/SOC teams do not watch terminal windows. They get
# push notifications via Slack, Teams, or Webex when something
# happens. This function replicates that pattern exactly:
#   1. Our script detects an outage
#   2. It calls the Webex REST API with a POST request
#   3. The message appears instantly in the team's Webex space
# This is a real API integration — the same technique used in
# production CI/CD pipelines and Network Event Management systems.
# ════════════════════════════════════════════════════════════════
def send_webex_alert(message_text):
    """
    Sends a message to a Cisco Webex Space via the REST API.

    The Webex Messages API works like any REST API:
      • Method  : POST (we are CREATING a new message resource)
      • Endpoint: https://webexapis.com/v1/messages
      • Auth    : Bearer token in the Authorization header
      • Body    : JSON payload with roomId and the message text

    Args:
        message_text (str): The text to post to the Webex space.

    Returns:
        bool: True if the message was sent successfully, False on failure.
    """

    log(f"Sending Webex alert → '{message_text[:50]}...'", level="WEBEX")

    # ── HTTP Headers ───────────────────────────────────────────────
    # Every request to the Webex API requires:
    #   Authorization: Bearer <token>  — proves we are allowed to post
    #   Content-Type: application/json — tells the API our body is JSON
    headers = {
        "Authorization" : f"Bearer {WEBEX_ACCESS_TOKEN}",
        "Content-Type"  : "application/json",
    }

    # ── Request Body ───────────────────────────────────────────────
    # The Webex API requires at minimum:
    #   roomId   — which space to post to
    #   text     — the plain-text message content
    # (The API also supports 'markdown' for rich formatting)
    payload = {
        "toPersonEmail": WEBEX_ROOM_ID,  # This uses the email you put in WEBEX_ROOM_ID
        "text": message,                 # Plain text fallback
        "markdown": message              # For nice bold/code formatting
    }
    # ── Make the HTTP POST request ─────────────────────────────────
    # We wrap this in try/except because network calls can always fail
    # (timeout, auth error, API downtime). We must not let a failed
    # Webex notification crash the actual network healing logic.
    try:
        response = requests.post(
            WEBEX_API_URL,
            headers = headers,
            json    = payload,    # 'json=' auto-serialises the dict and sets Content-Type
            timeout = 10          # Give up after 10 seconds if no response
        )

        # HTTP 200 = OK, HTTP 200 family = success
        # response.raise_for_status() throws an exception for 4xx / 5xx codes
        response.raise_for_status()

        log(f"Webex alert delivered successfully (HTTP {response.status_code})", level="WEBEX")
        return True

    except requests.exceptions.HTTPError as http_err:
        # 401 = bad token, 403 = wrong room, 404 = room not found
        log(f"Webex HTTP Error: {http_err}", level="ERROR")
        log("Check: Is your WEBEX_ACCESS_TOKEN correct? Is WEBEX_ROOM_ID valid?", level="ERROR")
        return False

    except requests.exceptions.ConnectionError:
        # Fired when there is no internet or DNS fails
        log("Webex Connection Error: Cannot reach webexapis.com. Check internet.", level="ERROR")
        return False

    except requests.exceptions.Timeout:
        # Fired when the API takes longer than our 10-second timeout
        log("Webex Timeout: API did not respond within 10 seconds.", level="ERROR")
        return False


# ════════════════════════════════════════════════════════════════
# SECTION 5: INTERFACE STATUS CHECKER (Unchanged from v1.0)
# Sends 'show ip interface brief', parses the output with regex,
# and returns the interface status as a clean string.
# ════════════════════════════════════════════════════════════════
def get_interface_status(connection, interface):
    """
    Returns the current status string of the given interface.
    Possible return values: 'up', 'administratively down', 'unknown'
    """
    log(f"Polling 'show interfaces {interface}'...")
    raw_output = connection.send_command(f"show interfaces {interface}")

    # Regex captures the word(s) after "is " on the first line of output.
    # Example line: "Loopback100 is administratively down, line protocol is down"
    pattern = rf"{re.escape(interface)} is ([\w\s]+?),"
    match   = re.search(pattern, raw_output, re.IGNORECASE)

    if match:
        status = match.group(1).strip().lower()
        log(f"Interface status parsed: '{status}'")
        return status
    else:
        log("Could not parse interface status from output.", level="WARN")
        return "unknown"


# ════════════════════════════════════════════════════════════════
# SECTION 6: SELF-HEALING ENGINE (Upgraded in v2.0)
# This is where all three capabilities combine:
#   1. Save PRE-heal audit snapshot
#   2. Send "outage detected" Webex alert
#   3. Push 'no shutdown' config
#   4. Save POST-heal audit snapshot
#   5. Send "resolved" Webex alert
# ════════════════════════════════════════════════════════════════
def heal_interface(connection, interface):
    """
    Performs the complete v2.0 self-healing sequence with full
    audit trail and Webex alerting at each critical stage.
    """

    log("=" * 55, level="INFO")
    log("  SELF-HEALING SEQUENCE INITIATED", level="ALERT")
    log("=" * 55, level="INFO")

    # ── STEP 1: Capture PRE-heal audit snapshot ────────────────────
    # We snapshot 'show ip interface brief' BEFORE making any change.
    # This is the "Before" evidence for our change management record.
    log("Capturing PRE-HEAL audit snapshot...", level="AUDIT")
    pre_heal_output = connection.send_command("show ip interface brief")

    # Save the raw output to pre_heal_audit_<timestamp>.txt
    pre_log_path = save_audit_log(
        content           = pre_heal_output,
        filename_prefix   = "pre_heal_audit",
        event_description = f"OUTAGE DETECTED — {interface} is administratively down"
    )

    # ── STEP 2: Send the Webex OUTAGE alert ───────────────────────
    # Notify the team IMMEDIATELY when an outage is confirmed.
    # We alert BEFORE healing so the team knows the issue existed,
    # even if healing completes in seconds (audit trail requirement).
    outage_message = (
        f"🚨 **Network Outage Detected**\n"
        f"• **Device**    : `{DEVICE['host']}`\n"
        f"• **Interface** : `{interface}`\n"
        f"• **Status**    : `administratively down`\n"
        f"• **Action**    : Initiating Netmiko Self-Healing Protocol.\n"
        f"• **Audit Log** : `{os.path.basename(pre_log_path)}`\n"
        f"• **Time**      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_webex_alert(outage_message)

    # ── STEP 3: Push the healing configuration ─────────────────────
    # send_config_set() automatically wraps commands in
    # 'configure terminal' ... 'end' — no need to type them manually.
    log("Pushing 'no shutdown' configuration to device...", level="INFO")
    healing_commands = [
        f"interface {interface}",
        "no shutdown",
    ]
    config_output = connection.send_config_set(healing_commands)
    log(f"Config push complete. Router response:\n{config_output}")

    # ── STEP 4: Wait for interface convergence ─────────────────────
    # Interfaces take a moment to transition from down → up.
    # Checking status immediately could return a false "still down."
    log(f"Waiting {CONVERGENCE_DELAY}s for interface convergence...", level="INFO")
    time.sleep(CONVERGENCE_DELAY)

    # ── STEP 5: Capture POST-heal audit snapshot ───────────────────
    # Snapshot the router state AFTER healing — the "After" evidence.
    # Comparing pre vs post files proves the automation worked.
    log("Capturing POST-HEAL audit snapshot...", level="AUDIT")
    post_heal_output = connection.send_command("show ip interface brief")

    post_log_path = save_audit_log(
        content           = post_heal_output,
        filename_prefix   = "post_heal_audit",
        event_description = f"HEAL ATTEMPT COMPLETED — {interface} no shutdown issued"
    )

    # ── STEP 6: Verify the heal was successful ─────────────────────
    final_status = get_interface_status(connection, interface)

    if final_status == "up":
        log(f"HEAL SUCCESSFUL ✅  {interface} is now [{final_status.upper()}]", level="INFO")

        # ── STEP 7: Send the Webex RESOLUTION alert ────────────────
        # Notify the team that the incident is resolved.
        # Include file names so the team knows where to find evidence.
        resolution_message = (
            f"✅ **Self-Healing Success — Network Restored**\n"
            f"• **Device**    : `{DEVICE['host']}`\n"
            f"• **Interface** : `{interface}`\n"
            f"• **Status**    : `up` (restored automatically)\n"
            f"• **Pre-Heal Audit**  : `{os.path.basename(pre_log_path)}`\n"
            f"• **Post-Heal Audit** : `{os.path.basename(post_log_path)}`\n"
            f"• **Time**      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"• **Action Required** : None — automated remediation complete."
        )
        send_webex_alert(resolution_message)
        return True

    else:
        # Healing failed — alert the team for manual intervention
        log(f"HEAL FAILED ❌  {interface} is still reporting: '{final_status}'", level="ERROR")

        failure_message = (
            f"❌ **Self-Healing FAILED — Manual Intervention Required**\n"
            f"• **Device**    : `{DEVICE['host']}`\n"
            f"• **Interface** : `{interface}`\n"
            f"• **Status**    : `{final_status}` (still down after repair attempt)\n"
            f"• **Audit Log** : `{os.path.basename(post_log_path)}`\n"
            f"• **Time**      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"• **Action Required** : ⚠️ Please investigate immediately."
        )
        send_webex_alert(failure_message)
        return False


# ════════════════════════════════════════════════════════════════
# SECTION 7: DEMO SETUP — INTERFACE BREAKER
# If the interface is UP when you run the script, this function
# intentionally shuts it down to stage the demo.
# Run the script TWICE:
#   Run 1 (UP)   → Breaks it.  "Run again to see healing."
#   Run 2 (DOWN) → Heals it.   Webex alert fires. Logs saved. ✅
# ════════════════════════════════════════════════════════════════
def break_interface(connection, interface):
    """Intentionally shuts down the interface to stage the healing demo."""

    log(f"{interface} is UP. Staging demo failure state...", level="INFO")
    shutdown_commands = [
        f"interface {interface}",
        "shutdown",
    ]
    connection.send_config_set(shutdown_commands)

    print()
    print("=" * 65)
    print("  🔴  DEMO STAGED — Interface is now ADMINISTRATIVELY DOWN.")
    print()
    print("  ▶   Run the script AGAIN to trigger:")
    print("       • Webex outage alert")
    print("       • Pre-heal audit log saved")
    print("       • Automatic no shutdown")
    print("       • Post-heal audit log saved")
    print("       • Webex resolution alert")
    print("=" * 65)
    print()


# ════════════════════════════════════════════════════════════════
# SECTION 8: MAIN ORCHESTRATOR
#
# This function is the conductor — it calls every other function
# in the correct order. The full v2.0 flow is:
#
#  SSH Connect
#      │
#      ▼
#  Check Interface Status
#      │
#      ├── [administratively down] ──► PRE-AUDIT → WEBEX ALERT
#      │                                   → HEAL → POST-AUDIT
#      │                                   → VERIFY → WEBEX ALERT
#      │
#      └── [up] ──────────────────────► Stage demo (shutdown)
# ════════════════════════════════════════════════════════════════
def main():
    print()
    print("=" * 65)
    print("   🔧  SELF-HEALING NETWORK v2.0  |  Enterprise Edition")
    print("   ★  Features: Audit Trail + Cisco Webex Alerting")
    print("=" * 65)
    log(f"Target Device   : {DEVICE['host']}:{DEVICE['port']}")
    log(f"Interface Watch : {TARGET_INTERFACE}")
    log(f"Audit Log Dir   : ./{AUDIT_LOG_DIR}/")
    log(f"Webex Target    : {WEBEX_TARGET_EMAIL}")
    print()

    connection = None

    try:
        # ── Connect via SSH ────────────────────────────────────────
        log(f"Initiating SSH connection to {DEVICE['host']}...")
        connection = ConnectHandler(**DEVICE)
        connection.enable()
        log("SSH connected. Privileged mode active. ✅")
        print()

        # ── Observe: Check current interface state ─────────────────
        log(f"--- PHASE 1: OBSERVE — Checking {TARGET_INTERFACE} ---")
        current_status = get_interface_status(connection, TARGET_INTERFACE)
        print()

        # ── Analyze & Act: Decision engine ─────────────────────────
        log(f"--- PHASE 2: ANALYZE — Status is '{current_status}' ---")
        print()

        if current_status == "administratively down":
            # ── HEALING PATH: Full v2.0 sequence ──────────────────
            log(f"--- PHASE 3: ACT — Self-Healing + Audit + Webex ---")
            heal_interface(connection, TARGET_INTERFACE)

        elif current_status == "up":
            # ── HEALTHY PATH: Do nothing ──────────
            log(f"--- PHASE 3: ACT — Network is HEALTHY. No action required. ---")
            # (We deleted the break_interface line here so it just watches)
            break_interface(connection, TARGET_INTERFACE)

        else:
            # ── UNKNOWN STATE: Cannot act safely ──────────────────
            log(f"Status '{current_status}' is unrecognised. No action taken.", level="WARN")
            log("Verify interface name and device connectivity.", level="WARN")

    except Exception as error:
        print()
        log(f"FATAL ERROR: {error}", level="ERROR")
        log("Checklist:", level="ERROR")
        log("  1. Credentials correct in DEVICE dictionary?", level="ERROR")
        log("  2. Run: Test-NetConnection -ComputerName <host> -Port 22", level="ERROR")
        log("  3. Check sandbox status: devnetsandbox.cisco.com", level="ERROR")

    finally:
        # Always disconnect cleanly — even if an error occurred above
        if connection:
            connection.disconnect()
            print()
            log("SSH session closed cleanly. ✅")

    print()
    print("=" * 65)
    log("Script execution complete. Check ./audit_logs/ for files.")
    print("=" * 65)
    print()


# ── ENTRY POINT ───────────────────────────────────────────────────
# ── ENTRY POINT ───────────────────────────────────────────────────
if __name__ == "__main__":
    import time
    print("\n🚀 STARTING ALWAYS-ON NETWORK MONITOR...")
    while True:
        main()
        log("Sleeping for 15 seconds before next health check...\n", level="INFO")
        time.sleep(15)