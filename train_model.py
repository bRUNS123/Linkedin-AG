import json
import os
import re
from collections import Counter

KEYWORDS_FILE = 'job_keywords.json'
TRAINING_DATA_FILE = 'training_data.json'

def normalize_text(text):
    text = text.lower()
    # Eliminar puntuación básica y caracteres especiales
    text = re.sub(r'[^\w\s]', ' ', text)
    # Colapsar espacios
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_ngrams(words, n):
    return [" ".join(words[i:i+n]) for i in range(len(words)-n+1)]

def train():
    print("LEARN: Iniciando proceso de entrenamiento...")
    
    if not os.path.exists(TRAINING_DATA_FILE):
        print("WARN: No hay datos de entrenamiento disponibles.")
        return

    with open(TRAINING_DATA_FILE, 'r', encoding='utf-8') as f:
        training_data = json.load(f)

    if len(training_data) < 5:
        print("INFO: Pocos datos para análisis estadístico. Se requiere más feedback.")
        return

    pos_texts = []
    neg_texts = []

    for item in training_data:
        text = normalize_text(item.get('text', ''))
        # Considerar tanto el flag is_offer como los votos agregados
        votes = item.get('votes', {})
        yes = votes.get('yes', 0)
        no = votes.get('no', 0)
        
        # Un post es positivo si tiene más votos YES o si fue marcado como oferta
        if yes > no or (yes == no and item.get('is_offer')):
            pos_texts.append(text)
        elif no > yes:
            neg_texts.append(text)

    # Contadores de n-gramas
    pos_counts = Counter()
    neg_counts = Counter()
    
    # Stopwords básicas en español para ignorar ruido
    stopwords = {'de', 'la', 'que', 'el', 'en', 'y', 'a', 'los', 'del', 'se', 'las', 'por', 'un', 'para', 'con', 'no', 'una', 'su', 'es', 'al', 'lo', 'como', 'más', 'pero', 'sus', 'le', 'ya', 'o', 'este', 'sí', 'porque', 'esta', 'entre', 'cuando', 'muy', 'sin', 'sobre', 'también', 'me', 'hasta', 'hay', 'donde', 'quien', 'desde', 'todo', 'nos', 'durante', 'todos', 'uno', 'les', 'ni', 'contra', 'otros', 'ese', 'eso', 'ante', 'ellos', 'e', 'esto', 'mí', 'antes', 'algunos', 'qué', 'unos', 'yo', 'otro', 'otras', 'otra', 'él', 'tanto', 'esa', 'estos', 'mucho', 'quienes', 'nada', 'muchos', 'cual', 'poco', 'ella', 'estar', 'estas', 'algunas', 'algo', 'nosotros', 'mi', 'mis', 'tu', 'tus'}

    def process_corpus(texts, counter):
        for text in texts:
            words = [w for w in text.split() if w not in stopwords and len(w) > 2]
            # Unigramas
            counter.update(words)
            # Bigramas
            counter.update(get_ngrams(words, 2))

    process_corpus(pos_texts, pos_counts)
    process_corpus(neg_texts, neg_counts)

    # Cargar keywords actuales para no duplicar
    with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
        current_keywords = json.load(f)
    
    new_pos = set(current_keywords.get('positive', []))
    new_neg = set(current_keywords.get('negative', []))

    # Lógica de Promoción:
    # Un término se promociona si aparece en al menos 2 posts positivos 
    # y su frecuencia es al menos 3 veces mayor que en negativos.
    
    potential_pos = []
    for term, count in pos_counts.items():
        if count >= 2:
            neg_freq = neg_counts.get(term, 0)
            if count > neg_freq * 3:
                if term not in new_pos and term not in new_neg:
                    potential_pos.append(term)

    potential_neg = []
    for term, count in neg_counts.items():
        if count >= 2:
            pos_freq = pos_counts.get(term, 0)
            if count > pos_freq * 3:
                if term not in new_pos and term not in new_neg:
                    potential_neg.append(term)

    # Limitar para no saturar de una vez (Top 5 de cada)
    top_pos = sorted(potential_pos, key=lambda x: pos_counts[x], reverse=True)[:5]
    top_neg = sorted(potential_neg, key=lambda x: neg_counts[x], reverse=True)[:5]

    added_count = 0
    if top_pos:
        print(f"LEARN: Nuevas palabras clave POSITIVAS detectadas: {', '.join(top_pos)}")
        new_pos.update(top_pos)
        added_count += len(top_pos)
    
    if top_neg:
        print(f"LEARN: Nuevas palabras clave NEGATIVAS detectadas: {', '.join(top_neg)}")
        new_neg.update(top_neg)
        added_count += len(top_neg)

    if added_count > 0:
        current_keywords['positive'] = sorted(list(new_pos))
        current_keywords['negative'] = sorted(list(new_neg))
        
        with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_keywords, f, ensure_ascii=False, indent=2)
        print(f"SUCCESS: Se han incorporado {added_count} términos nuevos al sistema.")
    else:
        print("INFO: No se encontraron patrones nuevos significativos en esta sesión.")

if __name__ == "__main__":
    train()
