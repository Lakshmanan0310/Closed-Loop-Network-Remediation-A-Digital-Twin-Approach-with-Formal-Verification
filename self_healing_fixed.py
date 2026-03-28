# ================================================================
#  PROJECT : Self-Healing Network — Proof of Concept (DEBUGGED)
#  DEVICE  : Cisco IOS-XE (Cisco DevNet Always-On Sandbox)
#  LIBRARY : Netmiko (SSH automation for network devices)
#  STATUS  : Ping failure debugged - IPv4 forced, connectivity check added
# ================================================================

import netmiko
import re
import time
import datetime
import socket  # Added for SSH port check instead of ping

DEVICE = {
    "device_type": "cisco_ios",
    "host": "131.226.217.182",  # Explicit IPv4 to bypass DNS/IPv6 issues
    "username": "lakshmanan.e1652",
    "password": "jR3H_Nl43Llv-D4u",
    "secret": "jR3H_Nl43Llv-D4u",
    "conn_timeout": 30,
    "banner_timeout": 90,
    "auth_timeout": 30,
    "global_delay_factor": 2
}

TARGET_INTERFACE = "Loopback100"  # Safe virtual interface for sandbox
CONVERGENCE_DELAY = 3

def log(message, level="INFO"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level:<5}] {message}")

def check_connectivity():
    """Pre-flight: Verify SSH port is open before attempting connection."""
    log(f"Checking SSH connectivity to {DEVICE['host']} on port 22...")
    try:
        with socket.create_connection((DEVICE["host"], 22), timeout=10) as s:
            log("SSH Port 22 is open ✅")
            return True
    except Exception as e:
        log(f"Connectivity FAILED: {str(e)}", "ERROR")
        log("Make sure you are connected to the Cisco AnyConnect VPN if this is a reserved sandbox (or that the sandbox is active).", "ERROR")
        
    log("Fix: Check sandbox status at devnetsandbox.cisco.com", "ERROR")
    return False

# [Rest of functions unchanged: get_interface_status, heal_interface, break_interface, main]

def get_interface_status(connection, interface):
    log(f"Sending 'show interfaces {interface}' to router...")
    raw_output = connection.send_command(f"show interfaces {interface}")
    pattern = rf"{re.escape(interface)} is ([\w\s]+?),"
    match = re.search(pattern, raw_output, re.IGNORECASE)
    if match:
        status = match.group(1).strip().lower()
        log(f"Parsed interface status: '{status}'")
        return status
    log(f"Could not parse status. Raw: {raw_output[:200]}...", "WARN")
    return "unknown"

def heal_interface(connection, interface):
    log(f"SELF-HEALING → Repairing {interface}...", "ALERT")
    healing_commands = [f"interface {interface}", "no shutdown"]
    config_output = connection.send_config_set(healing_commands)
    log(f"Config response: {config_output}")
    time.sleep(CONVERGENCE_DELAY)
    new_status = get_interface_status(connection, interface)
    if new_status == "up":
        log(f"SUCCESS! {interface} is UP ✅", "INFO")
    else:
        log(f"FAILED: still '{new_status}' ❌", "ERROR")

def break_interface(connection, interface):
    log(f"Staging demo: shutting {interface}...")
    shutdown_commands = [f"interface {interface}", "shutdown"]
    config_output = connection.send_config_set(shutdown_commands)
    log(f"Shutdown response: {config_output}")
    print("\n" + "="*65)
    print("  Run AGAIN to see SELF-HEALING!")
    print("="*65 + "\n")

def main():
    print("\n" + "="*65)
    print("   🔧 SELF-HEALING PoC (Ping Debugged)")
    print("="*65)
    
    if not check_connectivity():
        return
    
    connection = None
    try:
        log(f"SSH to {DEVICE['host']}...")
        connection = netmiko.ConnectHandler(**DEVICE)
        log("Connected! ✅")
        connection.enable()
        log("Enable mode ✅")
        
        print("\nInterfaces:")
        print(connection.send_command("show ip interface brief"))
        
        status = get_interface_status(connection, TARGET_INTERFACE)
        log(f"Status: '{status}'")
        
        if status == "administratively down":
            heal_interface(connection, TARGET_INTERFACE)
        elif status == "up":
            break_interface(connection, TARGET_INTERFACE)
        else:
            log(f"Unhandled: '{status}'", "WARN")
            
    except Exception as e:
        log(f"ERROR: {e}", "ERROR")
    finally:
        if connection:
            connection.disconnect()
            log("Disconnected ✅")
    
    print("="*65 + "\n")

if __name__ == "__main__":
    main()

