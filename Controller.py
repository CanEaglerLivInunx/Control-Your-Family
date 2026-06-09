# MUST BE LINE 1: Loads Tkinter DLLs before OpenCV/Numpy can conflict
import customtkinter as ctk
import socket
import threading
import struct
import time
import cv2
import numpy as np
from PIL import Image
from screeninfo import get_monitors

# --- CS:GO Style Palette ---
ACCENT = "#00FF7F"  # Neon Spring Green
BG_DARK = "#0B0C10"
BG_SLATE = "#1F2833"
TEXT_CYAN = "#66FCF1"


class ClientScreenCard(ctk.CTkFrame):
    def __init__(self, master, client_socket, address):
        super().__init__(master, fg_color=BG_SLATE, border_color=ACCENT, border_width=1, corner_radius=5)
        self.client_socket = client_socket
        self.address = address

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=5, pady=2)

        self.status_led = ctk.CTkLabel(header, text="●", text_color=ACCENT, font=("Consolas", 14))
        self.status_led.pack(side="left", padx=5)

        self.label_name = ctk.CTkLabel(header, text=f"TARGET_NODE: {address[0]}", font=("Consolas", 11, "bold"),
                                       text_color=TEXT_CYAN)
        self.label_name.pack(side="left")

        self.screen_display = ctk.CTkLabel(self, text="SYNCING...", font=("Consolas", 10))
        self.screen_display.pack(expand=True, fill="both", padx=5, pady=5)
        self.screen_display.bind("<Button-1>", self.on_click)

        # Start the background receiver
        threading.Thread(target=self.receive_data, daemon=True).start()

    def receive_data(self):
        """Runs in background: receives and decodes data."""
        data = b""
        payload_size = struct.calcsize(">L")
        try:
            while True:
                while len(data) < payload_size:
                    chunk = self.client_socket.recv(8192)
                    if not chunk: raise Exception("Connection dropped")
                    data += chunk

                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                msg_size = struct.unpack(">L", packed_msg_size)[0]

                while len(data) < msg_size:
                    chunk = self.client_socket.recv(8192)
                    if not chunk: raise Exception("Connection dropped")
                    data += chunk

                frame_data = data[:msg_size]
                data = data[msg_size:]

                # Decode the frame
                nparr = np.frombuffer(frame_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)

                # SAFELY hand the image back to the main thread to update the UI
                self.after(0, self.update_ui_image, img)

        except Exception as e:
            self.after(0, self.set_disconnected)

    def update_ui_image(self, img):
        """Runs on main thread: updates the actual label."""
        self.ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(320, 180))
        self.screen_display.configure(image=self.ctk_img, text="")

    def set_disconnected(self):
        """Runs on main thread: updates status."""
        self.status_led.configure(text_color="#FF4B4B")
        self.label_name.configure(text="CONNECTION_TERMINATED")

    def on_click(self, event):
        try:
            self.client_socket.sendall(f"CLICK:{event.x / 320}:{event.y / 180}".encode())
        except:
            pass


class RemoteControlTray(ctk.CTk):
    def __init__(self):
        super().__init__()
        monitor = get_monitors()[0]
        self.scr_w, self.scr_h = monitor.width, monitor.height
        self.active_nodes = {}

        # Overlay settings
        self.attributes("-topmost", True)
        self.overrideredirect(True)
        self.configure(fg_color=BG_DARK)

        # Transparent background for Windows
        self.wm_attributes("-transparentcolor", BG_DARK)

        self.width, self.height = 400, 600
        self.x_pos = self.scr_w - self.width - 20
        self.start_y = self.scr_h - 70  # Only show the toggle arrow
        self.target_y = self.scr_h - self.height - 40
        self.curr_y = self.start_y

        self.geometry(f"{self.width}x{self.height}+{self.x_pos}+{self.curr_y}")

        # Main UI
        self.container = ctk.CTkFrame(self, corner_radius=15, border_width=2, border_color=ACCENT, fg_color=BG_DARK)
        self.container.pack(fill="both", expand=True, padx=5, pady=5)

        self.toggle_btn = ctk.CTkButton(self.container, text="▲", width=50, height=35, corner_radius=25,
                                        border_width=1, border_color=ACCENT, fg_color="transparent",
                                        text_color=ACCENT, font=("Consolas", 18, "bold"),
                                        command=self.toggle_tray)
        self.toggle_btn.pack(pady=10)

        ctk.CTkLabel(self.container, text="S-I-W // AUTOMATIC_CONTROLLER", font=("Consolas", 12, "bold"),
                     text_color=TEXT_CYAN).pack()

        self.scroll_frame = ctk.CTkScrollableFrame(self.container, fg_color="transparent",
                                                   label_text="REMOTE_UNITS",
                                                   label_text_color=ACCENT, label_font=("Consolas", 10))
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Start background threads
        threading.Thread(target=self.discovery_beacon, daemon=True).start()
        threading.Thread(target=self.start_server, daemon=True).start()

        self.expanded = False

    def discovery_beacon(self):
        """Broadcasts a signal so the Client can find the Controller automatically."""
        beacon = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        beacon.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while True:
            try:
                beacon.sendto(b"SIW_DISCOVERY", ('<broadcast>', 49153))
            except:
                pass
            time.sleep(2)

    def start_server(self):
        """Listens for incoming clients."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', 49152))
        server.listen(5)
        while True:
            conn, addr = server.accept()
            ip = addr[0]
            # Must safely update UI from the background thread using .after
            self.after(0, lambda c=conn, a=addr, i=ip: self.add_node(c, a, i))

    def add_node(self, conn, addr, ip):
        """Runs on main thread: adds a new client card."""
        if ip in self.active_nodes:
            try:
                self.active_nodes[ip].destroy()
            except:
                pass

        card = ClientScreenCard(self.scroll_frame, conn, addr)
        card.pack(pady=10, fill="x")
        self.active_nodes[ip] = card

    def toggle_tray(self):
        """Triggers the slide animation."""
        if not self.expanded:
            target = self.target_y
            self.toggle_btn.configure(text="▼")
        else:
            target = self.start_y
            self.toggle_btn.configure(text="▲")

        self.animate_to(target)
        self.expanded = not self.expanded

    def animate_to(self, target):
        """Smooth sliding physics."""
        if abs(self.curr_y - target) > 1:
            step = (target - self.curr_y) / 5
            self.curr_y += int(step) if abs(step) > 1 else (1 if step > 0 else -1)
            self.geometry(f"{self.width}x{self.height}+{self.x_pos}+{self.curr_y}")
            self.after(10, lambda: self.animate_to(target))
        else:
            self.curr_y = target
            self.geometry(f"{self.width}x{self.height}+{self.x_pos}+{self.curr_y}")


if __name__ == "__main__":
    app = RemoteControlTray()
    app.mainloop()