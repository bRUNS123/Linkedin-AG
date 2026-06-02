import json
import re
import os
import time
import google.generativeai as genai

# Setup Gemini AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # Configure the model
    generation_config = {
        "temperature": 0.1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "application/json",
    }
    ai_model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config=generation_config,
    )
else:
    ai_model = None

def analyze_with_ai(text):
    """
    Llama a Gemini para validar si el texto es realmente una oferta laboral
    y extraer datos clave como rol y empresa.
    """
    if not ai_model:
        return None
        
    prompt = f"""
    Eres un experto analista de reclutamiento. Lee la siguiente publicación de LinkedIn.
    Tu objetivo es determinar SI ES UNA OFERTA DE TRABAJO (alguien contratando) 
    O SI ES ALGUIEN BUSCANDO EMPLEO (no es una oferta).
    
    Además, detecta si es una oferta relacionada a INGENIERIA CIVIL ESTRUCTURAL (cálculo estructural, modelado estructural, revisor estructural, revisor sismico, dibujante estructural).
    
    Publicación:
    \"\"\"{text}\"\"\"
    
    Responde ÚNICAMENTE con un objeto JSON válido con la siguiente estructura exacta:
    {{
      "is_offer": booleano (true si es una empresa/persona publicando una vacante real, false si es alguien buscando trabajo o publicidad),
      "is_structural": booleano (true si el puesto es de ingeniería civil estructural, calculista, o dibujante estructural),
      "role": "Nombre del cargo ofrecido o null si no se detecta",
      "company": "Nombre de la empresa que contrata o null si no se detecta"
    }}
    """
    try:
        response = ai_model.generate_content(prompt)
        # Parse json
        result = json.loads(response.text)
        return result
    except Exception as e:
        print(f"Error AI: {e}")
        return None

def normalize_text(text):
    """Normaliza texto: minúsculas, sin acentos"""
    if not text: return ""
    text = text.lower()
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def detect_job_offer(text, keywords, user_vote=None):
    """
    Analiza el texto y determina si es una oferta laboral.
    Considera keywords y votos de usuario.
    Retorna score, boolean y keywords encontradas.
    """
    text_norm = normalize_text(text)
    
    found_positive = []
    found_negative = []
    
    # Buscar keywords positivas
    for kw in keywords['positive']:
        kw_norm = normalize_text(kw)
        if kw_norm in text_norm:
            found_positive.append(kw)
            
    # Buscar keywords negativas
    for kw in keywords['negative']:
        kw_norm = normalize_text(kw)
        if kw_norm in text_norm:
            found_negative.append(kw)
            
    # Calcular score de keywords (0 a 1)
    # Partimos de 0.0 (No es oferta)
    # Cada palabra positiva suma 0.3, cada negativa penaliza
    keyword_score = 0
    if found_positive:
        keyword_score += len(found_positive) * 0.4 # Subimos un poco el impacto
    if found_negative:
        keyword_score -= len(found_negative) * 0.6
    
    # Clamp inicial del keyword score para que sea una "base" razonable
    # Si tiene muchas negativas, bajará a 0 rápidamente
    keyword_score = max(0.0, min(keyword_score, 1.0))
    
    # Integrar voto de usuario (ponderación dinámica)
    # Si hay voto, le damos peso basado en la cantidad de votos (confianza)
    
    final_score = keyword_score
    vote_val = 0
    has_vote = False
    
    # Check if user_vote is the new dict format or legacy boolean
    yes_votes = 0
    no_votes = 0
    
    if user_vote is not None:
        has_vote = True
        if isinstance(user_vote, dict):
            yes_votes = user_vote.get('yes', 0)
            no_votes = user_vote.get('no', 0)
        elif isinstance(user_vote, bool):
            yes_votes = 1 if user_vote else 0
            no_votes = 1 if not user_vote else 0
            
        total_votes = yes_votes + no_votes
        
        if total_votes > 0:
            # Puntuación Asintótica (Suavizado de Laplace modificado)
            # Esto asegura que con 0 votos SIEMPRE haya un mínimo, 
            # y con muchos votos se acerque a 0 o 1 sin tocarlo.
            # Ejemplo: 0 yes, 20 total -> 0.05 / 20.1 = 0.0024 (0.24%)
            # Ejemplo: 0 yes, 1000 total -> 0.05 / 1000.1 = 0.00005 (0.005%)
            asymptotic_ratio = (yes_votes + 0.05) / (total_votes + 0.1)
            
            # Peso de los votos (Confianza)
            vote_weight = 0.8
            if total_votes >= 3:
                vote_weight = 0.95
            
            # Blending: (Ratio * Peso) + (BaseKeywords * (1-Peso))
            keyword_weight = 1.0 - vote_weight
            final_score = (asymptotic_ratio * vote_weight) + (keyword_score * keyword_weight)
            
            vote_val = asymptotic_ratio
    
    # Asegurar rango 0.0 a 1.0 (aunque la f(x) anterior ya lo garantiza)
    final_score = max(1e-6, min(final_score, 0.999999))
    is_offer = final_score > 0.4 

    structural_terms = ["estructural", "calculista", "cálculo estructural", "diseño estructural", "memoria de cálculo", "modelador estructural", "estructuras"]
    is_structural = any(term in text_norm for term in structural_terms)
    
    ai_role = None
    ai_company = None
    used_ai = False

    # INTEGRACIÓN DE GEMINI AI (Pre-filtro: solo enviar si final_score > 0.15)
    if final_score > 0.15 and ai_model:
        ai_prediction = analyze_with_ai(text)
        if ai_prediction:
            used_ai = True
            is_offer = ai_prediction.get("is_offer", is_offer)
            is_structural = ai_prediction.get("is_structural", is_structural)
            ai_role = ai_prediction.get("role")
            ai_company = ai_prediction.get("company")
            # Ajustar score visual basado en la certeza de la IA
            final_score = 0.95 if is_offer else 0.05
            
            # Rate limiting prevention para capa gratuita
            time.sleep(4.5)

    # Detección de Emails - Regex profesional robusto
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    found_emails = list(set(re.findall(email_pattern, text, re.IGNORECASE)))
    
    # Limpieza: quitar posibles comas o puntos al final pegados al email
    found_emails = [e.rstrip('.,') for e in found_emails]

    return {
        "is_offer": is_offer,
        "is_structural": is_structural,
        "score": round(final_score, 2),
        "found_positive": found_positive,
        "found_negative": found_negative,
        "has_vote": has_vote,
        "vote_val": vote_val,
        "emails": found_emails,
        "ai_verified": used_ai,
        "role": ai_role,
        "company": ai_company
    }

def process_posts():
    print("LOG: Cargando archivos...")
    
    try:
        with open('job_keywords.json', 'r', encoding='utf-8') as f:
            keywords = json.load(f)
            
        input_file = 'extracted_posts_with_locations.json' 
        with open(input_file, 'r', encoding='utf-8') as f:
            posts = json.load(f)
            
        # Cargar datos de entrenamiento (votos)
        training_data = []
        if os.path.exists('training_data.json'):
            with open('training_data.json', 'r', encoding='utf-8') as f:
                training_data = json.load(f)
        
        # Crear mapa de votos para búsqueda rápida: "author|text_start" -> vote (bool)
        vote_map = {}
        for item in training_data:
            key = f"{item.get('author', '')}|{item.get('text', '')[:50]}"
            vote_map[key] = item.get('is_offer')
            
        print(f"INFO: {len(posts)} posts cargados")
        print(f"INFO: {len(training_data)} votos de usuario cargados")
        print("INFO: Analizando ofertas laborales con ponderación...")
        
        offers_count = 0
        
        for i, post in enumerate(posts):
            # Buscar si este post tiene voto
            key = f"{post.get('author', '')}|{post.get('text', '')[:50]}"
            user_vote = vote_map.get(key)
            
            result = detect_job_offer(post['text'], keywords, user_vote)
            
            post['job_prediction'] = result
            
            if result['is_offer']:
                offers_count += 1
                
            if (i + 1) % 2000 == 0:
                print(f"Progress: {i + 1}/{len(posts)}")
        
        print(f"\nSUCCESS: Análisis completado!")
        print(f"STATS: Ofertas detectadas: {offers_count}/{len(posts)} ({offers_count/len(posts)*100:.1f}%)")
        
        output_file = 'extracted_posts_with_locations.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
            
        print(f"SAVE: Archivo actualizado: {output_file}")
        
    except FileNotFoundError as e:
        print(f"❌ Error: No se encontró el archivo {e.filename}")

if __name__ == "__main__":
    process_posts()

