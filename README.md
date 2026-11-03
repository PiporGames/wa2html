# wa2html (WhatsApp to HTML)

wa2html permite convertir una conversación exportada desde WhatsApp en una página HTML autocontenida, con los mensajes y los archivos adjuntos en la misma conversación. Procesamiento totalmente local y sin conexión, libre de terceros.

## Características del HTML

- Conserva los mensajes, los nombres de los participantes, los emojis, los saltos de línea y las fechas originales.
- Localiza rápidamente texto, participantes y nombres de archivos desde el visor.
- Adapta automáticamente su apariencia al modo de color de tu sistema.
- Consulta imágenes, audios y vídeos compatibles directamente desde la página, con opción a descarga de documentos y otros formatos no compatibles con la reproducción integrada.
- Reconoce las referencias habituales a archivos en español e inglés.
- Señala los adjuntos que faltan o cuyos nombres son ambiguos.
- Reúne al final los archivos que no consigue vincular a un mensaje, para que no pierdas su contenido.

## Prerequisitos

Necesitas tener instalado **Python 3.10 o una versión posterior**.

Instala las dependencias del proyecto con el siguiente comando:

```powershell
python -m pip install -r requirements.txt
```

## Uso y argumentos

El programa trabaja con el archivo ZIP que obtienes al exportar un chat desde WhatsApp, tanto en Android como en iPhone. No sirve para abrir las copias de seguridad cifradas de Google Drive o iCloud, ni los archivos de tipo `crypt14` o `crypt15`.

Desde WhatsApp, exporta la conversación que quieras guardar y elige la opción **Incluir archivos** (si existe) si deseas conservar también los adjuntos que WhatsApp permita exportar. Guarda el ZIP en tu equipo y pasa su ruta al programa, sin necesidad de descomprimirlo previamente:

```powershell
python whatsapp_html.py "conversacion.zip" -o "conversacion.html" --me "Tu nombre"
```

Donde:
- `conversacion.zip` es la ruta al archivo ZIP que contiene la conversación exportada.
- `-o conversacion.html` es la ruta donde se guardará el HTML resultante. (Opcional; si no se indica, se crea un archivo con el mismo nombre que el ZIP y extensión `.html`).
- `--me "Tu nombre"` es el nombre que se usará para identificar tus mensajes en la conversación para renderizarlos a la derecha. (Opcional).

### Otras opciones disponibles

Si el ZIP contiene varios archivos de conversación, puedes seleccionar el que quieres convertir mediante `--chat`, indicando su ruta dentro del ZIP, como en este ejemplo:

```powershell
python whatsapp_html.py "conversacion.zip" --chat "carpeta/_chat.txt"
```

Para desactivar los colores de la terminal, añade `--no-color` al comando o define la variable de entorno `NO_COLOR`. Si necesitas consultar todas las opciones disponibles, puedes hacerlo con `python whatsapp_html.py --help`.

## Aviso de privacidad y seguridad

**El HTML resultante contiene la conversación y sus adjuntos sin cifrar**, por lo que cualquier persona que tenga acceso a él podrá leer los mensajes y descargar los archivos.

El visor no necesita Internet y utiliza una política de seguridad del navegador para bloquear las conexiones remotas y el código que pudiera venir en los mensajes. Aun así, los archivos que descargues desde una conversación deben tratarse como cualquier otro archivo de origen no confiable, especialmente al mirar HTMLs que no sean los tuyos.

## Limitaciones y consideraciones adicionales

La aplicación acepta ZIP con un máximo de **2 GiB de contenido descomprimido y 50.000 entradas**. Los adjuntos se incluyen en el HTML mediante base64, por lo que una conversación con muchos archivos puede producir un HTML muy pesado y consumir bastante memoria en el navegador. Los adjuntos se cargan de forma diferida y cada archivo se incorpora una sola vez por esta misma razón.

Se admiten textos UTF-8 y UTF-16 con los formatos habituales de exportación de Android y iPhone, pero no todas las variantes regionales posibles. Solo se ha probado en conversaciones en español desde un dipositivo Android.

El programa no recupera mensajes ni adjuntos que WhatsApp haya omitido al exportar.

La apariencia del visor utiliza estilos propios inspirados en WhatsApp Web, pero wa2html es un proyecto independiente y no es un producto oficial de WhatsApp.

En ocasiones, el programa puede no parsear correctamente algún elemento de la conversación, lo que generará mensajes con el contenido a "null".

#### Uso responsable de la IA

> Este proyecto ha sido construido en su totalidad utilizando inteligencia artificial, siendo supervisado y controlado por humanos de verdad.
