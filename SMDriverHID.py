"""
# SMDriverHID.py - Module de pilote HID pour SpaceMouse
Compatible avec Windows, macOS et Linux
Basé sur le code de pyspacemouse
"""

from collections import namedtuple
import timeit
import logging
import sys
import time
import os
from typing import Callable, Union, List, Optional, Dict, Any, Tuple

# Importer les fonctions pour charger les périphériques
from .SMNewDevice import load_devices_from_config

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SMDriverHID")

# Version
__version__ = "1.0.0"

# Horloge pour le timing
high_acc_clock = timeit.default_timer

# Tuple pour les résultats 6DOF
SpaceNavigator = namedtuple(
    "SpaceNavigator", ["t", "x", "y", "z", "roll", "pitch", "yaw", "buttons"]
)

class ButtonState(list):
    """Classe représentant l'état des boutons"""
    def __int__(self):
        return sum((b << i) for (i, b) in enumerate(reversed(self)))

# Classes pour les callbacks
class ButtonCallback:
    """Register new button callback"""

    def __init__(
            self, buttons: Union[int, List[int]], callback: Callable[[int, int], None]
    ):
        self.buttons = buttons
        self.callback = callback


class DofCallback:
    """Register new DoF callback"""

    def __init__(
            self,
            axis: str,
            callback: Callable[[int], None],
            sleep: float = 0.0,
            callback_minus: Callable[[int], None] = None,
            filter: float = 0.0
    ):
        self.axis = axis
        self.callback = callback
        self.sleep = sleep
        self.callback_minus = callback_minus
        self.filter = filter


class Config:
    """Create new config file with correct structure and check that the configuration has correct parts"""

    def __init__(
            self,
            callback: Callable[[object], None] = None,
            dof_callback: Callable[[object], None] = None,
            dof_callback_arr: List[DofCallback] = None,
            button_callback: Callable[[object, list], None] = None,
            button_callback_arr: List[ButtonCallback] = None,

    ):
        check_config(callback, dof_callback, dof_callback_arr, button_callback, button_callback_arr)
        self.callback = callback
        self.dof_callback = dof_callback
        self.dof_callback_arr = dof_callback_arr
        self.button_callback = button_callback
        self.button_callback_arr = button_callback_arr

# Variables globales
_device = None
_connected = False
_last_state = None
_button_state = None
_active_device = None
_platform = None
_data_buffer = []  # Buffer pour les données reçues
_device_info = None  # Informations sur le périphérique connecté

# Charger les périphériques depuis le fichier de configuration
_device_specs = load_devices_from_config()

def _detect_platform():
    """Détecte la plateforme actuelle"""
    if sys.platform.startswith('win'):
        return 'windows'
    elif sys.platform.startswith('darwin'):
        return 'macos'
    elif sys.platform.startswith('linux'):
        return 'linux'
    else:
        return 'unknown'

# Initialiser la plateforme
_platform = _detect_platform()
logger.info(f"Detected platform: {_platform}")

def _to_int16(y1, y2):
    """Convertit deux octets en entier signé 16 bits"""
    x = (y1) | (y2 << 8)
    if x >= 32768:
        x = -(65536 - x)
    return x

def _sample_handler(data):
    """Gestionnaire d'événements pour les données reçues via pywinusb"""
    global _data_buffer
    logger.info(f"Received data: {data}")
    _data_buffer.append(data)

def check_config(callback=None, dof_callback=None, dof_callback_arr=None, button_callback=None,
                 button_callback_arr=None):
    """Check that the input configuration has the correct components.
    Raise an exception if it encounters incorrect component.
    """
    if dof_callback_arr and check_dof_callback_arr(dof_callback_arr):
        pass
    if button_callback_arr and check_button_callback_arr(button_callback_arr):
        pass

def check_button_callback_arr(button_callback_arr: List[ButtonCallback]) -> List[ButtonCallback]:
    """Check that the button_callback_arr has the correct components.
    Raise an exception if it encounters incorrect component.
    """
    # foreach ButtonCallback
    for num, butt_call in enumerate(button_callback_arr):
        if not isinstance(butt_call, ButtonCallback):
            raise Exception(f"'ButtonCallback[{num}]' is not instance of 'ButtonCallback'")
        if type(butt_call.buttons) is int:
            pass
        elif type(butt_call.buttons) is list:
            for xnum, butt in enumerate(butt_call.buttons):
                if type(butt) is not int:
                    raise Exception(f"'ButtonCallback[{num}]:buttons[{xnum}]' is not type int or list of int")
        else:
            raise Exception(f"'ButtonCallback[{num}]:buttons' is not type int or list of int")
        if not callable(butt_call.callback):
            raise Exception(f"'ButtonCallback[{num}]:callback' is not callable")
    return button_callback_arr

def check_dof_callback_arr(dof_callback_arr: List[DofCallback]) -> List[DofCallback]:
    """Check that the dof_callback_arr has the correct components.
    Raise an exception if it encounters incorrect component."""
    # foreach DofCallback
    for num, dof_call in enumerate(dof_callback_arr):
        if not isinstance(dof_call, DofCallback):
            raise Exception(f"'DofCallback[{num}]' is not instance of 'DofCallback'")
            # has the correct axis name
        if dof_call.axis not in ["x", "y", "z", "roll", "pitch", "yaw"]:
            raise Exception(
                f"'DofCallback[{num}]:axis' is not string from ['x', 'y', 'z', 'roll', 'pitch', 'yaw']")
            # is callback callable
        if not callable(dof_call.callback):
            raise Exception(f"'DofCallback[{num}]:callback' is not callable")
            # is sleep type float
        if type(dof_call.sleep) is not float:
            raise Exception(f"'DofCallback[{num}]:sleep' is not type float")
            # is callback_minus callable
        if dof_call.callback_minus is not None and not callable(dof_call.callback_minus):
            raise Exception(f"'DofCallback[{num}]:callback_minus' is not callable")
            # is filter type float
        if type(dof_call.filter) is not float:
            raise Exception(f"'DofCallback[{num}]:filter' is not type float")
    return dof_callback_arr

def list_devices():
    """Liste tous les périphériques SpaceMouse connectés"""
    devices = []
    
    try:
        # Essayer d'abord avec pywinusb si nous sommes sur Windows
        if _platform == 'windows':
            try:
                import pywinusb.hid as hid_win
                
                # Trouver tous les périphériques 3DConnexion
                all_devices = hid_win.HidDeviceFilter(vendor_id=0x046D).get_devices()
                all_devices.extend(hid_win.HidDeviceFilter(vendor_id=0x256F).get_devices())
                
                for device in all_devices:
                    for device_name, spec in _device_specs.items():
                        if device.vendor_id == spec["hid_id"][0] and device.product_id == spec["hid_id"][1]:
                            devices.append(device_name)
                            break
                
                if devices:
                    return devices
            except ImportError:
                logger.warning("pywinusb not available")
        
        # Essayer ensuite avec easyhid
        try:
            from easyhid import Enumeration
            
            hid = Enumeration()
            all_hids = hid.find()
            
            for device in all_hids:
                for device_name, spec in _device_specs.items():
                    if device.vendor_id == spec["hid_id"][0] and device.product_id == spec["hid_id"][1]:
                        devices.append(device_name)
                        break
            
            return devices
        except ImportError:
            logger.warning("easyhid not available")
            return devices
    except Exception as e:
        logger.error(f"Error listing devices: {e}")
        return devices

def list_all_hid_devices():
    """Liste tous les périphériques HID connectés"""
    devices = []
    
    # Essayer d'abord avec pywinusb si nous sommes sur Windows
    if _platform == 'windows':
        try:
            import pywinusb.hid as hid_win
            
            # Trouver tous les périphériques HID
            all_devices = hid_win.HidDeviceFilter().get_devices()
            
            for device in all_devices:
                devices.append((
                    device.product_name,
                    device.vendor_name,
                    device.vendor_id,
                    device.product_id
                ))
            
            if devices:
                return devices
        except ImportError:
            logger.warning("pywinusb not available")
    
    # Essayer ensuite avec easyhid
    try:
        from easyhid import Enumeration
        
        hid = Enumeration()
        all_hids = hid.find()
        
        for device in all_hids:
            devices.append((
                device.product_string,
                device.manufacturer_string,
                device.vendor_id,
                device.product_id
            ))
        
        return devices
    except ImportError:
        logger.warning("easyhid not available")
        return devices
    except Exception as e:
        logger.error(f"Error listing all HID devices: {e}")
        return devices

def list_available_devices():
    """Retourne une liste de tous les périphériques supportés"""
    logger.info("Listing available devices")
    return [
        (device_name, spec["hid_id"][0], spec["hid_id"][1])
        for device_name, spec in _device_specs.items()
    ]

def _detect_device_type(vendor_id, product_id):
    """Détecte le type de périphérique en fonction de son ID"""
    for device_name, spec in _device_specs.items():
        if spec["hid_id"][0] == vendor_id and spec["hid_id"][1] == product_id:
            return device_name
    return None

def open(callback=None, dof_callback=None, dof_callback_arr=None, 
         button_callback=None, button_callback_arr=None, 
         set_nonblocking_loop=True, device=None, path=None, DeviceNumber=0):
    """Ouvre un périphérique SpaceMouse"""
    global _device, _connected, _last_state, _button_state, _active_device, _data_buffer, _device_info
    
    # Fermer toute connexion existante
    close()
    
    # Réinitialiser le buffer de données
    _data_buffer = []
    
    # Si aucun nom de périphérique n'est spécifié, chercher n'importe quel périphérique correspondant et choisir le premier
    if device is None:
        all_devices = list_devices()
        if len(all_devices) > 0:
            device = all_devices[0]
        else:
            logger.error("No supported devices found")
            return False
    
    # Vérifier que la configuration d'entrée a les bons composants
    check_config(callback, dof_callback, dof_callback_arr, button_callback, button_callback_arr)
    
    # Essayer d'abord avec pywinusb si nous sommes sur Windows
    if _platform == 'windows':
        try:
            import pywinusb.hid as hid_win
            
            # Trouver tous les périphériques 3DConnexion
            all_devices = hid_win.HidDeviceFilter(vendor_id=0x046D).get_devices()
            all_devices.extend(hid_win.HidDeviceFilter(vendor_id=0x256F).get_devices())
            
            found_devices = []
            for dev in all_devices:
                spec = _device_specs.get(device)
                if spec and dev.vendor_id == spec["hid_id"][0] and dev.product_id == spec["hid_id"][1]:
                    found_devices.append({"spec": spec, "device": dev})
            
            if found_devices:
                # Sélectionner le périphérique
                if DeviceNumber >= len(found_devices):
                    DeviceNumber = 0
                
                selected_device = found_devices[DeviceNumber]
                dev = selected_device["device"]
                spec = selected_device["spec"]
                
                logger.info(f"Selected device with pywinusb: {spec['name']}")
                
                # Essayer d'ouvrir le périphérique
                try:
                    # Ouvrir le périphérique
                    dev.open()
                    
                    # Configurer le gestionnaire de données
                    dev.set_raw_data_handler(_sample_handler)
                    
                    # Initialiser l'état
                    _device = dev
                    _device_info = spec
                    _connected = True
                    _button_state = ButtonState([0] * len(spec["button_mapping"]))
                    _last_state = SpaceNavigator(
                        t=high_acc_clock(),
                        x=0.0, y=0.0, z=0.0,
                        roll=0.0, pitch=0.0, yaw=0.0,
                        buttons=_button_state
                    )
                    
                    # Créer un objet de périphérique pour la compatibilité
                    device_obj = DeviceWrapper(
                        name=spec["name"],
                        device=dev,
                        callback=callback,
                        dof_callback=dof_callback,
                        dof_callback_arr=dof_callback_arr,
                        button_callback=button_callback,
                        button_callback_arr=button_callback_arr
                    )
                    
                    _active_device = device_obj
                    logger.info("Successfully opened device with pywinusb")
                    return True
                except Exception as e:
                    logger.error(f"Failed to open device with pywinusb: {e}")
            else:
                logger.warning("No devices found with pywinusb")
        except ImportError:
            logger.warning("pywinusb not available")
    
    # Essayer ensuite avec easyhid
    try:
        from easyhid import Enumeration
        
        # Lister tous les périphériques HID
        hid = Enumeration()
        all_hids = hid.find()
        
        # Afficher tous les périphériques HID trouvés pour le débogage
        logger.info(f"Found {len(all_hids)} HID devices with easyhid:")
        for i, dev in enumerate(all_hids):
            logger.info(f"Device {i}: VID=0x{dev.vendor_id:04x}, PID=0x{dev.product_id:04x}, Path={dev.path}")
        
        # Trouver les périphériques correspondants
        found_devices = []
        for dev in all_hids:
            if path:
                dev.path = path
            
            spec = _device_specs.get(device)
            if spec and dev.vendor_id == spec["hid_id"][0] and dev.product_id == spec["hid_id"][1]:
                found_devices.append({"spec": spec, "device": dev})
        
        if not found_devices:
            logger.warning("No supported devices found with easyhid")
            return False
        
        # Sélectionner le périphérique
        if DeviceNumber >= len(found_devices):
            DeviceNumber = 0
        
        selected_device = found_devices[DeviceNumber]
        dev = selected_device["device"]
        spec = selected_device["spec"]
        
        logger.info(f"Selected device with easyhid: {spec['name']}")
        
        # Essayer d'ouvrir le périphérique
        try:
            # Sur Windows, essayer plusieurs fois
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Opening device attempt {attempt+1}/{max_attempts}")
                    dev.open()
                    logger.info("Device opened successfully with easyhid")
                    break
                except Exception as e:
                    logger.warning(f"Attempt {attempt+1} failed: {e}")
                    if attempt < max_attempts - 1:
                        time.sleep(1.0)
                    else:
                        raise
            
            # Configurer le périphérique
            dev.set_nonblocking(1 if set_nonblocking_loop else 0)
            
            # Initialiser l'état
            _device = dev
            _device_info = spec
            _connected = True
            _button_state = ButtonState([0] * len(spec["button_mapping"]))
            _last_state = SpaceNavigator(
                t=high_acc_clock(),
                x=0.0, y=0.0, z=0.0,
                roll=0.0, pitch=0.0, yaw=0.0,
                buttons=_button_state
            )
            
            # Tester la lecture
            try:
                test_data = dev.read(64)
                logger.info(f"Initial read test with easyhid: {test_data}")
            except Exception as e:
                logger.warning(f"Initial read test with easyhid failed: {e}")
            
            # Créer un objet de périphérique pour la compatibilité
            device_obj = DeviceWrapper(
                name=spec["name"],
                device=dev,
                callback=callback,
                dof_callback=dof_callback,
                dof_callback_arr=dof_callback_arr,
                button_callback=button_callback,
                button_callback_arr=button_callback_arr
            )
            
            _active_device = device_obj
            return True
        except Exception as e:
            logger.error(f"Failed to open device with easyhid: {e}")
            return False
    except ImportError:
        logger.error("Neither pywinusb nor easyhid are available")
        return False
    except Exception as e:
        logger.error(f"Error opening device: {e}")
        return False

def close():
    """Ferme la connexion au périphérique SpaceMouse"""
    global _device, _connected, _active_device
    
    if _device and _connected:
        try:
            # Vérifier si c'est un périphérique pywinusb
            if hasattr(_device, 'close') and callable(_device.close):
                _device.close()
                logger.info("Device closed")
            # Vérifier si c'est un périphérique easyhid
            elif hasattr(_device, 'is_opened') and callable(_device.is_opened):
                if _device.is_opened():
                    _device.close()
                    logger.info("Device closed")
        except Exception as e:
            logger.warning(f"Error closing device: {e}")
        _device = None
        _connected = False
        _active_device = None

def read():
    """Lit les données du périphérique SpaceMouse"""
    global _device, _connected, _last_state, _data_buffer, _device_info
    
    if not _device or not _connected or not _device_info:
        return None
    
    try:
        # Vérifier si c'est un périphérique pywinusb
        if hasattr(_device, 'is_opened') and callable(_device.is_opened) and _data_buffer:
            # Traiter les données du buffer
            data = _data_buffer.pop(0)
            
            if data and len(data) >= 7:
                # Traiter les données en fonction du canal
                channel = data[0]
                
                # Traiter les axes
                for axis_name, (chan, b1, b2, scale) in _device_info["mappings"].items():
                    if channel == chan and b1 < len(data) and b2 < len(data):
                        # Lire les valeurs brutes
                        raw_value = _to_int16(data[b1], data[b2])
                        
                        # Appliquer l'échelle (comme dans pyspacemouse)
                        value = scale * raw_value / float(_device_info["axis_scale"])
                        
                        # Mettre à jour l'état
                        _last_state = _last_state._replace(**{axis_name: value})
                
                # Traiter les boutons
                for button_index, (chan, byte, bit) in enumerate(_device_info["button_mapping"]):
                    if channel == chan and byte < len(data):
                        mask = 1 << bit
                        _button_state[button_index] = 1 if (data[byte] & mask) != 0 else 0
                
                # Mettre à jour l'horodatage et les boutons
                _last_state = _last_state._replace(t=high_acc_clock(), buttons=_button_state)
        
        # Vérifier si c'est un périphérique easyhid
        elif hasattr(_device, 'read') and callable(_device.read):
            # Lire les données
            data = _device.read(64)
            
            if data and len(data) >= 7:
                # Traiter les données en fonction du canal
                channel = data[0]
                
                # Traiter les axes
                for axis_name, (chan, b1, b2, scale) in _device_info["mappings"].items():
                    if channel == chan and b1 < len(data) and b2 < len(data):
                        # Lire les valeurs brutes
                        raw_value = _to_int16(data[b1], data[b2])
                        
                        # Appliquer l'échelle (comme dans pyspacemouse)
                        value = scale * raw_value / float(_device_info["axis_scale"])
                        
                        # Mettre à jour l'état
                        _last_state = _last_state._replace(**{axis_name: value})
                
                # Traiter les boutons
                for button_index, (chan, byte, bit) in enumerate(_device_info["button_mapping"]):
                    if channel == chan and byte < len(data):
                        mask = 1 << bit
                        _button_state[button_index] = 1 if (data[byte] & mask) != 0 else 0
                
                # Mettre à jour l'horodatage et les boutons
                _last_state = _last_state._replace(t=high_acc_clock(), buttons=_button_state)
        
        return _last_state
        
    except Exception as e:
        logger.error(f"Error reading from device: {e}")
        return None

class DeviceWrapper:
    """Classe wrapper pour la compatibilité avec l'API pyspacemouse"""
    
    def __init__(self, name, device, callback=None, dof_callback=None, 
                 dof_callback_arr=None, button_callback=None, button_callback_arr=None):
        self.name = name
        self.device = device
        self.callback = callback
        self.dof_callback = dof_callback
        self.dof_callback_arr = dof_callback_arr
        self.button_callback = button_callback
        self.button_callback_arr = button_callback_arr
        self.connected = True
        self.previous_state = None
        self.dict_state_last = {
            'x': 0.0, 'y': 0.0, 'z': 0.0,
            'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0
        }
        
    def read(self):
        """Lit les données du périphérique et appelle les callbacks appropriés"""
        state = read()
        
        if state:
            # Détecter les changements
            dof_changed = False
            button_changed = False
            
            if self.previous_state:
                # Vérifier si les DoF ont changé
                for axis in ["x", "y", "z", "roll", "pitch", "yaw"]:
                    if getattr(state, axis) != getattr(self.previous_state, axis):
                        dof_changed = True
                        break
                
                # Vérifier si les boutons ont changé
                if state.buttons != self.previous_state.buttons:
                    button_changed = True
            else:
                dof_changed = True
                button_changed = True
            
            # Appeler les callbacks
            if self.callback:
                self.callback(state)
                
            if dof_changed and self.dof_callback:
                self.dof_callback(state)
                
            if button_changed and self.button_callback:
                self.button_callback(state, state.buttons)
                
            # Appeler les callbacks spécifiques aux axes
            if dof_changed and self.dof_callback_arr:
                for block_dof_callback in self.dof_callback_arr:
                    now = high_acc_clock()
                    axis_name = block_dof_callback.axis
                    axis_val = getattr(state, axis_name)
                    
                    if now >= self.dict_state_last.get(axis_name, 0.0) + block_dof_callback.sleep:
                        # Vérifier si la valeur est supérieure au seuil
                        if block_dof_callback.callback_minus:
                            if axis_val > block_dof_callback.filter:
                                block_dof_callback.callback(state, axis_val)
                            elif axis_val < -block_dof_callback.filter:
                                block_dof_callback.callback_minus(state, axis_val)
                        elif axis_val > block_dof_callback.filter or axis_val < -block_dof_callback.filter:
                            block_dof_callback.callback(state, axis_val)
                        
                        self.dict_state_last[axis_name] = now
            
            # Appeler les callbacks spécifiques aux boutons
            if button_changed and self.button_callback_arr:
                for block_button_callback in self.button_callback_arr:
                    run = True
                    
                    # Vérifier si les boutons sont pressés
                    if isinstance(block_button_callback.buttons, list):
                        for button_id in block_button_callback.buttons:
                            if not state.buttons[button_id]:
                                run = False
                                break
                    elif isinstance(block_button_callback.buttons, int):
                        if not state.buttons[block_button_callback.buttons]:
                            run = False
                    
                    # Appeler le callback si les boutons sont pressés
                    if run:
                        block_button_callback.callback(state, state.buttons, block_button_callback.buttons)
                
            # Stocker l'état précédent
            self.previous_state = state
            
        return state
        
    def close(self):
        """Ferme la connexion au périphérique"""
        if self.connected:
            close()
            self.connected = False
            
    def config_set(self, config):
        """Configure les callbacks"""
        self.callback = config.callback
        self.dof_callback = config.dof_callback
        self.dof_callback_arr = config.dof_callback_arr
        self.button_callback = config.button_callback
        self.button_callback_arr = config.button_callback_arr
        
    def config_set_sep(self, callback=None, dof_callback=None, dof_callback_arr=None, 
                      button_callback=None, button_callback_arr=None):
        """Configure les callbacks individuellement"""
        check_config(callback, dof_callback, dof_callback_arr, button_callback, button_callback_arr)
        if callback is not None:
            self.callback = callback
        if dof_callback is not None:
            self.dof_callback = dof_callback
        if dof_callback_arr is not None:
            self.dof_callback_arr = dof_callback_arr
        if button_callback is not None:
            self.button_callback = button_callback
        if button_callback_arr is not None:
            self.button_callback_arr = button_callback_arr
            
    def config_remove(self):
        """Supprime tous les callbacks"""
        self.callback = None
        self.dof_callback = None
        self.dof_callback_arr = None
        self.button_callback = None
        self.button_callback_arr = None

def openCfg(config, set_nonblocking_loop=True, device=None, DeviceNumber=0):
    """Ouvre un périphérique avec une configuration"""
    global _active_device
    success = open(
        config.callback, 
        config.dof_callback, 
        config.dof_callback_arr, 
        config.button_callback, 
        config.button_callback_arr, 
        set_nonblocking_loop, 
        device, 
        None, 
        DeviceNumber
    )
    return _active_device if success else None

# Fonctions de compatibilité avec l'API pyspacemouse
def config_set(config):
    """Configure les callbacks du périphérique actif"""
    if _active_device:
        _active_device.config_set(config)

def config_set_sep(callback=None, dof_callback=None, dof_callback_arr=None, 
                  button_callback=None, button_callback_arr=None):
    """Configure les callbacks du périphérique actif individuellement"""
    if _active_device:
        _active_device.config_set_sep(
            callback, dof_callback, dof_callback_arr, button_callback, button_callback_arr
        )

def config_remove():
    """Supprime tous les callbacks du périphérique actif"""
    if _active_device:
        _active_device.config_remove()

def print_state(state):
    """Affiche l'état du périphérique"""
    if state:
        print(
            " ".join(
                [
                    "%4s %+.2f" % (k, getattr(state, k))
                    for k in ["x", "y", "z", "roll", "pitch", "yaw", "t"]
                ]
            )
        )

def silent_callback(state):
    """Callback silencieux"""
    pass

def print_buttons(state, buttons):
    """Affiche l'état des boutons"""
    print(
        (
            (
                "["
                + " ".join(["%2d, " % buttons[k] for k in range(len(buttons))])
            )
            + "]"
        )
    )

# Fonction pour recharger les périphériques depuis le fichier de configuration
def reload_devices():
    """Recharge les périphériques depuis le fichier de configuration"""
    global _device_specs
    _device_specs = load_devices_from_config()
    logger.info(f"Reloaded {len(_device_specs)} devices from config file")

# Initialisation
def init():
    """Initialise le module"""
    global _device, _connected, _last_state, _button_state, _active_device, _data_buffer, _device_info
    _device = None
    _connected = False
    _last_state = None
    _button_state = None
    _active_device = None
    _data_buffer = []
    _device_info = None

# Appeler init() lors de l'importation du module
init()
