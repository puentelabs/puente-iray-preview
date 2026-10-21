# Validación de la beta 0.3.0-beta.1

Pruebas del 19 de octubre de 2026 en Windows x64, Daz Studio 6.25.2026.14722,
RTX 4090 y driver NVIDIA 617.42. Se usó una instancia propia de Daz con copia
local del programa y el plugin nuevo; la DLL instalada original se preservó.
La API privada de validación estuvo desactivada.

| Flujo | Resultado observado |
| --- | --- |
| BYO desde el método utilizado por el botón, y repetición | Pasó; copia verificada y reutilización segura. |
| Render Iray nuevo + NR + Real-ESRGAN 2x | 256×192 → 512×384. |
| Procesamiento automático Direct-to-File | Pasó; salida y opciones de render preservadas. |
| Render propio existente + NR + Real-ESRGAN 2x | 1280×720 → 2560×1440. |
| Destino ya existente | Rechazado sin sobrescribir. |
| Cancelar 4x y volver a procesar | Pasó; worker detenido y recuperación comprobada. |
| Preview, blend cero y reinicio | Pasó; imagen recibida y overlay retirado con blend cero. |
| Worker Full aislado, sin Python externo | NR 1x repetible; NR + 2x y 4x pasaron. |
| Originales y alfa | SHA-256 preservado; prueba adicional con alfa variable. |

Durante la prueba se encontró un error real de rutas: dos hashes completos
anidados podían llevar el helper más allá de MAX_PATH y producir 0xBAD00002.
La misma imagen y binarios pasaron en ruta corta y fallaron en la larga. Ahora
el importador usa un identificador de 24 caracteres, verifica los dos SHA-256
completos antes de reutilizar una carpeta y diagnostica rutas excesivas. La
prueba completa dentro de Daz pasó después del cambio.

Pendientes: instalación/actualización/desinstalación en Windows limpio, otras
GPU y versiones de Daz/runtime/driver, sesiones largas y más escenas. Las
mediciones no constituyen una garantía de calidad ni ahorro de render.
Las imágenes del usuario, copias privadas de Daz y registros con rutas locales
no forman parte de este repositorio.
