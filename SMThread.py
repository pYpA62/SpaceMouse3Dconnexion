from PyQt5.QtCore import QThread, pyqtSignal
from qgis.core import QgsMessageLog, Qgis
import pyspacemouse
import time
import numpy as np
from typing import Optional, Tuple, Dict
from .SMConfig import Config
from .SMKalmanFilters import KalmanFilter

class SpaceMouseThread(QThread):
    """
    Thread for handling SpaceMouse device input in QGIS.
    Provides efficient, non-blocking access to 3D mouse data.
    """
    data_received = pyqtSignal(str, float, float, float, float, float, float)
    error_occurred = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)
    
    def __init__(self, device_id: str, scale_factor: float = 1.0):
        """
        Initialize the SpaceMouse thread.
        
        Args:
            device_id: Unique identifier for the device
            scale_factor: Scaling factor for input values
        """
        super().__init__()
        self.device_id = device_id
        self.scale_factor = scale_factor
        
        # Thread control
        self._running: bool = False
        self._connected: bool = False
        
        # Performance optimization
        self._scale_factor: float = scale_factor
        self._last_update: float = 0.0
        self._update_interval: float = Config.UPDATE_INTERVAL
        
        # Pre-allocated numpy arrays for better performance
        self._state_buffer: np.ndarray = np.zeros(Config.BUFFER_SIZE, 
                                                 dtype=np.float32)
        self._scale_vector: np.ndarray = np.full(Config.BUFFER_SIZE, 
                                                self._scale_factor, 
                                                dtype=np.float32)
        
        # State tracking
        self._previous_state: Optional[Dict[str, float]] = None
        self._state_changed: bool = False
        self._error_count: int = 0
        self._max_errors: int = Config.MAX_ERRORS
        
        # Validation timing
        self._last_validation_time: float = 0.0
        self._validation_interval: float = 10.0  # seconds

    def _log_message(self, message: str, level: int = Qgis.Info) -> None:
        """Thread-safe logging with level control"""
        if level >= Config.LOG_LEVEL:
            QgsMessageLog.logMessage(message, Config.PLUGIN_NAME, level=level)

    def update_settings(self, scale_factor: float = None, update_interval: float = None) -> None:
        """Update thread settings safely"""
        try:
            if scale_factor is not None:
                self._scale_factor = scale_factor
                self._scale_vector.fill(scale_factor)
            
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
                test_state = pyspacemouse.read()
                if test_state is not None:
                    return True
                time.sleep(0.05)
                
            return False
            
        except Exception as e:
            self._log_message(f"Connection validation failed: {str(e)}", Qgis.Warning)
            return False
        
    def _check_device_availability(self) -> bool:
        """Check if SpaceMouse device is available"""
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
                
                self._log_message(f"Found devices: {device_info}", Qgis.Info)
                return True
            else:
                self._log_message("No SpaceMouse devices found", Qgis.Warning)
                return False
                
        except Exception as e:
            self._log_message(f"Error enumerating devices: {str(e)}", Qgis.Critical)
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
                pyspacemouse.close()
            except Exception as e:
                self._log_message(f"Error closing existing connection: {str(e)}", Qgis.Info)
                
            # Attempt to open with explicit error handling
            try:
                self._log_message("Attempting to open SpaceMouse device...", Qgis.Info)
                success = pyspacemouse.open()
                self._log_message(f"pyspacemouse.open() returned: {success}", Qgis.Info)
                
                if not success:
                    # Additional debugging information
                    devices = pyspacemouse.list_devices()
                    self._log_message(f"Available devices: {devices}", Qgis.Info)
                    
                    if not devices:
                        self._log_message("No devices found by pyspacemouse.list_devices()", Qgis.Warning)
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
                    self._log_message("Attempting to read from SpaceMouse...", Qgis.Info)
                    test_state = pyspacemouse.read()
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
                   
    def _check_windows_permissions(self) -> bool:
        """Check Windows-specific device permissions"""
        import platform
        if platform.system() != 'Windows':
            self._log_message("Not on Windows, skipping permission check", Qgis.Info)
            return True
            
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
            
        except Exception as e:
            self._log_message(f"Permission check error: {str(e)}", Qgis.Warning)
            return False

    def _disconnect_device(self) -> None:
        """Safely disconnect SpaceMouse device"""
        try:
            if self._connected:
                pyspacemouse.close()
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
        #Update the active canvas ID for this thread.
        self.active_canvas_id = new_canvas_id
        if new_canvas_id is None:
            # Stop processing input when no canvas is active
            self._state_changed = False
        else:
            # Resume normal operation
            self._state_changed = True 
                
    def _process_state(self, state) -> Tuple[float, float, float, float, float, float]:
        """Process state data efficiently using vectorized operations"""
        try:
            if not state:
                return tuple(np.zeros(Config.BUFFER_SIZE, dtype=np.float32))

            # Update state buffer efficiently
            new_state = np.array([
                state.x, state.y, state.z,
                state.roll, state.pitch, state.yaw
            ], dtype=np.float32)

            # Check if state has changed significantly
            if self._previous_state is not None:
                state_diff = np.abs(new_state - self._state_buffer)
                self._state_changed = np.any(state_diff > Config.STATE_CHANGE_THRESHOLD)
            else:
                self._state_changed = True

            if self._state_changed:
                # Update buffer only if state changed
                np.copyto(self._state_buffer, new_state)
                
                # Vectorized scaling
                scaled_state = np.multiply(self._state_buffer, self._scale_vector)
                
                # Cache state
                self._previous_state = dict(zip(
                    Config.STATE_KEYS,
                    self._state_buffer
                ))

                
                return tuple(scaled_state)
            
            # Return previous scaled state if no significant change
            if self._previous_state is not None:
                return tuple(np.multiply(
                    np.array(list(self._previous_state.values()), dtype=np.float32),
                    self._scale_vector
                ))
            
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
            # Check permissions first
            self._check_windows_permissions()
            
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
                    
                    state = pyspacemouse.read()
                    if state:
                        consecutive_errors = 0  # Reset error counter on successful read
                        scaled_values = self._process_state(state)
                        
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
                pyspacemouse.close()
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
