from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import contextmanager
import json

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QFileDialog, QDoubleSpinBox
from qgis.core import QgsMessageLog, Qgis

from .SMSettings import SMSettings

class SettingsFileError(Exception):
    """Custom exception for settings file operations"""
    pass

class SettingsFileManager:
    """Handles settings file operations"""
    
    @staticmethod
    def get_save_path() -> Optional[Path]:
        """Get path for saving settings file"""
        try:
            file_name, _ = QFileDialog.getSaveFileName(
                None,
                "Save Settings",
                str(Path.home()),
                "Settings Files (*.json);;All Files (*.*)"
            )
            return Path(file_name).with_suffix('.json') if file_name else None
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error getting save path: {str(e)}", 
                "SpaceMouse", 
                Qgis.Warning
            )
            return None

    @staticmethod
    def get_load_path() -> Optional[Path]:
        """Get path for loading settings file"""
        try:
            file_name, _ = QFileDialog.getOpenFileName(
                None,
                "Load Settings",
                str(Path.home()),
                "Settings Files (*.json);;All Files (*.*)"
            )
            return Path(file_name) if file_name else None
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error getting load path: {str(e)}", 
                "SpaceMouse", 
                Qgis.Warning
            )
            return None

    @staticmethod
    def save_settings(file_path: Path, settings: Dict[str, Any]) -> None:
        """Save settings to JSON file"""
        try:
            with open(file_path, 'w') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            raise SettingsFileError(f"Failed to save settings: {str(e)}")

    @staticmethod
    def load_settings(file_path: Path) -> Dict[str, Any]:
        """Load settings from JSON file"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise SettingsFileError(f"Invalid JSON format: {str(e)}")
        except Exception as e:
            raise SettingsFileError(f"Failed to load settings: {str(e)}")

class SettingsManager:
    """Manages settings operations"""
    
    def __init__(self):
        """Initialize settings manager"""
        self.settings_group = SMSettings.SETTINGS_GROUP

    @contextmanager
    def settings_group_context(self):
        """Context manager for QSettings group operations"""
        settings = QSettings()
        settings.beginGroup(self.settings_group)
        try:
            yield settings
        finally:
            settings.endGroup()

    def load_settings(self, spinboxes: Dict[str, QDoubleSpinBox]) -> None:
        """Load settings from QSettings to spinboxes"""
        try:
            with self.settings_group_context() as settings:
                for key, (default, *_) in SMSettings.DEFAULTS.items():
                    if key in spinboxes:
                        value = settings.value(key, default, type=float)
                        if SMSettings.validate_setting_value(key, value):
                            spinboxes[key].setValue(value)
                        else:
                            spinboxes[key].setValue(default)
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error loading settings: {str(e)}", 
                "SpaceMouse", 
                Qgis.Warning
            )
            self._load_defaults(spinboxes)

    def save_settings(self, spinboxes: Dict[str, QDoubleSpinBox]) -> Dict[str, float]:
        """Save settings from spinboxes to QSettings"""
        current_settings = {}
        try:
            with self.settings_group_context() as settings:
                for key, spinbox in spinboxes.items():
                    value = spinbox.value()
                    if SMSettings.validate_setting_value(key, value):
                        settings.setValue(key, value)
                        current_settings[key] = value
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error saving settings: {str(e)}", 
                "SpaceMouse", 
                Qgis.Warning
            )
        return current_settings

    def _load_defaults(self, spinboxes: Dict[str, QDoubleSpinBox]) -> None:
        """Load default values into spinboxes"""
        for key, spinbox in spinboxes.items():
            default_value = SMSettings.get_default_value(key)
            spinbox.setValue(default_value)
