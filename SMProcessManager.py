import subprocess
import os
import psutil  # Assurez-vous d'installer psutil avec `pip install psutil`
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,  # Niveau de log par défaut
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("process_manager.log"),  # Enregistre les logs dans un fichier
        logging.StreamHandler()  # Affiche les logs dans la console
    ]
)

class ProcessManager:
    def __init__(self, executable_path: str):
        self.executable_path = executable_path

    def is_running(self):
        """Vérifie si le processus 3DxService est en cours d'exécution."""
        process_name = "3DxService.exe"
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == process_name:
                return True
        return False

    def start(self):
        """Démarre le service 3DxService."""
        if not os.path.exists(self.executable_path):
            logging.error(f"⛔ Le chemin de l'exécutable n'existe pas : {self.executable_path}")
            return f"⛔ Le chemin de l'exécutable n'existe pas : {self.executable_path}"

        if self.is_running():
            logging.warning("⚠️ Le service est déjà en cours d'exécution.")
            return "⚠️ Le service est déjà en cours d'exécution."

        try:
            process = subprocess.Popen(self.executable_path, shell=True)
            logging.info(f"✅ Service démarré avec PID : {process.pid}")
            return f"✅ Service démarré avec PID : {process.pid}"
        except Exception as e:
            logging.error(f"❌ Erreur lors du démarrage du service : {e}")
            return f"❌ Erreur lors du démarrage du service : {e}"

    def stop(self):
        """Arrête le service 3DxService."""
        if not self.is_running():
            logging.warning("⚠️ Le service n'est pas en cours d'exécution.")
            return "⚠️ Le service n'est pas en cours d'exécution."

        powershell_path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        
        try:
            result = subprocess.run(
                [powershell_path, "-Command", "Stop-Process -Name '3DxService' -Force"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logging.info("✅ Service arrêté avec succès.")
                return "✅ Service arrêté avec succès."
            else:
                logging.error(f"❌ Erreur lors de l'arrêt du service : {result.stderr.strip()}")
                return f"❌ Erreur lors de l'arrêt du service : {result.stderr.strip()}"
        except Exception as e:
            logging.error(f"❌ Erreur : {e}")
            return f"❌ Erreur : {e}"
