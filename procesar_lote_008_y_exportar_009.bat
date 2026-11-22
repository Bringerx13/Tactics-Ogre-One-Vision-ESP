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

echo [1/5] Actualizando las 3 correcciones del lote 006...
python "%SCRIPT%" integrar "%CATALOGO%" "%CORRECCIONES_006%" --sobrescribir
if errorlevel 1 goto error
if exist "%CATALOGO%.bak" copy /y "%CATALOGO%.bak" "%CATALOGO%.pre_correcciones_006.bak" >nul

echo [2/5] Integrando las traducciones nuevas del lote 008...
python "%SCRIPT%" integrar "%CATALOGO%" "%LOTE_TRADUCIDO%"
if errorlevel 1 goto error
if exist "%CATALOGO%.bak" copy /y "%CATALOGO%.bak" "%CATALOGO%.pre_lote_008.bak" >nul

echo [3/5] Aplicando las traducciones globalmente al CSV neutral...
python "%SCRIPT%" aplicar "%NEUTRAL%" "%CATALOGO%" --salida "%NEUTRAL%"
if errorlevel 1 goto error

echo [4/5] Actualizando el catalogo maestro desde el neutral...
python "%SCRIPT%" actualizar "%NEUTRAL%" "%CATALOGO%"
if errorlevel 1 goto error

echo [5/5] Exportando los siguientes 200 hashes pendientes...
python "%SCRIPT%" exportar "%CATALOGO%" --limite 200 --offset 34 --salida "%LOTE_009%"
if errorlevel 1 goto error

echo.
echo PROCESO COMPLETADO.
echo Lote 009: %LOTE_009%
echo Se conservan omitidos los 34 pendientes antiguos.
echo Copias previas: catalogo.pre_correcciones_006.bak y catalogo.pre_lote_008.bak
echo.
pause
exit /b 0

:error
echo.
echo ERROR. No continues con el siguiente lote.
echo.
pause
exit /b 1
