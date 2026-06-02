import json
import csv
import os

input_file = 'extracted_posts_with_locations.json'
output_file = 'Ofertas_Estructurales.csv'

def main():
    if not os.path.exists(input_file):
        print(f"❌ Error: Archivo {input_file} no encontrado. Ejecuta scrap.py y detect_jobs.py primero.")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        try:
            posts = json.load(f)
        except json.JSONDecodeError:
            print(f"❌ Error: El archivo {input_file} no tiene un formato JSON válido.")
            return

    structural_offers = []
    total_emails_found = 0

    for post in posts:
        prediction = post.get('job_prediction', {})
        # Queremos ofertas (is_offer=True) y que sean estructurales (is_structural=True)
        is_offer = prediction.get('is_offer', False)
        is_structural = prediction.get('is_structural', False)
        
        if is_offer and is_structural:
            emails = prediction.get('emails', [])
            total_emails_found += len(emails)
            
            author = post.get('author', 'Desconocido')
            profile_url = post.get('profile_url', '')
            time_posted = post.get('time_posted', '')
            text = post.get('text', '').replace('\n', ' ')
            
            # Si hay varios emails, creamos una fila por email o los unimos con coma.
            # Los unimos con coma para mantener 1 fila = 1 oferta
            emails_str = ", ".join(emails)
            
            structural_offers.append({
                'Autor': author,
                'URL Perfil': profile_url,
                'Correos': emails_str,
                'Fecha Publicacion': time_posted,
                'Texto Oferta': text
            })

    if not structural_offers:
        print("⚠️ No se encontraron ofertas estructurales en los datos analizados.")
        return

    # Escribir a CSV
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Autor', 'URL Perfil', 'Correos', 'Fecha Publicacion', 'Texto Oferta'])
        writer.writeheader()
        writer.writerows(structural_offers)

    print(f"Exito! Se encontraron {len(structural_offers)} ofertas estructurales.")
    print(f"Total de correos extraídos: {total_emails_found}")
    print(f"Guardado en: {output_file}")

if __name__ == "__main__":
    main()
