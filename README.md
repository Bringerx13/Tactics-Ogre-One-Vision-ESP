# Tactics Ogre: Let Us Cling Together — One Vision (PSP)
## Traducción al español neutro

Proyecto de traducción no oficial al español neutro de **Tactics Ogre: Let Us Cling Together para PSP**, compatible con **One Vision v1.11d**, el mod de raics.

La descarga pública se distribuye como un parche **xdelta**. No se distribuyen imágenes ISO ni archivos originales del juego.

## Descargar la traducción

**[Descargar la última versión desde GitHub Releases](https://github.com/Bringerx13/Tactics-Ogre-One-Vision-ESP/releases/latest)**

En la sección *Assets* de la publicación, descarga el archivo `.xdelta` correspondiente a la versión que quieras instalar.

## Requisitos y compatibilidad

- Una copia propia de **Tactics Ogre: Let Us Cling Together para PSP**, probado en la edición **USA**.
- **One Vision v1.11d**.
- Para preparar una ISO en PC: [7-Zip](https://www.7-zip.org/) y [UMDGen](https://www.romhacking.net/utilities/1218/).
- Para aplicar el parche en PC: [Delta Patcher](https://github.com/marco-calautti/DeltaPatcher/releases).
- Para jugar en móvil: [PPSSPP](https://www.ppsspp.org/download/).

**Región compatible con este parche:** USA, código **ULUS10565**.

> **Importante:** el parche xdelta solo funciona con la ISO USA de One Vision v1.11d preparada de la misma forma que la ISO utilizada para crear el parche. No lo apliques sobre una ISO limpia, una versión distinta de One Vision. Si el programa informa que el archivo original no coincide, detente y comprueba la fuente.

## 1. Instalar One Vision en PC (crear una ISO)

Este es el método recomendado para preparar la ISO que necesita nuestro parche español. Las imágenes son capturas de la [guía oficial de instalación de One Vision](https://ogre-db.github.io/one-vision/installation.html); algunas muestran una versión anterior del mod, pero ilustran el mismo procedimiento general.

### Descargar y extraer One Vision

1. Descarga **One Vision v1.11d** desde [ModDB](https://www.moddb.com/mods/one-vision1/downloads/one-vision1).
2. Coloca el archivo `.7z` de One Vision y tu ISO USA original en una carpeta de trabajo.
3. Extrae el archivo `.7z` de One Vision con 7-Zip. En la carpeta extraída debe aparecer `PSP_GAME`.

<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/iso_01.jpg" alt="Extraer el archivo 7z de One Vision en Windows" width="80%">
</p>

### Aplicar los archivos del mod con UMDGen

4. Abre **UMDGen** y carga tu ISO USA original.
5. Comprueba que estás en la raíz de la imagen y que aparece la carpeta `PSP_GAME`.
6. Desde la carpeta extraída de One Vision, arrastra la carpeta principal `PSP_GAME` del mod a la ventana de UMDGen.
7. Cuando UMDGen pregunte si deseas reemplazar los archivos, selecciona **Yes to All**.

<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/iso_02.jpg" alt="Abrir la ISO original en UMDGen" width="48%">
  <img src="https://ogre-db.github.io/one-vision/img/installation/iso_03.jpg" alt="Comprobar la raíz de la ISO en UMDGen" width="48%">
</p>
<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/iso_04.jpg" alt="Arrastrar PSP_GAME de One Vision a UMDGen" width="48%">
  <img src="https://ogre-db.github.io/one-vision/img/installation/iso_05.jpg" alt="Confirmar el reemplazo de archivos en UMDGen" width="48%">
</p>

> **No uses las carpetas `DataInstall Fix USA` ni `DataInstall Fix EUR` para preparar la ISO de origen de esta traducción.** Para este parche, aplica únicamente la carpeta principal `PSP_GAME` de One Vision v1.11d. No añadas correcciones adicionales de Data Install.

### Guardar la ISO de One Vision

8. En UMDGen, selecciona **File → Save As → Uncompressed (*.iso)**.
9. Guarda la imagen con un nombre nuevo, por ejemplo `Tactics_Ogre_One_Vision_v1.11d_USA.iso`. No sobrescribas tu ISO original.
10. Conserva esta ISO: será el archivo de origen para aplicar la traducción.

<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/iso_09.jpg" alt="Seleccionar Save As Uncompressed ISO en UMDGen" width="48%">
  <img src="https://ogre-db.github.io/one-vision/img/installation/iso_10.jpg" alt="Guardar la ISO modificada con un nombre nuevo" width="48%">
</p>

## 2. Aplicar la traducción en PC

1. Descarga el parche `.xdelta` desde [GitHub Releases](https://github.com/Bringerx13/Tactics-Ogre-One-Vision-ESP/releases/latest).
2. Abre **Delta Patcher**.
3. Selecciona los archivos:
   - **Original file:** `Tactics_Ogre_One_Vision_v1.11d_USA.iso`, creada en el apartado anterior.
   - **XDelta patch:** el archivo `.xdelta` descargado.
   - **Output file:** la ubicación y el nombre de la ISO traducida, por ejemplo `Tactics_Ogre_One_Vision_ESP.iso`.
4. Aplica el parche. No selecciones la ISO original sin modificar.
5. Abre la ISO española resultante en PPSSPP.

## 3. Instalar One Vision en un celular Android (método de carpeta de PPSSPP)

La guía oficial de One Vision también permite instalar el mod en Android sin reconstruir una ISO. Este método extrae el juego y combina las carpetas para que PPSSPP lo ejecute directamente.

**Atención:** este método instala One Vision en una carpeta, pero **no crea la ISO que necesita nuestro parche xdelta**. Úsalo para jugar la versión de One Vision desde una carpeta. Para jugar nuestra traducción española, consulta el apartado **4. Aplicar y jugar la traducción en un celular**.

### Preparar los archivos

Necesitarás:
- Tu ISO USA original de Tactics Ogre.
- El archivo de One Vision v1.11d en formato `.7z`.
- Una aplicación para extraer archivos `.7z` y archivos de juego (la guía oficial usa 7Z).
- Un administrador de archivos para copiar y combinar carpetas.
- PPSSPP instalado.

1. Descarga One Vision v1.11d desde [ModDB](https://www.moddb.com/mods/one-vision1/downloads/one-vision1).
2. Coloca el archivo `.7z` de One Vision y tu ISO original en una misma carpeta del almacenamiento del teléfono.
3. Abre tu aplicación de extracción, toca la ISO y selecciona **Attempt Extract** y después **Extract here**. Se creará una carpeta con los archivos del juego.
4. Extrae también el archivo `.7z` de One Vision. Tendrás una carpeta con los archivos originales extraídos y otra con los archivos del mod.

<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_01.jpg" alt="Colocar la ISO y el archivo One Vision 7z en la misma carpeta" width="32%">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_02.jpg" alt="Seleccionar Attempt Extract en la ISO" width="32%">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_03.jpg" alt="Elegir Extract here para extraer la ISO" width="32%">
</p>
<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_04.jpg" alt="Carpetas del juego y de One Vision ya extraídas" width="48%">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_05.jpg" alt="Abrir el administrador de archivos y localizar las carpetas" width="48%">
</p>

### Copiar y combinar los archivos de One Vision

5. Abre el administrador de archivos y entra en la carpeta de One Vision.
6. Mantén pulsada la carpeta principal `PSP_GAME` del mod y toca **Copy**.
7. Regresa a la carpeta del juego extraído, abre la carpeta que contiene el `PSP_GAME` original y selecciona **Paste**.
8. Cuando pregunte si deseas combinar las carpetas, selecciona **Merge**.
9. Cuando pregunte qué archivos conservar, selecciona los archivos **New** o la opción equivalente de reemplazar con los archivos del mod. Si aparece **Remember**, puedes marcarla para no repetir la pregunta.
10. **No copies ni combines las carpetas `DataInstall Fix USA` o `DataInstall Fix EUR`** para esta instalación de la traducción.

<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_06.jpg" alt="Seleccionar y copiar la carpeta PSP_GAME del mod" width="48%">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_07.jpg" alt="Pegar la carpeta PSP_GAME en los archivos del juego" width="48%">
</p>
<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_08.jpg" alt="Elegir Merge para combinar las carpetas" width="48%">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_09.jpg" alt="Elegir los archivos New para conservar los archivos del mod" width="48%">
</p>

### Abrir One Vision en PPSSPP

11. Cuando termine la combinación, abre PPSSPP.
12. En la pestaña **Games**, selecciona **Browse**.
13. Navega hasta la carpeta que contiene la carpeta del juego extraído. Selecciona **Use this folder** y concede permiso de acceso cuando Android lo solicite.
14. El juego aparecerá en la lista de PPSSPP. Ya puedes iniciarlo.

<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_15.jpg" alt="Carpeta del juego lista para abrirse en PPSSPP" width="48%">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_16.jpg" alt="Abrir Browse en PPSSPP" width="48%">
</p>
<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_17.jpg" alt="Seleccionar la carpeta del juego en Android" width="48%">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_18.jpg" alt="Conceder permiso de acceso a PPSSPP" width="48%">
</p>
<p align="center">
  <img src="https://ogre-db.github.io/one-vision/img/installation/ppsspp_19.jpg" alt="One Vision visible en la lista de juegos de PPSSPP" width="80%">
</p>

## 4. Aplicar y jugar la traducción en un celular

Nuestro parche es `.xdelta` y necesita una **ISO USA de One Vision v1.11d**, no una carpeta extraída. Por eso, para jugar la traducción en Android:

1. Prepara la ISO de One Vision v1.11d USA siguiendo el método de PC del apartado **1**. Puedes hacerlo en un ordenador y luego transferir la ISO al teléfono.
2. En el teléfono, abre un navegador y visita [xdelta.app en español](https://xdelta.app/es/). El parcheador funciona en el navegador; también puedes aplicar el parche en PC con Delta Patcher.
3. Selecciona como archivo original la ISO exacta de One Vision v1.11d USA.
4. Selecciona el archivo `.xdelta` descargado de [Releases](https://github.com/Bringerx13/Tactics-Ogre-One-Vision-ESP/releases/latest).
5. Elige un nombre diferente para el archivo de salida, por ejemplo `Tactics_Ogre_One_Vision_ESP.iso`, y aplica el parche.
6. Cuando termine, guarda la ISO española en el teléfono. Copia el archivo a una carpeta fácil de localizar, por ejemplo `PSP/ISO`.
7. Abre PPSSPP, entra en **Games** y navega hasta esa carpeta para iniciar el juego.

> **Nota para Android:** las ISO de PSP son archivos grandes. El parcheo desde el navegador depende de la memoria disponible en el teléfono y puede fallar en dispositivos con poca memoria. Si ocurre, aplica el xdelta en un PC y transfiere la ISO española al teléfono mediante USB o Wi-Fi. La transferencia por Wi-Fi integrada requiere PPSSPP 1.20 o posterior; consulta la [guía oficial de PPSSPP](https://www.ppsspp.org/docs/getting-started/installing-games-android/).

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

Agradecimientos a todas las personas que han contribuido a la comunidad de modding de Tactics Ogre. Las capturas de instalación de One Vision enlazadas en esta guía proceden de la [guía oficial del mod](https://ogre-db.github.io/one-vision/installation.html).

## Aviso legal

Este es un proyecto de fans, gratuito y sin afiliación oficial con Square Enix, raics ni los autores de las herramientas mencionadas. **Tactics Ogre: Let Us Cling Together** y sus elementos originales pertenecen a sus respectivos titulares. El parche no incluye la ISO ni pretende sustituir una copia legítima del juego.
