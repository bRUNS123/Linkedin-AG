import spacy
import json
import sys
from pathlib import Path

# Añadir el directorio padre al path
sys.path.append(str(Path(__file__).parent.parent))

from config import config
from src.utils import normalize_text, setup_logging

# Configurar logging
logger = setup_logging(config.LOGS_DIR)


def chunk_reader(path, max_chars=200_000, overlap=0):
    """
    Lee el archivo por bloques de tamaño <= max_chars.
    'overlap' permite solapar algunos caracteres entre chunks si te preocupa cortar entidades.
    """
    buf = []
    size = 0
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            l = len(line)
            if size + l > max_chars and buf:
                # entrega chunk
                chunk = ''.join(buf)
                yield chunk
                # prepara siguiente bloque
                if overlap > 0:
                    # conserva cola de 'overlap' chars
                    tail = chunk[-overlap:]
                    buf = [tail]
                    size = len(tail)
                else:
                    buf = []
                    size = 0
            buf.append(line)
            size += l
        if buf:
            yield ''.join(buf)


def load_feedback():
    """Cargar feedback de cargos desde archivo JSON"""
    try:
        with config.FEEDBACK_FILE.open('r', encoding='utf-8') as f:
            feedback = json.load(f)
            correctos_data = feedback.get('correctos', [])
            logger.info(f"Cargados {len(correctos_data)} cargos correctos del feedback")
    except FileNotFoundError:
        logger.warning("Archivo feedback_cargos.json no encontrado. Usando lista vacía")
        correctos_data = []
        feedback = {'correctos': [], 'incorrectos': []}
    
    return feedback, correctos_data


def extract_job_titles_from_chunks(text_iterable, correctos_norm, nlp):
    """
    Procesa un iterable de textos con nlp.pipe, devolviendo una lista de entidades que
    coincidan con los 'correctos' ya guardados (normalizados).
    """
    job_titles = []
    # batch_size controla cuántos chunks procesa en paralelo
    for doc in nlp.pipe(text_iterable, batch_size=2):
        for ent in doc.ents:
            ent_norm = normalize_text(ent.text)
            # Coincidencia flexible: si el título está contenido en la entidad o viceversa
            if any(c in ent_norm or ent_norm in c for c in correctos_norm):
                job_titles.append(ent.text)
    return job_titles


def provide_feedback(cargos, feedback):
    """Solicitar feedback del usuario para validar cargos"""
    correctos = []
    incorrectos = []
    
    for cargo in cargos:
        if cargo in feedback['correctos']:
            logger.debug(f"Cargo '{cargo}' ya marcado como correcto")
            continue
        if cargo in feedback['incorrectos']:
            logger.debug(f"Cargo '{cargo}' ya marcado como incorrecto")
            continue
        
        print(f"¿El cargo '{cargo}' es correcto? (s/n): ")
        feedback_usuario = input().strip().lower()
        
        if feedback_usuario == 's':
            correctos.append(cargo)
            feedback['correctos'].append(cargo)
        else:
            incorrectos.append(cargo)
            feedback['incorrectos'].append(cargo)
    
    return correctos, incorrectos


def save_feedback(feedback):
    """Guardar feedback en archivo JSON"""
    feedback['correctos'] = sorted(set(feedback['correctos']))
    feedback['incorrectos'] = sorted(set(feedback['incorrectos']))
    
    with config.FEEDBACK_FILE.open('w', encoding='utf-8') as f:
        json.dump(feedback, f, ensure_ascii=False, indent=4)
    
    logger.info(f"Feedback guardado: {len(feedback['correctos'])} correctos, {len(feedback['incorrectos'])} incorrectos")


def save_all_correctos(feedback):
    """Guardar todos los cargos correctos en archivo de texto"""
    with config.CARGOS_FILE.open('w', encoding='utf-8') as f:
        for cargo in feedback['correctos']:
            f.write(f"{cargo}\n")
    
    logger.info(f"Guardados {len(feedback['correctos'])} cargos en {config.CARGOS_FILE.name}")


def main():
    """Función principal"""
    logger.info("=== Iniciando extracción de cargos ===")
    
    # Cargar modelo de spaCy
    logger.info("Cargando modelo de spaCy...")
    try:
        nlp = spacy.load('es_core_news_md')
        nlp.max_length = 250_000
        logger.info("Modelo cargado exitosamente")
    except OSError as e:
        logger.error(f"Error al cargar modelo de spaCy: {e}")
        logger.error("Ejecuta: python -m spacy download es_core_news_md")
        return
    
    # Cargar feedback
    feedback, correctos_data = load_feedback()
    
    # Pre-normalizar títulos correctos
    correctos_norm = [normalize_text(t) for t in correctos_data]
    
    # Determinar archivo de entrada
    texto_path = config.OUTPUT_DIR / 'filtro_laburo.txt'
    
    if not texto_path.exists():
        logger.error(f"Archivo {texto_path} no encontrado")
        logger.info("Primero ejecuta el scraper para generar datos")
        return
    
    logger.info(f"Procesando archivo: {texto_path}")
    
    # Leer y procesar en chunks
    chunks = chunk_reader(texto_path, max_chars=config.CHUNK_SIZE, overlap=500)
    cargos_encontrados = extract_job_titles_from_chunks(chunks, correctos_norm, nlp)
    
    logger.info(f"Encontrados {len(cargos_encontrados)} cargos candidatos")
    
    # Solicitar feedback
    if cargos_encontrados:
        cargos_correctos, cargos_incorrectos = provide_feedback(cargos_encontrados, feedback)
        save_feedback(feedback)
        save_all_correctos(feedback)
        
        # Mostrar resultados
        print("\n" + "="*50)
        print("RESULTADOS FINALES")
        print("="*50)
        print(f"\n Cargos Correctos ({len(cargos_correctos)}):")
        for c in cargos_correctos:
            print(f" - {c}")
        
        print(f"\n Cargos Incorrectos ({len(cargos_incorrectos)}):")
        for c in cargos_incorrectos:
            print(f" - {c}")
        
        logger.info("Proceso completado exitosamente")
    else:
        logger.info("No se encontraron nuevos cargos para validar")


if __name__ == "__main__":
    main()
