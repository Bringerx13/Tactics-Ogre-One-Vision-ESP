@echo off
setlocal
cd /d "%~dp0"

set "SCRIPT=Correcciones\gestionar_hashes_global.py"
set "CATALOGO=Gibbed_English_CSV\Tactics_Ogre_Proyecto_Hashes.csv"
set "NEUTRAL=Gibbed_English_CSV\Tactics_Ogre_espanol_neutral_desde_hash.csv"
set "CORRECCIONES_006=Gibbed_English_CSV\Lotes_Hashes\Tactics_Ogre_Hashes_Lote_006_correcciones.csv"
set "LOTE_TRADUCIDO=Gibbed_English_CSV\Lotes_Hashes\Tactics_Ogre_Hashes_Lote_008_traducido.csv"
set "LOTE_009=Gibbed_English_CSV\Lotes_Hashes\Tactics_Ogre_Hashes_Lote_009.csv"

if not exist "%SCRIPT%" goto error
if not exist "%CATALOGO%" goto error
if not exist "%NEUTRAL%" goto error
if not exist "%CORRECCIONES_006%" goto error
if not exist "%LOTE_TRADUCIDO%" goto error

echo [1/6] Integrando las 3 correcciones puntuales del lote 006...
python "%SCRIPT%" integrar "%CATALOGO%" "%CORRECCIONES_006%" --sobrescribir
if errorlevel 1 goto error
if exist "%CATALOGO%.bak" copy /y "%CATALOGO%.bak" "%CATALOGO%.pre_correcciones_006.bak" >nul

echo [2/6] Aplicando esas 3 correcciones al neutral...
python "%SCRIPT%" aplicar "%NEUTRAL%" "%CORRECCIONES_006%" --salida "%NEUTRAL%" --sobrescribir-existentes
if errorlevel 1 goto error
if exist "%NEUTRAL%.bak" copy /y "%NEUTRAL%.bak" "%NEUTRAL%.pre_correcciones_006.bak" >nul

echo [3/6] Integrando las traducciones nuevas del lote 008...
python "%SCRIPT%" integrar "%CATALOGO%" "%LOTE_TRADUCIDO%"
if errorlevel 1 goto error
if exist "%CATALOGO%.bak" copy /y "%CATALOGO%.bak" "%CATALOGO%.pre_lote_008.bak" >nul

echo [4/6] Aplicando el catalogo global al neutral sin sobrescribir traducciones existentes...
python "%SCRIPT%" aplicar "%NEUTRAL%" "%CATALOGO%" --salida "%NEUTRAL%"
if errorlevel 1 goto error
if exist "%NEUTRAL%.bak" copy /y "%NEUTRAL%.bak" "%NEUTRAL%.pre_aplicacion_lote_008.bak" >nul

echo [5/6] Actualizando el catalogo maestro desde el neutral...
python "%SCRIPT%" actualizar "%NEUTRAL%" "%CATALOGO%"
if errorlevel 1 goto error

echo [6/6] Exportando los siguientes 200 hashes pendientes...
python "%SCRIPT%" exportar "%CATALOGO%" --limite 200 --offset 34 --salida "%LOTE_009%"
if errorlevel 1 goto error

echo.
echo PROCESO COMPLETADO.
echo Lote 009: %LOTE_009%
echo Se conservan omitidos los 34 pendientes antiguos.
echo Se guardaron copias previas del catalogo y del neutral.
echo.
pause
exit /b 0

:error
echo.
echo ERROR. No continues con el siguiente lote.
echo.
pause
exit /b 1
