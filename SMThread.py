# SMThread.py

from PyQt5.QtCore import QThread, pyqtSignal
from qgis.core import QgsMessageLog, Qgis

import time
import numpy as np
import sys
import os
import platform
import glob
from typing import Optional, Tuple, Dict, List, Union

from .SMDriverHID import open as spacemouse_open
from .SMDriverHID import close as spacemouse_close
from .SMDriverHID import read as spacemouse_read
from .SMDriverHID import list_devices as spacemouse_list_devices
from .SMConfig import Config
from .SMKalmanFilters import KalmanFilter

class SpaceMouseThread(QThread):
    """
    Thread for handling SpaceMouse device input in QGIS.
    Provides efficient, non-blocking access to 3D mouse data.
    Compatible with Windows, macOS, and Linux.
    """
    data_received = pyqtSignal(str, float, float, float, float, float, float)
    error_occurred = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)
    button_pressed = pyqtSignal(str, int)  # device_id, button_index
   
    def __init__(self, device_id: str):
        """
        Initialize the SpaceMouse thread.
        
        Args:
            device_id: Unique identifier for the device
        """
        super().__init__()
        self.device_id = device_id
        
        # Platform detection
        self._platform = self._detect_platform()
        
        # Thread control
        self._running: bool = False
        self._connected: bool = False
        
        # Performance optimization
        self._last_update: float = 0.0
        self._update_interval: float = Config.UPDATE_INTERVAL
        
        # Pre-allocated numpy arrays for better performance
        self._state_buffer: np.ndarray = np.zeros(Config.BUFFER_SIZE, dtype=np.float32)
        
        # State tracking
        self._previous_state: Optional[Dict[str, float]] = None
        self._state_changed: bool = False
        self._error_count: int = 0
        self._max_errors: int = Config.MAX_ERRORS
        
        # Validation timing
        self._last_validation_time: float = 0.0
        self._validation_interval: float = 10.0  # seconds
        
        # Platform-specific settings
        self._device_paths = self._get_platform_device_paths()
        
        self._log_message(f"SpaceMouse thread initialized on {self._platform}")

    def _detect_platform(self) -> str:
        """
        Detect the current operating system platform.
        
        Returns:
            String identifying the platform: 'windows', 'macos', or 'linux'
        """
        if sys.platform.startswith('win'):
            return 'windows'
        elif sys.platform.startswith('darwin'):
            return 'macos'
        elif sys.platform.startswith('linux'):
            return 'linux'
        else:
            return 'unknown'
            
    def _get_platform_device_paths(self) -> List[str]:
        """
        Get platform-specific device paths to check for SpaceMouse devices.
        
        Returns:
            List of device paths to check
        """
        if self._platform == 'linux':
            return [
                '/dev/input/spacenavigator',
                '/dev/input/spacemouse',
                '/dev/input/3dconnexion',
                '/dev/hidraw*'  # Will be expanded later
            ]
        elif self._platform == 'macos':
            return [
                '/dev/cu.usbmodem*'  # Will be expanded later
            ]
        else:  # Windows or unknown
            return []
            
    def _log_message(self, message: str, level: int = Qgis.Info) -> None:
        """Thread-safe logging with level control"""
        if level >= Config.LOG_LEVEL:
            QgsMessageLog.logMessage(message, Config.PLUGIN_NAME, level=level)

    def update_settings(self, update_interval: float = None) -> None:
        """Update thread settings safely"""
        try:       
            if update_interval is not None:
                self._update_interval = update_interval
                
        except Exception as e:
            self.error_occurred.emit(f"Failed to update settings: {str(e)}")
            self._log_message(f"Settings update error: {str(e)}", Qgis.Critical)

    def _validate_connection(self) -> bool:
        """Validate device connection is working"""
        try:
            if not self._connected:
                return False
                
            # Try a test read with timeout
            start_time = time.time()
            while time.time() - start_time < 0.5:  # 500ms timeout
                test_state = spacemouse_read()
                if test_state is not None:
                    return True
                time.sleep(0.05)
                
            return False
            
        except Exception as e:
            self._log_message(f"Connection validation failed: {str(e)}", Qgis.Warning)
            return False
        
    def _check_device_availability(self) -> bool:
        """Check if SpaceMouse device is available on the current platform"""
        # Try different methods based on platform
        methods = [
            self._check_device_with_easyhid,
            self._check_device_with_platform_specific
        ]
        
        for method in methods:
            try:
                if method():
                    return True
            except Exception as e:
                self._log_message(f"Device check method {method.__name__} failed: {str(e)}", Qgis.Info)
                continue
                
        self._log_message("No SpaceMouse devices found with any method", Qgis.Warning)
        return False
        
    def _check_device_with_easyhid(self) -> bool:
        """Check for devices using easyhid library (works on Windows and some Linux)"""
        try:
            from easyhid import Enumeration
            
            enum = Enumeration()
            devices = enum.find(vid=0x046d)  # 3DConnexion vendor ID
            
            if devices:
                device_info = []
                for dev in devices:
                    info = {
                        'vendor_id': f'0x{dev.vendor_id:04x}',
                        'product_id': f'0x{dev.product_id:04x}',
                        'path': dev.path
                    }
                    device_info.append(info)
                
                self._log_message(f"Found devices with easyhid: {device_info}", Qgis.Info)
                return True
            else:
                self._log_message("No SpaceMouse devices found with easyhid", Qgis.Info)
                return False
                
        except ImportError:
            self._log_message("easyhid not available, skipping this method", Qgis.Info)
            return False
        except Exception as e:
            self._log_message(f"Error using easyhid: {str(e)}", Qgis.Info)
            return False
            
    def _check_device_with_platform_specific(self) -> bool:
        """Check for devices using platform-specific methods"""
        if self._platform == 'linux':
            return self._check_device_linux()
        elif self._platform == 'macos':
            return self._check_device_macos()
        elif self._platform == 'windows':
            return self._check_device_windows()
        else:
            self._log_message(f"No specific device check for platform: {self._platform}", Qgis.Info)
            return False
            
    def _check_device_linux(self) -> bool:
        """Check for SpaceMouse devices on Linux"""
        try:
            # Check if spacemouse can list devices directly
            devices = spacemouse_list_devices()
            if devices:
                self._log_message(f"Found devices with spacemouse_list_devices(): {devices}", Qgis.Info)
                return True
                
            # Check common device paths
            for path_pattern in self._device_paths:
                if '*' in path_pattern:
                    # Expand wildcards
                    matching_paths = glob.glob(path_pattern)
                    for path in matching_paths:
                        if os.path.exists(path):
                            self._log_message(f"Found device at path: {path}", Qgis.Info)
                            return True
                elif os.path.exists(path_pattern):
                    self._log_message(f"Found device at path: {path_pattern}", Qgis.Info)
                    return True
                    
            # Try using lsusb command
            try:
                import subprocess
                result = subprocess.run(['lsusb', '-d', '046d:'], capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    self._log_message(f"Found 3Dconnexion device with lsusb: {result.stdout.strip()}", Qgis.Info)
                    return True
            except Exception as e:
                self._log_message(f"lsusb check failed: {str(e)}", Qgis.Info)
                
            return False
            
        except Exception as e:
            self._log_message(f"Error checking Linux devices: {str(e)}", Qgis.Info)
            return False
            
    def _check_device_macos(self) -> bool:
        """Check for SpaceMouse devices on macOS"""
        try:
            # Check if spacemouse can list devices directly
            devices = spacemouse_list_devices()
            if devices:
                self._log_message(f"Found devices with spacemouse_list_devices(): {devices}", Qgis.Info)
                return True
                
            # Check device paths
            for path_pattern in self._device_paths:
                if '*' in path_pattern:
                    # Expand wildcards
                    matching_paths = glob.glob(path_pattern)
                    for path in matching_paths:
                        if os.path.exists(path):
                            self._log_message(f"Found device at path: {path}", Qgis.Info)
                            return True
                elif os.path.exists(path_pattern):
                    self._log_message(f"Found device at path: {path_pattern}", Qgis.Info)
                    return True
                    
            # Try using system_profiler
            try:
                import subprocess
                result = subprocess.run(
                    ['system_profiler', 'SPUSBDataType', '|', 'grep', '-A', '10', '3Dconnexion'], 
                    shell=True, 
                    capture_output=True, 
                    text=True
                )
                if result.returncode == 0 and result.stdout.strip():
                    self._log_message(f"Found 3Dconnexion device with system_profiler", Qgis.Info)
                    return True
            except Exception as e:
                self._log_message(f"system_profiler check failed: {str(e)}", Qgis.Info)
                
            return False
            
        except Exception as e:
            self._log_message(f"Error checking macOS devices: {str(e)}", Qgis.Info)
            return False
            
    def _check_device_windows(self) -> bool:
        """Check for SpaceMouse devices on Windows using Windows-specific methods"""
        # First try with spacemouse's built-in function
        try:
            devices = spacemouse_list_devices()
            if devices:
                self._log_message(f"Found devices with spacemouse_list_devices(): {devices}", Qgis.Info)
                return True
        except Exception as e:
            self._log_message(f"spacemouse_list_devices() failed: {str(e)}", Qgis.Info)
            
        # Try with Windows-specific methods if needed
        try:
            import winreg
            # Check for 3Dconnexion devices in registry
            key_path = r"SYSTEM\CurrentControlSet\Enum\HID"
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                for i in range(winreg.QueryInfoKey(key)[0]):
                    subkey_name = winreg.EnumKey(key, i)
                    if "VID_046D" in subkey_name.upper():  # 3Dconnexion vendor ID
                        self._log_message(f"Found 3Dconnexion device in registry: {subkey_name}", Qgis.Info)
                        return True
            except Exception as e:
                self._log_message(f"Registry check failed: {str(e)}", Qgis.Info)
                
        except ImportError:
            self._log_message("winreg not available", Qgis.Info)
            
        return False

    def _connect_device(self) -> bool:
        """Establish connection to SpaceMouse device"""
        if self._connected:
            return True
                
        try:
            # First check if device is available
            if not self._check_device_availability():
                return False
                
            # Add small delay before connection attempt
            time.sleep(0.5)
                    
            # Try to close any existing connections first
            try:
                spacemouse_close()
            except Exception as e:
                self._log_message(f"Error closing existing connection: {str(e)}", Qgis.Info)
                
            # Attempt to open with explicit error handling
            try:
                self._log_message("Attempting to open SpaceMouse device...", Qgis.Info)
                success = spacemouse_open()
                self._log_message(f"spacemouse_open() returned: {success}", Qgis.Info)
                
                if not success:
                    # Additional debugging information
                    devices = spacemouse_list_devices()
                    self._log_message(f"Available devices: {devices}", Qgis.Info)
                    
                    if not devices:
                        self._log_message("No devices found by spacemouse_list_devices()", Qgis.Warning)
                    else:
                        self._log_message("Devices found, but unable to open. Possible permission issue.", Qgis.Warning)
                    
            except Exception as e:
                self._log_message(f"Open error details: {str(e)}", Qgis.Critical)
                success = False
                
            if success:
                self._connected = True
                self._error_count = 0
                
                # Verify we can actually read from the device
                test_state = None
                try:
                    self._log_message("Attempting to read from spacemouse_..", Qgis.Info)
                    test_state = spacemouse_read()
                    self._log_message(f"Initial read test result: {test_state}", Qgis.Info)
                except Exception as e:
                    self._log_message(f"Initial read test failed: {str(e)}", Qgis.Warning)
                
                if test_state is not None:
                    self._log_message("SpaceMouse connected and readable", Qgis.Info)
                    self.connection_changed.emit(True)
                    return True
                else:
                    self._log_message("Device opened but not readable", Qgis.Warning)
                    self._disconnect_device()
                    return False
            else:
                self._error_count += 1
                error_msg = "Failed to open SpaceMouse device"
                self.error_occurred.emit(error_msg)
                self._log_message(error_msg, Qgis.Critical)
                return False
                
        except Exception as e:
            self._error_count += 1
            error_msg = f"Error connecting to SpaceMouse: {str(e)}"
            self.error_occurred.emit(error_msg)
            self._log_message(error_msg, Qgis.Critical)
            return False
                   
    def _check_permissions(self) -> bool:
        """Check platform-specific device permissions"""
        if self._platform == 'windows':
            return self._check_windows_permissions()
        elif self._platform == 'linux':
            return self._check_linux_permissions()
        elif self._platform == 'macos':
            return self._check_macos_permissions()
        else:
            self._log_message(f"No specific permission check for platform: {self._platform}", Qgis.Info)
            return True
            
    def _check_windows_permissions(self) -> bool:
        """Check Windows-specific device permissions"""
        self._log_message("Checking Windows permissions", Qgis.Info)
        try:
            import win32api
            import win32security
            
            # Get current process token
            process = win32api.GetCurrentProcess()
            token = win32security.OpenProcessToken(process, win32security.TOKEN_QUERY)
            
            # Check if running with admin rights
            is_admin = win32security.GetTokenInformation(
                token, win32security.TokenElevation)
                
            self._log_message(f"Running with admin rights: {is_admin}", Qgis.Info)
            return True
            
        except ImportError:
            self._log_message("win32api/win32security not available, skipping admin check", Qgis.Info)
            return True
        except Exception as e:
            self._log_message(f"Windows permission check error: {str(e)}", Qgis.Warning)
            return False
            
    def _check_linux_permissions(self) -> bool:
        """Check Linux-specific device permissions"""
        self._log_message("Checking Linux permissions", Qgis.Info)
        try:
            # Check if user has access to input devices
            import os
            import grp
            
            # Check if user is in the input group
            input_group = 'input'
            try:
                input_gid = grp.getgrnam(input_group).gr_gid
                user_groups = os.getgroups()
                
                if input_gid in user_groups:
                    self._log_message(f"User is in the '{input_group}' group", Qgis.Info)
                else:
                    self._log_message(f"User is NOT in the '{input_group}' group - may need permissions", Qgis.Warning)
            except Exception as e:
                self._log_message(f"Could not check group membership: {str(e)}", Qgis.Info)
                
            # Check permissions on device files
            for path_pattern in self._device_paths:
                if '*' in path_pattern:
                    # Expand wildcards
                    matching_paths = glob.glob(path_pattern)
                    for path in matching_paths:
                        if os.path.exists(path):
                            try:
                                mode = os.stat(path).st_mode
                                if mode & 0o006:  # Check if readable by others
                                    self._log_message(f"Device {path} is readable", Qgis.Info)
                                else:
                                    self._log_message(f"Device {path} may not be readable - check permissions", Qgis.Warning)
                            except Exception as e:
                                self._log_message(f"Could not check permissions on {path}: {str(e)}", Qgis.Info)
                elif os.path.exists(path_pattern):
                    try:
                        mode = os.stat(path_pattern).st_mode
                        if mode & 0o006:  # Check if readable by others
                            self._log_message(f"Device {path_pattern} is readable", Qgis.Info)
                        else:
                            self._log_message(f"Device {path_pattern} may not be readable - check permissions", Qgis.Warning)
                    except Exception as e:
                        self._log_message(f"Could not check permissions on {path_pattern}: {str(e)}", Qgis.Info)
                        
            return True
            
        except Exception as e:
            self._log_message(f"Linux permission check error: {str(e)}", Qgis.Warning)
            return True  # Continue anyway
            
    def _check_macos_permissions(self) -> bool:
        """Check macOS-specific device permissions"""
        self._log_message("Checking macOS permissions", Qgis.Info)
        
        # On macOS, we mainly need to check if the app has been granted input monitoring permissions
        # This is hard to check programmatically, so we'll just log a message
        self._log_message("On macOS, ensure QGIS has Input Monitoring permissions in System Preferences > Security & Privacy", Qgis.Info)
        
        return True  # Continue anyway

    def _disconnect_device(self) -> None:
        """Safely disconnect SpaceMouse device"""
        try:
            if self._connected:
                spacemouse_close()
                self._connected = False
                self.connection_changed.emit(False)
                self._log_message("SpaceMouse disconnected successfully")
        except Exception as e:
            error_msg = f"Error disconnecting SpaceMouse: {str(e)}"
            self.error_occurred.emit(error_msg)
            self._log_message(error_msg, Qgis.Warning)
        finally:
            self._connected = False
            
    def update_active_canvas(self, new_canvas_id):
        """Update the active canvas ID for this thread."""
        self.active_canvas_id = new_canvas_id
        if new_canvas_id is None:
            # Stop processing input when no canvas is active
            self._state_changed = False
        else:
            # Resume normal operation
            self._state_changed = True 
                
    def _process_state(self, state) -> Tuple[float, float, float, float, float, float]:
        """Process state data efficiently using vectorized operations and apply filters"""
        try:
            if not state:
                return tuple(np.zeros(Config.BUFFER_SIZE, dtype=np.float32))

            # Update state buffer efficiently
            new_state = np.array([
                state.x, state.y, state.z,
                state.roll, state.pitch, state.yaw
            ], dtype=np.float32)

            # Apply Kalman filter if enabled
            if hasattr(self, '_kalman_filter') and self._kalman_filter:
                filtered_state = self._kalman_filter.update(new_state)
                new_state = filtered_state

            # Check if state has changed significantly
            if self._previous_state is not None:
                state_diff = np.abs(new_state - self._state_buffer)
                self._state_changed = np.any(state_diff > Config.STATE_CHANGE_THRESHOLD)
            else:
                self._state_changed = True

            if self._state_changed:
                # Update buffer only if state changed
                np.copyto(self._state_buffer, new_state)
                
                # Cache state
                self._previous_state = dict(zip(
                    Config.STATE_KEYS,
                    self._state_buffer
                ))
                
                # Retourner directement les valeurs du buffer sans scaling
                return tuple(self._state_buffer)
            
            # Return previous state if no significant change
            if self._previous_state is not None:
                return tuple(np.array(list(self._previous_state.values()), dtype=np.float32))
            
            return tuple(np.zeros(Config.BUFFER_SIZE, dtype=np.float32))

        except Exception as e:
            self._log_message(f"Error in _process_state: {str(e)}", Qgis.Critical)
            return tuple(np.zeros(Config.BUFFER_SIZE, dtype=np.float32))

    def _cleanup(self) -> None:
        """Comprehensive cleanup of resources"""
        try:
            self._disconnect_device()
            self._state_buffer.fill(0)
            self._previous_state = None
            self._state_changed = False
            self._last_update = 0.0
            self._error_count = 0
        except Exception as e:
            error_msg = f"Error during cleanup: {str(e)}"
            self.error_occurred.emit(error_msg)
            self._log_message(error_msg, Qgis.Warning)

    def run(self) -> None:
        """Main thread loop with optimized performance and resource management"""
        try:
            # Check platform-specific permissions first
            self._log_message(f"Starting SpaceMouse thread on {self._platform}")
            self._check_permissions()
            
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries and not self.isInterruptionRequested():
                self._log_message(f"Connection attempt {retry_count + 1}/{max_retries}", Qgis.Info)
                if self._check_device_availability():
                    self._log_message("Device available, attempting to connect...", Qgis.Info)
                    if self._connect_device():
                        self._log_message("Device connected, validating connection...", Qgis.Info)
                        if self._validate_connection():
                            self._log_message("Connection validated successfully", Qgis.Info)
                            break
                        else:
                            self._log_message("Connection validation failed", Qgis.Warning)
                    else:
                        self._log_message("Failed to connect to device", Qgis.Warning)
                else:
                    self._log_message("Device not available", Qgis.Warning)
                    
                    # Platform-specific advice
                    if self._platform == 'linux':
                        self._log_message("On Linux, ensure user has permissions to access input devices", Qgis.Info)
                        self._log_message("Try: sudo usermod -a -G input $USER", Qgis.Info)
                    elif self._platform == 'macos':
                        self._log_message("On macOS, ensure QGIS has Input Monitoring permissions", Qgis.Info)
                        
                retry_count += 1
                self._log_message(f"Waiting {Config.RECONNECT_DELAY} seconds before next attempt", Qgis.Info)
                time.sleep(Config.RECONNECT_DELAY)

            if not self._connected:
                self._log_message("""
                    Failed to start SpaceMouse thread - connection failed
                    Please check:
                    1. Device is properly connected
                    2. No other application is using the device
                    3. You have necessary permissions
                    4. Device drivers are properly installed
                """, Qgis.Critical)
                return

            self._running = True
            self._log_message("SpaceMouse thread started")

            consecutive_errors = 0
            self._last_validation_time = time.time()
            
            # Initialiser le dictionnaire des états de bouton précédents
            self._previous_button_states = {}
            
            while self._running and not self.isInterruptionRequested():
                try:
                    current_time = time.time()
                    
                    # Efficient rate limiting
                    if current_time - self._last_update < self._update_interval:
                        time.sleep(Config.SLEEP_TIME)
                        continue

                    # Periodic connection validation
                    if consecutive_errors > 0 or (current_time - self._last_validation_time >= self._validation_interval):
                        self._last_validation_time = current_time
                        if not self._validate_connection():
                            self._log_message("Connection validation failed, attempting reconnect", Qgis.Warning)
                            self._disconnect_device()
                            if not self._connect_device():
                                consecutive_errors += 1
                                if consecutive_errors > 3:
                                    raise Exception("Failed to reconnect after multiple attempts")
                                time.sleep(Config.RECONNECT_DELAY)
                                continue
                    
                    state = spacemouse_read()
                    if state:
                        consecutive_errors = 0  # Reset error counter on successful read
                        
                        scaled_values = self._process_state(state)

                        # Vérifier les boutons si disponibles
                        if hasattr(state, 'buttons') and state.buttons:
                            for button_index, button_state in enumerate(state.buttons):
                                # Récupérer l'état précédent du bouton
                                prev_state = self._previous_button_states.get(button_index, 0)
                                
                                # Détecter la transition de 0 à 1 (bouton vient d'être pressé)
                                if button_state == 1 and prev_state == 0:
                                    self._log_message(f"Button {button_index} pressed", Qgis.Info)
                                    self.button_pressed.emit(self.device_id, button_index)
                                
                                # Mettre à jour l'état précédent
                                self._previous_button_states[button_index] = button_state
                    
                        if self._state_changed and len(scaled_values) == Config.BUFFER_SIZE:
                            self.data_received.emit(self.device_id, *scaled_values)
                            self._last_update = current_time

                except IOError as io_err:
                    consecutive_errors += 1
                    self._log_message(f"IO Error: {str(io_err)}", Qgis.Warning)
                    time.sleep(0.5)
                except Exception as e:
                    self._log_message(f"Unexpected error in main loop: {str(e)}", Qgis.Critical)
                    break
                    
        except Exception as e:
            self._log_message(f"Critical error in SpaceMouse thread: {str(e)}", Qgis.Critical)
        finally:
            self._log_message("SpaceMouse thread is shutting down", Qgis.Info)
            self._running = False
            self._cleanup()
            self._log_message("SpaceMouse thread has shut down", Qgis.Info)
        
    def stop(self) -> None:
        """Safe thread termination with resource cleanup"""
        if not self._running:
            return
            
        self._running = False
        self._cleanup()
        
        try:
            # Give the thread a chance to stop gracefully
            for _ in range(2):
                if self.wait(msecs=Config.THREAD_STOP_TIMEOUT):
                    self._log_message("SpaceMouse thread stopped gracefully")
                    return
                    
                self._log_message("Waiting for thread to stop...", Qgis.Warning)
            
            # Force stop if necessary
            self._log_message("Force stopping SpaceMouse thread", Qgis.Warning)
            self.terminate()
            
            if not self.wait(msecs=Config.THREAD_STOP_TIMEOUT):
                error_msg = "Thread failed to stop after termination"
                self.error_occurred.emit(error_msg)
                self._log_message(error_msg, Qgis.Critical)
            
        except Exception as e:
            error_msg = f"Error stopping thread: {str(e)}"
            self.error_occurred.emit(error_msg)
            self._log_message(error_msg, Qgis.Critical)
        finally:
            # Ensure device is disconnected
            try:
                spacemouse_close()
            except Exception as e:
                self._log_message(f"Error closing device during stop: {str(e)}", Qgis.Info)

    def __enter__(self):
        """Support for context manager protocol"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure cleanup when used as context manager"""
        self.stop()

    def __del__(self) -> None:
        """Ensure proper cleanup on object deletion"""
        try:
            if self._running or self._connected:
                self.stop()
        except Exception as e:
            self._log_message(f"Error during deletion: {str(e)}", Qgis.Warning)