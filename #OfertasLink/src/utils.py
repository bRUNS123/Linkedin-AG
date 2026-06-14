import unicodedata
import logging
from pathlib import Path

def setup_logging(log_dir='logs'):
    """Configurar logging para el proyecto"""
    Path(log_dir).mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'{log_dir}/scraper.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def normalize_text(text: str) -> str:
    """Normalización consistente de texto"""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in text if not unicodedata.combining(c))
