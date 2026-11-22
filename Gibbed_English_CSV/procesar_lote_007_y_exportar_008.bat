@echo off
setlocal
cd /d "%~dp0"

set "SCRIPT=Correcciones\gestionar_hashes_global.py"
set "CATALOGO=Gibbed_English_CSV\Tactics_Ogre_Proyecto_Hashes.csv"
set "NEUTRAL=Gibbed_English_CSV\Tactics_Ogre_espanol_neutral_desde_hash.csv"
set "LOTE_TRADUCIDO=Gibbed_English_CSV\Lotes_Hashes\Tactics_Ogre_Hashes_Lote_007_traducido.csv"
set "LOTE_008=Gibbed_English_CSV\Lotes_Hashes\Tactics_Ogre_Hashes_Lote_008.csv"

if not exist "%SCRIPT%" goto error
if not exist "%CATALOGO%" goto error
if not exist "%NEUTRAL%" goto error
if not exist "%LOTE_TRADUCIDO%" goto error

echo [1/4] Integrando traducciones del lote 007...
python "%SCRIPT%" integrar "%CATALOGO%" "%LOTE_TRADUCIDO%"
if errorlevel 1 goto error

if exist "%CATALOGO%.bak" copy /y "%CATALOGO%.bak" "%CATALOGO%.pre_lote_007.bak" >nul

echo [2/4] Aplicando traducciones globalmente...
python "%SCRIPT%" aplicar "%NEUTRAL%" "%CATALOGO%" --salida "%NEUTRAL%"
if errorlevel 1 goto error

echo [3/4] Actualizando catalogo maestro...
python "%SCRIPT%" actualizar "%NEUTRAL%" "%CATALOGO%"
if errorlevel 1 goto error

echo [4/4] Exportando 200 hashes nuevos...
python "%SCRIPT%" exportar "%CATALOGO%" --limite 200 --offset 34 --salida "%LOTE_008%"
if errorlevel 1 goto error

echo.
echo PROCESO COMPLETADO.
echo Lote 008: %LOTE_008%
echo Se mantienen omitidos los 34 pendientes antiguos.
echo.
pause
exit /b 0

:error
echo.
echo ERROR. No continues con el siguiente lote.
echo.
pause
exit /b 1