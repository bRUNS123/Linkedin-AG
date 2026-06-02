import re

def test_email_extraction():
    # User's provided text snippet
    text = """🎨 INACAP Apoquindo busca Docente de Diseño 🚀 En INACAP Sede Apoquindo estamos en búsqueda de docentes del área de Diseño para incorporarse desde marzo 2026, en asignaturas vinculadas a la creación digital, multimedia y animación. 📚 Asignaturas a dictar: Diseño Digital 3D Efectos Visuales en Animación Digital Laboratorio Digital Diseño 2D Laboratorio Digital Multimedia Laboratorio Digital Personajes Animados Programación Visual Taller de Diseño Multimedia 🔎 Buscamos profesionales con experiencia en diseño digital, animación, multimedia y/o programación visual, con interés genuino por la docencia y la formación de futuros profesionales. Valoramos el dominio técnico, la creatividad y la capacidad de trabajar con estudiantes en contextos prácticos y aplicados. 📍 Lugar: INACAP Sede Apoquindo 📅 Inicio: Marzo 2026 📩 Postulación: Enviar CV actualizado a mgosselin@inacap.cl , indicando en el asunto “Postulación Docente Diseño – Apoquindo”. Si conoces a alguien que calce perfecto con este perfil, ¡comparte esta publicación! El talento se mueve mejor en red 😉 … más"""
    
    # Current regex in dashboard.html (JavaScript style translated to Python)
    # \b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b
    js_equivalent_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    found_js = re.findall(js_equivalent_pattern, text, re.IGNORECASE)
    print(f"JS-Equivalent Regex Found: {found_js}")
    
    # Improved test regex
    improved_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+'
    found_improved = re.findall(improved_pattern, text, re.IGNORECASE)
    print(f"Improved Regex Found: {found_improved}")

if __name__ == "__main__":
    test_email_extraction()
