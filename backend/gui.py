"""
Obscura Desktop Application v1.0
Enhanced Modern GUI with Extension Toggle Control
"""

import tkinter as tk
from tkinter import messagebox
import threading
import os
import logging
import sys
import time
import requests

# Configure Logging
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'launcher_debug.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('Obscura')

log.info(f"Obscura starting on {sys.platform}")
log.info(f"Python version: {sys.version}")


class MacButton(tk.Frame):
    """Custom button that renders properly on macOS with colored backgrounds"""

    def __init__(self, parent, text="", bg="#58a6ff", fg="#0d1117",
                 active_bg="#79b8ff", font=None, command=None, **kwargs):
        super().__init__(parent, bg=bg, cursor="hand2")

        self.bg = bg
        self.fg = fg
        self.active_bg = active_bg
        self.command = command
        self._disabled = False

        # Create inner label
        self.label = tk.Label(
            self, text=text, bg=bg, fg=fg, font=font,
            padx=kwargs.get('padx', 12), pady=kwargs.get('pady', 10)
        )
        self.label.pack(fill=tk.BOTH, expand=True)

        # Bind events
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.label.bind("<Enter>", self._on_enter)
        self.label.bind("<Leave>", self._on_leave)
        self.label.bind("<Button-1>", self._on_click)

    def _on_enter(self, e):
        if not self._disabled:
            self.configure(bg=self.active_bg)
            self.label.configure(bg=self.active_bg)

    def _on_leave(self, e):
        if not self._disabled:
            self.configure(bg=self.bg)
            self.label.configure(bg=self.bg)

    def _on_click(self, e):
        if not self._disabled and self.command:
            self.command()

    def config(self, **kwargs):
        if 'text' in kwargs:
            self.label.configure(text=kwargs.pop('text'))
        if 'bg' in kwargs:
            self.bg = kwargs['bg']
            self.configure(bg=self.bg)
            self.label.configure(bg=self.bg)
            kwargs.pop('bg')
        if 'fg' in kwargs:
            self.fg = kwargs['fg']
            self.label.configure(fg=self.fg)
            kwargs.pop('fg')
        if 'activebackground' in kwargs:
            self.active_bg = kwargs.pop('activebackground')
        if 'state' in kwargs:
            state = kwargs.pop('state')
            self._disabled = (state == tk.DISABLED)
            if self._disabled:
                self.label.configure(fg="#666666")
            else:
                self.label.configure(fg=self.fg)
        if kwargs:
            super().configure(**kwargs)

    # Alias for config
    configure = config


class PIIShieldApp:
    """Modern Obscura Desktop Application"""

    def __init__(self, root):
        log.info("Initializing PIIShieldApp")
        self.root = root
        self.root.title("Obscura - Privacy Protection")

        # State
        self.is_server_running = False
        self.is_extension_enabled = True  # ON by default = PII detection enabled
        self.api_server = None

        # Configure window
        self.configure_window()

        # Build UI
        self.build_ui()

        log.info("App ready")
    
    def configure_window(self):
        """Configure window size and position"""
        width = 450
        height = 550
        
        # Center on screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.resizable(False, False)
        
        # Terminal Security Design System - Steel Blue
        self.bg_color = "#0d1117"      # GitHub dark base
        self.card_color = "#161b22"    # Surface
        self.bg_elevated = "#21262d"   # Elevated elements
        self.accent = "#58a6ff"        # Steel Blue (primary)
        self.accent_emphasis = "#79b8ff"  # Lighter blue for hover
        self.success = "#238636"       # Success green
        self.danger = "#da3633"        # Danger red
        self.text_color = "#e6edf3"    # Primary text
        self.text_muted = "#8b949e"    # Secondary text
        self.border_color = "#30363d"  # Borders
        # Legacy names for compatibility
        self.accent_green = self.success
        self.accent_red = self.danger
        self.accent_blue = self.accent
        
        self.root.configure(bg=self.bg_color)

    def _font_exists(self, font_name):
        """Check if a font is available on the system"""
        try:
            import tkinter.font as tkfont
            return font_name in tkfont.families()
        except:
            return False

    def _get_mono_font(self, size=11, bold=False):
        """Get the best available monospace font"""
        weight = "bold" if bold else "normal"
        for font in ["JetBrains Mono", "SF Mono", "Consolas", "Courier New"]:
            if self._font_exists(font):
                return (font, size, weight)
        return ("TkFixedFont", size, weight)

    def build_ui(self):
        """Build the modern UI"""
        # Main container
        main = tk.Frame(self.root, bg=self.bg_color)
        main.pack(fill=tk.BOTH, expand=True, padx=30, pady=25)
        
        # === Header with Logo ===
        header = tk.Frame(main, bg=self.bg_color)
        header.pack(fill=tk.X, pady=(0, 25))
        
        # Shield icon with Steel Blue accent
        icon_frame = tk.Frame(header, bg=self.accent, width=70, height=70)
        icon_frame.pack()
        icon_frame.pack_propagate(False)

        icon_label = tk.Label(icon_frame, text="🛡️", font=("Segoe UI Emoji", 32),
                             bg=self.accent, fg=self.bg_color)
        icon_label.place(relx=0.5, rely=0.5, anchor="center")
        
        # Title
        title = tk.Label(header, text="Obscura",
                        font=("Segoe UI", 28, "bold"),
                        bg=self.bg_color, fg=self.text_color)
        title.pack(pady=(15, 0))
        
        subtitle = tk.Label(header, text="Real-Time Privacy Protection",
                           font=("Segoe UI", 11),
                           bg=self.bg_color, fg=self.text_muted)
        subtitle.pack()
        
        # === Server Card ===
        server_card = tk.Frame(main, bg=self.card_color)
        server_card.pack(fill=tk.X, pady=8, ipady=15, ipadx=15)
        
        server_inner = tk.Frame(server_card, bg=self.card_color)
        server_inner.pack(fill=tk.X, padx=20, pady=10)
        
        # Server header row
        server_header = tk.Frame(server_inner, bg=self.card_color)
        server_header.pack(fill=tk.X)
        
        server_title = tk.Label(server_header, text="Backend Server",
                               font=("Segoe UI", 12, "bold"),
                               bg=self.card_color, fg=self.text_color)
        server_title.pack(side=tk.LEFT)
        
        # Status indicator
        self.server_status_frame = tk.Frame(server_header, bg=self.card_color)
        self.server_status_frame.pack(side=tk.RIGHT)
        
        self.server_dot = tk.Label(self.server_status_frame, text="●", 
                                   font=("Segoe UI", 10),
                                   bg=self.card_color, fg="#666666")
        self.server_dot.pack(side=tk.LEFT)
        
        self.server_status = tk.Label(self.server_status_frame, text="Stopped",
                                      font=("Segoe UI", 10),
                                      bg=self.card_color, fg=self.text_muted)
        self.server_status.pack(side=tk.LEFT, padx=(5, 0))
        
        # Server button - Steel Blue accent (MacButton for proper color rendering)
        self.server_btn = MacButton(
            server_inner, text="▶  START SERVER",
            font=self._get_mono_font(11, bold=True),
            bg=self.accent, fg=self.bg_color,
            active_bg=self.accent_emphasis,
            command=self.toggle_server
        )
        self.server_btn.pack(fill=tk.X, pady=(15, 0))
        
        # === Extension Toggle Card ===
        ext_card = tk.Frame(main, bg=self.card_color)
        ext_card.pack(fill=tk.X, pady=8, ipady=15, ipadx=15)
        
        ext_inner = tk.Frame(ext_card, bg=self.card_color)
        ext_inner.pack(fill=tk.X, padx=20, pady=10)
        
        ext_header = tk.Frame(ext_inner, bg=self.card_color)
        ext_header.pack(fill=tk.X)
        
        ext_title = tk.Label(ext_header, text="PII Detection",
                            font=("Segoe UI", 12, "bold"),
                            bg=self.card_color, fg=self.text_color)
        ext_title.pack(side=tk.LEFT)
        
        # Toggle button (styled as ON/OFF button) - Terminal style (MacButton)
        self.toggle_btn = MacButton(
            ext_header, text="  ON  ",
            font=self._get_mono_font(10, bold=True),
            bg=self.success, fg=self.text_color,
            active_bg="#2ea043",
            command=self.toggle_extension,
            padx=8, pady=4
        )
        self.toggle_btn.pack(side=tk.RIGHT)

        self.ext_status = tk.Label(ext_inner,
                                   text="PII detection is ACTIVE - Your data is protected",
                                   font=self._get_mono_font(10),
                                   bg=self.card_color, fg=self.success)
        self.ext_status.pack(anchor=tk.W, pady=(10, 0))
        
        # === Info Card ===
        info_card = tk.Frame(main, bg=self.card_color)
        info_card.pack(fill=tk.X, pady=8, ipady=15, ipadx=15)
        
        info_inner = tk.Frame(info_card, bg=self.card_color)
        info_inner.pack(fill=tk.X, padx=20, pady=10)
        
        info_title = tk.Label(info_inner, text="How It Works",
                             font=("Segoe UI", 12, "bold"),
                             bg=self.card_color, fg=self.text_color)
        info_title.pack(anchor=tk.W)
        
        info_text = tk.Label(info_inner, 
                            text="1. Keep this app running\n"
                                 "2. Browse the web with Chrome\n"
                                 "3. PII is automatically detected & highlighted\n"
                                 "4. Click to anonymize sensitive data",
                            font=("Segoe UI", 10),
                            bg=self.card_color, fg=self.text_muted,
                            justify=tk.LEFT)
        info_text.pack(anchor=tk.W, pady=(8, 0))
        
        # === Quick Actions ===
        actions_frame = tk.Frame(main, bg=self.bg_color)
        actions_frame.pack(fill=tk.X, pady=(15, 0))
        
        reset_btn = MacButton(
            actions_frame, text="Reset History",
            font=self._get_mono_font(10),
            bg=self.bg_elevated, fg=self.text_muted,
            active_bg=self.border_color,
            command=self.reset_history,
            padx=10, pady=5
        )
        reset_btn.pack(side=tk.LEFT)

        # === Footer ===
        footer = tk.Frame(main, bg=self.bg_color)
        footer.pack(side=tk.BOTTOM, fill=tk.X)

        version = tk.Label(footer, text="v1.0 | Port 5001 | Local Processing",
                          font=self._get_mono_font(9),
                          bg=self.bg_color, fg=self.text_muted)
        version.pack()
    
    def toggle_server(self):
        """Start or stop the backend server"""
        if self.is_server_running:
            self.stop_server()
        else:
            self.start_server()
    
    def start_server(self):
        """Start the API server"""
        log.info("Starting server...")
        
        self.server_dot.config(fg="#FFA500")
        self.server_status.config(text="Starting...")
        self.server_btn.config(state=tk.DISABLED, text="Starting...")
        
        def start():
            try:
                from api_server import app, initialize_model
                
                log.info("Initializing model...")
                initialize_model()
                
                log.info("Starting Flask...")
                self.api_server = threading.Thread(
                    target=lambda: app.run(host='127.0.0.1', port=5001, 
                                          debug=False, use_reloader=False),
                    daemon=True
                )
                self.api_server.start()
                
                self.root.after(0, self.on_server_started)
            except Exception as e:
                log.error(f"Start failed: {e}")
                self.root.after(0, lambda: self.on_server_error(str(e)))
        
        threading.Thread(target=start, daemon=True).start()
    
    def on_server_started(self):
        """Called when server starts successfully"""
        self.is_server_running = True
        self.server_dot.config(fg=self.success)
        self.server_status.config(text="Running", fg=self.success)
        self.server_btn.config(text="■  STOP SERVER", state=tk.NORMAL,
                              bg=self.danger, activebackground="#f85149", fg=self.text_color)
        log.info("Server started")

        # Sync extension toggle state with server
        self.sync_extension_state()

    def on_server_error(self, error):
        """Called when server fails to start"""
        self.server_dot.config(fg=self.danger)
        self.server_status.config(text="Error", fg=self.danger)
        self.server_btn.config(text="▶  START SERVER", state=tk.NORMAL)
        messagebox.showerror("Error", f"Failed to start server:\n{error}")

    def stop_server(self):
        """Stop the server"""
        self.is_server_running = False
        self.server_dot.config(fg=self.text_muted)
        self.server_status.config(text="Stopped", fg=self.text_muted)
        self.server_btn.config(text="▶  START SERVER",
                              bg=self.accent, activebackground=self.accent_emphasis, fg=self.bg_color)
        messagebox.showinfo("Info",
                           "Server will fully stop when you close the app.\n"
                           "Restart the app for a fresh server.")
    
    def toggle_extension(self):
        """Toggle PII detection on/off"""
        self.is_extension_enabled = not self.is_extension_enabled

        if self.is_extension_enabled:
            # ON = PII detection is ACTIVE
            self.toggle_btn.config(text="  ON  ", bg=self.success,
                                  activebackground="#2ea043", fg=self.text_color)
            self.ext_status.config(text="PII detection is ACTIVE - Your data is protected",
                                  fg=self.success)
        else:
            # OFF = PII detection is DISABLED
            self.toggle_btn.config(text="  OFF  ", bg=self.danger,
                                  activebackground="#f85149", fg=self.text_color)
            self.ext_status.config(text="PII detection is OFF - No protection",
                                  fg=self.danger)

        # Send to backend if server is running
        if self.is_server_running:
            self.update_extension_state(self.is_extension_enabled)
    
    def update_extension_state(self, enabled):
        """Update extension state on the backend (threaded)"""
        def do_update():
            try:
                response = requests.post(
                    "http://localhost:5001/api/extension-toggle",
                    json={"enabled": enabled},
                    timeout=2
                )
                if response.ok:
                    log.info(f"Extension state updated: {'enabled' if enabled else 'disabled'}")
                else:
                    log.error(f"Failed to update: {response.text}")
            except Exception as e:
                log.error(f"Error updating: {e}")
        
        threading.Thread(target=do_update, daemon=True).start()
    
    def sync_extension_state(self):
        """Sync toggle with backend state (threaded)"""
        def do_sync():
            try:
                time.sleep(0.5)
                response = requests.get(
                    "http://localhost:5001/api/extension-status",
                    timeout=2
                )
                if response.ok:
                    data = response.json()
                    enabled = data.get('enabled', True)
                    self.root.after(0, lambda: self._update_toggle_ui(enabled))
            except Exception as e:
                log.warning(f"Sync failed: {e}")
        
        threading.Thread(target=do_sync, daemon=True).start()
    
    def _update_toggle_ui(self, enabled):
        """Update toggle UI from main thread"""
        self.is_extension_enabled = enabled
        if enabled:
            self.toggle_btn.config(text="  ON  ", bg=self.success, fg=self.text_color)
            self.ext_status.config(text="PII detection is ACTIVE - Your data is protected",
                                  fg=self.success)
        else:
            self.toggle_btn.config(text="  OFF  ", bg=self.danger, fg=self.text_color)
            self.ext_status.config(text="PII detection is OFF - No protection",
                                  fg=self.danger)
    
    def reset_history(self):
        """Reset all session history"""
        result = messagebox.askyesno(
            "Reset History",
            "Delete all anonymization sessions?\n\nThis cannot be undone."
        )
        if result:
            try:
                db_file = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    'obscura.db'
                )
                if os.path.exists(db_file):
                    os.remove(db_file)
                    messagebox.showinfo("Success", "History cleared!")
                else:
                    messagebox.showinfo("Info", "No history to clear.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to reset:\n{e}")


class ModernPIIDetectorGUI:
    """Compatibility wrapper for main.py"""
    def __init__(self, root):
        log.info("ModernPIIDetectorGUI wrapper initialized")
        self.app = PIIShieldApp(root)
        log.info("Scheduling auto-start")
        root.after(500, self.app.start_server)


def main():
    log.info("Starting from gui.py main()")
    root = tk.Tk()
    PIIShieldApp(root)
    root.mainloop()
    log.info("App closed")


if __name__ == "__main__":
    main()
