from dataclasses import dataclass
from typing import Optional, Dict
import numpy as np
from filterpy.kalman import KalmanFilter
from .SMConfig import Config

@dataclass(frozen=True)
class KalmanConfig:
    """Kalman filter configuration"""
    DIM_X: int = 2
    DIM_Z: int = 1
    INITIAL_P: float = 1000.0
    DEFAULT_R: float = 5.0
    DEFAULT_Q: float = 0.01

class KalmanFilters:
    """Kalman filter implementation for smoothing SpaceMouse input"""
    
    def __init__(self, settings: Dict[str, float]):
        """
        Initialize Kalman filter with settings
        Args:
            settings: Dictionary containing kalman_R and kalman_Q values
        """
        self.settings = settings
        self.filters: Dict[str, KalmanFilter] = {}
        self._initialize_filters()

    def _initialize_filters(self) -> None:
        """Initialize separate Kalman filters for each axis"""
        for axis in Config.STATE_KEYS:
            self.filters[axis] = self._create_kalman_filter()

    def _create_kalman_filter(self) -> KalmanFilter:
        """Create a new Kalman filter with current settings"""
        kf = KalmanFilter(dim_x=KalmanConfig.DIM_X, dim_z=KalmanConfig.DIM_Z)
        kf.x = np.zeros((KalmanConfig.DIM_X, 1))
        kf.F = np.array([[1., 1.], [0., 1.]])
        kf.H = np.array([[1., 0.]])
        kf.P *= KalmanConfig.INITIAL_P
        kf.R = np.array([[self.settings['kalman_R']]])
        kf.Q = np.array([[self.settings['kalman_Q'], 0.],
                        [0., self.settings['kalman_Q']]])
        return kf

    def update(self, measurements: Dict[str, float]) -> Dict[str, float]:
        """
        Update Kalman filters with new measurements
        Args:
            measurements: Dictionary of axis measurements
        Returns:
            Dictionary of filtered values
        """
        filtered_values = {}
        
        for axis, value in measurements.items():
            if axis in self.filters:
                # Update filter with measurement
                self.filters[axis].predict()
                self.filters[axis].update(value)
                
                # Get filtered value (first state variable)
                # Fixed deprecation warning by using item()
                filtered_values[axis] = float(self.filters[axis].x.item(0))
            else:
                filtered_values[axis] = value
                
        return filtered_values

    def update_settings(self, new_settings: Dict[str, float]) -> None:
        """
        Update Kalman filter settings and reinitialize filters
        Args:
            new_settings: New settings dictionary
        """
        self.settings = new_settings
        self._initialize_filters()

    def reset(self) -> None:
        """Reset all filters to initial state"""
        self._initialize_filters()
