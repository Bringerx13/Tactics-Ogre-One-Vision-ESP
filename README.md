# Tactics Ogre: Let Us Cling Together — One Vision (PSP)
## Traducción al español neutro

Proyecto de traducción no oficial al español neutro de **Tactics Ogre: Let Us Cling Together para PSP**, compatible con la modificación **One Vision** de raics.

La descarga pública se distribuirá como un parche **xdelta**. No se distribuyen imágenes ISO ni archivos originales del juego.

## Descargar

**[Descargar la última versión desde GitHub Releases](https://github.com/Bringerx13/Tactics-Ogre-One-Vision-ESP/releases/latest)**

En la sección *Assets* de la publicación, descarga el archivo `.xdelta` correspondiente a la versión que quieras instalar.

## Requisitos

- Una copia propia de **Tactics Ogre: Let Us Cling Together para PSP**.
- La modificación **One Vision** ya aplicada.
- La misma edición, región y revisión de la ISO inglesa que se utilizó como archivo de origen al crear el parche. El parche no está pensado para aplicarse sobre una ISO sin modificar, una versión distinta de One Vision ni **Tactics Ogre: Reborn**.
- **Delta Patcher** para Windows: [GitHub — Delta Patcher](https://github.com/marco-calautti/DeltaPatcher/releases).

> **Importante:** un parche xdelta depende de la ISO de origen exacta. Si Delta Patcher indica que el archivo original no coincide, no fuerces la aplicación: comprueba que estás usando la ISO inglesa de One Vision correcta.

## Instalación

1. Haz una copia de seguridad de tu ISO original de One Vision.
2. Descarga el parche `.xdelta` desde [Releases](https://github.com/Bringerx13/Tactics-Ogre-One-Vision-ESP/releases/latest).
3. Abre Delta Patcher y selecciona:
   - **Original file:** tu ISO inglesa de Tactics Ogre con One Vision ya aplicado.
   - **XDelta patch:** el archivo `.xdelta` descargado.
   - **Output file:** el nombre y la ubicación donde guardarás la ISO en español.
4. Aplica el parche y espera a que termine el proceso.
5. Abre la ISO resultante en PPSSPP o en el dispositivo compatible que utilices.

No compartas ni descargues ISOs pretraducidas de terceros: el parche está diseñado para aplicarse a una copia propia del juego.

## Compatibilidad con el HD UI Pack en PPSSPP

El HD UI Pack es independiente del parche de traducción y debe instalarse por separado. Para que el texto del menú principal mantenga la textura HD en la versión española, conserva `ignoreAddress = false` en el `textures.ini` del pack y añade las siguientes entradas en sus secciones correspondientes.

En **[hashes]**:

```ini
095d311007f80e0abb0f539f = ui/titlescreentext.png
```

En **[hashranges]**:

```ini
0x095d3110, 256, 128 = 256, 72
```

No cambies globalmente `ignoreAddress` a `true`: esa opción impide que muchas de las texturas del pack coincidan correctamente.

## Alcance

Esta modificación distribuye la traducción al español neutro de los textos del juego y de One Vision incluidos en el parche, entre ellos menús, nombres y descripciones de objetos, clases, habilidades, magia, mensajes y textos del Warren Report.

One Vision es una modificación de equilibrio y contenido creada por **raics**. Este proyecto no es una nueva versión del mod ni pretende sustituir su distribución original.

## Créditos y agradecimientos

- **Bringerx13** — traducción al español neutro, integración, correcciones y pruebas de la versión española.
- **Gabin-CC** — por compartir su trabajo y sus herramientas de localización para Tactics Ogre PSP, utilizadas como referencia y apoyo técnico. Sus herramientas se publican bajo licencia MIT; consulta [FrenchTools/LICENSE](FrenchTools/LICENSE) y el [proyecto original](https://github.com/Gabin-CC/tactics-ogre-psp-fr).
- **Rick “Gibbed”** — por la investigación de formatos y [Gibbed's Let Us Cling Together Tools](https://github.com/gibbed/Gibbed.LetUsClingTogether), fundamentales para la exploración y modificación de los archivos del juego.
- **raics** — creador de [One Vision](https://www.moddb.com/mods/one-vision1), la modificación sobre la que se basa este proyecto.

Agradecimientos a todas las personas que han contribuido a la comunidad de modding de Tactics Ogre.

## Aviso legal

Este es un proyecto de fans, gratuito y sin afiliación oficial con Square Enix, raics ni los autores de las herramientas mencionadas. **Tactics Ogre: Let Us Cling Together** y sus elementos originales pertenecen a sus respectivos titulares. El parche no incluye la ISO ni pretende sustituir una copia legítima del juego.
