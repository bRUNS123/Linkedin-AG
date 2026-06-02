import json

with open('extracted_posts_with_locations.json', 'r', encoding='utf-8') as f:
    posts = json.load(f)

offers = [p for p in posts if p.get('job_prediction', {}).get('is_offer')]
structural = [p for p in posts if p.get('job_prediction', {}).get('is_structural')]
emails_posts = [p for p in posts if p.get('job_prediction', {}).get('emails')]

print(f"Total posts analizados: {len(posts)}")
print(f"Ofertas laborales: {len(offers)}")
print(f"Ofertas estructurales: {len(structural)}")
print(f"Posts con correos: {len(emails_posts)}")
print()

print("=== EJEMPLOS DE OFERTAS CON CORREOS ===")
for p in emails_posts[:2]:
    pred = p['job_prediction']
    print(f"Autor: {p.get('author')}")
    print(f"Correos: {pred.get('emails')}")
    print(f"Texto: {p.get('text')[:200]}...")
    print("---")
