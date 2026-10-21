# Instalación — beta 0.3.0-beta.1 en preparación

La DLL pasó la integración en Daz Studio 6.25.2026.14722, Windows x64, RTX 4090
y driver 617.42. El paquete sigue en borrador por los permisos documentados.
No sustituir el plugin que funciona durante una sesión activa.

1. Guardar el trabajo y cerrar Daz Studio.
2. Si existe una instalación de Puente Iray Preview, conservar una copia de su
   DLL y de su carpeta auxiliar antes de actualizar.
3. Copiar el contenido de `plugins/` del paquete a la carpeta `plugins/` de la
   instalación correcta de Daz Studio. Mantener juntos la DLL y el directorio
   `PuenteIrayPreview`; no extraer solo la DLL.
4. Abrir Daz y el panel **Puente Iray Preview**.
5. En configuración, usar **Importar DLL NR...** para seleccionar el
   `nvngx_dlssnr.dll` compatible que se tiene derecho a utilizar. El plugin
   prepara una copia verificada con el helper incluido. Cada combinación se
   guarda en su propia carpeta; no cambia el original ni descarga DLL.
6. Iniciar el preview o procesar un render. Los diagnósticos de componentes
   faltantes aparecen antes de iniciar el render. Si se desea Real-ESRGAN, usar
   el paquete Full; no hace falta instalar Python, Conda, ComfyUI ni paquetes.

Para comprobar solo el paquete puede ejecutarse `puente-worker.exe check`.
Que ese diagnóstico pase no demuestra por sí solo la compatibilidad NR de la
GPU; esta se comprueba al procesar una imagen.

Para volver a la versión anterior, cerrar Daz y restaurar la DLL y carpeta
auxiliar guardadas. Los renders originales y los runtimes importados permanecen
fuera de la carpeta del programa. Eliminar el plugin no elimina esos datos.

La importación, render/proceso, Direct-to-File, imagen existente, cancelación y
preview se verificaron en una instancia propia de Daz con esta DLL. Falta la
prueba de instalación/actualización/desinstalación en Windows limpio. La
instalación original se preservó durante las pruebas.
