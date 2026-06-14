import re
import json
import difflib
import sys
from pathlib import Path
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

# Añadir el directorio padre al path
sys.path.append(str(Path(__file__).parent.parent))

from config import config
from src.utils import normalize_text, setup_logging

# Configurar logging
logger = setup_logging(config.LOGS_DIR)


def clean_excel_string(s: str) -> str:
    """Elimina caracteres no permitidos por Excel y recorta a 32767 caracteres."""
    if s is None:
        return ""
    s = str(s)
    s = ILLEGAL_CHARACTERS_RE.sub("", s)
    return s[:32767]


def safe_set(ws, cell_ref: str, value: str, alignment: Alignment = None, border: Border = None):
    """Asigna valor limpiando para Excel y aplicando estilo si se entrega."""
    value = clean_excel_string(value)
    ws[cell_ref] = value
    if alignment is not None:
        ws[cell_ref].alignment = alignment
    if border is not None:
        ws[cell_ref].border = border


def generate_ngrams(words, n):
    """Genera n-gramas de una lista de palabras"""
    if len(words) < n:
        return []
    return [' '.join(words[i:i+n]) for i in range(len(words) - n + 1)]


def find_similar_cargos(description: str, normalized_cargos_correctos, cargos_correctos, threshold: float = 0.95) -> str:
    """
    Busca títulos de cargo similares en la descripción usando coincidencia exacta.
    Devuelve una lista ordenada alfabéticamente y sin duplicados.
    Solo agrega cargos si hay coincidencia muy precisa.
    """
    normalized_description = normalize_text(description)
    words_in_description = normalized_description.split()
    found_cargos = set()
    
    # Buscar coincidencias exactas primero
    for idx, norm_cargo in enumerate(normalized_cargos_correctos):
        # Coincidencia exacta del cargo completo en la descripción
        if norm_cargo in normalized_description:
            found_cargos.add(cargos_correctos[idx])
            continue
    
    # Si no se encontraron coincidencias exactas, buscar con n-gramas más estrictos
    if not found_cargos:
        for n in range(2, 5):  # Solo bi, tri y cuatrigramas (más específicos)
            ngrams = generate_ngrams(words_in_description, n)
            for ngram in ngrams:
                for idx, norm_cargo in enumerate(normalized_cargos_correctos):
                    # Solo coincidencia EXACTA de palabras completas
                    cargo_words = set(norm_cargo.split())
                    ngram_words = set(ngram.split())
                    
                    # Si todas las palabras del cargo están en el ngrama
                    if cargo_words.issubset(ngram_words) or ngram_words.issubset(cargo_words):
                        # Verificar similitud alta
                        similarity = difflib.SequenceMatcher(None, norm_cargo, ngram).ratio()
                        if similarity >= threshold:
                            found_cargos.add(cargos_correctos[idx])
    
    if not found_cargos:
        return "No disponible"
    return ', '.join(sorted(found_cargos))


EMAIL_RE = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')


def find_places_in_text(text: str, normalized_place_names, normalized_place_names_map) -> str:
    """
    Busca menciones de regiones/comunas por inclusión en el texto normalizado.
    Retorna lista ordenada, sin duplicados.
    """
    found_places = set()
    normalized_text = normalize_text(text)
    
    for normalized_place in normalized_place_names:
        if normalized_place and normalized_place in normalized_text:
            original_place = normalized_place_names_map[normalized_place]
            found_places.add(original_place)
    
    if not found_places:
        return "No disponible"
    return ', '.join(sorted(found_places))


def parse_and_format_date(fecha_raw: str) -> str:
    """
    Intenta parsear 'YYYY-MM-DD HH:MM:SS' y devolver 'YYYY-MM-DD'.
    Si falla, devuelve la cadena limpia original.
    """
    fecha_raw = fecha_raw.strip()
    try:
        fecha_datetime = datetime.strptime(fecha_raw, '%Y-%m-%d %H:%M:%S')
        return fecha_datetime.strftime('%Y-%m-%d')
    except ValueError:
        return fecha_raw


def main():
    """Función principal para generar Excel"""
    logger.info("=== Iniciando generación de Excel ===")
    
    # Configurar rutas
    input_file_path = config.OUTPUT_DIR / 'filtro_laburo.txt'
    output_xlsx_path = config.OUTPUT_DIR / 'resultados_laburo.xlsx'
    
    # Verificar archivos requeridos
    required_files = [input_file_path, config.LOCALIDADES_FILE, config.CARGOS_FILE]
    for p in required_files:
        if not p.exists():
            logger.error(f"Archivo requerido no encontrado: {p.resolve()}")
            return
    
    logger.info("Todos los archivos requeridos encontrados")
    
    # Cargar localidades.json
    logger.info("Cargando localidades...")
    with config.LOCALIDADES_FILE.open('r', encoding='utf-8') as f:
        localidades_data = json.load(f)
    
    # Construir lista y mapa de lugares
    place_names = []
    for region in localidades_data.get('regions', []):
        if 'name' in region:
            place_names.append(region['name'])
        for commune in region.get('communes', []):
            if 'name' in commune:
                place_names.append(commune['name'])
    
    normalized_place_names_map = {normalize_text(p): p for p in place_names}
    normalized_place_names = list(normalized_place_names_map.keys())
    logger.info(f"Cargadas {len(place_names)} ubicaciones")
    
    # Cargar cargos correctos
    logger.info("Cargando cargos correctos...")
    with config.CARGOS_FILE.open('r', encoding='utf-8') as f:
        cargos_correctos = [line.strip() for line in f if line.strip()]
    normalized_cargos_correctos = [normalize_text(cargo) for cargo in cargos_correctos]
    logger.info(f"Cargados {len(cargos_correctos)} cargos")
    
    # Leer fuente de datos
    logger.info(f"Leyendo {input_file_path.name}...")
    with input_file_path.open('r', encoding='utf-8') as file:
        data = file.read()
    
    # Extraer campos con regex
    pattern = r'^(.*?) - (.*?) - Perfil: (.*?) - Fecha: (.*?)\s*\*\*\*$'
    matches = re.findall(pattern, data, re.MULTILINE | re.DOTALL)
    logger.info(f"Encontradas {len(matches)} publicaciones")
    
    if not matches:
        logger.warning("No se encontraron publicaciones para procesar")
        return
    
    # Preparar Excel
    logger.info("Creando archivo Excel...")
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = 'Resultados'
    
    # Estilos
    bold_font = Font(bold=True)
    alignment_center = Alignment(vertical='center', horizontal='center')
    alignment_top = Alignment(vertical='top', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Encabezados
    headers = ['Usuario', 'Descripción', 'Cargo', 'Perfil', 'Email', 'Lugar', 'Fecha']
    for col_idx, header in enumerate(headers, start=1):
        cell = worksheet.cell(row=1, column=col_idx)
        cell.value = header
        cell.font = bold_font
        cell.alignment = alignment_center
        cell.border = thin_border
    
    # Anchos de columna
    worksheet.column_dimensions['A'].width = 30
    worksheet.column_dimensions['B'].width = 80
    worksheet.column_dimensions['C'].width = 30
    worksheet.column_dimensions['D'].width = 20
    worksheet.column_dimensions['E'].width = 30
    worksheet.column_dimensions['F'].width = 30
    worksheet.column_dimensions['G'].width = 15
    
    # Congelar encabezado y filtro automático
    worksheet.freeze_panes = 'A2'
    worksheet.auto_filter.ref = f"A1:G1"
    
    # Procesar filas
    logger.info("Procesando y escribiendo filas...")
    for i, (user, description, perfil, fecha) in enumerate(matches, start=2):
        # Limpieza base
        user = ' '.join(user.strip().split())
        description = description.strip()
        perfil = perfil.strip()
        fecha = fecha.strip()
        
        # Extracciones
        lugares = find_places_in_text(description, normalized_place_names, normalized_place_names_map)
        cargos = find_similar_cargos(description, normalized_cargos_correctos, cargos_correctos)
        email_matches = EMAIL_RE.findall(description)
        email = ', '.join(email_matches) if email_matches else 'No disponible'
        fecha_formateada = parse_and_format_date(fecha)
        
        # Escribir celdas
        safe_set(worksheet, f'A{i}', user, alignment_center, thin_border)
        safe_set(worksheet, f'B{i}', description, alignment_top, thin_border)
        safe_set(worksheet, f'C{i}', cargos, alignment_center, thin_border)
        
        # Perfil como hipervínculo
        link_text = clean_excel_string('Ver Perfil')
        cell = worksheet[f'D{i}']
        cell.value = link_text
        cell.hyperlink = perfil
        cell.style = 'Hyperlink'
        cell.alignment = alignment_center
        cell.border = thin_border
        
        safe_set(worksheet, f'E{i}', email, alignment_center, thin_border)
        safe_set(worksheet, f'F{i}', lugares, alignment_center, thin_border)
        safe_set(worksheet, f'G{i}', fecha_formateada, alignment_center, thin_border)
    
    # Guardar Excel
    workbook.save(output_xlsx_path)
    logger.info(f"✅ Archivo Excel guardado en: {output_xlsx_path.resolve()}")
    print(f"\n✅ Excel generado exitosamente: {output_xlsx_path}")


if __name__ == "__main__":
    main()
