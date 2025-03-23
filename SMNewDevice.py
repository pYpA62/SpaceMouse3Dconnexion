# SMNewDevice.py - Module pour ajouter et gérer de nouveaux périphériques SpaceMouse

import os
import json
import logging
from typing import Dict, List, Tuple, Any, Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QSpinBox, QDoubleSpinBox, QComboBox
)
from PyQt5.QtCore import Qt
from qgis.core import Qgis

# Configuration du logging
logger = logging.getLogger("SpaceMouse.SMNewDevice")

# Chemin vers le fichier de configuration des périphériques
DEVICES_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "devices.json")

def load_devices_from_config() -> Dict[str, Dict[str, Any]]:
    """Charge les périphériques depuis le fichier de configuration"""
    # Périphériques par défaut
    default_devices = {
        "SpaceNavigator": {
            "name": "SpaceNavigator",
            "hid_id": [1133, 50726],
            "mappings": {
                "x": [1, 1, 2, 1],
                "y": [1, 3, 4, -1],
                "z": [1, 5, 6, -1],
                "roll": [2, 1, 2, -1],
                "pitch": [2, 3, 4, -1],
                "yaw": [2, 5, 6, 1]
            },
            "button_mapping": [
                [3, 1, 0],
                [3, 1, 1]
            ],
            "axis_scale": 327.0
        },
        # ... autres périphériques par défaut ...
    }
    
    try:
        # Vérifier si le fichier existe
        if os.path.exists(DEVICES_CONFIG_FILE):
            with open(DEVICES_CONFIG_FILE, 'r') as f:
                devices = json.load(f)
                
            # Convertir les IDs hexadécimaux en décimaux si nécessaire
            for device_name, device_info in devices.items():
                if "hid_id" in device_info:
                    hid_id = device_info["hid_id"]
                    if isinstance(hid_id[0], str) and hid_id[0].startswith("0x"):
                        hid_id[0] = int(hid_id[0], 16)
                    if isinstance(hid_id[1], str) and hid_id[1].startswith("0x"):
                        hid_id[1] = int(hid_id[1], 16)
                    device_info["hid_id"] = hid_id
                
            logger.info(f"Loaded {len(devices)} devices from config file")
            return devices
        else:
            # Créer le fichier avec les périphériques par défaut
            logger.info("Devices config file not found, creating with default devices")
            save_devices_to_config(default_devices)
            return default_devices
    except Exception as e:
        logger.error(f"Error loading devices from config file: {e}")
        return default_devices

def save_devices_to_config(devices: Dict[str, Dict[str, Any]]) -> bool:
    """Sauvegarde les périphériques dans le fichier de configuration"""
    try:
        # Créer le répertoire si nécessaire
        os.makedirs(os.path.dirname(DEVICES_CONFIG_FILE), exist_ok=True)
        
        with open(DEVICES_CONFIG_FILE, 'w') as f:
            json.dump(devices, f, indent=2)
        
        logger.info(f"Saved {len(devices)} devices to config file")
        return True
    except Exception as e:
        logger.error(f"Error saving devices to config file: {e}")
        return False

def add_device(device_name: str, hid_id: List[int], mappings: Dict[str, List[int]], 
               button_mapping: List[List[int]], axis_scale: float = 327.0) -> bool:
    """Ajoute un nouveau périphérique à la configuration"""
    # Charger les périphériques existants
    devices = load_devices_from_config()
    
    # Vérifier si le périphérique existe déjà
    if device_name in devices:
        logger.warning(f"Device {device_name} already exists")
        return False
    
    # Ajouter le périphérique
    devices[device_name] = {
        "name": device_name,
        "hid_id": hid_id,
        "mappings": mappings,
        "button_mapping": button_mapping,
        "axis_scale": axis_scale
    }
    
    # Sauvegarder la configuration
    return save_devices_to_config(devices)

def update_device(device_name: str, hid_id: List[int], mappings: Dict[str, List[int]], 
                  button_mapping: List[List[int]], axis_scale: float = 327.0) -> bool:
    """Met à jour un périphérique existant dans la configuration"""
    # Charger les périphériques existants
    devices = load_devices_from_config()
    
    # Vérifier si le périphérique existe
    if device_name not in devices:
        logger.warning(f"Device {device_name} does not exist")
        return False
    
    # Mettre à jour le périphérique
    devices[device_name] = {
        "name": device_name,
        "hid_id": hid_id,
        "mappings": mappings,
        "button_mapping": button_mapping,
        "axis_scale": axis_scale
    }
    
    # Sauvegarder la configuration
    return save_devices_to_config(devices)

def delete_device(device_name: str) -> bool:
    """Supprime un périphérique de la configuration"""
    # Charger les périphériques existants
    devices = load_devices_from_config()
    
    # Vérifier si le périphérique existe
    if device_name not in devices:
        logger.warning(f"Device {device_name} does not exist")
        return False
    
    # Supprimer le périphérique
    del devices[device_name]
    
    # Sauvegarder la configuration
    return save_devices_to_config(devices)

def get_device(device_name: str) -> Optional[Dict[str, Any]]:
    """Récupère les informations d'un périphérique"""
    # Charger les périphériques existants
    devices = load_devices_from_config()
    
    # Vérifier si le périphérique existe
    if device_name not in devices:
        logger.warning(f"Device {device_name} does not exist")
        return None
    
    return devices[device_name]

def list_devices() -> List[str]:
    """Liste tous les périphériques configurés"""
    # Charger les périphériques existants
    devices = load_devices_from_config()
    
    return list(devices.keys())

class AddDeviceDialog(QDialog):
    """Boîte de dialogue pour ajouter un nouveau périphérique"""
    
    def __init__(self, parent=None, device_name: str = None):
        super().__init__(parent)
        
        self.edit_mode = device_name is not None
        self.device_name = device_name
        
        if self.edit_mode:
            self.setWindowTitle(f"Modifier le périphérique {device_name}")
        else:
            self.setWindowTitle("Ajouter un nouveau périphérique")
        
        self.setMinimumWidth(600)
        
        # Créer les widgets
        self.device_name_edit = QLineEdit()
        self.vendor_id_edit = QLineEdit()
        self.vendor_id_edit.setPlaceholderText("ex: 0x046D")
        self.product_id_edit = QLineEdit()
        self.product_id_edit.setPlaceholderText("ex: 0xC626")
        self.axis_scale_edit = QDoubleSpinBox()
        self.axis_scale_edit.setRange(1.0, 1000.0)
        self.axis_scale_edit.setValue(327.0)
        self.axis_scale_edit.setDecimals(1)
        
        # Tableau pour les mappings des axes
        self.axis_mappings_table = QTableWidget(6, 4)
        self.axis_mappings_table.setHorizontalHeaderLabels(["Canal", "Byte1", "Byte2", "Échelle"])
        self.axis_mappings_table.setVerticalHeaderLabels(["x", "y", "z", "roll", "pitch", "yaw"])
        self.axis_mappings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # Initialiser les valeurs par défaut pour les mappings des axes
        default_mappings = [
            [1, 1, 2, 1],    # x
            [1, 3, 4, -1],   # y
            [1, 5, 6, -1],   # z
            [2, 1, 2, -1],   # roll
            [2, 3, 4, -1],   # pitch
            [2, 5, 6, 1]     # yaw
        ]
        
        for row, mapping in enumerate(default_mappings):
            for col, value in enumerate(mapping):
                item = QTableWidgetItem(str(value))
                self.axis_mappings_table.setItem(row, col, item)
        
        # Tableau pour les mappings des boutons
        self.button_mappings_table = QTableWidget(2, 3)
        self.button_mappings_table.setHorizontalHeaderLabels(["Canal", "Byte", "Bit"])
        self.button_mappings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # Initialiser les valeurs par défaut pour les mappings des boutons
        default_button_mappings = [
            [3, 1, 0],    # LEFT
            [3, 1, 1]     # RIGHT
        ]
        
        for row, mapping in enumerate(default_button_mappings):
            for col, value in enumerate(mapping):
                item = QTableWidgetItem(str(value))
                self.button_mappings_table.setItem(row, col, item)
        
        # Boutons
        self.add_button_row_button = QPushButton("Ajouter une ligne")
        self.add_button_row_button.clicked.connect(self.add_button_row)
        
        self.remove_button_row_button = QPushButton("Supprimer la dernière ligne")
        self.remove_button_row_button.clicked.connect(self.remove_button_row)
        
        self.save_button = QPushButton("Enregistrer")
        self.save_button.clicked.connect(self.save_device)
        
        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.clicked.connect(self.reject)
        
        # Créer les layouts
        main_layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        form_layout.addRow("Nom du périphérique:", self.device_name_edit)
        form_layout.addRow("ID du vendeur (hex):", self.vendor_id_edit)
        form_layout.addRow("ID du produit (hex):", self.product_id_edit)
        form_layout.addRow("Échelle des axes:", self.axis_scale_edit)
        
        main_layout.addLayout(form_layout)
        
        main_layout.addWidget(QLabel("Mappings des axes:"))
        main_layout.addWidget(self.axis_mappings_table)
        
        main_layout.addWidget(QLabel("Mappings des boutons:"))
        main_layout.addWidget(self.button_mappings_table)
        
        button_row_layout = QHBoxLayout()
        button_row_layout.addWidget(self.add_button_row_button)
        button_row_layout.addWidget(self.remove_button_row_button)
        main_layout.addLayout(button_row_layout)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
        
        # Si nous sommes en mode édition, charger les données du périphérique
        if self.edit_mode:
            self.load_device_data()
    
    def load_device_data(self):
        """Charge les données du périphérique à éditer"""
        device_data = get_device(self.device_name)
        
        if not device_data:
            QMessageBox.warning(self, "Erreur", f"Le périphérique {self.device_name} n'existe pas")
            self.reject()
            return
        
        # Remplir les champs
        self.device_name_edit.setText(device_data["name"])
        self.vendor_id_edit.setText(f"0x{device_data['hid_id'][0]:04X}")
        self.product_id_edit.setText(f"0x{device_data['hid_id'][1]:04X}")
        self.axis_scale_edit.setValue(device_data["axis_scale"])
        
        # Remplir les mappings des axes
        axis_names = ["x", "y", "z", "roll", "pitch", "yaw"]
        for row, axis_name in enumerate(axis_names):
            if axis_name in device_data["mappings"]:
                mapping = device_data["mappings"][axis_name]
                for col, value in enumerate(mapping):
                    item = QTableWidgetItem(str(value))
                    self.axis_mappings_table.setItem(row, col, item)
        
        # Remplir les mappings des boutons
        self.button_mappings_table.setRowCount(0)
        for mapping in device_data["button_mapping"]:
            row = self.button_mappings_table.rowCount()
            self.button_mappings_table.insertRow(row)
            for col, value in enumerate(mapping):
                item = QTableWidgetItem(str(value))
                self.button_mappings_table.setItem(row, col, item)
    
    def add_button_row(self):
        """Ajoute une ligne au tableau des mappings des boutons"""
        row_count = self.button_mappings_table.rowCount()
        self.button_mappings_table.insertRow(row_count)
        
        # Initialiser les valeurs par défaut
        for col, value in enumerate([3, 1, row_count]):
            item = QTableWidgetItem(str(value))
            self.button_mappings_table.setItem(row_count, col, item)
    
    def remove_button_row(self):
        """Supprime la dernière ligne du tableau des mappings des boutons"""
        row_count = self.button_mappings_table.rowCount()
        if row_count > 0:
            self.button_mappings_table.removeRow(row_count - 1)
    
    def save_device(self):
        """Enregistre le périphérique"""
        try:
            # Récupérer les valeurs
            device_name = self.device_name_edit.text().strip()
            vendor_id_text = self.vendor_id_edit.text().strip()
            product_id_text = self.product_id_edit.text().strip()
            axis_scale = self.axis_scale_edit.value()
            
            # Vérifier les valeurs
            if not device_name:
                QMessageBox.warning(self, "Erreur", "Le nom du périphérique ne peut pas être vide")
                return
            
            # Convertir les IDs en entiers
            try:
                if vendor_id_text.startswith("0x"):
                    vendor_id = int(vendor_id_text, 16)
                else:
                    vendor_id = int(vendor_id_text)
                
                if product_id_text.startswith("0x"):
                    product_id = int(product_id_text, 16)
                else:
                    product_id = int(product_id_text)
            except ValueError:
                QMessageBox.warning(self, "Erreur", "Les IDs du vendeur et du produit doivent être des nombres hexadécimaux (ex: 0x046D) ou décimaux")
                return
            
            # Récupérer les mappings des axes
            mappings = {}
            axis_names = ["x", "y", "z", "roll", "pitch", "yaw"]
            
            for row, axis_name in enumerate(axis_names):
                try:
                    channel = int(self.axis_mappings_table.item(row, 0).text())
                    byte1 = int(self.axis_mappings_table.item(row, 1).text())
                    byte2 = int(self.axis_mappings_table.item(row, 2).text())
                    scale = int(self.axis_mappings_table.item(row, 3).text())
                    
                    mappings[axis_name] = [channel, byte1, byte2, scale]
                except (ValueError, AttributeError):
                    QMessageBox.warning(self, "Erreur", f"Les valeurs pour l'axe {axis_name} doivent être des nombres entiers")
                    return
            
            # Récupérer les mappings des boutons
            button_mapping = []
            
            for row in range(self.button_mappings_table.rowCount()):
                try:
                    channel = int(self.button_mappings_table.item(row, 0).text())
                    byte = int(self.button_mappings_table.item(row, 1).text())
                    bit = int(self.button_mappings_table.item(row, 2).text())
                    
                    button_mapping.append([channel, byte, bit])
                except (ValueError, AttributeError):
                    QMessageBox.warning(self, "Erreur", f"Les valeurs pour le bouton {row+1} doivent être des nombres entiers")
                    return
            
            # Ajouter ou mettre à jour le périphérique
            if self.edit_mode and self.device_name != device_name:
                # Si le nom a changé, supprimer l'ancien périphérique
                delete_device(self.device_name)
                
            if self.edit_mode:
                success = update_device(
                    device_name=device_name,
                    hid_id=[vendor_id, product_id],
                    mappings=mappings,
                    button_mapping=button_mapping,
                    axis_scale=axis_scale
                )
                
                if success:
                    QMessageBox.information(self, "Succès", f"Le périphérique {device_name} a été mis à jour avec succès")
                    self.accept()
                else:
                    QMessageBox.warning(self, "Erreur", f"Erreur lors de la mise à jour du périphérique {device_name}")
            else:
                success = add_device(
                    device_name=device_name,
                    hid_id=[vendor_id, product_id],
                    mappings=mappings,
                    button_mapping=button_mapping,
                    axis_scale=axis_scale
                )
                
                if success:
                    QMessageBox.information(self, "Succès", f"Le périphérique {device_name} a été ajouté avec succès")
                    self.accept()
                else:
                    QMessageBox.warning(self, "Erreur", f"Le périphérique {device_name} existe déjà")
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Erreur lors de l'ajout du périphérique: {str(e)}")

class ManageDevicesDialog(QDialog):
    """Boîte de dialogue pour gérer les périphériques"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("Gérer les périphériques")
        self.setMinimumWidth(500)
        
        # Créer les widgets
        self.devices_combo = QComboBox()
        self.refresh_devices()
        
        self.add_button = QPushButton("Ajouter")
        self.add_button.clicked.connect(self.add_device)
        
        self.edit_button = QPushButton("Modifier")
        self.edit_button.clicked.connect(self.edit_device)
        
        self.delete_button = QPushButton("Supprimer")
        self.delete_button.clicked.connect(self.delete_device)
        
        self.close_button = QPushButton("Fermer")
        self.close_button.clicked.connect(self.accept)
        
        # Créer les layouts
        main_layout = QVBoxLayout()
        
        devices_layout = QHBoxLayout()
        devices_layout.addWidget(QLabel("Périphériques:"))
        devices_layout.addWidget(self.devices_combo, 1)
        
        main_layout.addLayout(devices_layout)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.add_button)
        buttons_layout.addWidget(self.edit_button)
        buttons_layout.addWidget(self.delete_button)
        
        main_layout.addLayout(buttons_layout)
        main_layout.addWidget(self.close_button)
        
        self.setLayout(main_layout)
    
    def refresh_devices(self):
        """Rafraîchit la liste des périphériques"""
        self.devices_combo.clear()
        
        devices = list_devices()
        for device in devices:
            self.devices_combo.addItem(device)
    
    def add_device(self):
        """Ouvre la boîte de dialogue d'ajout de périphérique"""
        dialog = AddDeviceDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_devices()
    
    def edit_device(self):
        """Ouvre la boîte de dialogue d'édition de périphérique"""
        device_name = self.devices_combo.currentText()
        if not device_name:
            QMessageBox.warning(self, "Erreur", "Aucun périphérique sélectionné")
            return
        
        dialog = AddDeviceDialog(self, device_name)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_devices()
    
    def delete_device(self):
        """Supprime le périphérique sélectionné"""
        device_name = self.devices_combo.currentText()
        if not device_name:
            QMessageBox.warning(self, "Erreur", "Aucun périphérique sélectionné")
            return
        
        reply = QMessageBox.question(
            self, "Confirmation",
            f"Êtes-vous sûr de vouloir supprimer le périphérique {device_name} ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success = delete_device(device_name)
            
            if success:
                QMessageBox.information(self, "Succès", f"Le périphérique {device_name} a été supprimé avec succès")
                self.refresh_devices()
            else:
                QMessageBox.warning(self, "Erreur", f"Erreur lors de la suppression du périphérique {device_name}")
