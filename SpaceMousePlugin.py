# SpaceMousePlugin.py
# Standard library imports
import os
import sys
import time
import weakref
import sip
from typing import Optional, Dict, List, Any
from functools import lru_cache

# PyQt5 imports
from PyQt5.QtWidgets import (
    QApplication, QAction, QMessageBox, QDialog, QVBoxLayout, 
    QLabel, QSlider, QPushButton, QWidget, QDockWidget
)
from PyQt5.QtCore import QObject, QTimer, QSettings, Qt, QEvent, QMutex, QMutexLocker
from PyQt5.QtGui import QIcon

# QGIS imports
from qgis.utils import iface
from qgis._3d import Qgs3DMapCanvas
from qgis.core import QgsMessageLog, QgsProject, Qgis

# Third-party imports
import numpy as np

# Local imports
from .SMThread import SpaceMouseThread
from .SMSettings import SettingsConfig, SettingsDock
from .SMConfig import Config
from .SMCameraController import CameraController
from .SMKalmanFilters import KalmanFilters
from .SMProcessManager import ProcessManager
from .SMNewDevice import (
    load_devices_from_config, list_devices, 
    ManageDevicesDialog, AddDeviceDialog
)
from easyhid import Enumeration

class SpaceMousePlugin(QObject):
    """Main plugin class for SpaceMouse integration with QGIS."""

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self._initialize_attributes()
        self._setup_event_filter()
        self._load_settings()
        self._init_kalman_filters()
        
        # Platform-specific executable paths
        self.platform = self._detect_platform()
        self.executable_path = self._get_platform_executable_path()
        self.process_manager = ProcessManager(self.executable_path)
        
        self.active_window = None
        self._log_message(f"Plugin initialized on {self.platform}", Qgis.Info)

        # Only stop the service on Windows as it might interfere
        if self.platform == 'windows':
            stop_message = self.process_manager.stop()
            self._log_message(stop_message)
        
        try:
            from qgis.gui import QgsGui
            QApplication.instance().focusChanged.connect(self._on_focus_changed)
        except Exception as e:
            self._log_message(f"Could not connect to focus change signal: {str(e)}", Qgis.Warning)
            
           

    # Initialization Methods
    def _initialize_attributes(self) -> None:
        """Initialize class attributes."""
        # Core components
        self.settings_dock: Optional[SettingsDock] = None
        self.canvas_3d: Optional[Qgs3DMapCanvas] = None  # Keep for backward compatibility
        self.canvases_3d: Dict[int, Qgs3DMapCanvas] = {}  # Store multiple canvases by ID
        self.active_canvas_id: Optional[int] = None  # Track which canvas is currently active
        self.spacemouse_threads: Dict[str, SpaceMouseThread] = {}
        self.camera_controllers: Dict[str, Dict[int, CameraController]] = {}  # Nested dict: device_id -> canvas_id -> controller
        self.kalman_filter: Optional[KalmanFilters] = None
        self.device_states: Dict[str, Dict[str, float]] = {}

        # UI elements
        self._actions: Dict[str, QAction] = {}
        self.dock_action: Optional[QAction] = None

        # State tracking
        self.warning_shown: bool = False
        self.is_operational: bool = False
        self.active_devices: set = set()

        # Thread safety
        self.thread_mutex = QMutex()

        # Initialize settings with default values
        self.settings: Dict[str, float] = {
            key: SettingsConfig.get_default_value(key) 
            for key in SettingsConfig.DEFAULTS.keys()
        }

        # Get thresholds
        self.THRESHOLDS = SettingsConfig.get_default_thresholds()

        # Thread settings
        self.UPDATE_INTERVAL = self.settings.get('update_interval', 0.01)
        self.SLEEP_TIME = self.settings.get('sleep_time', 0.005)
        self.STATE_CHANGE_THRESHOLD = self.settings.get('state_change_threshold', 0.001)
        self.RECONNECT_DELAY = self.settings.get('reconnect_delay', 1.0)
        self.THREAD_STOP_TIMEOUT = self.settings.get('thread_stop_timeout', 1000)
        
        # Constants
        self.BUFFER_SIZE = SettingsConfig.BUFFER_SIZE
        self.STATE_KEYS = SettingsConfig.STATE_KEYS

    def _setup_event_filter(self):
        """Setup event filter for the main window."""
        try:
            self.iface.mainWindow().installEventFilter(self)
            self._log_message("Event filter installed successfully", Qgis.Info)
        except Exception as e:
            self._log_message(f"Error setting up event filter: {str(e)}", Qgis.Critical)

    def _load_settings(self) -> None:
        """Load plugin settings from QGIS settings."""
        try:
            settings = QSettings()
            settings.beginGroup(SettingsConfig.SETTINGS_GROUP)

            # Load all settings with defaults from SettingsConfig
            self.settings = {}
            for key, (default, min_val, max_val, step) in SettingsConfig.DEFAULTS.items():
                value = settings.value(key, default, type=float)
                # Validate value is within bounds
                value = max(min_val, min(max_val, value))
                self.settings[key] = value

            settings.endGroup()
            
            # Update instance variables with loaded settings
            self._update_instance_settings()
            
            self._log_message("Settings loaded successfully", Qgis.Info)

        except Exception as e:
            self._log_message(f"Error loading settings: {str(e)}", Qgis.Critical)
            # Fallback to defaults
            self.settings = {key: default for key, (default, *_) 
                            in SettingsConfig.DEFAULTS.items()}
            self._update_instance_settings()

    def _update_instance_settings(self) -> None:
        """Update instance variables with current settings."""
        self.UPDATE_INTERVAL = self.settings.get('update_interval', 0.01)
        self.SLEEP_TIME = self.settings.get('sleep_time', 0.005)
        self.STATE_CHANGE_THRESHOLD = self.settings.get('state_change_threshold', 0.001)
        self.RECONNECT_DELAY = self.settings.get('reconnect_delay', 1.0)
        self.THREAD_STOP_TIMEOUT = self.settings.get('thread_stop_timeout', 1000)
        
        # Update thresholds
        self.THRESHOLDS = {
            'xy': self.settings.get('threshold_xy', 0.01),
            'z': self.settings.get('threshold_z', 0.01),
            'rotation': self.settings.get('threshold_rotation', 0.01)
        }

    def _init_kalman_filters(self) -> None:
        """Initialize Kalman filters with current settings."""
        try:
            if self.kalman_filter is not None:
                self.kalman_filter.cleanup()
            self.kalman_filter = KalmanFilters(self.settings)
            self._log_message("Kalman filters initialized successfully", Qgis.Info)
        except Exception as e:
            self._log_message(f"Error initializing Kalman filters: {str(e)}", Qgis.Critical)
            self.kalman_filter = None

    # GUI Methods
    def initGui(self) -> None:
        """Initialize the graphical user interface."""
        try:
            self._create_actions()
            self._add_actions_to_menu()

            # Set up periodic check for 3D views
            if hasattr(self, 'check_timer'):
                self.check_timer.stop()
                
            self.check_timer = QTimer(self)
            self.check_timer.timeout.connect(self._check_for_new_3d_views)
            self.check_timer.start(5000)  # Check every 5 seconds
            
            # Install event filter
            self.iface.mainWindow().installEventFilter(self)
            self._log_message("GUI initialized successfully", Qgis.Info)
            
        except Exception as e:
            self._log_message(f"Error initializing GUI: {str(e)}", Qgis.Critical)
            raise

    def _create_actions(self) -> None:
        """Create plugin actions."""
        try:
            self._create_dock_action()
            self._create_start_stop_actions()
        except Exception as e:
            self._log_message(f"Error creating actions: {str(e)}", Qgis.Critical)
            raise

    def _create_dock_action(self) -> None:
        """Create settings dock action with platform-safe path handling."""
        try:
            # Utiliser le sous-répertoire "icons"
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(plugin_dir, "icons", "settings_icon.png")
            self._log_message(f"Looking for settings icon at: {icon_path}", Qgis.Info)

            if os.path.exists(icon_path):
                self.dock_action = QAction(QIcon(icon_path), "Settings", self.iface.mainWindow())
            else:
                self._log_message(f"Icon file not found at: {icon_path}", Qgis.Warning)
                self.dock_action = QAction("Settings", self.iface.mainWindow())
                
            self.dock_action.setCheckable(True)
            self.dock_action.triggered.connect(self.toggle_settings_dock)
            self.dock_action.setEnabled(True)
        except Exception as e:
            self._log_message(f"Error creating dock action: {str(e)}", Qgis.Critical)
            raise

    def _create_start_stop_actions(self) -> None:
        """Create start and stop actions with platform-safe path handling."""
        try:
            # Get the plugin directory path with normpath for platform compatibility
            plugin_dir = os.path.normpath(os.path.dirname(__file__))

            # Create start action with icon
            start_icon_path = os.path.normpath(os.path.join(plugin_dir, "icons", "start_icon.png"))
            self._log_message(f"Looking for start icon at: {start_icon_path}", Qgis.Info)
            
            self._actions['start'] = QAction(
                QIcon(start_icon_path) if os.path.exists(start_icon_path) else QIcon(),
                "Start", 
                self.iface.mainWindow()
            )
            self._actions['start'].triggered.connect(self.start_spacemouse)
            self._actions['start'].setEnabled(True)

            # Create stop action with icon
            stop_icon_path = os.path.normpath(os.path.join(plugin_dir, "icons", "stop_icon.png"))
            self._log_message(f"Looking for stop icon at: {stop_icon_path}", Qgis.Info)
            self._actions['stop'] = QAction(
                QIcon(stop_icon_path) if os.path.exists(stop_icon_path) else QIcon(),
                "Stop", 
                self.iface.mainWindow()
            )
            self._actions['stop'].triggered.connect(self.stop_spacemouse)
            self._actions['stop'].setEnabled(False)
        except Exception as e:
            self._log_message(f"Error creating start/stop actions: {str(e)}", Qgis.Critical)
            raise

    def _add_actions_to_menu(self) -> None:
        """Add actions to plugin menu."""
        try:
            actions_to_add = [self.dock_action] + list(self._actions.values())
            for action in actions_to_add:
                if action is not None:
                    try:
                        self.iface.addPluginToMenu(Config.MENU_NAME, action)
                    except Exception as e:
                        self._log_message(f"Error adding action to menu: {str(e)}", Qgis.Warning)
        except Exception as e:
            self._log_message(f"Error adding actions to menu: {str(e)}", Qgis.Critical)

    def toggle_settings_dock(self, checked: bool) -> None:
        """
        Toggle settings dock visibility.

        Args:
            checked: Whether the dock should be shown.
        """
        try:
            if not hasattr(self, 'settings_dock') or self.settings_dock is None:
                # Create settings dock with just the parent parameter
                self.settings_dock = SettingsDock(self.iface.mainWindow())
                self.settings_dock.applied.connect(self._on_settings_applied)
                
                # Connect destroyed signal if you have the handler method
                if hasattr(self, '_on_dock_destroyed'):
                    self.settings_dock.destroyed.connect(self._on_dock_destroyed)
                    
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self.settings_dock)
                
                # Update with current settings
                self.settings_dock.update_values(self.settings)

            if checked:
                self.settings_dock.show()
                self.settings_dock.update_values(self.settings)
            else:
                self.settings_dock.hide()
        except Exception as e:
            self._log_message(f"Error toggling settings dock: {str(e)}", Qgis.Critical)
            # Show error to user
            QMessageBox.warning(
                self.iface.mainWindow(),
                "SpaceMouse Error",
                f"Error opening settings: {str(e)}"
            )

    def _on_settings_applied(self, new_values: Dict[str, float]) -> None:
        """
        Handle settings applied from dock.

        Args:
            new_values: Dictionary of new setting values.
        """
        try:
            # Validate new values
            for key, value in new_values.items():
                if key in SettingsConfig.DEFAULTS:
                    default, min_val, max_val, step = SettingsConfig.DEFAULTS[key]
                    new_values[key] = max(min_val, min(max_val, value))

            self.settings.update(new_values)
            
            # Update instance variables
            self._update_instance_settings()

            # Save to QSettings
            settings = QSettings()
            settings.beginGroup(SettingsConfig.SETTINGS_GROUP)
            try:
                for key, value in self.settings.items():
                    settings.setValue(key, value)
            finally:
                settings.endGroup()

            # Update components with new settings
            self._update_components_with_settings()

            self._log_message("Settings applied successfully", Qgis.Info)
        except Exception as e:
            self._log_message(f"Error applying settings: {str(e)}", Qgis.Critical)
            
    def _update_components_with_settings(self) -> None:
        """Update all components with new settings."""
        try:
            # Update Kalman filter
            if self.kalman_filter:
                self.kalman_filter.update_settings(self.settings)

            # Update camera controller (legacy)
            if hasattr(self, 'camera_controller') and self.camera_controller:
                try:
                    self.camera_controller.update_settings({
                        'move_factor': self.settings['move_factor'],
                        'rotation_factor': self.settings['rotation_factor'],
                        'zoom_factor': self.settings['zoom_factor']
                    })
                except Exception as e:
                    self._log_message(f"Error updating legacy camera controller: {str(e)}", Qgis.Warning)
                    self.camera_controller = None
            
            # Update all camera controllers (nested dictionary)
            invalid_entries = []
            for device_id, canvas_controllers in self.camera_controllers.items():
                for canvas_id, controller in canvas_controllers.items():
                    try:
                        # Check if controller is still valid
                        if hasattr(controller, 'update_settings'):
                            controller.update_settings({
                                'move_factor': self.settings['move_factor'],
                                'rotation_factor': self.settings['rotation_factor'],
                                'zoom_factor': self.settings['zoom_factor']
                            })
                        else:
                            invalid_entries.append((device_id, canvas_id))
                    except Exception as e:
                        self._log_message(f"Error updating controller for device {device_id}, canvas {canvas_id}: {str(e)}", Qgis.Warning)
                        invalid_entries.append((device_id, canvas_id))
            
            # Clean up invalid controllers
            for device_id, canvas_id in invalid_entries:
                if device_id in self.camera_controllers and canvas_id in self.camera_controllers[device_id]:
                    del self.camera_controllers[device_id][canvas_id]
                    self._log_message(f"Removed invalid controller for device {device_id}, canvas {canvas_id}", Qgis.Info)

            # Update thread settings for all threads
            for thread in self.spacemouse_threads.values():
                if thread.isRunning():
                    thread.update_settings(
                        update_interval=self.settings['update_interval']
                    )

            self._log_message("Components updated with new settings", Qgis.Info)
        except Exception as e:
            self._log_message(f"Error updating components with settings: {str(e)}", Qgis.Critical)

    # Event Handling Methods
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """
        Filtrer les événements pour détecter les changements de focus et les clics de souris.
        """
        if event.type() == QEvent.WindowActivate:
            self._log_message(f"Événement WindowActivate détecté sur l'objet : {obj}", Qgis.Info)
            QTimer.singleShot(100, lambda: self._handle_window_activate(obj))

        elif event.type() == QEvent.FocusIn:
            self._log_message(f"Événement FocusIn détecté sur l'objet : {obj}", Qgis.Info)
            if isinstance(obj, Qgs3DMapCanvas):
                self._log_message(f"Focus acquis sur le canvas 3D (ID : {id(obj)})", Qgis.Info)
                self._update_active_canvas(id(obj))
            else:
                self._log_message("Focus acquis sur un objet non-canvas 3D", Qgis.Info)
                self._update_active_canvas(None)

        elif event.type() == QEvent.FocusOut:
            self._log_message(f"Événement FocusOut détecté sur l'objet : {obj}", Qgis.Info)
            if isinstance(obj, Qgs3DMapCanvas):
                self._log_message(f"Focus perdu sur le canvas 3D (ID : {id(obj)})", Qgis.Info)
            else:
                self._log_message("Focus perdu sur un objet non-canvas 3D", Qgis.Info)

        elif event.type() == QEvent.MouseButtonPress:
            self._log_message(f"Événement MouseButtonPress détecté sur l'objet : {obj}", Qgis.Info)
            if isinstance(obj, Qgs3DMapCanvas):
                self._update_active_canvas(id(obj))
                self._log_message(f"Bouton de souris pressé sur le canvas 3D (ID : {id(obj)})", Qgis.Info)
            else:
                self._log_message("Bouton de souris pressé sur un objet non-canvas 3D", Qgis.Info)

        return False  # Laisser l'événement se propager
    
    def _handle_window_activate(self, obj):
        """Handle window activation with a slight delay."""
        if isinstance(obj, Qgs3DMapCanvas):
            self._log_message(f"Window activated for 3D canvas (ID: {id(obj)})", Qgis.Info)
            self._update_active_canvas(id(obj))
            self.check_active_canvas()

    def _on_focus_changed(self, old, new):
        """Gérer les changements de focus entre différentes fenêtres et widgets."""
        self._log_message(f"Focus changé de {old} à {new}", Qgis.Info)
        
        # Vérifier si le nouveau focus est directement un canvas 3D
        if isinstance(new, Qgs3DMapCanvas):
            self._update_active_canvas(id(new))
            return
        
        # Si le focus est perdu ou déplacé vers un non-widget
        if new is None or not isinstance(new, QWidget):
            self._update_active_canvas(None)
            return
        
        # Vérifier si le nouveau focus est un enfant d'un canvas 3D
        parent = new
        while parent is not None:
            if isinstance(parent, Qgs3DMapCanvas):
                self._update_active_canvas(id(parent))
                return
            parent = parent.parent()
        
        # Si aucun canvas 3D n'est trouvé dans la hiérarchie
        self._update_active_canvas(None)

    def _update_active_canvas(self, canvas_id: Optional[int]) -> None:
        """
        Update the active canvas for SpaceMouse control.
        
        Args:
            canvas_id: The ID of the canvas to set as active, or None if no canvas should be active.
        """
        self._log_message(f"Updating active canvas to ID: {canvas_id}", Qgis.Info)
        if canvas_id != self.active_canvas_id:
            self.active_canvas_id = canvas_id
            if canvas_id is not None and canvas_id in self.canvases_3d:
                self.canvas_3d = self.canvases_3d[canvas_id]
                self._log_message(f"Active 3D canvas updated to ID: {canvas_id}", Qgis.Info)
            else:
                self.canvas_3d = None
                self._log_message("No active 3D canvas", Qgis.Info)
            
            # Update SpaceMouse threads with new active canvas
            for thread in self.spacemouse_threads.values():
                self._log_message(f"Updating SpaceMouse thread for device {thread.device_id} with new active canvas", Qgis.Info)
                thread.update_active_canvas(self.canvas_3d)
            
            # Update camera controllers
            self._update_camera_controllers(canvas_id)
            
            # Start SpaceMouse if not already started
            if self.canvas_3d and not self.is_operational:
                self.start_spacemouse()

    def _update_camera_controllers(self, new_active_canvas_id):
        """Update camera controllers for the new active canvas."""
        self._log_message(f"Updating camera controllers for new active canvas ID: {new_active_canvas_id}", Qgis.Info)
        if new_active_canvas_id is not None:
            for device_id in self.active_devices:
                if device_id not in self.camera_controllers:
                    self.camera_controllers[device_id] = {}
                
                if new_active_canvas_id not in self.camera_controllers[device_id]:
                    canvas = self.canvases_3d.get(new_active_canvas_id)
                    if canvas:
                        self.camera_controllers[device_id][new_active_canvas_id] = CameraController(
                            canvas_3d=canvas,
                            settings={
                                'move_factor': self.settings['move_factor'],
                                'rotation_factor': self.settings['rotation_factor'],
                                'zoom_factor': self.settings['zoom_factor']
                            },
                            thresholds=self.THRESHOLDS
                        )
                        self._log_message(f"Camera controller initialized for device {device_id}, canvas {new_active_canvas_id}", Qgis.Info)
                else:
                    self._log_message(f"Camera controller already exists for device {device_id}, canvas {new_active_canvas_id}", Qgis.Info)

    def _check_for_new_3d_views(self):
        """Vérifie la présence de vues 3D dans la fenêtre principale."""
        if hasattr(self, 'is_checking') and self.is_checking:
            return
            
        try:
            self.is_checking = True
            
            # Ajout d'un délai pour s'assurer que les canvases 3D sont bien initialisés
            QTimer.singleShot(1000, self._perform_canvas_check)
            
        except Exception as e:
            self._log_message(f"Erreur lors de la vérification des vues 3D: {str(e)}", Qgis.Critical)
            import traceback
            self._log_message(f"Traceback: {traceback.format_exc()}", Qgis.Critical)
        finally:
            self.is_checking = False

    def _perform_canvas_check(self):
        """Effectue la vérification des canvases 3D après un délai."""
        try:
            canvases = self.iface.mapCanvases3D() or self.iface.mainWindow().findChildren(Qgs3DMapCanvas)
            
            current_ids = {id(canvas) for canvas in canvases if not sip.isdeleted(canvas)}
            existing_ids = set(self.canvases_3d.keys())
            
            new_ids = current_ids - existing_ids
            removed_ids = existing_ids - current_ids
            
            for canvas_id in removed_ids:
                self.on_3d_canvas_closed(canvas_id)
            
            for canvas in canvases:
                canvas_id = id(canvas)
                if canvas_id in new_ids:
                    self.canvases_3d[canvas_id] = canvas
                    self._initialize_camera_controller(canvas, canvas_id)
                    
                    canvas.installEventFilter(self)
                    canvas.destroyed.connect(lambda obj=None, cid=canvas_id: self.on_3d_canvas_closed(cid))
                    
                    if self.active_canvas_id is None:
                        self._update_active_canvas(canvas_id)
                        if self.settings.get('auto_start', True):
                            QTimer.singleShot(100, self.start_spacemouse)
                    
                    self._log_message(f"Nouveau canvas 3D détecté (ID: {canvas_id})", Qgis.Info)
            
            if not self.canvases_3d and self.is_operational:
                self._log_message("Aucun canvas 3D disponible, arrêt du SpaceMouse", Qgis.Info)
                self.stop_spacemouse()
            
            self.check_active_canvas()
            
        except Exception as e:
            self._log_message(f"Erreur lors de la vérification des vues 3D: {str(e)}", Qgis.Critical)
            import traceback
            self._log_message(f"Traceback: {traceback.format_exc()}", Qgis.Critical)
        
            
    def check_active_canvas(self):
        """Vérifie la vue 3D active et les couches visibles."""
        active_canvas = None
        for canvas_id, canvas in self.canvases_3d.items():
            if canvas.isActive():  # Vérifier si la vue est active
                active_canvas = canvas
                self._update_active_canvas(canvas_id)
                break
        
        # Vérifier si le projet a des couches visibles
        layers = QgsProject.instance().layerTreeRoot().children()
        visible_layers = [layer for layer in layers if layer.isVisible()]

        if active_canvas and visible_layers:
            self._log_message(f"La vue 3D active est : ID {id(active_canvas)} avec {len(visible_layers)} couches visibles.", Qgis.Info)
            
            # Si le SpaceMouse n'est pas opérationnel, le démarrer
            if not self.is_operational:
                QTimer.singleShot(50, self.start_spacemouse)
        else:
            if not active_canvas:
                self._log_message("Aucune vue 3D active détectée.", Qgis.Info)
            if not visible_layers:
                self._log_message("Aucune couche visible dans le projet.", Qgis.Info)
            
            # Si le SpaceMouse est opérationnel mais qu'il n'y a pas de vue 3D active ou de couches visibles, l'arrêter
            if self.is_operational:
                QTimer.singleShot(50, self.stop_spacemouse)

        # Mettre à jour l'état des actions
        QTimer.singleShot(50, lambda: self._update_action_states(start_enabled=not self.is_operational))  
                                
    def on_3d_canvas_closed(self, canvas_id: Optional[int] = None) -> None:
        """Handle 3D canvas closure."""
        try:
            if canvas_id is None and self.canvas_3d is not None:
                # Legacy case - use the current canvas_3d
                canvas_id = id(self.canvas_3d)
                
            if canvas_id is not None:
                # Remove this canvas from our tracking
                if canvas_id in self.canvases_3d:
                    del self.canvases_3d[canvas_id]
                    
                # Clean up camera controllers for this canvas
                for device_id in list(self.camera_controllers.keys()):
                    if canvas_id in self.camera_controllers[device_id]:
                        controller = self.camera_controllers[device_id][canvas_id]
                        if hasattr(controller, 'cleanup'):
                            controller.cleanup()
                        del self.camera_controllers[device_id][canvas_id]
                
                self._log_message(f"3D canvas {canvas_id} closed and resources cleaned up", Qgis.Info)
                
            # If no more canvases, clean up everything
            if not self.canvases_3d:
                self._cleanup_spacemouse_threads()
                self.canvas_3d = None
                self.active_canvas_id = None
                self._update_action_states(start_enabled=True)
                
                # Reset warning flag so we get notified when waiting for a new 3D view
                self.warning_shown = False
                
                # Restart the check timer to look for new 3D views
                if hasattr(self, 'check_timer') and not self.check_timer.isActive():
                    self.check_timer.start(1000)
                    self._log_message("Restarted 3D view detection", Qgis.Info)
            else:
                # Set another canvas as active if available
                if self.canvases_3d:
                    next_id = next(iter(self.canvases_3d))
                    self.active_canvas_id = next_id
                    self.canvas_3d = self.canvases_3d[next_id]
                    self._log_message(f"Switched active 3D canvas to {next_id}", Qgis.Info)
                    
        except Exception as e:
            self._log_message(f"Error in on_3d_canvas_closed: {str(e)}", Qgis.Critical)

    # Cleanup Methods
    def unload(self) -> None:
        """Cleanup plugin resources properly across all platforms."""
        try:
            if hasattr(self, 'check_timer'):
                self.check_timer.stop()
                self.check_timer.deleteLater()

            self._cleanup_settings_dock()
            self._cleanup_menu_items()
            self._cleanup_spacemouse_threads()
            self._cleanup_references()

            # Only restart the service on Windows
            if self.platform == 'windows':
                start_message = self.process_manager.start()
                self._log_message(start_message)
            elif self.platform == 'macos' or self.platform == 'linux':
                # On macOS and Linux, we don't need to restart the service
                # as it's typically managed by the system
                self._log_message(f"No need to restart service on {self.platform}", Qgis.Info)

            # Remove event filter
            try:
                self.iface.mainWindow().removeEventFilter(self)
            except Exception as e:
                self._log_message(f"Error removing event filter: {str(e)}", Qgis.Warning)

            self._log_message(f"SpaceMouse plugin unloaded successfully on {self.platform}.", Qgis.Info)
        except Exception as e:
            self._log_message(f"Error during plugin unload: {str(e)}", Qgis.Critical)

    def _cleanup_settings_dock(self) -> None:
        """Cleanup settings dock."""
        if self.settings_dock:
            try:
                try:
                    self.settings_dock.applied.disconnect(self._on_settings_applied)
                except (TypeError, RuntimeError):
                    # Signal was not connected or already disconnected
                    pass

                self.iface.removeDockWidget(self.settings_dock)
                self.settings_dock.deleteLater()
                self.settings_dock = None
            except Exception as e:
                self._log_message(f"Error cleaning up settings dock: {str(e)}", Qgis.Warning)

    def _cleanup_menu_items(self) -> None:
        """Remove menu items."""
        try:
            actions_to_remove = [self.dock_action] + list(self._actions.values())
            for action in actions_to_remove:
                if action is not None:
                    try:
                        self.iface.removePluginMenu(Config.MENU_NAME, action)
                        action.deleteLater()
                    except Exception as e:
                        self._log_message(f"Error removing menu item: {str(e)}", Qgis.Warning)
            self._actions.clear()
        except Exception as e:
            self._log_message(f"Error cleaning up menu items: {str(e)}", Qgis.Warning)

    def _cleanup_references(self) -> None:
        """Clear object references."""
        try:
            # Clear canvas reference
            if self.canvas_3d is not None:
                try:
                    self.canvas_3d.destroyed.disconnect(self.on_3d_canvas_closed)
                except (TypeError, RuntimeError):
                    # Signal was not connected or already disconnected
                    pass
            self.canvas_3d = None

            # Clear camera controllers
            for device_id, controllers in self.camera_controllers.items():
                for controller in controllers.values():
                    if hasattr(controller, 'cleanup'):
                        controller.cleanup()
            self.camera_controllers.clear()
            
            # Clear default camera controller
            if hasattr(self, 'camera_controller') and self.camera_controller:
                if hasattr(self.camera_controller, 'cleanup'):
                    self.camera_controller.cleanup()
                self.camera_controller = None

            # Clear Kalman filter
            if self.kalman_filter is not None:
                if hasattr(self.kalman_filter, 'cleanup'):
                    self.kalman_filter.cleanup()
                self.kalman_filter = None

            # Clear device states
            self.device_states.clear()

            self._log_message("References cleaned up", Qgis.Info)
        except Exception as e:
            self._log_message(f"Error cleaning up references: {str(e)}", Qgis.Warning)

    # Utility Methods
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
            self._log_message(f"Unknown platform: {sys.platform}, defaulting to linux", Qgis.Warning)
            return 'linux'

    def _get_platform_executable_path(self) -> str:
        """
        Get the platform-specific path to the 3DConnexion service executable.

        Returns:
            Path to the executable for the current platform
        """
        if self.platform == 'windows':
            return r"C:\Program Files\3Dconnexion\3DxWare\3DxWinCore\3DxService.exe"
        elif self.platform == 'macos':
            return "/Library/Application Support/3Dconnexion/3DxWareMac/3DxWareMac.app/Contents/MacOS/3DxWareMac"
        elif self.platform == 'linux':
            # Common paths for Linux, will try to find the actual path
            possible_paths = [
                "/usr/bin/3dxsrv",
                "/usr/local/bin/3dxsrv",
                "/opt/3dconnexion/3dxsrv"
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    return path
            return ""  # Return empty string if not found
        return 

    def _log_message(self, message: str, level: Qgis.MessageLevel = Qgis.Info) -> None:
        """
        Thread-safe logging with level control.

        Args:
            message: Message to log.
            level: Message level (Info, Warning, Critical).
        """
        if level >= Config.LOG_LEVEL:
            QgsMessageLog.logMessage(
                message,
                Config.PLUGIN_NAME,
                level=level
            )

    def _update_action_states(self, start_enabled: bool) -> None:
        """
        Update start/stop action states.

        Args:
            start_enabled: Whether the start action should be enabled.
        """
        try:
            if 'start' in self._actions and 'stop' in self._actions:
                self._actions['start'].setEnabled(start_enabled)
                self._actions['stop'].setEnabled(not start_enabled)
            else:
                self._log_message("Start or stop action not found in self._actions", Qgis.Warning)
        except Exception as e:
            self._log_message(f"Error updating action states: {str(e)}", Qgis.Warning)
            
    # SpaceMouse Control Methods
    def start_spacemouse(self) -> None:
        """Start SpaceMouse operation."""
        self._log_message("Attempting to start SpaceMouse...", Qgis.Info)

        # Vérifier si des vues 3D sont disponibles
        if not self.canvases_3d:
            # Forcer une vérification immédiate
            self._check_for_new_3d_views()
            
            if not self.canvases_3d:
                self._log_message("❌ No 3D View available.", Qgis.Critical)
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "SpaceMouse Error",
                    "No 3D view is open. Please open a 3D view first."
                )
                return

        try:
            # Vérifier si des périphériques sont configurés
            from .SMNewDevice import load_devices_from_config
            devices_config = load_devices_from_config()
            
            if not devices_config:
                self._log_message("❌ No SpaceMouse devices configured.", Qgis.Warning)
                
                # Demander à l'utilisateur s'il souhaite configurer un périphérique
                reply = QMessageBox.question(
                    self.iface.mainWindow(),
                    "SpaceMouse Configuration",
                    "No SpaceMouse devices are configured. Would you like to configure a device now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    # Afficher la boîte de dialogue de gestion des périphériques
                    self._show_manage_devices_dialog()
                    
                    # Vérifier à nouveau si des périphériques sont configurés
                    devices_config = load_devices_from_config()
                    if not devices_config:
                        # L'utilisateur n'a pas configuré de périphérique
                        self._update_action_states(start_enabled=True)
                        self.is_operational = False
                        return
                else:
                    # L'utilisateur ne souhaite pas configurer de périphérique
                    self._update_action_states(start_enabled=True)
                    self.is_operational = False
                    return
            
            # Tenter d'initialiser les périphériques
            if self._initialize_spacemouse_devices():
                QTimer.singleShot(10, lambda: self._update_action_states(start_enabled=False))
                self.is_operational = True
                self._log_message("✅ SpaceMouse started successfully", Qgis.Info)
            else:
                self._update_action_states(start_enabled=True)
                self.is_operational = False
                self._log_message("❌ Failed to start SpaceMouse - no devices found", Qgis.Warning)
                
                # Proposer à l'utilisateur de configurer un nouveau périphérique
                reply = QMessageBox.question(
                    self.iface.mainWindow(),
                    "SpaceMouse Error",
                    "No SpaceMouse devices were found. Your device might not be supported by default.\n\n"
                    "Would you like to configure a new device?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    # Afficher la boîte de dialogue de gestion des périphériques
                    self._show_manage_devices_dialog()
                    
                    # Tenter de redémarrer après la configuration
                    QTimer.singleShot(500, self.restart_spacemouse)
        except Exception as e:
            self._log_message(f"Error starting SpaceMouse: {str(e)}", Qgis.Critical)
            self._update_action_states(start_enabled=True)
            self.is_operational = False

    def stop_spacemouse(self, device_id: Optional[str] = None) -> None:
        """Stop specific or all SpaceMouse devices."""
        if device_id:
            self._cleanup_device(device_id)
            self._log_message(f"✅ SpaceMouse {device_id} stopped.", Qgis.Info)
        else:
            self._cleanup_spacemouse_threads()
            self._update_action_states(start_enabled=True)
            self.is_operational = False
            self._log_message("✅ All SpaceMouse devices stopped.", Qgis.Info)

    def update_camera(self, device_id: str, x: float, y: float, z: float,
                      roll: float, pitch: float, yaw: float) -> None:
        """Handle camera updates from a specific device."""
        if not self.is_operational or self.active_canvas_id is None:
            return

        try:
            # Récupérer le canvas actif
            canvas = self.canvases_3d.get(self.active_canvas_id)
            if canvas is None or sip.isdeleted(canvas):
                return

            # Assurez-vous que le contrôleur de caméra est correctement récupéré
            if device_id not in self.camera_controllers:
                self.camera_controllers[device_id] = {}
            
            controller = self.camera_controllers[device_id].get(self.active_canvas_id)
            if controller is None:
                # Si le contrôleur n'existe pas, l'initialiser
                controller = CameraController(
                    canvas_3d=canvas,
                    settings={
                        'move_factor': self.settings['move_factor'],
                        'rotation_factor': self.settings['rotation_factor'],
                        'zoom_factor': self.settings['zoom_factor']
                    },
                    thresholds=self.THRESHOLDS
                )
                self.camera_controllers[device_id][self.active_canvas_id] = controller
            
            # Filtrer les valeurs d'entrée
            filtered_values = controller.process_input_values(x, y, z, roll, pitch, yaw)
            if filtered_values is None:
                return
            
            # Mettre à jour la caméra avec les valeurs filtrées
            controller.update_camera(filtered_values)

        except Exception as e:
            self._log_message(f"Error in update_camera: {str(e)}", Qgis.Critical)

    def _initialize_spacemouse_devices(self) -> bool:
        """Initialize all connected SpaceMouse devices."""
        try:
            # Vérifier si des périphériques sont configurés
            from .SMNewDevice import load_devices_from_config
            devices_config = load_devices_from_config()
            if not devices_config:
                self._log_message("No devices configured in devices.json", Qgis.Warning)
                return False
            
            # Scan for connected devices
            connected_devices = self._scan_for_devices()
            
            if not connected_devices:
                self._log_message("No SpaceMouse devices found", Qgis.Warning)
                return False

            # Le reste de votre code existant...
            for device_id, device_info in connected_devices.items():
                if device_id not in self.spacemouse_threads:
                    # Create new thread for device
                    thread = SpaceMouseThread(
                        device_id=device_id
                    )

                    # Connect signals
                    thread.data_received.connect(self.update_camera)
                    thread.error_occurred.connect(
                        lambda msg, d_id=device_id: self._handle_thread_error(msg, d_id)
                    )
                    thread.connection_changed.connect(
                        lambda connected, d_id=device_id: self._handle_connection_change(connected, d_id)
                    )

                    thread.button_pressed.connect(
                        lambda d_id, button_index: self._handle_button_press(d_id, button_index)
                    )

                    # Start the thread
                    thread.start()
                    self.spacemouse_threads[device_id] = thread
                    self.active_devices.add(device_id)
                    self._log_message(f"Started thread for device {device_id}: {device_info.get('name', 'Unknown')}", Qgis.Info)

            return bool(self.spacemouse_threads)

        except Exception as e:
            self._log_message(f"Error initializing devices: {str(e)}", Qgis.Critical)
            return False

    def _scan_for_devices(self) -> Dict[str, Dict[str, str]]:
        """
        Scan for connected SpaceMouse devices across all platforms.
        
        Returns:
            Dict mapping device IDs to device info dictionaries
        """
        connected_devices = {}
        try:
            # For simplicity, start with a default device
            # This will be used if no actual devices are found
            connected_devices = {
                'default': {'name': 'SpaceMouse', 'serial': '000000', 'platform': self.platform}
            }
            
            # Try to detect actual devices if possible
            try:
                # First try with easyhid which works on Windows and some Linux distributions
                self._log_message(f"Attempting to detect devices using easyhid on {self.platform}", Qgis.Info)

                
                enum = Enumeration()
                devices = enum.find(vid=0x046d)  # 3DConnexion vendor ID
                
                if devices:
                    # Clear the default device if we found real ones
                    connected_devices = {}
                    
                    for i, dev in enumerate(devices):
                        device_id = f"spacemouse_{i}"
                        connected_devices[device_id] = {
                            'name': f"SpaceMouse Device {i+1}",
                            'vendor_id': f'0x{dev.vendor_id:04x}',
                            'product_id': f'0x{dev.product_id:04x}',
                            'path': dev.path,
                            'platform': self.platform
 
                        }
                    self._log_message(f"Found {len(devices)} devices using easyhid", Qgis.Info)
                    
                # Platform-specific device detection
                if self.platform == 'linux':
                    self._scan_linux_devices(connected_devices)
                elif self.platform == 'macos':
                    self._scan_macos_devices(connected_devices)
                else:
                    self._log_message("Using default device configuration", Qgis.Info)
                    
            except ImportError:
                self._log_message("easyhid not available, trying platform-specific methods", Qgis.Info)
            except Exception as e:
                self._log_message(f"Error enumerating devices: {str(e)}", Qgis.Warning)
                
        except Exception as e:
            self._log_message(f"Error scanning for devices: {str(e)}", Qgis.Warning)
            
        return connected_devices
        
    def _scan_linux_devices(self, connected_devices):
        """
        Scan for SpaceMouse devices on Linux using system commands.

        Args:
            connected_devices: Dictionary to update with found devices
        """
        try:
            # Try using lsusb to find 3Dconnexion devices
            import subprocess

            # Run lsusb and grep for 3Dconnexion's vendor ID (046d)
            result = subprocess.run(
                ["lsusb | grep -i '046d'"],
                shell=True,
                capture_output=True,
                text=True
            )

            if result.returncode == 0 and result.stdout:
                # Clear default device if we found actual ones
                connected_devices.clear()

                lines = result.stdout.strip().split('\n')
                for i, line in enumerate(lines):
                    # Parse the lsusb output to extract device info
                    parts = line.split()
                    if len(parts) >= 6:
                        bus = parts[1]
                        device = parts[3].rstrip(':')
                        id_parts = parts[5].split(':')
                        if len(id_parts) == 2:
                            vendor_id, product_id = id_parts

                            device_id = f"spacemouse_linux_{i}"
                            connected_devices[device_id] = {
                                'name': f"SpaceMouse Device {i+1}",
                                'vendor_id': vendor_id,
                                'product_id': product_id,
                                'bus': bus,
                                'device': device,
                                'platform': 'linux'
                            }

                self._log_message(f"Found {len(connected_devices)} devices using lsusb", Qgis.Info)
            else:
                self._log_message("No 3Dconnexion devices found with lsusb", Qgis.Info)

        except Exception as e:
            self._log_message(f"Error scanning Linux devices: {str(e)}", Qgis.Warning)

    def _scan_macos_devices(self, connected_devices):
        """
        Scan for SpaceMouse devices on macOS using system commands.

        Args:
            connected_devices: Dictionary to update with found devices
        """
        try:
            # Try using system_profiler to find 3Dconnexion devices
            import subprocess

            # Run system_profiler to get USB device info
            result = subprocess.run(
                ["system_profiler SPUSBDataType | grep -A 20 '3Dconnexion' | grep -B 20 'Manufacturer: 3Dconnexion'"],
                shell=True,
                capture_output=True,
                text=True
            )

            if result.returncode == 0 and result.stdout:
                # Clear default device if we found actual ones
                connected_devices.clear()

                # Parse the output to extract device info
                # This is a simplified approach - in a real implementation,
                # you would parse the output more carefully
                sections = result.stdout.split('3Dconnexion')
                for i, section in enumerate(sections):
                    if 'Product ID' in section and 'Vendor ID' in section:
                        # Extract product and vendor IDs
                        product_id = None
                        vendor_id = None

                        for line in section.split('\n'):
                            if 'Product ID' in line:
                                product_id = line.split(':')[1].strip()
                            elif 'Vendor ID' in line:
                                vendor_id = line.split(':')[1].strip()

                        if product_id and vendor_id:
                            device_id = f"spacemouse_macos_{i}"
                            connected_devices[device_id] = {
                                'name': f"SpaceMouse Device {i+1}",
                                'vendor_id': vendor_id,
                                'product_id': product_id,
                                'platform': 'macos'
                            }

                self._log_message(f"Found {len(connected_devices)} devices using system_profiler", Qgis.Info)
            else:
                self._log_message("No 3Dconnexion devices found with system_profiler", Qgis.Info)

        except Exception as e:
            self._log_message(f"Error scanning macOS devices: {str(e)}", Qgis.Warning)

    def _handle_connection_change(self, connected: bool, device_id: str) -> None:
        """
        Handle connection state changes for a device.
        
        Args:
            connected: Whether the device is now connected
            device_id: Unique identifier for the device
        """
        if connected:
            self._log_message(f"Device {device_id} connected", Qgis.Info)
            self.active_devices.add(device_id)
        else:
            self._log_message(f"Device {device_id} disconnected", Qgis.Warning)
            self.active_devices.discard(device_id)
            
        # Update UI to reflect connection state
        self._update_action_states(start_enabled=not bool(self.active_devices))
        
    def _handle_button_press(self, device_id: str, button_index: int) -> None:
        """
        Handle button press events from SpaceMouse.
        Args:
            device_id: Unique identifier for the device
            button_index: Index of the button that was pressed
        """
        self._log_message(f"Button {button_index} pressed on device {device_id}", Qgis.Info)
        
        # Right button (usually index 1) resets to top view
        if button_index == 1:  # Right button
            self._reset_to_top_view()
        
        # Left button (usually index 0) sets isometric view
        elif button_index == 0:  # Left button
            self._set_isometric_view()

    def _reset_to_top_view(self) -> None:
        """Reset the camera to top view using both resetView and setViewFromTop."""
        if not self.active_canvas_id or self.active_canvas_id not in self.canvases_3d:
            self._log_message("No active 3D canvas to reset view", Qgis.Warning)
            return
            
        try:
            canvas = self.canvases_3d[self.active_canvas_id]
            navigation = canvas.cameraController()
            
            if navigation:
                # Étape 1: Déterminer une distance appropriée
                distance = 200.0  # Valeur par défaut
                center_x, center_y = 0.0, 0.0  # Valeurs par défaut pour le centre
                
                try:
                    # Essayer d'obtenir l'étendue de la scène
                    scene = canvas.scene()
                    if scene and hasattr(scene, 'extent'):
                        extent = scene.extent()
                        if extent and extent.isFinite():
                            # Calculer le centre de l'étendue
                            center = extent.center()
                            center_x = center.x()
                            center_y = center.y()
                            
                            # Calculer une distance appropriée
                            width = extent.width()
                            height = extent.height()
                            max_dimension = max(width, height)
                            distance = max_dimension * 0.6
                            
                            # Assurer une distance raisonnable
                            distance = max(10.0, min(distance, 1000.0))
                            
                            self._log_message(f"Using scene extent: center ({center_x}, {center_y}), distance {distance}", Qgis.Info)
                        else:
                            self._log_message("Scene extent is not valid, using default values", Qgis.Warning)
                    else:
                        self._log_message("Could not get scene extent, using default values", Qgis.Info)
                except Exception as e:
                    self._log_message(f"Error getting scene extent: {str(e)}, using default values", Qgis.Warning)
                
                # Étape 2: Utiliser resetView pour centrer la vue sur l'origine
                try:
                    self._log_message(f"Resetting view with distance: {distance}", Qgis.Info)
                    navigation.resetView(distance)
                except Exception as e:
                    self._log_message(f"Error in resetView: {str(e)}", Qgis.Warning)
                
                # Étape 3: Si nous avons un centre valide, utiliser setViewFromTop pour centrer sur ce point
                if center_x != 0.0 or center_y != 0.0:
                    try:
                        self._log_message(f"Setting view from top at center ({center_x}, {center_y}) with distance {distance}", Qgis.Info)
                        navigation.setViewFromTop(center_x, center_y, distance)
                    except Exception as e:
                        self._log_message(f"Error in setViewFromTop: {str(e)}", Qgis.Warning)
                
                # Étape 4: Vérifier et ajuster l'angle de tangage si nécessaire
                try:
                    camera_pose = navigation.cameraPose()
                    if camera_pose:
                        current_pitch = camera_pose.pitchAngle()
                        self._log_message(f"Current pitch angle: {current_pitch}", Qgis.Info)
                        
                        # Si l'angle de tangage n'est pas déjà proche de -90 degrés, l'ajuster
                        if abs(current_pitch + 90.0) > 1.0:  # Si plus de 1 degré de différence
                            camera_pose.setPitchAngle(-89.0)  # -89 au lieu de -90 pour éviter le gimbal lock
                            navigation.setCameraPose(camera_pose)
                            self._log_message("Adjusted pitch angle to -89 degrees", Qgis.Info)
                except Exception as e:
                    self._log_message(f"Error adjusting pitch angle: {str(e)}", Qgis.Warning)
                
                self._log_message("Camera reset to top view", Qgis.Info)
            else:
                self._log_message("Failed to get navigation controller", Qgis.Warning)
                
        except Exception as e:
            self._log_message(f"Error resetting to top view: {str(e)}", Qgis.Critical)

    def _set_isometric_view(self) -> None:
        """Set the camera to an isometric view (45° angle)."""
        if not self.active_canvas_id or self.active_canvas_id not in self.canvases_3d:
            self._log_message("No active 3D canvas to set isometric view", Qgis.Warning)
            return
            
        try:
            canvas = self.canvases_3d[self.active_canvas_id]
            navigation = canvas.cameraController()
            
            if navigation:
                # Étape 1: Déterminer une distance appropriée et le centre
                distance = 200.0  # Valeur par défaut
                center_x, center_y = 0.0, 0.0  # Valeurs par défaut pour le centre
                
                try:
                    # Essayer d'obtenir l'étendue de la scène
                    scene = canvas.scene()
                    if scene and hasattr(scene, 'extent'):
                        extent = scene.extent()
                        if extent and extent.isFinite():
                            # Calculer le centre de l'étendue
                            center = extent.center()
                            center_x = center.x()
                            center_y = center.y()
                            
                            # Calculer une distance appropriée
                            width = extent.width()
                            height = extent.height()
                            max_dimension = max(width, height)
                            distance = max_dimension * 0.8  # Légèrement plus grande pour la vue isométrique
                            
                            # Assurer une distance raisonnable
                            distance = max(10.0, min(distance, 1000.0))
                            
                            self._log_message(f"Using scene extent for isometric view: center ({center_x}, {center_y}), distance {distance}", Qgis.Info)
                        else:
                            self._log_message("Scene extent is not valid, using default values", Qgis.Warning)
                    else:
                        self._log_message("Could not get scene extent, using default values", Qgis.Info)
                except Exception as e:
                    self._log_message(f"Error getting scene extent: {str(e)}, using default values", Qgis.Warning)
                
                # Étape 2: Utiliser resetView pour centrer la vue sur l'origine
                try:
                    self._log_message(f"Resetting view with distance: {distance}", Qgis.Info)
                    navigation.resetView(distance)
                except Exception as e:
                    self._log_message(f"Error in resetView: {str(e)}", Qgis.Warning)
                
                # Étape 3: Si nous avons un centre valide, ajuster la position
                if center_x != 0.0 or center_y != 0.0:
                    try:
                        # Pour la vue isométrique, nous ne pouvons pas utiliser setViewFromTop
                        # Nous devons ajuster la position manuellement
                        camera_pose = navigation.cameraPose()
                        if camera_pose:
                            # Définir le centre
                            camera_pose.setCenterPoint(QgsVector3D(center_x, center_y, 0))
                            navigation.setCameraPose(camera_pose)
                            self._log_message(f"Adjusted center to ({center_x}, {center_y})", Qgis.Info)
                    except Exception as e:
                        self._log_message(f"Error adjusting center: {str(e)}", Qgis.Warning)
                
                # Étape 4: Ajuster les angles pour la vue isométrique
                try:
                    camera_pose = navigation.cameraPose()
                    if camera_pose:
                        # Définir l'angle de tangage à 45 degrés (vue isométrique)
                        camera_pose.setPitchAngle(45.0)
                        
                        # Définir l'angle de lacet à 45 degrés
                        camera_pose.setHeadingAngle(45.0)
                        
                        # Appliquer la pose mise à jour
                        navigation.setCameraPose(camera_pose)
                        
                        self._log_message("Camera set to isometric view", Qgis.Info)
                    else:
                        self._log_message("Failed to get camera pose", Qgis.Warning)
                except Exception as e:
                    self._log_message(f"Error setting isometric angles: {str(e)}", Qgis.Warning)
                
            else:
                self._log_message("Failed to get navigation controller", Qgis.Warning)
                
        except Exception as e:
            self._log_message(f"Error setting isometric view: {str(e)}", Qgis.Critical)
        
    def _handle_thread_error(self, error_message: str, device_id: str) -> None:
        """
        Handle errors from a specific device thread.
        
        Args:
            error_message: Error message from the thread
            device_id: Unique identifier for the device
        """
        self._log_message(f"Thread error for device {device_id}: {error_message}", Qgis.Critical)
        self._cleanup_device(device_id)

    def _cleanup_device(self, device_id: str) -> None:
        """
        Clean up resources for a specific device.

        Args:
            device_id: Unique identifier for the device.
        """
        with QMutexLocker(self.thread_mutex):
            if device_id in self.spacemouse_threads:
                thread = self.spacemouse_threads[device_id]
                if thread.isRunning():
                    try:
                        thread.data_received.disconnect()
                        thread.error_occurred.disconnect()
                        thread.connection_changed.disconnect()
                    except (TypeError, RuntimeError):
                        # Signal was not connected or already disconnected
                        pass
                        
                    thread.stop()
                    # Convert THREAD_STOP_TIMEOUT to int before passing to wait()
                    timeout = int(self.THREAD_STOP_TIMEOUT)
                    if not thread.wait(timeout):
                        self._log_message(f"Thread stop timeout for device {device_id} - forcing termination", Qgis.Warning)
                        thread.terminate()
                        
                del self.spacemouse_threads[device_id]

            if device_id in self.camera_controllers:
                del self.camera_controllers[device_id]

            if device_id in self.device_states:
                del self.device_states[device_id]

            self.active_devices.discard(device_id)
            
            # Update UI if no devices are active
            if not self.active_devices:
                self._update_action_states(start_enabled=True)
                self.is_operational = False

    def _cleanup_spacemouse_threads(self) -> None:
        """Clean up all device threads."""
        for device_id in list(self.spacemouse_threads.keys()):
            self._cleanup_device(device_id)
        
        self.spacemouse_threads.clear()
        self.active_devices.clear()
        self.is_operational = False

    def _initialize_camera_controller(self, canvas: Qgs3DMapCanvas, canvas_id: Optional[int] = None) -> None:
        """Initialize the camera controller for the given 3D canvas."""
        try:
            if canvas_id is None:
                canvas_id = id(canvas)
                
            # Create a default camera controller
            controller = CameraController(
                canvas_3d=canvas,
                settings={
                    'move_factor': self.settings['move_factor'],
                    'rotation_factor': self.settings['rotation_factor'],
                    'zoom_factor': self.settings['zoom_factor']
                },
                thresholds=self.THRESHOLDS
            )
            
            # Initialize the nested dictionary structure if needed
            for device_id in self.active_devices:
                if device_id not in self.camera_controllers:
                    self.camera_controllers[device_id] = {}
                self.camera_controllers[device_id][canvas_id] = controller
            
            # Connect focus events directly to the canvas
            canvas.focusInEvent = lambda event: self._handle_focus_change(canvas_id)
            canvas.focusOutEvent = lambda event: self._handle_focus_change(None)  # Handle focus out if needed
            
            self._log_message(f"Camera controller initialized for canvas {canvas_id}", Qgis.Info)
        except Exception as e:
            self._log_message(f"Error initializing camera controller: {str(e)}", Qgis.Critical)

    def _handle_focus_change(self, canvas_id: int) -> None:
        """
        Handle focus change between 3D views.
        
        Args:
            canvas_id: ID of the canvas that received focus
        """
        if canvas_id in self.canvases_3d:
            self.active_canvas_id = canvas_id
            self.canvas_3d = self.canvases_3d[canvas_id]
            self._log_message(f"Switched active 3D canvas to {canvas_id}", Qgis.Info)
            
            # Update camera controllers for all devices
            for device_id in self.active_devices:
                if device_id not in self.camera_controllers:
                    self.camera_controllers[device_id] = {}
                
                # If the controller does not exist for the active canvas, initialize it
                if canvas_id not in self.camera_controllers[device_id]:
                    self._log_message(f"Initializing camera controller for device {device_id}, canvas {canvas_id}", Qgis.Info)
                    self.camera_controllers[device_id][canvas_id] = CameraController(
                        canvas_3d=self.canvas_3d,
                        settings={
                            'move_factor': self.settings['move_factor'],
                            'rotation_factor': self.settings['rotation_factor'],
                            'zoom_factor': self.settings['zoom_factor']
                        },
                        thresholds=self.THRESHOLDS
                    )
                else:
                    self._log_message(f"Camera controller already exists for device {device_id}, canvas {canvas_id}", Qgis.Info)
            
            # Update action states
            self._update_action_states(start_enabled=True)
