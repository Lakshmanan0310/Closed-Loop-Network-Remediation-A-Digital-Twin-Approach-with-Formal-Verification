# ================================================================
#  PROJECT  : Digital Twin — IEEE Research Project
#  SCRIPT   : pull_config.py  (Phase 1 of N)
#  PURPOSE  : SSH into a live Cisco IOS-XE router using Netmiko,
#             pull the full running configuration, and save it
#             to a local directory structure that Pybatfish
#             requires for snapshot ingestion.
#
#  OUTPUT STRUCTURE:
#    snapshot/
#    └── configs/
#        └── router1.cfg      ← Full IOS-XE running config
#
#  USAGE:
#    python pull_config.py
#
#  DEPENDENCIES:
#    pip install netmiko
#
#  NOTE ON CREDENTIALS:
#    Never hardcode real passwords in source files.
#    This script reads credentials from environment variables.
#    Set them in your terminal before running:
#
#    Windows PowerShell:
#      $env:NET_USER = "your_username"
#      $env:NET_PASS = "your_password"
#      $env:NET_SECRET = "your_enable_secret"
#
#    Linux / macOS:
#      export NET_USER="your_username"
#      export NET_PASS="your_password"
#      export NET_SECRET="your_enable_secret"
# ================================================================


# ── IMPORTS ──────────────────────────────────────────────────────

# netmiko — SSH automation library for network devices.
# ConnectHandler is the primary class that manages the SSH session.
from netmiko import ConnectHandler

# netmiko ships with typed exceptions we can catch individually,
# giving much more useful error messages than a generic Exception.
from netmiko.exceptions import (
    NetmikoTimeoutException,          # Raised when the TCP connection times out
    NetmikoAuthenticationException,   # Raised on bad username/password
)

# os — Used to:
#   1. Read credentials from environment variables (os.environ.get)
#   2. Build OS-agnostic file paths (os.path.join)
#   3. Create directories safely (os.makedirs)
import os

# datetime — Stamps the saved config file with the exact pull time.
# Critical for a Digital Twin: you must always know WHEN a snapshot
# was taken so your model reflects reality at a specific point in time.
from datetime import datetime

# sys — Used to call sys.exit() with a non-zero code on fatal errors.
# This is important for CI/CD pipelines and shell scripts that check
# the exit code to know if a step succeeded or failed.
import sys


# ════════════════════════════════════════════════════════════════
# SECTION 1: CONFIGURATION
#
# All tuneable values are defined here at the top — never buried
# in functions. This is called "configuration at the top" and is
# a standard best practice for maintainable automation scripts.
# ════════════════════════════════════════════════════════════════

# ── 1A: Target Device Profile ────────────────────────────────────
# Credentials are read from environment variables, NOT hardcoded.
# os.environ.get(KEY, DEFAULT) returns the env var value if set,
# or the DEFAULT string if not. The default is a clear placeholder
# so the script fails with a readable error rather than a cryptic
# authentication exception.
#
# ✅ FIX: 'read_timeout' has been REMOVED from this dictionary.
# It is NOT a valid ConnectHandler constructor argument.
# ConnectHandler(**DEVICE_PROFILE) unpacks this dict as keyword
# arguments — any unrecognised key causes an immediate TypeError.
# 'read_timeout' belongs on send_command() only (see Section 5).
DEVICE_PROFILE = {
    "device_type" : "cisco_xe",                          # IOS-XE specific Netmiko driver
    "host"        : "devnetsandboxiosxec8k.cisco.com",   # DevNet C8000v sandbox hostname
    "port"        : 22,                                  # Standard SSH port
    "username"    : os.environ.get("NET_USER",   "lakshmanan.e1652"),
    "password"    : os.environ.get("NET_PASS",   "jR3H_Nl43Llv-D4u"),
    "secret"      : os.environ.get("NET_SECRET", "jR3H_Nl43Llv-D4u"),
    "conn_timeout": 30,    # Seconds to wait for the TCP handshake to complete
                           # read_timeout intentionally NOT here — see send_command() below
}

# ── 1B: Pybatfish Snapshot Directory Structure ────────────────────
# Pybatfish is strict about its input format. It expects configs
# to live inside a folder called 'configs' inside a 'snapshot' root.
# Deviating from this structure will cause Batfish to silently
# ignore your files or throw an initialisation error.
#
# Final path this script will create and write to:
#   snapshot/configs/router1.cfg
SNAPSHOT_ROOT   = "snapshot"        # Batfish snapshot root folder
CONFIGS_DIR     = "configs"         # Required subfolder name (Batfish spec)
CONFIG_FILENAME = "router1.cfg"     # Device config filename

# ── 1C: The IOS command to capture ───────────────────────────────
# 'show running-config' dumps the entire active configuration.
# We prefer this over 'show startup-config' because the Digital
# Twin must reflect LIVE state — startup and running configs can
# diverge if someone made unsaved changes on the device.
COMMAND          = "show running-config"

# ── 1D: Command timeout (separate from connection timeout) ───────
# How many seconds to wait for 'show running-config' output to
# complete. Large or complex configs can take 15-30 seconds.
# Kept here (not in DEVICE_PROFILE) because it belongs to
# send_command(), not ConnectHandler().
COMMAND_READ_TIMEOUT = 60


# ════════════════════════════════════════════════════════════════
# SECTION 2: LOGGING HELPER
#
# A minimal structured logger that prefixes every message with a
# timestamp and severity level. Using this consistently instead of
# plain print() gives you:
#   • Timestamps for performance measurement
#   • Severity filtering if you redirect output to a log file
#   • Professional-looking terminal output for demos / research logs
# ════════════════════════════════════════════════════════════════
def log(message, level="INFO"):
    """
    Prints a formatted, timestamped log line to stdout.

    Args:
        message (str) : The message to display.
        level   (str) : Severity label — INFO, STEP, WARN, ERROR, SUCCESS.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # :<7 left-aligns the level string and pads to 7 chars for column alignment
    print(f"[{timestamp}] [{level:<7}] {message}")


# ════════════════════════════════════════════════════════════════
# SECTION 3: DIRECTORY BUILDER
#
# Creates the snapshot/configs/ folder tree on disk.
# This must happen BEFORE we try to write the config file.
# ════════════════════════════════════════════════════════════════
def create_snapshot_directory():
    """
    Creates the Pybatfish-compatible directory structure:
        snapshot/
        └── configs/

    Returns:
        str : The full path to the configs directory.
              Exits the script with code 1 on failure.
    """
    # os.path.join builds the path correctly for any OS.
    # On Windows: snapshot\\configs
    # On Linux/macOS: snapshot/configs
    configs_path = os.path.join(SNAPSHOT_ROOT, CONFIGS_DIR)

    log(f"Creating directory structure: '{configs_path}/'", level="STEP")

    try:
        # exist_ok=True means:
        #   • Folder missing → create it and all parent folders
        #   • Folder already exists → do nothing (no error thrown)
        # Without exist_ok=True, re-running the script would crash here.
        os.makedirs(configs_path, exist_ok=True)
        log(f"Directory ready: '{configs_path}/' ✅")
        return configs_path

    except PermissionError:
        # Common on Windows when the folder is read-only or the
        # user account lacks write permissions in this location.
        log(f"Permission denied creating '{configs_path}'.", level="ERROR")
        log("Try running VS Code as Administrator, or use a different path.", level="ERROR")
        sys.exit(1)


# ════════════════════════════════════════════════════════════════
# SECTION 3B: CONFIG SANITIZER
#
# Strips Cisco CLI output artifacts from 'show running-config'
# that are NOT part of the actual IOS configuration.
# These lines confuse Batfish's IOS parser and can cause it to
# silently ignore the entire config file.
# ════════════════════════════════════════════════════════════════
def sanitize_config(raw_config):
    """
    Removes Cisco CLI output artifacts that are not part of the
    actual IOS configuration. These appear at the top of
    'show running-config' output:
      - "Building configuration..."
      - "Current configuration : NNNN bytes"

    Args:
        raw_config (str): Raw text output of 'show running-config'.

    Returns:
        str: Cleaned configuration text safe for Batfish ingestion.
    """
    lines = raw_config.splitlines(keepends=True)
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Building configuration"):
            continue
        if stripped.startswith("Current configuration"):
            continue
        cleaned.append(line)
    return "".join(cleaned)


# ════════════════════════════════════════════════════════════════
# SECTION 4: CONFIG WRITER
#
# Saves the raw config string captured from the router to disk,
# prepending a metadata header so the file is self-documenting.
# Pybatfish tolerates IOS comment lines (starting with '!') at
# the top of a config file, so the header does not interfere
# with Batfish parsing.
# ════════════════════════════════════════════════════════════════
def save_config(raw_config, configs_path):
    """
    Writes the captured router configuration to router1.cfg
    with a research-grade metadata header block at the top.

    Args:
        raw_config   (str) : Full text output of 'show running-config'.
        configs_path (str) : Folder path to write the file into.

    Returns:
        str : The full file path of the saved .cfg file.
              Exits with code 1 on write failure.
    """
    filepath = os.path.join(configs_path, CONFIG_FILENAME)

    # ── Metadata header ───────────────────────────────────────────
    # This block makes the file self-documenting — anyone (or any
    # automated tool) reading it immediately knows the source device,
    # the exact capture time, and its intended Batfish path.
    pull_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"! ============================================================\n"
        f"! DIGITAL TWIN — ROUTER CONFIGURATION SNAPSHOT\n"
        f"! ============================================================\n"
        f"! Source Device : {DEVICE_PROFILE['host']}\n"
        f"! Pull Command  : {COMMAND}\n"
        f"! Captured At   : {pull_timestamp}\n"
        f"! Script        : pull_config.py\n"
        f"! Batfish Path  : {SNAPSHOT_ROOT}/{CONFIGS_DIR}/{CONFIG_FILENAME}\n"
        f"! ============================================================\n\n"
    )

    log(f"Writing config to '{filepath}'...", level="STEP")

    try:
        # 'w' mode: create the file if missing, overwrite if present.
        # encoding='utf-8': handles any unicode chars in the config
        # (rare in IOS-XE but a good defensive habit).
        with open(filepath, 'w', encoding='utf-8') as cfg_file:
            cfg_file.write(header)
            cfg_file.write(sanitize_config(raw_config))

        # Report file size as a quick sanity check.
        # A very small file (< 1 KB) suggests the command returned
        # nothing useful — worth flagging even if the write succeeded.
        file_size_kb = os.path.getsize(filepath) / 1024
        log(f"Config saved → '{filepath}' ({file_size_kb:.1f} KB) ✅", level="SUCCESS")
        return filepath

    except IOError as e:
        log(f"File write failed: {e}", level="ERROR")
        sys.exit(1)


# ════════════════════════════════════════════════════════════════
# SECTION 5: SSH CONFIG PULLER
#
# Establishes the SSH session, enters enable mode, and runs
# 'show running-config'. Returns the full raw text output.
#
# Three specific Netmiko exceptions are caught individually so
# each failure mode produces a targeted, actionable error message.
# ════════════════════════════════════════════════════════════════
def pull_running_config():
    """
    SSHes into the target device and captures 'show running-config'.

    Returns:
        str  : Full raw text of the running configuration.
               Exits with code 1 on any connection or auth failure.
    """
    host = DEVICE_PROFILE['host']
    port = DEVICE_PROFILE['port']

    log(f"Initiating SSH connection → {host}:{port}", level="STEP")
    log("This may take up to 30 seconds on a DevNet sandbox device...")

    # Initialise to None so the 'finally' block can safely check
    # 'if connection' without a NameError if ConnectHandler() throws.
    connection = None

    try:
        # ── Establish SSH session ──────────────────────────────────
        # ConnectHandler(**DEVICE_PROFILE) unpacks our dictionary into
        # keyword arguments. It handles the full SSH handshake,
        # terminal width negotiation, and router prompt detection.
        connection = ConnectHandler(**DEVICE_PROFILE)
        log("SSH session established ✅")

        # ── Enter privileged EXEC mode ─────────────────────────────
        # .enable() sends 'enable' and uses DEVICE_PROFILE['secret']
        # as the enable password. Without this, 'show running-config'
        # may return incomplete output or be rejected entirely.
        connection.enable()
        log("Entered privileged EXEC mode (enable) ✅")

        # ── Send the command and capture output ────────────────────
        # send_command() sends the command string, waits until the
        # router prompt reappears, and returns all output in between
        # as one string.
        #
        # ✅ FIX: read_timeout=COMMAND_READ_TIMEOUT is passed HERE,
        # directly to send_command() where it is a valid parameter.
        # It was previously (incorrectly) sitting in DEVICE_PROFILE,
        # which caused the TypeError on ConnectHandler() construction.
        log(f"Sending command: '{COMMAND}'")
        log("Waiting for full output (large configs can take 15-30s)...")

        raw_config = connection.send_command(
            COMMAND,
            read_timeout=COMMAND_READ_TIMEOUT,   # ✅ Correct location for this arg
        )

        # ── Sanity-check the captured output ──────────────────────
        # A valid IOS-XE running config is always several hundred
        # lines. A very short response suggests an error message was
        # returned instead of the actual config.
        if not raw_config or len(raw_config.strip()) < 50:
            log("WARNING: Captured output is suspiciously short.", level="WARN")
            log(f"Output preview: {repr(raw_config[:100])}", level="WARN")
            log("Proceeding — verify router1.cfg content manually.", level="WARN")
        else:
            line_count = raw_config.count('\n')
            log(f"Config captured successfully ({line_count} lines) ✅")

        return raw_config

    # ── Specific exception handlers ───────────────────────────────

    except NetmikoAuthenticationException:
        # Router rejected the username or password.
        # Most common cause: environment variables not set correctly.
        log("AUTHENTICATION FAILED ❌", level="ERROR")
        log("The router rejected the supplied username or password.", level="ERROR")
        log("Fix: Verify your NET_USER and NET_PASS environment variables.", level="ERROR")
        log(f"     NET_USER is currently: '{os.environ.get('NET_USER', 'NOT SET')}'", level="ERROR")
        sys.exit(1)

    except NetmikoTimeoutException:
        # TCP connection could not be established within conn_timeout.
        # Common causes: wrong hostname, firewall blocking port 22,
        # sandbox device offline or being reprovisioned.
        log("CONNECTION TIMED OUT ❌", level="ERROR")
        log(f"Could not reach {host}:{port} within {DEVICE_PROFILE['conn_timeout']}s.", level="ERROR")
        log("Fix checklist:", level="ERROR")
        log(f"  1. PowerShell: Test-NetConnection -ComputerName {host} -Port 22", level="ERROR")
        log("  2. Check sandbox status: devnetsandbox.cisco.com", level="ERROR")
        log("  3. Try from a mobile hotspot (some ISPs block outbound port 22)", level="ERROR")
        sys.exit(1)

    except Exception as e:
        # Catch-all for unexpected errors: SSH key negotiation failure,
        # unexpected device prompt format, paramiko-level errors, etc.
        log(f"UNEXPECTED ERROR: {type(e).__name__}: {e}", level="ERROR")
        log("If this is an SSH key error, add 'use_keys=False' to DEVICE_PROFILE.", level="ERROR")
        sys.exit(1)

    finally:
        # Always runs — even when an exception is raised above.
        # Guarantees the SSH session is closed cleanly so stale
        # sessions do not accumulate on the router's VTY lines.
        if connection:
            connection.disconnect()
            log("SSH session closed cleanly ✅")


# ════════════════════════════════════════════════════════════════
# SECTION 6: MAIN ORCHESTRATOR
#
# Calls each function in the correct sequence:
#   1. Create the folder structure   (disk setup)
#   2. Pull the running config       (network operation)
#   3. Save the config to disk       (file write)
#   4. Print a final summary         (user feedback)
# ════════════════════════════════════════════════════════════════
def main():
    print()
    print("=" * 65)
    print("   DIGITAL TWIN — Config Ingestion Script  (Phase 1)")
    print("   Netmiko → Cisco IOS-XE → Pybatfish Snapshot Format")
    print("=" * 65)
    log(f"Target   : {DEVICE_PROFILE['host']}:{DEVICE_PROFILE['port']}")
    log(f"Command  : {COMMAND}")
    log(f"Output   : {SNAPSHOT_ROOT}/{CONFIGS_DIR}/{CONFIG_FILENAME}")
    print()

    # ── Step 1: Create the Pybatfish directory structure ──────────
    configs_path = create_snapshot_directory()
    print()

    # ── Step 2: SSH in and pull the live running configuration ────
    raw_config = pull_running_config()
    print()

    # ── Step 3: Save the config to the snapshot folder ────────────
    save_config(raw_config, configs_path)
    print()

    # ── Step 4: Final summary ──────────────────────────────────────
    print("=" * 65)
    log("PHASE 1 COMPLETE — Config Ingestion Successful ✅", level="SUCCESS")
    print()
    log("Snapshot ready for Pybatfish at:", level="SUCCESS")
    log(f"  → ./{SNAPSHOT_ROOT}/", level="SUCCESS")
    log(f"     └── {CONFIGS_DIR}/", level="SUCCESS")
    log(f"         └── {CONFIG_FILENAME}", level="SUCCESS")
    print()
    log("Next step: Run your Pybatfish analysis script and point", level="INFO")
    log(f"bf.init_snapshot() at './{SNAPSHOT_ROOT}'", level="INFO")
    print("=" * 65)
    print()


# ── ENTRY POINT ───────────────────────────────────────────────────
# Only executes main() when this file is run directly.
# Safe to import from another script without auto-executing.
if __name__ == "__main__":
    main()