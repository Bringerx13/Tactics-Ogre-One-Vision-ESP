# Tactics Ogre: Let Us Cling Together — One Vision (PSP)
## Traducción al español

Proyecto de traducción no oficial al español neutro de **Tactics Ogre: Let Us Cling Together para PSP**, compatible con la modificación **One Vision** de raics.

La descarga pública se distribuye como un parche **xdelta**. No se distribuyen imágenes ISO ni archivos originales del juego.

## Descargar la traducción

**[Descargar la última versión desde GitHub Releases](https://github.com/Bringerx13/Tactics-Ogre-One-Vision-ESP/releases/latest)**

En la sección *Assets* de la publicación, descarga el archivo `.xdelta` correspondiente a la versión que quieras instalar.

## Requisitos

- Una copia propia de **Tactics Ogre: Let Us Cling Together para PSP**.
- Los archivos de la modificación **One Vision**, Versión v1.11d.
- **7-Zip** u otro programa capaz de extraer archivos `.7z`.
- **UMDGen** para preparar la ISO modificada.
- **Delta Patcher** para aplicar la traducción: [descargar desde GitHub](https://github.com/marco-calautti/DeltaPatcher/releases).
- La misma edición, región y versión de One Vision que se utilizó como archivo de origen al crear el parche español.

> **Importante:** el parche xdelta solo funciona con la ISO exacta usada como base. No lo apliques sobre una ISO limpia, una versión diferente de One Vision ni **Tactics Ogre: Reborn**. Si Delta Patcher informa que el archivo original no coincide, detente y comprueba la región y la versión, la traducción fué creada usando la versión USA del ISO. 

## 1. Instalar One Vision

La página oficial del mod ofrece la descarga y una guía ilustrada de instalación:

- **[Descargar One Vision](https://www.moddb.com/mods/one-vision1/downloads/one-vision1)**.
- **[Guía oficial de instalación](https://ogre-db.github.io/one-vision/installation.html)**.

Descarga la versión de One Vision compatible con la versión base que requiere el parche español. La página de ModDB identifica el paquete completo v1.11d; comprueba siempre la versión indicada en la publicación del parche español antes de continuar.

### Preparar la ISO de One Vision con UMDGen

1. Haz una copia de seguridad de tu ISO original.
2. Extrae el archivo de One Vision `.7z` en una carpeta. Dentro encontrarás la carpeta `PSP_GAME` del mod y las carpetas de corrección de *Data Install*(No usar).
3. Abre **UMDGen** y carga tu ISO original de Tactics Ogre. Asegúrate de estar viendo la raíz de la ISO, donde aparece `PSP_GAME`.
4. Desde la carpeta extraída de One Vision, arrastra la carpeta `PSP_GAME` del mod a la ventana de UMDGen. Cuando pregunte si deseas reemplazar archivos, selecciona **Yes to All**.
5. Abre en los archivos extraídos de One Vision la carpeta de **Data Install Fix** correspondiente a tu región (USA o Europa).
6. Arrastra a UMDGen la carpeta `PSP_GAME` que se encuentra dentro de esa carpeta de corrección. Cuando pregunte si deseas sobrescribir archivos, selecciona **Yes to All**.
7. En UMDGen, elige **File → Save As → Uncompressed (*.iso)** y guarda la nueva imagen con un nombre distinto, por ejemplo `Tactics_Ogre_One_Vision.iso`.
8. Conserva esa ISO como tu base de One Vision. No la confundas con la ISO original ni con la ISO española que crearás en el siguiente paso.

**Nota sobre Data Install:** en una instalación nueva de One Vision, aplica la corrección de *Data Install* correspondiente a tu región. La guía oficial indica que, al actualizar desde una versión anterior del mod que ya tiene esa corrección, no es necesario volver a aplicarla.

## 2. Aplicar la traducción al español

Una vez que tengas preparada la ISO de One Vision:

1. Haz otra copia de seguridad de la ISO de One Vision.
2. Descarga el parche `.xdelta` desde [GitHub Releases](https://github.com/Bringerx13/Tactics-Ogre-One-Vision-ESP/releases/latest).
3. Abre **Delta Patcher** y selecciona:
   - **Original file:** la ISO de One Vision preparada en el paso anterior y que coincida exactamente con la versión base del parche.
   - **XDelta patch:** el archivo `.xdelta` descargado.
   - **Output file:** la ubicación y el nombre de la nueva ISO española, por ejemplo `Tactics_Ogre_One_Vision_ESP.iso`.
4. Aplica el parche y espera a que termine el proceso.
5. Abre la ISO española resultante en PPSSPP o en el dispositivo compatible que utilices.

No apliques el parche español antes de instalar One Vision. Tampoco uses una ISO de una región o versión distinta: aunque el juego llegue a iniciar, el parche podría no funcionar correctamente.

### Nota para usuarios de PPSSPP

La guía oficial de One Vision también explica cómo ejecutar el juego desde una carpeta extraída, sin reconstruir una ISO. Sin embargo, el parche español distribuido aquí es xdelta y necesita una ISO de origen. Para usar este parche, sigue el método con UMDGen descrito arriba y luego aplica el xdelta.

Al probar una versión nueva del mod o de la traducción, carga una partida guardada normal. Evita cargar estados rápidos (*save states*) creados con una versión diferente del juego, ya que pueden conservar datos antiguos en memoria.

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
