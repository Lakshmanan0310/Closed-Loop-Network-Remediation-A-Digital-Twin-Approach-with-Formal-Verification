from netmiko import ConnectHandler

DEVICE_PROFILE = {
    "device_type": "cisco_xe",
    "host": "devnetsandboxiosxec8k.cisco.com",
    "port": 22,
    "username": "lakshmanan.e1652",
    "password": "jR3H_Nl43Llv-D4u",
    "secret": "jR3H_Nl43Llv-D4u",
    "conn_timeout": 30,
}

print("Connecting to router to rebuild lab...")
connection = ConnectHandler(**DEVICE_PROFILE)
connection.enable()

# Create the interface and intentionally shut it down
commands = [
    "interface Loopback100",
    "description DESC-Loopback100",
    "ip address 10.100.100.1 255.255.255.255",
    "shutdown"
]

print("Injecting broken Loopback100...")
connection.send_config_set(commands)
connection.disconnect()
print("Lab rebuilt! Loopback100 is now administratively down.")