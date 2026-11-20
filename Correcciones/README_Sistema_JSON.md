# Sistema JSON de traducción — Tactics Ogre One Vision ESP

El sistema agrupa las entradas por texto inglés único y conserva excepciones cuando
el género, número o contexto exige traducciones diferentes.

## 1. Migración inicial

Ejecutar una sola vez desde la raíz del repositorio:

```bat
python Correcciones\generar_sistema_json.py Tactics_Ogre_espanol_neutral_espacios.csv --salida-dir JSON_Translation
```

Esto crea o reconstruye los siguientes archivos:

- traducciones.json: mapa hash -> español. Solo incluye grupos cuya traducción actual es uniforme.
- excepciones_contexto.json: traducciones actuales por ubicación exacta cuando un mismo inglés tiene varias traducciones españolas.
- catalogo_textos.json: catálogo de textos únicos, cantidad de apariciones y todas sus ubicaciones.
- conflictos_contexto.json: variantes españolas y sus ubicaciones para revisión.
- duplicados_ubicacion.json: ubicaciones idénticas que presentan traducciones diferentes.
- resumen_migracion.txt: estadísticas de la migración.

IMPORTANTE: esta es una operación de migración inicial. No vuelvas a ejecutar el generador
después de empezar a traducir el JSON, salvo que quieras reconstruir el sistema desde el CSV
y recuperar los valores que contiene ese CSV.

## 2. Exportar bloques para traducir

Para exportar 200 textos únicos pendientes:

```bat
python Correcciones\exportar_lote_json.py --limite 200 --offset 0 --salida JSON_Translation\lote_001.json
```

Para el siguiente bloque, cambia offset a 200; luego 400, 600, etc.

Para limitar el lote a un archivo o grupo de archivos, añade por ejemplo:

```bat
python Correcciones\exportar_lote_json.py --archivo WarrenReport --limite 200 --offset 0 --salida JSON_Translation\warren_lote_001.json
```

El archivo del lote tendrá formato JSON hash -> inglés. La traducción debe conservar las claves
sin modificarlas y reemplazar cada valor inglés por su traducción española.

## 3. Incorporar un lote traducido

Cuando el lote esté traducido, guárdalo como JSON y ejecuta:

```bat
python Correcciones\fusionar_lote_json.py JSON_Translation\lote_001_traducido.json
```

El fusionador comprueba que las claves existan en el catálogo, que los valores sean cadenas
no vacías y que no se sobrescriban traducciones existentes por accidente. Crea una copia
de seguridad del diccionario antes de guardarlo.

Los textos marcados como conflicto_contexto no se incorporan como traducción global por
defecto. Para hacerlo debe usarse --permitir-conflictos y revisar sus excepciones.

## 4. Regenerar el CSV para el proceso actual

```bat
python Correcciones\aplicar_json_al_csv.py Tactics_Ogre_espanol_neutral_espacios.csv JSON_Translation\traducciones.json JSON_Translation\excepciones_contexto.json
```

Por defecto se crea Tactics_Ogre_espanol_neutral_espacios_desde_json.csv.
El CSV conserva sus columnas y ubicaciones originales, por lo que sigue siendo compatible
con el insertor actual. El CSV fuente no se modifica.

## Normalización de claves y marcadores

La clave reproduce FrenchTools/outils/export.py:
- elimina el encabezado {span ...} inicial;
- elimina {w} del cuerpo;
- conserva los demás marcadores y el texto inglés restante.

No se deben modificar los hashes. Conserva los marcadores funcionales como {np}, {pp},
{hero} y los demás códigos que formen parte del texto. No añadas manualmente {span ...}
ni {w}; FrenchTools se encarga de generarlos cuando corresponda.

Los identificadores y ubicaciones (archivo, tipo, fila, columna, id_entrada y nid) permanecen
en el catálogo y en las excepciones. El JSON reduce el trabajo de traducción; el CSV sigue
siendo la salida por ubicación para el insertor actual.
