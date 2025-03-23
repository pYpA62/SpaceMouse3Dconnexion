# SMProcessManager.py
# Gestion des processus 3DConnexion sur différentes plateformes

import os
import sys
import subprocess
import logging
import time
from typing import List, Dict, Optional, Tuple, Union

# Importation conditionnelle de psutil pour éviter les erreurs si non installé
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Configuration du logging
logger = logging.getLogger("SpaceMouse.ProcessManager")

class ProcessManager:
    """
    Gestionnaire de processus pour les services 3DConnexion sur différentes plateformes.
    Permet de démarrer, arrêter et vérifier l'état des services 3DConnexion.
    """
    
    def __init__(self, executable_path: str):
        """
        Initialise le gestionnaire de processus.
        
        Args:
            executable_path: Chemin vers l'exécutable du service 3DConnexion
        """
        self.executable_path = executable_path
        self.platform = self._detect_platform()
        self.process_info = self._get_platform_process_info()
        logger.info(f"ProcessManager initialisé pour {self.platform}")
        
    def _detect_platform(self) -> str:
        """
        Détecte la plateforme actuelle.
        
        Returns:
            Chaîne identifiant la plateforme: 'windows', 'macos', ou 'linux'
        """
        if sys.platform.startswith('win'):
            return 'windows'
        elif sys.platform.startswith('darwin'):
            return 'macos'
        elif sys.platform.startswith('linux'):
            return 'linux'
        else:
            logger.warning(f"Plateforme inconnue: {sys.platform}, utilisation de 'linux' par défaut")
            return 'linux'
    
    def _get_platform_process_info(self) -> Dict[str, Dict[str, Union[List[str], str, List[List[str]]]]]:
        """
        Obtient les informations spécifiques à la plateforme pour les processus 3DConnexion.
        
        Returns:
            Dictionnaire contenant les informations de processus pour chaque plateforme
        """
        return {
            'windows': {
                'process_names': ['3DxService.exe', '3DxWare.exe'],
                'service_name': '3dxsrv',
                'start_commands': [[self.executable_path]],
                'stop_commands': [
                    [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", 
                     "-Command", "Stop-Process -Name '3DxService' -Force -ErrorAction SilentlyContinue"],
                    [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", 
                     "-Command", "Stop-Process -Name '3DxWare' -Force -ErrorAction SilentlyContinue"]
                ]
            },
            'macos': {
                'process_names': ['3DxWareMac', '3dxsrv'],
                'service_name': '3DxWareMac',
                'start_commands': [['open', self.executable_path]],
                'stop_commands': [
                    ['pkill', '-f', '3DxWareMac'],
                    ['pkill', '-f', '3dxsrv']
                ]
            },
            'linux': {
                'process_names': ['3dxsrv', 'spacenavd'],
                'service_name': 'spacenavd',
                'start_commands': [
                    [self.executable_path],
                    ['systemctl', 'start', 'spacenavd']
                ],
                'stop_commands': [
                    ['pkill', '-f', '3dxsrv'],
                    ['pkill', '-f', 'spacenavd'],
                    ['systemctl', 'stop', 'spacenavd']
                ]
            }
        }
    
    def is_running(self) -> bool:
        """
        Vérifie si le service 3DConnexion est en cours d'exécution.
        
        Returns:
            True si le service est en cours d'exécution, False sinon
        """
        # Obtenir les noms de processus pour la plateforme actuelle
        process_names = self.process_info[self.platform]['process_names']
        
        # Méthode 1: Utiliser psutil si disponible
        if PSUTIL_AVAILABLE:
            for process_name in process_names:
                for proc in psutil.process_iter(['name']):
                    try:
                        proc_name = proc.info['name']
                        if proc_name == process_name or process_name in proc_name:
                            logger.info(f"Processus en cours d'exécution trouvé: {process_name}")
                            return True
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
        
        # Méthode 2: Utiliser des commandes spécifiques à la plateforme
        try:
            if self.platform == 'windows':
                for process_name in process_names:
                    result = subprocess.run(
                        ['tasklist', '/FI', f'IMAGENAME eq {process_name}'], 
                        capture_output=True, 
                        text=True
                    )
                    if process_name in result.stdout:
                        return True
                        
            elif self.platform == 'macos' or self.platform == 'linux':
                for process_name in process_names:
                    result = subprocess.run(
                        ['pgrep', '-f', process_name], 
                        capture_output=True, 
                        text=True
                    )
                    if result.returncode == 0:
                        return True
                        
                # Vérifier également le service sur Linux
                if self.platform == 'linux':
                    service_name = self.process_info[self.platform]['service_name']
                    result = subprocess.run(
                        ['systemctl', 'is-active', service_name], 
                        capture_output=True, 
                        text=True
                    )
                    if 'active' in result.stdout:
                        return True
        except Exception as e:
            logger.warning(f"Erreur lors de la vérification du processus: {e}")
            
        return False
    
    def start(self) -> str:
        """
        Démarre le service 3DConnexion pour la plateforme actuelle.
        
        Returns:
            Message indiquant le résultat de l'opération
        """
        # Vérifier si l'exécutable existe
        if self.executable_path and not os.path.exists(self.executable_path):
            message = f"⛔ Le chemin de l'exécutable n'existe pas: {self.executable_path}"
            logger.error(message)
            return message
        
        # Vérifier si le service est déjà en cours d'exécution
        if self.is_running():
            message = "⚠️ Le service est déjà en cours d'exécution"
            logger.warning(message)
            return message
        
        # Obtenir les commandes de démarrage pour la plateforme actuelle
        start_commands = self.process_info[self.platform]['start_commands']
        
        # Essayer chaque commande de démarrage jusqu'à ce qu'une réussisse
        for cmd in start_commands:
            try:
                logger.info(f"Tentative de démarrage avec la commande: {cmd}")
                
                # Exécuter la commande
                if len(cmd) == 1 and self.platform == 'windows':
                    # Sur Windows, utiliser shell=True pour les chemins avec espaces
                    process = subprocess.Popen(cmd[0], shell=True)
                else:
                    process = subprocess.Popen(cmd, shell=False)
                
                # Attendre un peu pour que le processus démarre
                time.sleep(1)
                
                # Vérifier si le service est maintenant en cours d'exécution
                if self.is_running():
                    message = f"✅ Service démarré avec succès sur {self.platform}"
                    logger.info(message)
                    return message
                    
            except Exception as e:
                logger.warning(f"Échec du démarrage avec la commande {cmd}: {e}")
        
        # Si toutes les commandes ont échoué
        message = f"❌ Échec du démarrage du service sur {self.platform}"
        logger.error(message)
        return message
    
    def stop(self) -> str:
        """
        Arrête le service 3DConnexion pour la plateforme actuelle.
        
        Returns:
            Message indiquant le résultat de l'opération
        """
        # Vérifier si le service est en cours d'exécution
        if not self.is_running():
            message = "⚠️ Le service n'est pas en cours d'exécution"
            logger.warning(message)
            return message
        
        # Obtenir les commandes d'arrêt pour la plateforme actuelle
        stop_commands = self.process_info[self.platform]['stop_commands']
        
        # Essayer chaque commande d'arrêt jusqu'à ce qu'une réussisse
        for cmd in stop_commands:
            try:
                logger.info(f"Tentative d'arrêt avec la commande: {cmd}")
                
                # Exécuter la commande
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                # Attendre un peu pour que le processus s'arrête
                time.sleep(1)
                
                # Vérifier si le service est maintenant arrêté
                if not self.is_running():
                    message = f"✅ Service arrêté avec succès sur {self.platform}"
                    logger.info(message)
                    return message
                    
            except Exception as e:
                logger.warning(f"Échec de l'arrêt avec la commande {cmd}: {e}")
        
        # Si toutes les commandes ont échoué
        message = f"❌ Échec de l'arrêt du service sur {self.platform}"
        logger.error(message)
        return message
    
    def restart(self) -> str:
        """
        Redémarre le service 3DConnexion pour la plateforme actuelle.
        
        Returns:
            Message indiquant le résultat de l'opération
        """
        stop_result = self.stop()
        if "❌" in stop_result:
            return stop_result
            
        # Attendre un peu avant de redémarrer
        time.sleep(2)
        
        return self.start()
    
    def get_status(self) -> Dict[str, Union[bool, str]]:
        """
        Obtient l'état détaillé du service 3DConnexion.
        
        Returns:
            Dictionnaire contenant des informations sur l'état du service
        """
        status = {
            'running': self.is_running(),
            'platform': self.platform,
            'executable': self.executable_path,
            'executable_exists': os.path.exists(self.executable_path) if self.executable_path else False
        }
        
        # Ajouter des informations spécifiques à la plateforme
        if PSUTIL_AVAILABLE and status['running']:
            process_names = self.process_info[self.platform]['process_names']
            processes = []
            
            for process_name in process_names:
                for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                    try:
                        proc_name = proc.info['name']
                        if proc_name == process_name or process_name in proc_name:
                            processes.append({
                                'pid': proc.info['pid'],
                                'name': proc_name,
                                'running_time': time.time() - proc.info['create_time']
                            })
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                        
            status['processes'] = processes
            
        return status