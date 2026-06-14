@echo off
title LinkedIn-AG - Scraper Automatico
color 0B
cls

set "LINKEDIN_DIR=C:\Users\Usuario\Desktop\Programacion\Linkedin-AG"
set "LOG_FILE=%LINKEDIN_DIR%\scrap_log.txt"

echo [%date% %time%] Iniciando LinkedIn scraper... >> "%LOG_FILE%"
echo.
echo  ===================================
echo   LinkedIn-AG Scraper
echo   Iniciando...
echo  ===================================
echo.

cd /d "%LINKEDIN_DIR%"

:: Verificar sesion
if exist "linkedin_state.json" (
    echo [%date% %time%] Sesion encontrada, iniciando scraper headless >> "%LOG_FILE%"
    echo Sesion detectada - ejecutando scraper...
    python scrap.py >> "%LOG_FILE%" 2>&1
    echo [%date% %time%] Scraper finalizado (codigo: %errorlevel%) >> "%LOG_FILE%"
) else (
    echo [%date% %time%] ERROR: No hay linkedin_state.json - necesita login manual >> "%LOG_FILE%"
    echo ADVERTENCIA: No se encontro sesion guardada.
    echo Ejecuta scrap.py manualmente para hacer login primero.
    pause
)
