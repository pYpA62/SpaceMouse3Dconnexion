from typing import Dict, Optional
from qgis.core import QgsMessageLog, Qgis
from PyQt5.QtCore import Qt
import numpy as np

class CameraController:
    """Controls camera movement and rotation in 3D view"""
    
    def __init__(self, canvas_3d, settings: Dict[str, float], thresholds: Dict[str, float]):
        """
        Initialize camera controller
        
        Args:
            canvas_3d: QGIS 3D canvas
            settings: Dictionary of movement settings
            thresholds: Dictionary of movement thresholds
        """
        self.canvas_3d = canvas_3d
        self.settings = settings
        self.thresholds = thresholds
        # Cache frequently used values
        self._move_factor = settings['move_factor']
        self._rotation_factor = settings['rotation_factor']
        self._zoom_factor = settings['zoom_factor']
        self._z_threshold = thresholds['z']
        self.navigation = self._get_navigation_widget()
        # Paramètres d'interpolation
        self._lerp_factor = settings.get('lerp_factor', 0.3)  # Facteur d'interpolation (0.0 à 1.0)
        self._current_values = {
            'x': 0.0,
            'y': 0.0,
            'z': 0.0,
            'pitch': 0.0,
            'yaw': 0.0
        }
        
    def _get_navigation_widget(self) -> Optional[object]:
        """Get navigation widget from canvas"""
        try:
            return self.canvas_3d.cameraController()
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error getting navigation widget: {str(e)}", 
                "SpaceMouse", 
                Qgis.Critical
            )
            return None
        
    def _lerp(self, start: float, end: float, alpha: float) -> float:
        """
        Interpolation linéaire entre deux valeurs.
        
        Args:
            start: Valeur de départ
            end: Valeur d'arrivée
            alpha: Facteur d'interpolation (0.0 à 1.0)
            
        Returns:
            Valeur interpolée
        """
        return start + alpha * (end - start)

    def update_camera(self, filtered_values: Dict[str, float]) -> None:
        """
        Update camera position and rotation using filtered values with interpolation
        
        Args:
            filtered_values: Dictionary containing filtered movement values
                        (x, y, z, roll, pitch, yaw)
        """
        if not self.navigation:
            self.navigation = self._get_navigation_widget()
            if not self.navigation:
                return

        try:
            # Interpoler les valeurs pour des mouvements plus fluides
            self._current_values['x'] = self._lerp(self._current_values['x'], filtered_values['x'], self._lerp_factor)
            self._current_values['y'] = self._lerp(self._current_values['y'], filtered_values['y'], self._lerp_factor)
            self._current_values['z'] = self._lerp(self._current_values['z'], filtered_values['z'], self._lerp_factor)
            self._current_values['pitch'] = self._lerp(self._current_values['pitch'], filtered_values['pitch'], self._lerp_factor)
            self._current_values['yaw'] = self._lerp(self._current_values['yaw'], filtered_values['yaw'], self._lerp_factor)
            
            # Move view (translation) with interpolated values
            self.navigation.moveView(
                -self._current_values['x'] * self._move_factor,
                -self._current_values['y'] * self._move_factor
            )

            # Update rotation using camera pose
            if camera_pose := self.navigation.cameraPose():
                # Update heading (yaw) with interpolated value
                camera_pose.setHeadingAngle(
                    camera_pose.headingAngle() + 
                    self._current_values['yaw'] * self._rotation_factor
                )
                # Apply updated pose immediately
                self.navigation.setCameraPose(camera_pose)
            
                # Get fresh camera pose
                camera_pose = self.navigation.cameraPose()
                
                # Get current pitch angle
                current_pitch = camera_pose.pitchAngle()
                
                # Calculate new pitch angle with interpolated value
                new_pitch = current_pitch + self._current_values['pitch'] * self._rotation_factor
                
                # Limit pitch to avoid gimbal lock (-89 to 89 degrees)
                new_pitch = max(-89.0, min(89.0, new_pitch))
                
                # Update pitch
                camera_pose.setPitchAngle(new_pitch)
                
                # Apply updated pose
                self.navigation.setCameraPose(camera_pose)

            # Handle zoom with interpolated value
            if abs(self._current_values['z']) > self._z_threshold:
                zoom_value = self._current_values['z'] * self._zoom_factor
                self.navigation.zoom(zoom_value)

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error updating camera: {str(e)}", 
                "SpaceMouse", 
                Qgis.Critical
            )
            
    def process_input_values(self, x: float, y: float, z: float,
                             roll: float, pitch: float, yaw: float) -> Optional[Dict[str, float]]:
        """
        Process and filter input values.

        Args:
            x: X-axis movement value.
            y: Y-axis movement value.
            z: Z-axis movement value.
            roll: Roll rotation value.
            pitch: Pitch rotation value.
            yaw: Yaw rotation value.

        Returns:
            Optional[Dict[str, float]]: Filtered values or None if all values are below the threshold.
        """
        try:
            # Validate input values
            if not all(isinstance(v, (int, float)) for v in [x, y, z, roll, pitch, yaw]):
                raise ValueError("Invalid input types")

            values = np.array([x, y, z, yaw, pitch, roll], dtype=np.float32)
            thresholds = self._get_threshold_array()

            # Check for NaN or infinite values
            if not np.all(np.isfinite(values)):
                QgsMessageLog.logMessage("Invalid input values detected", "SpaceMouse", Qgis.Warning)
                return None

            # Apply thresholds
            mask = np.abs(values) > thresholds
            values = np.where(mask, values, 0)

            if not np.any(values):
                return None

            input_values = {
                'x': float(values[0]),
                'y': float(values[1]),
                'z': float(values[2]),
                'yaw': float(values[3]),
                'pitch': float(values[4]),
                'roll': float(values[5])
            }

            return input_values

        except Exception as e:
            QgsMessageLog.logMessage(f"Error in input processing: {str(e)}", "SpaceMouse", Qgis.Critical)
            return None

    def _get_threshold_array(self) -> np.ndarray:
        """
        Get threshold array for all axes.

        Returns:
            np.ndarray: Array of thresholds for [x, y, z, yaw, pitch, roll].
        """
        return np.array([
            self.thresholds['xy'],
            self.thresholds['xy'],
            self.thresholds['z'],
            self.thresholds['rotation'],
            self.thresholds['rotation'],
            self.thresholds['rotation']
        ], dtype=np.float32)
        
    def update_settings(self, new_settings: Dict[str, float]) -> None:
        """
        Update controller settings
        
        Args:
            new_settings: Dictionary with new settings values
        """
        self.settings.update(new_settings)
        
        # Update cached values
        if 'move_factor' in new_settings:
            self._move_factor = new_settings['move_factor']
        if 'rotation_factor' in new_settings:
            self._rotation_factor = new_settings['rotation_factor']
        if 'zoom_factor' in new_settings:
            self._zoom_factor = new_settings['zoom_factor']
