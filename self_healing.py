# ================================================================
#  PROJECT : Self-Healing Network — Proof of Concept
#  DEVICE  : Cisco IOS-XE (Cisco DevNet Always-On Sandbox)
#  LIBRARY : Netmiko (SSH automation for network devices)
#  AUTHOR  : [Your Full Name]
#  PURPOSE : Automatically detects and repairs a downed interface.
#            This demonstrates closed-loop network automation —
#            the same principle used in enterprise tools like
#            Cisco DNA Center and Cisco NSO.
# ================================================================


# ── IMPORTS ─────────────────────────────────────────────────────
# Netmiko is the industry-standard Python library for SSH-ing into
# network devices. ConnectHandler is its main connection class.
from netmiko import ConnectHandler

# 're' is Python's built-in Regular Expression library.
# We use it to intelligently search through CLI output text,
# just like a 'grep' command in Linux.
import re

# 'time' lets us pause the script for a set number of seconds.
# We use this to give the router time to process a change before
# we verify the result. This is called "convergence time."
import time

# 'datetime' lets us print a real timestamp with each log message.
# Professional automation scripts always timestamp their actions
# for auditing and troubleshooting purposes.
from datetime import datetime


# ── SECTION 1: DEVICE PROFILE ────────────────────────────────────
# This dictionary is the "connection blueprint" for our target device.
# Netmiko reads this to know HOW and WHERE to connect.
# Think of it as the dial-up card for your SSH session.
# ─────────────────────────────────────────────────────────────────
DEVICE = {
    "device_type" : "cisco_xe",                          # IOS-XE uses "cisco_xe" (NOT "cisco_ios")
    "host"        : "devnetsandboxiosxec8k.cisco.com",   # The DevNet Sandbox hostname
    "port"        : 22,                                  # Standard SSH port
    "username"    : "YOUR_USERNAME_HERE",                # ← Replace with your DevNet credentials
    "password"    : "YOUR_PASSWORD_HERE",                # ← Replace with your DevNet credentials
    "secret"      : "YOUR_ENABLE_SECRET_HERE",           # ← Enable password (often same as password)
                                                         #   Leave as "" if no enable password is needed
}

# ── SECTION 2: SCRIPT SETTINGS ───────────────────────────────────
# These are the key variables that control the script's behavior.
# Defining them here (not buried in the code) is a best practice
# called "configuration at the top." It makes the script easy to
# reuse — you only need to change values in ONE place.
# ─────────────────────────────────────────────────────────────────

# The specific interface we will monitor and control.
# Loopback100 is safe to use on a shared sandbox — it's a virtual,
# software-only interface that has no effect on other users.
TARGET_INTERFACE = "Loopback100"

# How many seconds to wait after sending a config change before
# we verify the result. 3 seconds is safe for most lab devices.
CONVERGENCE_DELAY = 3


# ── SECTION 3: LOGGING HELPER ────────────────────────────────────
# This is a reusable helper function to print clean, timestamped
# log messages. Instead of using plain 'print()', every message
# from this script gets a timestamp and a severity label like:
#   [2025-06-10 14:32:01] [INFO]  Connecting to device...
#   [2025-06-10 14:32:04] [ALERT] Interface is DOWN!
# ─────────────────────────────────────────────────────────────────
def log(message, level="INFO"):
    """Prints a formatted, timestamped log message to the console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level:<5}] {message}")


# ── SECTION 4: INTERFACE STATUS CHECKER ──────────────────────────
# This function SSHes into the device, runs a show command, and
# uses regex to parse the output. It returns a simple status string
# like "up", "down", or "administratively down" so our main
# program logic can decide what action to take.
# ─────────────────────────────────────────────────────────────────
def get_interface_status(connection, interface):
    """
    Checks the current status of a given interface.

    How it works:
      1. Sends 'show interfaces <name>' to the router.
      2. Uses a Regular Expression to find the status line
         in the returned text output.
      3. Returns the status as a clean lowercase string.

    Returns:
      'up'                  → Interface is fully operational.
      'administratively down' → Interface was manually shut down.
      'unknown'             → Could not parse the output (error state).
    """

    log(f"Sending 'show interfaces {interface}' to router...")

    # send_command() sends a single exec-mode command (no config changes)
    # and returns all the text the router prints back as one big string.
    raw_output = connection.send_command(f"show interfaces {interface}")

    # ── PARSING LOGIC ──
    # The first line of 'show interfaces' output always looks like this:
    #   Loopback100 is up, line protocol is up
    #   Loopback100 is administratively down, line protocol is down
    #
    # Our regex pattern captures the word(s) right after "is " on that line.
    # re.search() scans the entire output string for the first match.
    # re.IGNORECASE makes it match regardless of uppercase/lowercase.

    pattern = rf"{re.escape(interface)} is ([\w\s]+?),"
    match   = re.search(pattern, raw_output, re.IGNORECASE)

    if match:
        # .group(1) extracts just the captured part inside the parentheses.
        # .strip() removes any accidental leading/trailing whitespace.
        # .lower() converts to lowercase for easy, consistent comparisons.
        status = match.group(1).strip().lower()
        log(f"Parsed interface status: '{status}'")
        return status
    else:
        # If the regex found nothing, the interface might not exist yet
        # on this device, or the output format was unexpected.
        log(f"Could not parse status from output. Raw output was:\n{raw_output}", level="WARN")
        return "unknown"


# ── SECTION 5: INTERFACE HEALER ──────────────────────────────────
# This function performs the actual "self-healing" action.
# It sends configuration commands to the router to bring the
# interface back up, then verifies the fix worked.
# ─────────────────────────────────────────────────────────────────
def heal_interface(connection, interface):
    """
    Brings an administratively-down interface back up.

    How it works:
      1. Builds a list of IOS configuration commands.
      2. Uses send_config_set() which automatically:
         a. Types 'configure terminal' (enters config mode)
         b. Sends each command in the list one by one
         c. Types 'end' (exits back to privileged exec mode)
      3. Waits for the router to process the change.
      4. Re-checks the status to confirm success.
    """

    log(f"SELF-HEALING TRIGGERED → Initiating repair of {interface}...", level="ALERT")

    # This is the list of IOS commands we want to push to the router.
    # send_config_set() handles the 'configure terminal' and 'end' for us.
    healing_commands = [
        f"interface {interface}",   # Navigate into the interface's config sub-mode
        "no shutdown",              # THE FIX: removes the administrative shutdown
    ]

    # Send the config commands and capture the router's response text
    config_output = connection.send_config_set(healing_commands)
    log(f"Configuration pushed. Router response:\n{config_output}")

    # Pause for CONVERGENCE_DELAY seconds to let the router process the change.
    # If we check the status immediately, the router might still be processing
    # and we could get a false "still down" reading. This is called a race condition.
    log(f"Waiting {CONVERGENCE_DELAY} seconds for interface convergence...")
    time.sleep(CONVERGENCE_DELAY)

    # ── VERIFICATION STEP ──
    # A good automation script ALWAYS verifies its own work.
    # We re-check the status after healing to confirm success.
    log("Verifying repair — re-checking interface status...")
    new_status = get_interface_status(connection, interface)

    if new_status == "up":
        log(f"SUCCESS! ✅ {interface} is now [{new_status.upper()}]. Network is HEALED.", level="INFO")
    else:
        log(f"REPAIR FAILED ❌ {interface} is still reporting: '{new_status}'.", level="ERROR")
        log("Possible causes: device policy blocking change, wrong interface name, or privilege issue.", level="ERROR")


# ── SECTION 6: INTERFACE "BREAKER" (FOR DEMO SETUP) ──────────────
# This function is the demo setup tool. When we run the script
# and the interface is already up, we use this function to
# intentionally bring it down. On the NEXT script run, it will
# be down, so the self-healing logic will trigger.
#
# This creates a clean, repeatable demo loop:
#   Run 1 (interface UP)   → Script breaks it. "Run again to see healing."
#   Run 2 (interface DOWN) → Script heals it. Recruiter impressed. 🎯
#   Run 3 (interface UP)   → Script breaks it again. Loop repeats.
# ─────────────────────────────────────────────────────────────────
def break_interface(connection, interface):
    """
    Intentionally shuts down an interface for demo/testing purposes.
    """

    log(f"Interface is currently UP. Preparing demo state...", level="INFO")
    log(f"Sending 'shutdown' to {interface} to stage the self-healing demo.", level="INFO")

    # Build the shutdown commands
    shutdown_commands = [
        f"interface {interface}",
        "shutdown",                # This puts the interface into 'administratively down' state
    ]

    # Push the commands to the router
    config_output = connection.send_config_set(shutdown_commands)
    log(f"Shutdown commands sent. Router response:\n{config_output}")

    # Print clear instructions for the recruiter / tester watching the demo
    print()
    print("=" * 65)
    print("  🔴  DEMO STATE SET — Interface is now ADMINISTRATIVELY DOWN.")
    print()
    print("  ▶  Run this script ONE MORE TIME to watch it SELF-HEAL!")
    print("=" * 65)
    print()


# ── SECTION 7: MAIN PROGRAM ───────────────────────────────────────
# This is the "conductor" function that orchestrates everything.
# It follows a professional automation pattern called a
# Closed-Loop Control System:
#
#   OBSERVE  → Connect & check current state
#   ANALYZE  → Determine if action is needed
#   ACT      → Heal or stage the demo
#   VERIFY   → Confirm the action worked
#
# This is the same pattern used in Cisco's intent-based networking.
# ─────────────────────────────────────────────────────────────────
def main():
    # Print a clean banner when the script starts — professional touch
    print()
    print("=" * 65)
    print("   🔧  SELF-HEALING NETWORK PoC  |  Cisco DevNet Sandbox")
    print("=" * 65)
    log(f"Target Device    : {DEVICE['host']}:{DEVICE['port']}")
    log(f"Monitored Port   : {TARGET_INTERFACE}")
    log(f"Device OS Type   : {DEVICE['device_type']}")
    print()

    # ── STEP 1: ESTABLISH SSH CONNECTION ──────────────────────────
    # We wrap the entire script in a try/except/finally block.
    # This is Python's error-handling mechanism — it makes sure
    # that even if something crashes, we always disconnect cleanly
    # and print a useful error message instead of a cryptic traceback.

    connection = None  # Initialize to None so 'finally' block doesn't crash if connect fails

    try:
        log(f"Attempting SSH connection to {DEVICE['host']}...")

        # ConnectHandler takes our DEVICE dictionary and creates
        # a live SSH session. The ** operator "unpacks" the dictionary
        # into keyword arguments that ConnectHandler expects.
        connection = ConnectHandler(**DEVICE)

        log("SSH connection established! ✅")

        # Enter privileged exec mode ("enable" mode).
        # Without this, we can run show commands but NOT push configs.
        # .enable() uses the 'secret' key from our DEVICE dictionary.
        connection.enable()
        log("Entered privileged EXEC mode (enable mode). ✅")

        # ── STEP 2: CHECK CURRENT INTERFACE STATUS ─────────────────
        # OBSERVE phase: What is the current state of the network?
        print()
        log(f"--- OBSERVING: Checking {TARGET_INTERFACE} status ---")
        current_status = get_interface_status(connection, TARGET_INTERFACE)

        # ── STEP 3: DECISION ENGINE ────────────────────────────────
        # ANALYZE phase: Based on what we observed, what should we do?
        print()
        log(f"--- ANALYZING: Current status is '{current_status}' ---")

        if current_status == "administratively down":
            # ── SELF-HEALING PATH ──────────────────────────────────
            # The interface is down. This is the scenario we're
            # automating. Trigger the healer.
            log(f"ALERT ⚠️  {TARGET_INTERFACE} is ADMINISTRATIVELY DOWN!", level="ALERT")
            print()
            log(f"--- ACTING: Initiating Self-Healing Sequence ---")
            heal_interface(connection, TARGET_INTERFACE)

        elif current_status == "up":
            # ── DEMO SETUP PATH ────────────────────────────────────
            # The interface is healthy. For our demo loop, we break
            # it now so the next run can heal it.
            log(f"{TARGET_INTERFACE} is currently UP and healthy.")
            print()
            log(f"--- ACTING: Staging Demo — Shutting down interface ---")
            break_interface(connection, TARGET_INTERFACE)

        else:
            # ── UNKNOWN STATE PATH ─────────────────────────────────
            # Something unexpected happened (e.g., interface doesn't
            # exist yet, or there's a parsing error). Notify the user.
            log(f"UNKNOWN STATUS: '{current_status}'. No automated action taken.", level="WARN")
            log("Action required: Verify the interface name and device connectivity.", level="WARN")

    except Exception as error:
        # If ANY error occurs inside the try block (wrong password,
        # network timeout, bad hostname, etc.), we land here.
        # We print the specific error message to help with debugging.
        print()
        log(f"A FATAL ERROR OCCURRED: {error}", level="ERROR")
        log("Troubleshooting checklist:", level="ERROR")
        log("  1. Are your credentials correct in the DEVICE dictionary?", level="ERROR")
        log("  2. Can you ping devnetsandboxiosxec8k.cisco.com from your terminal?", level="ERROR")
        log("  3. Is the DevNet Sandbox currently available? Check developer.cisco.com/site/sandbox", level="ERROR")

    finally:
        # The 'finally' block ALWAYS runs, even if an error occurred.
        # This is where we guarantee a clean SSH disconnection.
        # Leaving ghost SSH sessions open wastes router resources.
        if connection:
            connection.disconnect()
            print()
            log("SSH session closed cleanly. ✅")

    print()
    print("=" * 65)
    log("Script execution complete.")
    print("=" * 65)
    print()


# ── ENTRY POINT ───────────────────────────────────────────────────
# This is standard Python convention.
# It means: "Only run main() if this file is executed directly
# (e.g., 'python self_healing_devnet.py'), NOT if it is imported
# as a module by another script."
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()