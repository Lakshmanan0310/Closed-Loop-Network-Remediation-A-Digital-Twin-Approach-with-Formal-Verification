from netmiko import ConnectHandler

DEVICE = {
    "device_type" : "cisco_xe",
    "host"        : "devnetsandboxiosxec8k.cisco.com",
    "port"        : 22,
    "username"    : "lakshmanan.e1652",
    "password"    : "jR3H_Nl43Llv-D4u",
}

print("\n😈 CHAOS MONKEY INITIATED: Logging in to sabotage Loopback100...")

try:
    connection = ConnectHandler(**DEVICE)
    connection.enable()
    
    # Send the shutdown command to break the network
    connection.send_config_set(["interface Loopback100", "shutdown"])
    connection.disconnect()
    
    print("💥 SABOTAGE COMPLETE: Loopback100 is now DOWN.")
    print("👉 Watch your main script on the left to see it Auto-Heal!\n")
    
except Exception as e:
    print(f"❌ Error connecting: {e}")