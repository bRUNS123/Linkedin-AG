import json

def deduplicate():
    file_path = 'extracted_posts.json'
    
    print(f"📂 Cargando {file_path}...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            posts = json.load(f)
    except FileNotFoundError:
        print("❌ Archivo no encontrado.")
        return

    print(f"📊 Total posts antes de limpieza: {len(posts)}")
    
    unique_ids = set()
    cleaned_posts = []
    duplicates_count = 0
    
    for post in posts:
        # Clave única basada en autor y fragmento largo de texto
        # Normalizamos espacios y saltos de línea para comparar mejor
        author = post.get('author', '').strip().lower()
        text_sample = " ".join(post.get('text', '').split())[:500].lower()
        
        unique_key = (author, text_sample)
        
        if unique_key not in unique_ids:
            unique_ids.add(unique_key)
            cleaned_posts.append(post)
        else:
            duplicates_count += 1
            
    print(f"♻️ Duplicados encontrados y removidos: {duplicates_count}")
    print(f"✅ Total posts finales: {len(cleaned_posts)}")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(cleaned_posts, f, ensure_ascii=False, indent=2)
        
    print(f"💾 Archivo Maestro '{file_path}' actualizado exitosamente.")

if __name__ == "__main__":
    deduplicate()
