# ==============================================================================
#  PROJECT  : Digital Twin — IEEE Research Project (Phase 3: The Grand Merge)
#  SCRIPT   : self_healing_devnet.py
#  PURPOSE  : Autonomous Closed-Loop Remediation with Pre-Deployment Verification
#             (Observe -> Analyze -> Simulate -> Act -> Verify)
# ==============================================================================

import time
import requests
from datetime import datetime
from netmiko import ConnectHandler

# --- IEEE DIGITAL TWIN MODULES ---
import pull_config
from twin_oracle import verify_remediation

# ==============================================================================
# 1. CONFIGURATION & CREDENTIALS
# ==============================================================================
DEVICE_PROFILE = {
    "device_type": "cisco_xe",
    "host": "devnetsandboxiosxec8k.cisco.com",
    "port": 22,
    "username": "lakshmanan.e1652",
    "password": "jR3H_Nl43Llv-D4u",
    "secret": "jR3H_Nl43Llv-D4u",
    "conn_timeout": 30,
}

# Webex API Configuration (Replace with your actual Webex Token and Room ID)
WEBEX_TOKEN = "OGYyYjM4NjctMTFkOC00MjExLTgyM2QtZWVjMWYyYmVmOThmZDc5NTk2ZTAtMzlh_P0A1_381a95f5-7349-4f5b-bc0d-1e1f574b419a"
# Replace with the email address you use to log into Webex
WEBEX_ROOM_ID = "lakshmanan.e1652@gmail.com"

TARGET_INTERFACE = "Loopback100"

# ==============================================================================
# 2. HELPER FUNCTIONS
# ==============================================================================
def log(message, level="INFO"):
    """Standardized timestamped logging."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level:<7}] {message}")

def send_webex_alert(message):
    """Sends an alert to the engineering team via Cisco Webex."""
    url = "https://webexapis.com/v1/messages"
    headers = {
        "Authorization": f"Bearer {WEBEX_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "toPersonEmail": WEBEX_ROOM_ID,  # Changed from roomId
        "text": message
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            log("Webex alert dispatched successfully.", level="SUCCESS")
        else:
            log(f"Failed to send Webex alert: {response.status_code}", level="WARN")
    except Exception as e:
        log(f"Webex API error: {e}", level="ERROR")

def get_interface_status(connection, interface_name):
    """
    Robust interface status parser.
    Uses 'show interfaces' instead of 'show ip interface brief | include'
    to avoid IOS-XE terminal-width truncation and pipe reliability issues.
    """
    # --- DEBUG BLOCK: See EXACTLY what the router returns ---
    command = f"show interfaces {interface_name}"
    print("\n" + "="*60)
    print(f"[DEBUG] Sending command: '{command}'")
    raw_output = connection.send_command(command)
    print(f"[DEBUG] Raw output length: {len(raw_output)} chars")
    print(f"[DEBUG] First 300 chars of raw output:")
    print("---RAW START---")
    print(raw_output[:300])
    print("---RAW END---\n")

    # Also fire the brief command so you can compare both outputs
    brief_output = connection.send_command(
        f"show ip interface brief | include {interface_name}"
    )
    print(f"[DEBUG] 'show ip interface brief' filtered output:")
    print(f"        repr() = {repr(brief_output)}")  # repr() exposes hidden \r\n chars
    print("="*60 + "\n")
    # --- END DEBUG BLOCK ---

    # Parse from 'show interfaces' — far more reliable than 'brief'
    # IOS-XE first line is always: "Loopback100 is <status>, line protocol is <proto>"
    first_line = raw_output.split("\n")[0].lower()
    print(f"[DEBUG] Parsing first line: {repr(first_line)}")

    if "administratively down" in first_line:
        return "administratively down"
    elif "line protocol is up" in first_line or (
        first_line.count(" is up") > 0
    ):
        return "up"
    elif " is down" in first_line:
        return "down"

    # Last resort: scan the entire output
    output_lower = raw_output.lower()
    if "administratively down" in output_lower:
        return "administratively down"
    elif " is up" in output_lower:
        return "up"

    print(f"[DEBUG] ⚠️  FELL THROUGH TO UNKNOWN — add the line above to your bug report!")
    return "unknown"

# ==============================================================================
# 3. THE IEEE DIGITAL TWIN ORACLE (SIMULATION PHASE)
# ==============================================================================
def simulate_proposed_fix():
    print("\n" + "="*70)
    log("--- DIGITAL TWIN INITIATED: Simulating Proposed Fix ---", level="STEP")

    # 1. Pull the current broken config from the live router
    log("Pulling current broken state from live router...", level="INFO")
    pull_config.main()

    config_path = "snapshot/configs/router1.cfg"

    # 2. READ the full config into memory
    with open(config_path, "r") as f:
        lines = f.readlines()

    log(f"Config loaded: {len(lines)} lines", level="INFO")

    # 3. SURGICALLY patch the shutdown line inside the correct block
    #    Strategy: track when we're inside the Loopback100 block,
    #    and flip 'shutdown' → 'no shutdown' only there.
    patched_lines = []
    inside_target_block = False
    patch_applied = False

    for line in lines:
        stripped = line.strip().lower()

        # Detect entry into the target interface block
        if stripped == f"interface {TARGET_INTERFACE.lower()}":
            inside_target_block = True
            patched_lines.append(line)
            continue

        # Detect exit from any interface block (next 'interface' keyword = new block)
        if inside_target_block and stripped.startswith("interface "):
            inside_target_block = False

        # Patch: replace 'shutdown' with 'no shutdown' inside the block only
        if inside_target_block and stripped == "shutdown":
            patched_line = line.replace("shutdown", "no shutdown")
            patched_lines.append(patched_line)
            patch_applied = True
            log(f"  ✅ Patched line: '{line.strip()}' → '{patched_line.strip()}'", level="INFO")
            continue

        patched_lines.append(line)

    # 4. Write the patched config back
    with open(config_path, "w") as f:
        f.writelines(patched_lines)

    if patch_applied:
        log("Proposed fix successfully injected into local twin ✅", level="INFO")
    else:
        log("WARNING: 'shutdown' line was NOT found in the Loopback100 block!", level="WARN")
        log("Check that TARGET_INTERFACE name matches exactly what's in the config.", level="WARN")

    # 5. Pass to the Oracle
    log("Passing proposed state to Batfish Oracle for formal verification...", level="INFO")
    is_safe = verify_remediation()
    print("="*70 + "\n")

    return is_safe
# ==============================================================================
# 4. MAIN ORCHESTRATOR
# ==============================================================================
def main():
    log("Starting Autonomous Healing Orchestrator (Digital Twin Edition)...", level="INFO")
    
    try:
        log(f"Connecting to {DEVICE_PROFILE['host']}...", level="STEP")
        connection = ConnectHandler(**DEVICE_PROFILE)
        connection.enable()
        log("SSH Session Established.", level="SUCCESS")
        
        # --- OBSERVE PHASE ---
        current_status = get_interface_status(connection, TARGET_INTERFACE)
        log(f"{TARGET_INTERFACE} current status: {current_status.upper()}", level="INFO")
        
        # --- ANALYZE & SIMULATE PHASE ---
        if current_status == "up":
            log(f"Network is healthy. No remediation required.", level="SUCCESS")
            
        elif current_status == "administratively down":
            log(f"ALERT: {TARGET_INTERFACE} is down! Triggering auto-remediation.", level="WARN")
            send_webex_alert(f"⚠️ **OUTAGE DETECTED:** {TARGET_INTERFACE} is down. Digital Twin simulation starting...")
            
            # 🚀 Call the Digital Twin Simulator
            is_safe = simulate_proposed_fix()
            
            # --- ACT PHASE ---
            if is_safe:
                log("Oracle returned TRUE. Fix is VERIFIED SAFE. Executing on live router! ✅", level="SUCCESS")
                
                # Push the actual fix to the live router
                commands = [f"interface {TARGET_INTERFACE}", "no shutdown"]
                connection.send_config_set(commands)
                
                # Verify physical heal
                time.sleep(2)
                new_status = get_interface_status(connection, TARGET_INTERFACE)
                
                if new_status == "up":
                    log(f"Physical Router Healed. {TARGET_INTERFACE} is now UP.", level="SUCCESS")
                    send_webex_alert(f"✅ **AUTO-HEAL SUCCESS:** Digital Twin verified the fix. {TARGET_INTERFACE} has been safely restored.")
                else:
                    log("Fix applied, but interface did not come up.", level="ERROR")
            
            else:
                log("Oracle returned FALSE. Fix violates safety policy. ABORTING HEAL! ❌", level="ERROR")
                send_webex_alert(f"🚨 **AUTO-HEAL ABORTED:** Digital Twin simulation predicted failure. Blast radius protected. Human intervention required.")

    except Exception as e:
        log(f"Fatal execution error: {e}", level="ERROR")
    finally:
        if 'connection' in locals() and connection:
            connection.disconnect()
            log("SSH Session Closed.", level="INFO")

if __name__ == "__main__":
    main()