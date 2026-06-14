import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Paths
    BASE_DIR = Path(__file__).parent
    SRC_DIR = BASE_DIR / 'src'
    DATA_DIR = BASE_DIR / 'data'
    OUTPUT_DIR = BASE_DIR / 'output'
    LOGS_DIR = BASE_DIR / 'logs'
    CHROME_DATA_DIR = BASE_DIR / 'chrome-data'
    
    # LinkedIn
    LINKEDIN_EMAIL = os.getenv('LINKEDIN_EMAIL')
    LINKEDIN_PASSWORD = os.getenv('LINKEDIN_PASSWORD')
    LINKEDIN_URL = "https://www.linkedin.com/feed/"
    
    # Scraping
    MAX_SCROLL_ITERATIONS = int(os.getenv('MAX_SCROLL_ITERATIONS', 1000))
    CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', 200000))
    
    # Files
    LOCALIDADES_FILE = DATA_DIR / 'localidades.json'
    FEEDBACK_FILE = DATA_DIR / 'feedback_cargos.json'
    CARGOS_FILE = DATA_DIR / 'cargos_correctos.txt'
    
    @classmethod
    def create_dirs(cls):
        """Crear directorios necesarios"""
        for dir_path in [cls.OUTPUT_DIR, cls.LOGS_DIR, cls.CHROME_DATA_DIR]:
            dir_path.mkdir(exist_ok=True)

config = Config()
