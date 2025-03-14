from dataclasses import dataclass, field
from typing import Dict, Tuple
from qgis.core import Qgis

@dataclass(frozen=True)
class Config:
    """Unified configuration settings for SpaceMouse Plugin"""
    # Plugin identification
    PLUGIN_NAME: str = "SpaceMouse3Dconnexion"
    MENU_NAME: str = "SpaceMouse"
    SETTINGS_NAMESPACE: str = "QGIS"
    SETTINGS_GROUP: str = "SpaceMousePlugin"
    
    # SpaceMouse thread settings
    UPDATE_INTERVAL: float = 0.01  # 10ms for smooth updates
    SCALE_FACTOR: float = 100.0
    SLEEP_TIME: float = 0.001  # 1ms sleep time for thread
    BUFFER_SIZE: int = 6  # Size of state buffer (x, y, z, roll, pitch, yaw)
    STATE_CHANGE_THRESHOLD: float = 0.0001  # Threshold for detecting state changes
    STATE_KEYS: Tuple[str, ...] = ('x', 'y', 'z', 'roll', 'pitch', 'yaw')
    RECONNECT_DELAY: float = 1.0  # Delay between reconnection attempts
    THREAD_STOP_TIMEOUT: int = 1000  # Timeout for thread stop in milliseconds
    
    # Error handling settings
    ERROR_RETRY_DELAY: float = 1.0  # Delay after error before retry
    MAX_ERRORS: int = 10  # Maximum number of errors before thread stops
    
    # Performance settings
    MIN_UPDATE_INTERVAL: float = 0.001  # Minimum allowed update interval
    MAX_UPDATE_INTERVAL: float = 0.1  # Maximum allowed update interval
    MIN_SCALE_FACTOR: float = 0.1  # Minimum allowed scale factor
    MAX_SCALE_FACTOR: float = 1000.0  # Maximum allowed scale factor
    
    # Device settings
    DEVICE_TIMEOUT: float = 0.5  # Timeout for device operations
    MAX_RECONNECT_ATTEMPTS: int = 5  # Maximum reconnection attempts
    
    # Thread management
    THREAD_STARTUP_TIMEOUT: int = 2000  # Timeout for thread startup in milliseconds
    THREAD_FORCE_KILL_TIMEOUT: int = 3000  # Timeout before force killing thread
    
    # Logging
    LOG_LEVEL: int = Qgis.Info
    LOG_TO_FILE: bool = False  # Option to log to file
    LOG_FILE_PATH: str = ""  # Path for log file if LOG_TO_FILE is True
    
    # Value validation thresholds
    MAX_VALID_COORDINATE: float = 1000.0  # Maximum valid coordinate value
    MAX_VALID_ROTATION: float = 360.0  # Maximum valid rotation value
    
    @classmethod
    def get_validation_limits(cls) -> Dict[str, float]:
        """Get validation limits for different value types"""
        return {
            'coordinate': cls.MAX_VALID_COORDINATE,
            'rotation': cls.MAX_VALID_ROTATION,
            'scale': cls.MAX_SCALE_FACTOR,
            'interval': cls.MAX_UPDATE_INTERVAL
        }
    
    @classmethod
    def validate_update_interval(cls, value: float) -> float:
        """Validate and clamp update interval value"""
        return max(cls.MIN_UPDATE_INTERVAL, 
                  min(cls.MAX_UPDATE_INTERVAL, value))
    
    @classmethod
    def validate_scale_factor(cls, value: float) -> float:
        """Validate and clamp scale factor value"""
        return max(cls.MIN_SCALE_FACTOR, 
                  min(cls.MAX_SCALE_FACTOR, value))
    
    @classmethod
    def set_log_level(cls, level: int) -> None:
        """Set the logging level."""
        object.__setattr__(cls, 'LOG_LEVEL', level)
