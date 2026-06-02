import json
import re
from difflib import SequenceMatcher

def normalize_text(text):
    """Normaliza texto: minúsculas, sin acentos"""
    if not text: return ""
    text = text.lower()
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u', 'à': 'a'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def fuzzy_match(word, target, threshold=0.88): # Umbral alto para evitar falsos positivos
    """
    Compara palabra del texto con palabra objetivo (ej: comuna).
    """
    word = normalize_text(word)
    target = normalize_text(target)
    
    if not word or not target: return False
    
    # 1. Coincidencia exacta
    if word == target:
        return True
        
    # 2. Si la palabra objetivo es muy corta (menos de 4 letras), solo permitir exacta
    if len(target) < 4:
        return False
        
    # 3. Fuzzy matching para errores tipográficos (ej: Atacma vs Atacama)
    # Solo verificar si las longitudes son similares (ej: no buscar "S" en "Santiago")
    len_diff = abs(len(word) - len(target))
    if len_diff > 2: # Si difieren mucho en largo, probablemente no es la misma palabra
        return False
        
    ratio = SequenceMatcher(None, word, target).ratio()
    return ratio >= threshold

def find_locations_in_text(text, localidades):
    found_regions = set()
    found_communes = []
    
    # Normalizar texto completo y dividir en palabras limpias
    text_norm = normalize_text(text)
    # Mantener solo caracteres alfanumericos y espacios para tokenizar
    text_clean = re.sub(r'[^a-z0-9\s]', ' ', text_norm)
    words = text_clean.split()
    
    # Convertir palabras a set para búsqueda rápida exacta inicial
    words_set = set(words)
    
    for region in localidades['regions']:
        region_name = region['name']
        region_norm = normalize_text(region_name)
        
        match_region = False
        
        # 1. Buscar nombre de región completo en el texto (ej: "metropolitana de santiago")
        if region_norm in text_norm:
            match_region = True
        else:
            # 2. Buscar palabras clave de la región (ej: "Atacama")
            # Ignorar palabras comunes como "region", "del", "de", "y", "los", "las"
            keywords = [w for w in region_norm.split() if len(w) > 3 and w not in ['gral', 'carlos', 'ibanez', 'campo']]
            
            for kw in keywords:
                # Buscar kw en las palabras del texto (exacta o fuzzy)
                for w in words:
                    if fuzzy_match(w, kw):
                        match_region = True
                        break
                if match_region: break
        
        if match_region:
            found_regions.add(region_name)
            
        # Buscar comunas de esta región
        for commune in region['communes']:
            commune_name = commune['name']
            commune_norm = normalize_text(commune_name)
            
            match_commune = False
            
            # 1. Buscar nombre multi-palabra exacto (ej: "San Pedro de Atacama")
            if " " in commune_norm:
                if commune_norm in text_norm:
                    match_commune = True
            else:
                # 2. Buscar nombre uni-palabra (exacta o fuzzy)
                # Primero chequear si está en el set de palabras (rápido)
                if commune_norm in words_set: # Coincidencia exacta
                    match_commune = True
                else:
                    # Búsqueda fuzzy palabra por palabra
                    for w in words:
                        if fuzzy_match(w, commune_norm, threshold=0.90): # Umbral estricto para comunas
                            match_commune = True
                            break
            
            if match_commune:
                # Verificar duplicados
                if not any(c['commune'] == commune_name for c in found_communes):
                    found_communes.append({
                        'commune': commune_name,
                        'region': region_name
                    })
                    # Si encontramos una comuna, implícitamente es la región
                    found_regions.add(region_name)

    return list(found_regions), found_communes

def process_posts():
    print("📍 Cargando datos...")
    with open('localidades.json', 'r', encoding='utf-8') as f:
        localidades = json.load(f)
    
    with open('extracted_posts.json', 'r', encoding='utf-8') as f:
        posts = json.load(f)
        
    print(f"🔍 Procesando {len(posts)} posts con algoritmo mejorado...")
    
    count_located = 0
    for i, post in enumerate(posts):
        regions, communes = find_locations_in_text(post['text'], localidades)
        post['locations'] = {
            'regions': regions,
            'communes': communes
        }
        if regions or communes:
            count_located += 1
            
        if (i+1) % 2000 == 0:
            print(f"   Progreso: {i+1}/{len(posts)}")
            
    print(f"✅ Finalizado. {count_located} posts con ubicación detectada.")
    
    with open('extracted_posts_with_locations.json', 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    process_posts()
