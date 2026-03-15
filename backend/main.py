"""
Obscura - Unified Main Entry Point
Runs BOTH Tkinter GUI AND Flask API Server in parallel threads

macOS Tahoe / Apple Silicon compatible
"""

import sys
import os
import threading
import logging
import time
import signal
import urllib.request
import urllib.error

# Configure Logging
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'launcher_debug.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('Main')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Global flag to track if API should keep running
api_running = True

def check_api_health(max_attempts=20, interval=0.5):
    """Poll API health endpoint until ready or timeout"""
    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(
                'http://127.0.0.1:5001/api/health',
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    log.info(f"[MAIN] + API ready after {attempt + 1} attempts")
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pass
        time.sleep(interval)
    log.warning(f"[MAIN] API not ready after {max_attempts} attempts")
    return False


def run_api_server():
    """Run Flask API server in background thread"""
    try:
        log.info("[API] Starting Flask API server...")
        from api_server import initialize_model, app
        
        # Initialize model
        log.info("[API] Initializing model...")
        initialize_model()
        
        # Run Flask app
        log.info("[API] + Flask API starting on http://localhost:5001")
        log.info("[API] ============================================")
        app.run(host='127.0.0.1', port=5001, debug=False, threaded=True, use_reloader=False)
        
    except ImportError as e:
        log.info(f"[API] x Import Error: {e}", exc_info=True)
    except Exception as e:
        log.error(f"[API] x Error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()


def run_gui():
    """Run Tkinter GUI in main thread"""
    try:
        import tkinter as tk
        
        log.info("[GUI] Starting Tkinter GUI...")
        
        # Try to import GUI
        try:
            log.info("[GUI] Attempting to import ModernPIIDetectorGUI from gui_tkinter...")
            from gui_tkinter import ModernPIIDetectorGUI
            log.info("[GUI] + Imported from gui_tkinter")
        except ImportError:
            log.info("[GUI] gui_tkinter not found, trying gui...")
            from gui import ModernPIIDetectorGUI
            log.info("[GUI] + Imported from gui")
        
        # Create and run GUI
        root = tk.Tk()
        log.info("[GUI] + Tkinter root window created")
        
        app_gui = ModernPIIDetectorGUI(root)
        log.info("[GUI] + GUI instance created")
        
        log.info("[GUI] + Entering main loop...")
        root.mainloop()
        
        log.info("[GUI] Window closed by user")
        return True
        
    except ImportError as e:
        log.error(f"[GUI] x Import Error: {e}", exc_info=True)
        print("\n- GUI Import Error")
        print("Make sure you have:")
        print("  • gui_tkinter.py (or gui.py)")
        print("  • model_handler.py")
        return False
    except Exception as e:
        log.error(f"[GUI] x Error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return False


def main():
    try:
        log.info("=" * 70)
        log.info("OBSCURA - UNIFIED LAUNCHER")
        log.info("=" * 70)
        
        # Step 1: Start API Server in background thread (non-blocking)
        log.info("\n[MAIN] Step 1: Starting API Server in background...")
        api_thread = threading.Thread(target=run_api_server, daemon=True)
        api_thread.start()
        log.info("[MAIN] + API server thread started (daemon)")
        
        # Step 2: Wait for API to be ready (with health check polling)
        log.info("[MAIN] Waiting for API to initialize...")
        api_ready = check_api_health(max_attempts=20, interval=0.5)
        if not api_ready:
            log.warning("[MAIN] API may not be fully ready, proceeding anyway...")
        
        # Step 3: Start GUI in main thread (blocking)
        log.info("\n[MAIN] Step 2: Starting Tkinter GUI...")
        gui_success = run_gui()
        
        # Step 4: Shutdown
        log.info("\n[MAIN] GUI closed, shutting down...")
        global api_running
        api_running = False

        if gui_success:
            log.info("[MAIN] + Obscura closed normally")
            print("\n+ Obscura closed successfully")
        else:
            log.error("[MAIN] x Obscura encountered an error")
            print("\n- Obscura encountered an error")
        
        sys.exit(0)
        
    except Exception as e:
        log.error(f"[MAIN] x Fatal Error: {e}", exc_info=True)
        print(f"\n- Fatal Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()