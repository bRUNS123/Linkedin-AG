# OfertasLink - LinkedIn Job Scraper 🔍

Sistema automatizado de extracción y análisis de ofertas laborales de LinkedIn usando web scraping, NLP y procesamiento de datos.

## 📋 Descripción

**OfertasLink** extrae publicaciones de LinkedIn que contienen ofertas de trabajo, identifica títulos de cargos usando procesamiento de lenguaje natural (NLP), y genera reportes estructurados en Excel con información enriquecida.

## 🚀 Características

- ✅ **Scraping automático** de LinkedIn con Selenium
- ✅ **Extracción de entidades** con spaCy (modelo español)
- ✅ **Filtrado inteligente** por palabras clave laborales
- ✅ **Identificación de ubicaciones** (regiones y comunas de Chile)
- ✅ **Detección de emails** con regex
- ✅ **Reportes en Excel** con formato profesional

## 📁 Estructura del Proyecto

```
#OfertasLink/
├── src/                      # Código fuente
│   ├── scraper.py           # Scraper principal de LinkedIn
│   ├── job_extractor.py     # Extractor de cargos con NLP
│   ├── excel_generator.py   # Generador de reportes Excel
│   ├── utils.py             # Funciones utilitarias
│   └── __init__.py
├── data/                     # Datos esenciales
│   ├── localidades.json     # Regiones y comunas de Chile
│   ├── feedback_cargos.json # Feedback de validación de cargos
│   └── cargos_correctos.txt # Títulos de trabajo validados
├── output/                   # Archivos generados
├── logs/                     # Logs de ejecución
├── .env.example             # Plantilla de variables de entorno
├── .gitignore               # Archivos ignorados por Git
├── config.py                # Configuración centralizada
├── requirements.txt         # Dependencias Python
└── README.md                # Este archivo
```

## 🛠️ Instalación

### 1. Clonar el repositorio

```bash
git clone <tu-repositorio>
cd "#OfertasLink"
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Descargar modelo de spaCy

```bash
python -m spacy download es_core_news_md
```

### 4. Configurar variables de entorno

Copia `.env.example` a `.env` y configura tus credenciales:

```bash
cp .env.example .env
```

Edita `.env`:
```env
LINKEDIN_EMAIL=tu_email@gmail.com
LINKEDIN_PASSWORD=tu_password
```

> ⚠️ **Importante:** Nunca subas el archivo `.env` a Git

## 📖 Uso

### Paso 1: Scraping de LinkedIn

```bash
python src/scraper.py
```

Esto generará:
- `output/total.txt`: Todas las publicaciones extraídas
- `output/filtro_laburo.txt`: Solo publicaciones con keywords laborales

### Paso 2: Extracción de Cargos

```bash
python src/job_extractor.py
```

El sistema te pedirá validar títulos de trabajo encontrados.

### Paso 3: Generar Reporte Excel

```bash
python src/excel_generator.py
```

Esto creará `output/resultados_laburo.xlsx` con columnas:
- Usuario
- Descripción
- Cargo
- Perfil (link a LinkedIn)
- Email
- Lugar
- Fecha

## 🔧 Configuración

Edita `config.py` para ajustar parámetros:

```python
MAX_SCROLL_ITERATIONS = 1000  # Número máximo de scrolls
CHUNK_SIZE = 200000           # Tamaño de chunks para procesamiento
```

## 📊 Tecnologías

- **Python 3.x**
- **Selenium** - Automatización web
- **spaCy** - Procesamiento de lenguaje natural
- **openpyxl** - Generación de archivos Excel
- **wakepy** - Mantener sistema activo durante scraping
- **python-dotenv** - Gestión de variables de entorno

## ⚖️ Consideraciones Legales

> ⚠️ **Advertencia:** El scraping de LinkedIn puede violar sus Términos de Servicio. 
> 
> Este proyecto es solo para fines educativos. Considera usar:
> - [LinkedIn Jobs API](https://developer.linkedin.com/) (oficial)
> - APIs de agregadores públicos (Indeed, Glassdoor)

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit tus cambios (`git commit -am 'Añadir nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Abre un Pull Request

## 📝 Licencia

Este proyecto es de código abierto y está disponible bajo la licencia MIT.

## 📧 Contacto

Para preguntas o soporte, abre un issue en GitHub.

---

**Última actualización:** 2025-12-26
