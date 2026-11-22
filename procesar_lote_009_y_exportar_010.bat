@echo off
setlocal
cd /d "%~dp0"

set "SCRIPT=Correcciones\gestionar_hashes_global.py"
set "CATALOGO=Gibbed_English_CSV\Tactics_Ogre_Proyecto_Hashes.csv"
set "NEUTRAL=Gibbed_English_CSV\Tactics_Ogre_espanol_neutral_desde_hash.csv"
set "LOTE_TRADUCIDO=Gibbed_English_CSV\Lotes_Hashes\Tactics_Ogre_Hashes_Lote_009_traducido.csv"
set "LOTE_010=Gibbed_English_CSV\Lotes_Hashes\Tactics_Ogre_Hashes_Lote_010.csv"

if not exist "%SCRIPT%" goto error
if not exist "%CATALOGO%" goto error
if not exist "%NEUTRAL%" goto error
if not exist "%LOTE_TRADUCIDO%" goto error
if exist "%LOTE_010%" goto lote_existe

echo [1/4] Integrando las traducciones del lote 009 al catalogo maestro...
python "%SCRIPT%" integrar "%CATALOGO%" "%LOTE_TRADUCIDO%"
if errorlevel 1 goto error
if exist "%CATALOGO%.bak" copy /y "%CATALOGO%.bak" "%CATALOGO%.pre_lote_009.bak" >nul

echo [2/4] Aplicando las traducciones globales al neutral...
python "%SCRIPT%" aplicar "%NEUTRAL%" "%CATALOGO%" --salida "%NEUTRAL%"
if errorlevel 1 goto error
if exist "%NEUTRAL%.bak" copy /y "%NEUTRAL%.bak" "%NEUTRAL%.pre_aplicacion_lote_009.bak" >nul

echo [3/4] Actualizando el catalogo maestro desde el neutral...
python "%SCRIPT%" actualizar "%NEUTRAL%" "%CATALOGO%"
if errorlevel 1 goto error

echo [4/4] Exportando los siguientes 200 hashes pendientes...
python "%SCRIPT%" exportar "%CATALOGO%" --limite 200 --offset 34 --salida "%LOTE_010%"
if errorlevel 1 goto error

echo.
echo PROCESO COMPLETADO.
echo Lote 010: %LOTE_010%
echo Se mantienen omitidos los 34 pendientes antiguos.
echo Se guardaron copias previas del catalogo y del neutral.
echo.
pause
exit /b 0

:lote_existe
echo.
echo ERROR: Ya existe "%LOTE_010%".
echo No se sobrescribio el archivo existente. Comprueba su contenido antes de continuar.
echo.
pause
exit /b 1

:error
echo.
echo ERROR. No continues con el siguiente lote.
echo Revisa el mensaje anterior antes de volver a ejecutar el BAT.
echo.
pause
exit /b 1
