import os
import sys

def main():
    # Obtener la ruta del directorio actual donde esta el bot
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Ruta de la carpeta "Inicio" (Startup) de Windows
    startup_dir = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
    
    # Archivo batch a crear
    startup_bat_path = os.path.join(startup_dir, "LinkedinScraperBot.bat")
    
    # Contenido del batch
    # Cambia a la carpeta del proyecto y ejecuta el bot con --autostart
    bat_content = f"""@echo off
cd /d "{current_dir}"
start "" /min python dashboard_app.py --autostart
"""
    
    try:
        with open(startup_bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        
        print("================================================================")
        print(" EXITOSO: Bot configurado para iniciar al encender Windows.")
        print(f" Archivo creado en: {startup_bat_path}")
        print(" El bot iniciara automaticamente de forma minimizada y comenzara")
        print(" a escrapear sin que debas intervenir.")
        print("================================================================")
    except Exception as e:
        print(f"Error al crear el acceso directo de inicio: {e}")

if __name__ == "__main__":
    main()
    os.system("pause")
