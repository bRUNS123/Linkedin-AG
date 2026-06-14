import time
import os
import re
import sys
import random
from datetime import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    ElementNotVisibleException,
    ElementNotSelectableException,
    NoSuchElementException,
    TimeoutException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from wakepy import keep
from collections import OrderedDict

# Añadir el directorio padre al path para imports
sys.path.append(str(Path(__file__).parent.parent))

from config import config
from src.utils import setup_logging

# Configurar logging
logger = setup_logging(config.LOGS_DIR)

# Palabras clave para filtrar publicaciones
FILTRO_LABURO = [
    "haypega", "busqueda", "búsqueda", "se necesita", "en búsqueda",
    "requisitos", "interesados", "enviar curriculum", "curriculum", "se requiere",
    "tu cv", "envía tu cv", "busca incorporar", "incorporar", "pretensiones de renta",
    "postulación", "postulacion", "postular", "ofrecemos", "interesado", "selección", "seleccion",
    "cargo", "antecedentes", "oportunidad laboral", "cv", "requiere", "oferta laboral", "pretensiones", "ofrecido",
    "funciones principales", "turno:", "oferta de trabajo", "estamos solicitando", "El profesional deberá contar",
    "Renta Líquida", "hay pega", "requerimiento de personal", "buscamos", "estamos en busqueda",
    "buscamos personal", "se busca", "nueva oportunidad", "nueva oportunidad de empleo", "oportunidad de empleo",
    "seguimos en busqueda", "nuevas oportunidades laborales", "estamos en la busqueda",
    "nos encontramos en búsqueda", "estamos buscando", "buscamos a", "estamos necesitando",
    "Nos encontramos en la búsqueda", "Te estamos buscando", "buscamos personal", "renta", "renta bruta"
]

# Rutas de archivos de salida
TOTAL_FILE_PATH = config.OUTPUT_DIR / "total.txt"
FILTRO_FILE_PATH = config.OUTPUT_DIR / "filtro_laburo.txt"

# Crear directorios necesarios
config.create_dirs()


def setup_driver():
    """Configurar y retornar driver de Selenium"""
    chrome_options = Options()
    chrome_options.add_argument(f"user-data-dir={config.CHROME_DATA_DIR}")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options.add_experimental_option("detach", True)
    
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 10, poll_frequency=1, ignored_exceptions=[
        ElementNotVisibleException, ElementNotSelectableException
    ])
    
    driver.maximize_window()
    return driver, wait


def check_login(driver, wait):
    """Verificar y realizar login si es necesario"""
    try:
        # Intentar detectar si está en la página de login
        try:
            login_button = driver.find_element(By.XPATH, '//button[contains(@aria-label, "Iniciar sesión")]')
            is_logged_out = True
        except NoSuchElementException:
            is_logged_out = False
        
        if is_logged_out:
            logger.info('Iniciando sesión en LinkedIn')
            
            # Verificar que las credenciales estén configuradas
            if not config.LINKEDIN_EMAIL or not config.LINKEDIN_PASSWORD:
                logger.error('Credenciales no configuradas. Por favor, configura el archivo .env')
                raise ValueError("Credenciales de LinkedIn no encontradas en .env")
            
            user_input = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="username"]')))
            ActionChains(driver).move_to_element(user_input).click(user_input).send_keys(config.LINKEDIN_EMAIL).perform()
            
            password_input = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="password"]')))
            ActionChains(driver).move_to_element(password_input).click(password_input).send_keys(config.LINKEDIN_PASSWORD).perform()
            
            login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[@data-litms-control-urn="login-submit"]')))
            login_btn.click()
            
            # Esperar a que cargue el feed
            time.sleep(5)
            logger.info('Sesión iniciada correctamente')
        else:
            logger.info('Sesión ya iniciada')
            
    except TimeoutException:
        logger.warning('No se pudo detectar la página de login, asumiendo sesión activa')
    except Exception as e:
        logger.error(f'Error durante el login: {e}')
        raise


def scroll_to_last_element(driver, wait):
    """Hacer scroll y cargar más publicaciones"""
    try:
        posts = wait.until(EC.presence_of_all_elements_located((By.XPATH, '//div[starts-with(@data-id, "urn:li:activity:")]')))
        if posts:
            last_post = posts[-1]
            driver.execute_script("arguments[0].scrollIntoView();", last_post)
            time.sleep(random.uniform(1, 2))
            driver.execute_script("window.scrollBy(0, 250);")
            time.sleep(random.uniform(2, 4))
    except TimeoutException:
        logger.warning("No se encontraron posts para hacer scroll")
    
    # Intentar encontrar y hacer clic en el botón "See new posts"
    try:
        see_new_posts_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "See new posts")]')))
        ActionChains(driver).move_to_element(see_new_posts_button).click(see_new_posts_button).perform()
        logger.info("Botón 'See new posts' encontrado y clicado")
        time.sleep(3)
    except TimeoutException:
        pass  # Es normal que no siempre aparezca


def load_existing_data():
    """Cargar datos existentes desde total.txt"""
    if TOTAL_FILE_PATH.exists():
        with TOTAL_FILE_PATH.open('r', encoding='utf-8') as file:
            data = {line.strip() for line in file.readlines()}
        logger.info(f"Cargados {len(data)} posts existentes")
    else:
        data = set()
        logger.info("No hay datos existentes, comenzando desde cero")
    return data


def save_new_data(new_data):
    """Guardar nuevos datos en total.txt"""
    with TOTAL_FILE_PATH.open('a', encoding='utf-8') as file:
        for entry in new_data:
            file.write(f"{entry} ***\n")
    logger.info(f"Guardados {len(new_data)} nuevos posts en {TOTAL_FILE_PATH.name}")


def save_filtered_data(filtered_data):
    """Guardar datos filtrados en filtro_laburo.txt"""
    with FILTRO_FILE_PATH.open('a', encoding='utf-8') as file:
        for entry in filtered_data:
            file.write(f"{entry} ***\n")
    logger.info(f"Guardados {len(filtered_data)} posts filtrados en {FILTRO_FILE_PATH.name}")


def decode_timestamp_from_post_id(post_id):
    """Decodificar timestamp del post ID de LinkedIn"""
    try:
        post_id_int = int(post_id)
        timestamp_ms = post_id_int >> 22
        timestamp_s = timestamp_ms / 1000
        return timestamp_s
    except (ValueError, TypeError) as e:
        logger.warning(f"Error al decodificar timestamp: {e}")
        return None


def format_timestamp(timestamp_s):
    """Formatear timestamp a string legible"""
    if timestamp_s is None:
        return "Fecha desconocida"
    try:
        local_time = datetime.fromtimestamp(timestamp_s)
        return local_time.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, OSError) as e:
        logger.warning(f"Error al formatear timestamp: {e}")
        return "Fecha desconocida"


def extract_post_data(driver, wait, existing_data):
    """Extraer datos de las publicaciones"""
    new_data = set()
    filtered_data = set()
    
    try:
        posts = wait.until(EC.presence_of_all_elements_located((By.XPATH, '//div[starts-with(@data-id, "urn:li:activity:")]')))
    except TimeoutException:
        logger.warning("No se encontraron posts")
        return new_data, filtered_data
    
    logger.info(f"Procesando {len(posts)} posts")
    
    for element in posts:
        try:
            # Obtener el data-id
            data_id = element.get_attribute('data-id')
            if data_id:
                activity_id_match = re.search(r'urn:li:activity:(\d+)', data_id)
                activity_id = activity_id_match.group(1) if activity_id_match else None
            else:
                activity_id = None
            
            # Obtener el nombre de usuario
            try:
                user_name_element = element.find_element(By.XPATH, './/span[contains(@class, "update-components-actor__title")]//span[contains(@class, "hoverable-link-text")]')
                user_name = user_name_element.text.strip()
                user_name = ' '.join(user_name.split())
                user_name = ' '.join(OrderedDict.fromkeys(user_name.split()))
            except NoSuchElementException:
                user_name = "No disponible"
            
            # Obtener la URL del perfil
            try:
                profile_url_element = element.find_element(By.XPATH, './/a[contains(@class, "update-components-actor__meta-link")]')
                profile_url = profile_url_element.get_attribute('href').split('?')[0]
                profile_url = f"Perfil: {profile_url}"
            except NoSuchElementException:
                profile_url = "Perfil: No disponible"
            
            # Obtener la descripción
            try:
                description_element = element.find_element(By.XPATH, './/div[contains(@class, "update-components-text")]//span[@dir="ltr"]')
                description = description_element.get_attribute("innerText").strip()
            except NoSuchElementException:
                description = "No disponible"
            
            # Calcular la fecha
            if activity_id:
                timestamp_s = decode_timestamp_from_post_id(activity_id)
                post_date_formatted = format_timestamp(timestamp_s)
                post_date = f"Fecha: {post_date_formatted}"
            else:
                post_date = "Fecha: No disponible"
            
            # Verificar duplicados
            user_desc = f"{user_name} - {description}"
            
            if user_desc not in existing_data:
                data_entry = f"{user_name} - {description} - {profile_url} - {post_date}"
                new_data.add(data_entry)
                existing_data.add(user_desc)
                
                # Aplicar filtro de palabras clave
                if any(word in description.lower() for word in FILTRO_LABURO):
                    logger.info(f"Post filtrado encontrado: {user_name}")
                    filtered_data.add(data_entry)
        
        except Exception as e:
            logger.error(f"Error al extraer datos de un elemento: {e}")
            continue
    
    return new_data, filtered_data


def eliminar_archivo_si_existe(file_path):
    """Eliminar archivo si existe"""
    if file_path.exists():
        file_path.unlink()
        logger.info(f"Archivo '{file_path.name}' eliminado")


def scrape_linkedin_posts(max_iterations=None):
    """Función principal para realizar el scraping"""
    # Eliminar archivo de filtro anterior
    eliminar_archivo_si_existe(FILTRO_FILE_PATH)
    
    # Configurar driver
    driver, wait = setup_driver()
    
    try:
        # Navegar a LinkedIn
        logger.info(f"Navegando a {config.LINKEDIN_URL}")
        driver.get(config.LINKEDIN_URL)
        time.sleep(3)
        
        # Check login
        check_login(driver, wait)
        
        # Cargar datos existentes
        existing_data = load_existing_data()
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        iteration = 0
        max_iter = max_iterations or config.MAX_SCROLL_ITERATIONS
        
        logger.info(f"Iniciando scraping (máximo {max_iter} iteraciones)")
        
        while iteration < max_iter:
            iteration += 1
            logger.info(f"Iteración {iteration}/{max_iter}")
            
            # Extraer datos
            new_data, filtered_data = extract_post_data(driver, wait, existing_data)
            
            # Guardar datos
            if new_data:
                save_new_data(new_data)
            
            if filtered_data:
                save_filtered_data(filtered_data)
            
            # Hacer scroll
            scroll_to_last_element(driver, wait)
            time.sleep(random.uniform(2, 3))
            
            # Verificar si llegamos al final
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                logger.info("No hay más posts para cargar")
                break
            
            last_height = new_height
        
        logger.info(f"Scraping completado. Total posts procesados: {len(existing_data)}")
    
    except KeyboardInterrupt:
        logger.info("Scraping interrumpido por el usuario")
    except Exception as e:
        logger.error(f"Error durante el scraping: {e}", exc_info=True)
        raise
    finally:
        # No cerrar el driver si detach=True
        logger.info("Proceso finalizado")


if __name__ == "__main__":
    with keep.running():
        # Ejecución completa - usa el límite de config (default 1000 iteraciones)
        scrape_linkedin_posts(max_iterations=None)
