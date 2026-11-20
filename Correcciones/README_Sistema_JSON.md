# Sistema JSON de traducción — Tactics Ogre One Vision ESP

El sistema agrupa las entradas por texto inglés único y conserva excepciones cuando
el género, número o contexto exige traducciones diferentes.

## 1. Generar los JSON

Ejecuta desde la raíz del repositorio:

```bat
python Correcciones\generar_sistema_json.py Tactics_Ogre_espanol_neutral_espacios.csv --salida-dir JSON_Translation
```

Se generan:

- traducciones.json: mapa hash -> español. Solo contiene grupos cuya traducción actual es uniforme.
- excepciones_contexto.json: traducciones por ubicación exacta para textos con variantes.
- catalogo_textos.json: textos únicos, número de apariciones y todas sus ubicaciones.
- conflictos_contexto.json: variantes españolas y ubicaciones para revisión.
- duplicados_ubicacion.json: ubicaciones idénticas con traducciones diferentes.
- resumen_migracion.txt: estadísticas.

## 2. Traducir

Edita traducciones.json. Cada clave es el SHA-1 truncado a 12 caracteres del texto inglés
normalizado. Traduce el valor una sola vez. No añadas span ni {w} manualmente.
Conserva los marcadores funcionales como {np}, {pp}, {hero} y los demás códigos que
formen parte del texto.

Para diferencias contextuales, utiliza excepciones_contexto.json. Cada excepción mantiene
el hash y la ubicación exacta (archivo, tipo, fila, columna, id_entrada y nid).

Si un grupo conflictivo debe tener una sola traducción global, elimina sus excepciones
y añade su hash a traducciones.json.

## 3. Regenerar el CSV para el proceso actual

```bat
python Correcciones\aplicar_json_al_csv.py Tactics_Ogre_espanol_neutral_espacios.csv JSON_Translation\traducciones.json JSON_Translation\excepciones_contexto.json
```

Por defecto se crea Tactics_Ogre_espanol_neutral_espacios_desde_json.csv.
El CSV conserva columnas y ubicaciones originales y sigue siendo compatible con el
insertor actual. El CSV fuente no se modifica.

## Normalización de las claves

La clave reproduce FrenchTools/outils/export.py:
- elimina el encabezado {span ...} inicial;
- elimina {w} del cuerpo;
- conserva los demás marcadores y el texto inglés restante.

Los identificadores y ubicaciones se conservan en el catálogo y las excepciones.
