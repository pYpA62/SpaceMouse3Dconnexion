# SMConfig.py

from dataclasses import dataclass, field
import sys
import os
from typing import Dict, Tuple, List, Optional
from qgis.core import Qgis

@dataclass(frozen=True)
class PlatformConfig:
    """Platform-specific configuration settings"""
    # Device paths for different platforms
    DEVICE_PATHS: List[str]
    
    # Service executable paths
    SERVICE_EXECUTABLE: str
    
    # Process names to check
    PROCESS_NAMES: List[str]
    
    # Platform-specific performance settings
    UPDATE_INTERVAL: float
    SLEEP_TIME: float
    
    # Platform-specific help messages
    SETUP_INSTRUCTIONS: str
    PERMISSION_INSTRUCTIONS: str

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
    
    # Device settings
    DEVICE_TIMEOUT: float = 0.5  # Timeout for device operations
    MAX_RECONNECT_ATTEMPTS: int = 5  # Maximum reconnection attempts
    
    # Thread management
    THREAD_STARTUP_TIMEOUT: int = 2000  # Timeout for thread startup in milliseconds
    THREAD_FORCE_KILL_TIMEOUT: int = 3000  # Timeout before force killing thread
    
    # Logging
    LOG_LEVEL: int = Qgis.Warning
    LOG_TO_FILE: bool = False  # Option to log to file
    LOG_FILE_PATH: str = ""  # Path for log file if LOG_TO_FILE is True
    
    # Value validation thresholds
    MAX_VALID_COORDINATE: float = 1000.0  # Maximum valid coordinate value
    MAX_VALID_ROTATION: float = 360.0  # Maximum valid rotation value
    
    # Platform-specific configurations
    PLATFORM_CONFIGS: Dict[str, PlatformConfig] = field(default_factory=lambda: {
        'windows': PlatformConfig(
            DEVICE_PATHS=[],  # Windows uses HID directly
            SERVICE_EXECUTABLE=r"C:\Program Files\3Dconnexion\3DxWare\3DxWinCore\3DxService.exe",
            PROCESS_NAMES=["3DxService.exe", "3DxWare.exe"],
            UPDATE_INTERVAL=0.01,
            SLEEP_TIME=0.001,
            SETUP_INSTRUCTIONS="""
                Pour configurer SpaceMouse sur Windows:
                1. Installez les pilotes 3DConnexion depuis le site officiel
                2. Redémarrez QGIS après l'installation
                3. Assurez-vous qu'aucune autre application n'utilise le périphérique
            """,
            PERMISSION_INSTRUCTIONS="""
                Si vous rencontrez des problèmes de permissions sur Windows:
                1. Exécutez QGIS en tant qu'administrateur
                2. Vérifiez que les pilotes 3DConnexion sont correctement installés
                3. Vérifiez que le service 3DxService est en cours d'exécution
            """
        ),
        'linux': PlatformConfig(
            DEVICE_PATHS=[
                '/dev/input/spacenavigator',
                '/dev/input/spacemouse',
                '/dev/input/3dconnexion',
                '/dev/hidraw*'
            ],
            SERVICE_EXECUTABLE="/usr/bin/spacenavd",
            PROCESS_NAMES=["spacenavd", "3dxsrv"],
            UPDATE_INTERVAL=0.01,
            SLEEP_TIME=0.001,
            SETUP_INSTRUCTIONS="""
                Pour configurer SpaceMouse sur Linux:
                1. Installez spacenavd: sudo apt install spacenavd
                2. Ajoutez votre utilisateur au groupe input: sudo usermod -a -G input $USER
                3. Redémarrez votre session
                4. Démarrez le service: sudo systemctl start spacenavd
            """,
            PERMISSION_INSTRUCTIONS="""
                Si vous rencontrez des problèmes de permissions sur Linux:
                1. Vérifiez que votre utilisateur est dans le groupe input: groups
                2. Vérifiez les permissions des fichiers de périphériques: ls -l /dev/input/
                3. Installez les règles udev pour 3Dconnexion
            """
        ),
        'macos': PlatformConfig(
            DEVICE_PATHS=[
                '/dev/cu.usbmodem*'
            ],
            SERVICE_EXECUTABLE="/Library/Application Support/3Dconnexion/3DxWareMac/3DxWareMac.app/Contents/MacOS/3DxWareMac",
            PROCESS_NAMES=["3DxWareMac"],
            UPDATE_INTERVAL=0.015,  # Slightly higher on macOS for better stability
            SLEEP_TIME=0.002,
            SETUP_INSTRUCTIONS="""
                Pour configurer SpaceMouse sur macOS:
                1. Installez les pilotes 3DConnexion depuis le site officiel
                2. Dans Préférences Système > Sécurité et confidentialité > Confidentialité:
                   - Accordez à QGIS l'accès à "Surveillance des entrées"
                3. Redémarrez QGIS après l'installation
            """,
            PERMISSION_INSTRUCTIONS="""
                Si vous rencontrez des problèmes de permissions sur macOS:
                1. Ouvrez Préférences Système > Sécurité et confidentialité > Confidentialité
                2. Sélectionnez "Surveillance des entrées" et assurez-vous que QGIS est coché
                3. Redémarrez QGIS après avoir modifié les permissions
            """
        )
    })
    
    @classmethod
    def get_platform(cls) -> str:
        """Detect the current platform"""
        if sys.platform.startswith('win'):
            return 'windows'
        elif sys.platform.startswith('darwin'):
            return 'macos'
        elif sys.platform.startswith('linux'):
            return 'linux'
        else:
            return 'unknown'
    
    @classmethod
    def get_platform_config(cls) -> Optional[PlatformConfig]:
        """Get configuration for the current platform"""
        platform = cls.get_platform()
        return cls.PLATFORM_CONFIGS.get(platform)
    
    @classmethod
    def get_service_executable(cls) -> str:
        """Get the service executable path for the current platform"""
        platform_config = cls.get_platform_config()
        if platform_config:
            return platform_config.SERVICE_EXECUTABLE
        return ""
    
    @classmethod
    def get_device_paths(cls) -> List[str]:
        """Get device paths for the current platform"""
        platform_config = cls.get_platform_config()
        if platform_config:
            return platform_config.DEVICE_PATHS
        return []
    
    @classmethod
    def get_process_names(cls) -> List[str]:
        """Get process names for the current platform"""
        platform_config = cls.get_platform_config()
        if platform_config:
            return platform_config.PROCESS_NAMES
        return []
    
    @classmethod
    def get_platform_update_interval(cls) -> float:
        """Get the recommended update interval for the current platform"""
        platform_config = cls.get_platform_config()
        if platform_config:
            return platform_config.UPDATE_INTERVAL
        return cls.UPDATE_INTERVAL
    
    @classmethod
    def get_platform_sleep_time(cls) -> float:
        """Get the recommended sleep time for the current platform"""
        platform_config = cls.get_platform_config()
        if platform_config:
            return platform_config.SLEEP_TIME
        return cls.SLEEP_TIME
    
    @classmethod
    def get_setup_instructions(cls) -> str:
        """Get setup instructions for the current platform"""
        platform_config = cls.get_platform_config()
        if platform_config:
            return platform_config.SETUP_INSTRUCTIONS
        return "Instructions non disponibles pour cette plateforme."
    
    @classmethod
    def get_permission_instructions(cls) -> str:
        """Get permission instructions for the current platform"""
        platform_config = cls.get_platform_config()
        if platform_config:
            return platform_config.PERMISSION_INSTRUCTIONS
        return "Instructions non disponibles pour cette plateforme."
    
    @classmethod
    def get_validation_limits(cls) -> Dict[str, float]:
        """Get validation limits for different value types"""
        return {
            'coordinate': cls.MAX_VALID_COORDINATE,
            'rotation': cls.MAX_VALID_ROTATION,
            'interval': cls.MAX_UPDATE_INTERVAL
        }
    
    @classmethod
    def validate_update_interval(cls, value: float) -> float:
        """Validate and clamp update interval value"""
        return max(cls.MIN_UPDATE_INTERVAL, 
                  min(cls.MAX_UPDATE_INTERVAL, value))
    
   
    @classmethod
    def set_log_level(cls, level: int) -> None:
        """Set the logging level."""
        object.__setattr__(cls, 'LOG_LEVEL', level)