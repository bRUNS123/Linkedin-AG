"""
contact_matcher.py
Cruza autores de posts con la red de contactos del usuario (Connections.csv de LinkedIn).
"""
import csv
import os
import re

CONNECTIONS_FILE = os.path.join("SourceLINK", "Connections.csv")

_contacts_cache = None

def _normalize(name):
    """Normaliza un nombre para comparación flexible."""
    if not name:
        return ""
    name = name.lower().strip()
    # Quitar acentos
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u', 'ä': 'a', 'ö': 'o'
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    # Quitar caracteres especiales
    name = re.sub(r'[^a-z0-9\s]', '', name)
    # Quitar espacios múltiples
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def load_contacts():
    """Carga contactos desde Connections.csv y retorna un dict {nombre_normalizado: datos}."""
    global _contacts_cache
    if _contacts_cache is not None:
        return _contacts_cache

    contacts = {}
    if not os.path.exists(CONNECTIONS_FILE):
        print(f"WARN: No se encontró {CONNECTIONS_FILE}")
        _contacts_cache = contacts
        return contacts

    try:
        with open(CONNECTIONS_FILE, 'r', encoding='utf-8') as f:
            # Saltar las primeras 3 líneas (notas de LinkedIn)
            lines = f.readlines()

        # Encontrar la línea del header
        header_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith("First Name,"):
                header_idx = i
                break

        if header_idx is None:
            print("WARN: No se encontró header en Connections.csv")
            _contacts_cache = contacts
            return contacts

        # Parsear CSV desde el header
        csv_text = ''.join(lines[header_idx:])
        reader = csv.DictReader(csv_text.splitlines())

        for row in reader:
            first = (row.get('First Name') or '').strip()
            last = (row.get('Last Name') or '').strip()
            company = (row.get('Company') or '').strip()
            position = (row.get('Position') or '').strip()
            url = (row.get('URL') or '').strip()
            email = (row.get('Email Address') or '').strip()

            if not first and not last:
                continue

            full_name = f"{first} {last}".strip()
            key = _normalize(full_name)

            contacts[key] = {
                'name': full_name,
                'company': company,
                'position': position,
                'url': url,
                'email': email
            }

            # También guardar variantes parciales para matching flexible
            # Ej: "Bruno Franco" además de "Bruno Alonso Franco Sentis"
            if first:
                first_key = _normalize(first)
                if last:
                    last_key = _normalize(last)
                    # first + last (sin segundo nombre/apellido)
                    short_key = f"{first_key} {last_key.split()[-1]}" if last_key else first_key
                    if short_key != key and len(short_key) > 5:
                        contacts.setdefault(short_key, contacts[key])

        print(f"LOG: {len(contacts)} contactos cargados desde SourceLINK.")

    except Exception as e:
        print(f"ERROR cargando contactos: {e}")

    _contacts_cache = contacts
    return contacts


def match_author(author_name):
    """
    Busca si el autor de un post es parte de la red de contactos.
    Retorna dict con datos del contacto si hay match, o None.
    """
    contacts = load_contacts()
    if not contacts or not author_name:
        return None

    author_norm = _normalize(author_name)

    # Match exacto
    if author_norm in contacts:
        return contacts[author_norm]

    # Match parcial: el nombre del autor contiene o está contenido en un contacto
    for contact_key, contact_data in contacts.items():
        if len(contact_key) < 5 or len(author_norm) < 5:
            continue
        # Si comparten al menos nombre + apellido
        author_parts = set(author_norm.split())
        contact_parts = set(contact_key.split())
        common = author_parts & contact_parts
        # Al menos 2 palabras en común y al menos el 50% del nombre más corto
        min_len = min(len(author_parts), len(contact_parts))
        if len(common) >= 2 and len(common) >= min_len * 0.5:
            return contact_data

    return None


def is_spam_author(author_name, contacts=None):
    """
    Detecta si un autor es un spammer conocido (asesores de isapre, AFP, etc.)
    basándose en su cargo en la red de contactos.
    """
    if contacts is None:
        contacts = load_contacts()

    match = match_author(author_name)
    if not match:
        return False, None

    position = (match.get('position') or '').lower()
    spam_positions = [
        'asesor de salud', 'asesora de salud',
        'asesor previsional', 'asesora previsional',
        'asesor isapre', 'asesora isapre',
        'asesor comercial', 'asesora comercial',
        'ejecutivo comercial', 'ejecutiva comercial',
        'corredor de seguros', 'corredora de seguros',
        'agente de ventas',
        'consultor previsional', 'consultora previsional',
    ]

    for spam_pos in spam_positions:
        if spam_pos in position:
            return True, match.get('position')

    return False, None


if __name__ == "__main__":
    contacts = load_contacts()
    print(f"\nTotal contactos: {len(contacts)}")
    # Test
    test_names = ["Bruno Franco", "Catalina Leiva", "Rodrigo Aqueveque"]
    for name in test_names:
        result = match_author(name)
        if result:
            print(f"  ✅ '{name}' -> {result['name']} @ {result['company']}")
        else:
            print(f"  [NO] '{name}' -> No encontrado")
