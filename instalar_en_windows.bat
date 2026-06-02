@echo off
echo ========================================================
echo  INSTALADOR DE LINKEDIN SCRAPER - WINDOWS
echo ========================================================
echo.
echo 1. Instalando librerias de Python...
pip install -r requirements.txt

echo.
echo 2. Descargando el cerebro local (spaCy NLP en espanol)...
python -m spacy download es_core_news_sm

echo.
echo 3. Instalando navegadores internos (Playwright)...
playwright install

echo.
echo ========================================================
echo  INSTALACION COMPLETADA
echo  Si no hubo errores, ya puedes ejecutar el bot.
echo  Para que inicie automaticamente con Windows, 
echo  haz doble clic en "setup_startup.py".
echo ========================================================
pause
