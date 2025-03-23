#♦ SMSettings.py

from PyQt5.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                            QPushButton, QFormLayout, QGroupBox, QDoubleSpinBox,
                            QMessageBox, QFileDialog, QComboBox,QLabel)
from PyQt5.QtCore import Qt, QSettings, pyqtSignal  
from dataclasses import dataclass, field
from qgis.core import QgsMessageLog, Qgis
from typing import Dict, Tuple, List
import json
import os

def get_labels() -> Dict[str, str]:
    return {
        # Movement factors
        "move_factor": "Movement Factor",
        "rotation_factor": "Rotation Factor",
        "zoom_factor": "Zoom Factor",
        
        # Thresholds
        "threshold_xy": "XY Movement Threshold",
        "threshold_rotation": "Rotation Threshold",
        "threshold_z": "Zoom Threshold",
        
        # Kalman filter
        "kalman_R": "Kalman Threshold (R)",
        "kalman_Q": "Kalman Noise (Q)",
        
        # Interpolation
        "lerp_factor": "Interpolation Factor", 
        
        # Thread settings labels (conservés pour référence mais non utilisés dans l'interface)
        "update_interval": "Update Interval (seconds)",
        "sleep_time": "Sleep Time (seconds)",
        "state_change_threshold": "State Change Threshold",
        "reconnect_delay": "Reconnect Delay (seconds)",
        "thread_stop_timeout": "Thread Stop Timeout (ms)"
    }

def get_groups() -> Dict[str, List[str]]:
    return {
        "Movement Factors": ["move_factor", "rotation_factor", "zoom_factor", "lerp_factor"], 
        "Movement Thresholds": ["threshold_xy", "threshold_rotation", "threshold_z"],
        "Kalman Filter": ["kalman_R", "kalman_Q"]
    }

def get_defaults() -> Dict[str, Tuple[float, float, float, float]]:
    return {
        # Movement factors - Adjusted max values
        "move_factor": (0.5, 0.1, 10.0, 0.1),
        "rotation_factor": (0.8, 0.1, 5.0, 0.1),
        "zoom_factor": (0.8, 0.1, 5.0, 0.1),

        # Thresholds - Unchanged
        "threshold_xy": (0.15, 0.005, 0.4, 0.005),
        "threshold_rotation": (0.15, 0.005, 0.4, 0.005),
        "threshold_z": (0.12, 0.005, 0.4, 0.005),

        # Kalman filter - Unchanged
        "kalman_R": (0.3, 0.001, 0.4, 0.001),
        "kalman_Q": (0.0005, 0.00001, 0.01, 0.00001),

        # Interpolation - Unchanged
        "lerp_factor": (0.5, 0.1, 0.9, 0.1),
        
       
        # Thread settings
        "update_interval": (0.016, 0.001, 0.1, 0.001),
        "sleep_time": (0.001, 0.0001, 0.01, 0.0001),
        "state_change_threshold": (0.0001, 0.00001, 0.001, 0.00001),
        "reconnect_delay": (1.0, 0.1, 5.0, 0.1),
        "thread_stop_timeout": (1000, 100, 5000, 100)
    }
    
def get_presets() -> Dict[str, Dict[str, float]]:
    return {
        "Precise": {
            # Facteurs de mouvement - Légèrement réduits pour moins de sensibilité
            "move_factor": 0.4,  
            "rotation_factor": 0.7,  
            "zoom_factor": 0.7,  
            
            # Seuils - Légèrement augmentés pour filtrer les petits mouvements involontaires
            "threshold_xy": 0.1,  
            "threshold_rotation": 0.1,  
            "threshold_z": 0.1,  
            
            # Kalman - Plus de lissage pour des mouvements précis
            "kalman_R": 0.1,  
            "kalman_Q": 0.0008,  
                  
            # Interpolation - Plus faible pour plus de précision
            "lerp_factor": 0.2,
        },
        "Standard": {
            # Facteurs de mouvement - Équilibrés
            "move_factor": 0.5,
            "rotation_factor": 1.0,
            "zoom_factor": 1.0,
            
            # Seuils - Équilibrés
            "threshold_xy": 0.2,  
            "threshold_rotation": 0.2,  
            "threshold_z": 0.2,  
            
            # Kalman - Équilibré
            "kalman_R": 0.06,  
            "kalman_Q": 0.0015,  
            
            # Interpolation - Plus faible pour plus de précision
            "lerp_factor": 0.9,
        },
        "Dynamic": {  # Remplace "Smooth"
            # Facteurs de mouvement - Plus grands pour des mouvements rapides
            "move_factor": 1.5,
            "rotation_factor": 2.5,
            "zoom_factor": 2.5,
            
            # Seuils - Plus bas pour une réactivité accrue
            "threshold_xy": 0.04,  
            "threshold_rotation": 0.04,  
            "threshold_z": 0.03, 
            
            # Kalman - Minimal pour une réactivité maximale
            "kalman_R": 0.04,  
            "kalman_Q": 0.002,  
            # Interpolation - Plus faible pour plus de précision
            "lerp_factor": 0.4,
        }
    }

@dataclass(frozen=True)
class SettingsConfig:
    """Configuration for settings with default values"""
    # Class constants
    PLUGIN_NAME: str = "SpaceMousePlugin"
    MENU_NAME: str = "SpaceMouse"
    SETTINGS_NAMESPACE: str = "QGIS"
    SETTINGS_GROUP: str = "QGIS/SpaceMousePlugin"
    SETTINGS_VERSION: str = "1.0"
    
    # Constants
    BUFFER_SIZE: int = 6
    STATE_KEYS: Tuple[str, ...] = ('x', 'y', 'z', 'roll', 'pitch', 'yaw')
    
    # Settings configuration
    DEFAULTS = get_defaults()
    LABELS = get_labels()
    GROUPS = get_groups()

    @classmethod
    def get_default_value(cls, setting: str) -> float:
        """Get default value for a setting"""
        return cls.DEFAULTS[setting][0]

    @classmethod
    def get_setting_range(cls, setting: str) -> Tuple[float, float]:
        """Get min/max range for a setting"""
        _, min_val, max_val, _ = cls.DEFAULTS[setting]
        return min_val, max_val

    @classmethod
    def get_setting_step(cls, setting: str) -> float:
        """Get step value for a setting"""
        return cls.DEFAULTS[setting][3]

    @classmethod
    def get_default_thresholds(cls) -> Dict[str, float]:
        """Get default thresholds for movement processing"""
        return {
            'xy': cls.DEFAULTS["threshold_xy"][0],
            'z': cls.DEFAULTS["threshold_z"][0],
            'rotation': cls.DEFAULTS["threshold_rotation"][0]
        }

    @classmethod
    def validate_setting(cls, setting: str, value: float) -> float:
        """Validate and adjust a setting value to be within bounds"""
        default_value, min_val, max_val, step = cls.DEFAULTS[setting]
        value = max(min_val, min(max_val, value))
        if step > 0:
            value = round(value / step) * step
        return value
    
# Create a single instance to be used throughout the application
settings_config = SettingsConfig()

class SettingsDock(QDockWidget):
    """Dock widget for SpaceMouse settings with real-time adjustment capability"""
    
    # Define the signal
    applied = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__("SpaceMouse Settings", parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetFloatable | 
                        QDockWidget.DockWidgetMovable | 
                        QDockWidget.DockWidgetClosable)
        
        # Initialize main widget and storage
        self.settings_widget = QWidget()
        self.setWidget(self.settings_widget)
        
        self._spinboxes: Dict[str, QDoubleSpinBox] = {}
        self._init_ui()
        self._load_settings()
        
        # Set minimum size
        self.setMinimumWidth(300)
        self.setMinimumHeight(400)
        
        self.device_selector = QComboBox()
        self.refresh_devices_button = QPushButton("Refresh Devices")
        self.refresh_devices_button.clicked.connect(self._refresh_devices)

    def show_settings(self):
        """Show the settings dock and bring it to front"""
        self.show()
        self.raise_()
        self.activateWindow()

    def _init_ui(self) -> None:
        """Initialize UI with grouped settings and controls"""
        main_layout = QVBoxLayout(self.settings_widget)

        # Preset selector
        preset_box = QGroupBox("Presets")
        preset_layout = QHBoxLayout()
        
        preset_label = QLabel("Select preset:")
        self.preset_selector = QComboBox()
        for preset_name in get_presets().keys():
            self.preset_selector.addItem(preset_name)
        
        # Bouton pour charger le préréglage sans l'appliquer
        load_preset_button = QPushButton("Load Preset")
        load_preset_button.clicked.connect(self._load_selected_preset)
        
        preset_layout.addWidget(preset_label)
        preset_layout.addWidget(self.preset_selector)
        preset_layout.addWidget(load_preset_button)
        preset_box.setLayout(preset_layout)
        main_layout.addWidget(preset_box)
        
        # File operation buttons
        self._create_file_buttons(main_layout)
        
        # Settings groups
        self._create_settings_groups(main_layout)
        
        # Control buttons
        self._create_control_buttons(main_layout)
        
        # Push everything to top
        main_layout.addStretch()
        
    # Push everything to top
    def _refresh_devices(self):
        """Refresh the list of connected devices"""
        self.device_selector.clear()
        connected_devices = self._scan_for_devices()
        for device_id, device_info in connected_devices.items():
            self.device_selector.addItem(
                f"{device_info['name']} ({device_id})", 
                device_id
            )
            
    def _scan_for_devices(self) -> Dict[str, Dict[str, str]]:
        """
        Scan for connected SpaceMouse devices.
        
        Returns:
            Dict[str, Dict[str, str]]: Dictionary of device information
        """
        # This is a placeholder - in a real implementation, you would
        # scan for actual devices using your device detection logic
        try:
            # Return an empty dict if no implementation is available
            return {}
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error scanning for devices: {str(e)}", 
                SettingsConfig.PLUGIN_NAME, 
                Qgis.Critical
            )
            return {}

    def _create_file_buttons(self, parent_layout: QVBoxLayout) -> None:
        """Create and add file operation buttons"""
        button_layout = QHBoxLayout()
        
        self.save_button = QPushButton("Save Settings to File...", self)
        self.save_button.clicked.connect(self._save_settings_to_file)
        button_layout.addWidget(self.save_button)
        
        self.load_button = QPushButton("Load Settings from File...", self)
        self.load_button.clicked.connect(self._load_settings_from_file)
        button_layout.addWidget(self.load_button)
        
        parent_layout.addLayout(button_layout)

    def _create_settings_groups(self, parent_layout: QVBoxLayout) -> None:
        """Create and add settings groups"""
        for group_name, settings in SettingsConfig.GROUPS.items():
            group_box = QGroupBox(group_name)
            group_layout = QFormLayout()
            
            for setting in settings:
                default, min_val, max_val, step = SettingsConfig.DEFAULTS[setting]
                spinbox = self._create_spinbox(min_val, max_val, step)
                self._spinboxes[setting] = spinbox
                group_layout.addRow(SettingsConfig.LABELS[setting], spinbox)
            
            group_box.setLayout(group_layout)
            parent_layout.addWidget(group_box)

    def _create_control_buttons(self, parent_layout: QVBoxLayout) -> None:
        """Create and add control buttons"""
        button_layout = QHBoxLayout()
        
        self.reset_button = QPushButton("Reset to Defaults", self)
        self.reset_button.clicked.connect(self._reset_to_defaults)
        button_layout.addWidget(self.reset_button)
        
        self.apply_button = QPushButton("Apply", self)
        self.apply_button.clicked.connect(self._apply_settings)
        button_layout.addWidget(self.apply_button)
        
        parent_layout.addLayout(button_layout)

    def _create_spinbox(self, min_val: float, max_val: float, step: float) -> QDoubleSpinBox:
        """Create a configured spinbox with given parameters"""
        spinbox = QDoubleSpinBox(self)
        spinbox.setRange(min_val, max_val)
        spinbox.setSingleStep(step)
        spinbox.setDecimals(len(str(step).split('.')[-1]))
        spinbox.setKeyboardTracking(False)
        return spinbox
    
    def update_values(self, settings: Dict[str, float]) -> None:
        """
        Update the UI with current settings values.
        
        Args:
            settings: Dictionary of setting values
        """
        try:
            for key, value in settings.items():
                if key in self._spinboxes:
                    # Validate value before setting
                    validated_value = SettingsConfig.validate_setting(key, float(value))
                    self._spinboxes[key].setValue(validated_value)
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error updating settings values: {str(e)}", 
                SettingsConfig.PLUGIN_NAME, 
                Qgis.Critical
            )

    def _apply_settings(self) -> None:
        """Save settings when Apply is clicked"""
        print("Starting _apply_settings")  # Debug
        if not self._validate_settings():
            print("Validation failed")  # Debug
            return

        settings = QSettings()
        settings.beginGroup(SettingsConfig.SETTINGS_GROUP)
        
        try:
            current_settings = {}
            for key, spinbox in self._spinboxes.items():
                print(f"Processing key: {key}")  # Debug
                value = spinbox.value()
                print(f"Value from spinbox: {value}")  # Debug
                print(f"Default tuple for {key}: {SettingsConfig.DEFAULTS[key]}")  # Debug
                validated_value = SettingsConfig.validate_setting(key, value)
                print(f"Validated value: {validated_value}")  # Debug
                settings.setValue(key, validated_value)
                current_settings[key] = validated_value
            
            print(f"Final settings: {current_settings}")  # Debug
            self.applied.emit(current_settings)
        except Exception as e:
            import traceback  # Add this import at the top
            error_trace = traceback.format_exc()  # Get full traceback
            QgsMessageLog.logMessage(
                f"Error applying settings:\n{error_trace}", 
                SettingsConfig.PLUGIN_NAME, 
                Qgis.Critical
            )
        finally:
            settings.endGroup()
            
    def _validate_settings(self) -> bool:
        """Validate all settings before saving"""
        for key, spinbox in self._spinboxes.items():
            default_value, min_val, max_val, step = SettingsConfig.DEFAULTS[key]
            if not min_val <= spinbox.value() <= max_val:
                QMessageBox.warning(
                    self,
                    "Invalid Setting",
                    f"Value for {SettingsConfig.LABELS[key]} must be between {min_val} and {max_val}"
                )
                return False
        return True

    def _load_settings(self) -> None:
        """Load settings from QSettings"""
        settings = QSettings()
        settings.beginGroup(SettingsConfig.SETTINGS_GROUP)
        
        try:
            for key in self._spinboxes.keys():
                default = SettingsConfig.DEFAULTS[key][0]  # Get just the default value
                value = settings.value(key, default, type=float)
                # Validate and set the value
                validated_value = SettingsConfig.validate_setting(key, value)
                self._spinboxes[key].setValue(validated_value)
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error loading settings: {str(e)}", 
                SettingsConfig.PLUGIN_NAME, 
                Qgis.Critical
            )
        finally:
            settings.endGroup()
            
    def _reset_to_defaults(self) -> None:
        """Reset all settings to default values"""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to their default values?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            for key, (default, *_) in SettingsConfig.DEFAULTS.items():
                self._spinboxes[key].setValue(default)
            # Apply the default settings
            self._apply_settings()

    def _save_settings_to_file(self) -> None:
        """Save current settings to a JSON file"""
        try:
            file_name, _ = QFileDialog.getSaveFileName(
                self,
                "Save Settings",
                os.path.expanduser("~"),
                "Settings Files (*.json);;All Files (*.*)"
            )
            
            if not file_name:
                return
                
            if not file_name.endswith('.json'):
                file_name += '.json'

            settings_dict = {
                'settings': {key: spinbox.value() for key, spinbox in self._spinboxes.items()},
                'version': SettingsConfig.SETTINGS_VERSION
            }
            
            with open(file_name, 'w') as f:
                json.dump(settings_dict, f, indent=4)
            
            QMessageBox.information(
                self,
                "Settings Saved",
                f"Settings successfully saved to:\n{file_name}"
            )
            
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error Saving Settings",
                f"Failed to save settings:\n{str(e)}"
            )

    def _load_settings_from_file(self) -> None:
        """Load settings from a JSON file"""
        try:
            file_name, _ = QFileDialog.getOpenFileName(
                self,
                "Load Settings",
                os.path.expanduser("~"),
                "Settings Files (*.json);;All Files (*.*)"
            )
            
            if not file_name:
                return

            with open(file_name, 'r') as f:
                settings_dict = json.load(f)

            if ('version' in settings_dict and 
                settings_dict['version'] == SettingsConfig.SETTINGS_VERSION):
                for key, value in settings_dict['settings'].items():
                    if key in self._spinboxes:
                        # Validate value before setting
                        validated_value = SettingsConfig.validate_setting(key, float(value))
                        self._spinboxes[key].setValue(validated_value)
                
                # Apply the loaded settings
                self._apply_settings()
                
                QMessageBox.information(
                    self,
                    "Settings Loaded",
                    f"Settings successfully loaded from:\n{file_name}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Invalid Settings File",
                    "The selected file is not a valid settings file."
                )
                
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error Loading Settings",
                f"Failed to load settings:\n{str(e)}"
            )
            
    def _load_selected_preset(self) -> None:
        """Load the selected preset values into the UI without applying them"""
        preset_name = self.preset_selector.currentText()
        presets = get_presets()
        if preset_name in presets:
            preset_values = presets[preset_name]
            for key, value in preset_values.items():
                if key in self._spinboxes:
                    self._spinboxes[key].setValue(value)
            
            # Informer l'utilisateur
            QMessageBox.information(
                self,
                "Preset Loaded",
                f"The '{preset_name}' preset has been loaded.\nClick 'Apply' to save these settings."
            )
