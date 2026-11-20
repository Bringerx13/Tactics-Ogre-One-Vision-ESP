# Traducción agrupada directamente sobre el CSV maestro

El CSV maestro sigue siendo el único archivo definitivo. Los bloques de trabajo también
son CSV, pero agrupan textos ingleses idénticos por hash para evitar repetir traducciones.

## Exportar el primer bloque de people.xlc

Desde la raíz del proyecto, ejecuta:

python Correcciones\exportar_bloque_unico_csv.py Tactics_Ogre_espanol_neutral_espacios.csv --archivo people.xlc --limite 200 --offset 0 --incluir-variantes --salida WarrenReport_people_lote_001.csv

Cada fila del lote representa un texto inglés único. La columna ubicaciones contiene todas
las apariciones con archivo, fila, columna, ID, NID, traducción actual y contexto anterior
y posterior. El CSV maestro no se modifica.

Para el siguiente bloque cambia offset a 200, 400, etc. Para todos los archivos de Warren
Report se puede usar --archivo WarrenReport.

## Integrar las traducciones

Una vez rellenada la columna texto_espanol_nuevo:

python Correcciones\aplicar_bloque_unico_csv.py Tactics_Ogre_espanol_neutral_espacios.csv WarrenReport_people_lote_001_traducido.csv

Por defecto se crea una copia nueva del CSV maestro. Las traducciones globales solo rellenan
celdas vacías; no sobrescriben traducciones existentes. Los grupos con más de una variante
española se omiten para revisión.

Las excepciones contextuales se guardan en la columna excepciones_por_ubicacion como una
lista JSON. Cada elemento contiene archivo, tipo, fila, columna, id_entrada, nid y
texto_espanol. Esto permite traducir apariciones específicas sin cambiar las demás.

## Normalización

Los hashes usan SHA-1 truncado a 12 caracteres sobre el inglés después de quitar solo
el encabezado span inicial y los marcadores {w}, igual que FrenchTools. El texto inglés
original nunca se modifica.
