# Puente Iray Preview

Plugin experimental gratuito de Puente Labs para **Daz Studio 6 en Windows x64**.
Ofrece preview neural de Iray, procesamiento de renders y ampliación opcional
Real-ESRGAN 2x/4x. El paquete Full incluye un worker con Python y sus dependencias;
el usuario no selecciona entornos Python ni necesita ComfyUI.

**Estado: preparación de la beta `0.3.0-beta.1`.** La nueva DLL ya pasó pruebas
dentro de Daz. Este repositorio publica el código del proyecto. Los binarios de
distribución siguen en borrador mientras se revisan los permisos indicados abajo;
todavía no se anuncia disponibilidad general.

## BYO DLL

El runtime NR de NVIDIA no se distribuye. El botón **Importar DLL NR...** recibe
un `nvngx_dlssnr.dll` compatible que el usuario tiene derecho a utilizar, verifica
su copia y prepara una carpeta local junto al helper abierto. No descarga ni
parchea el DLL. El driver NVIDIA es un requisito del sistema.

BYO evita que redistribuyamos ese runtime; no acredita todos los derechos de uso.
Siguen pendientes la autorización del contrato de inicialización/IDs y helper,
el acuerdo aplicable al runtime exacto y la revisión final de dependencias Full.
Ver [permisos del backend](docs/backend-permissions-review-2026-10-19.md).

## Verificación disponible

Se probó Daz Studio **6.25.2026.14722**, RTX 4090, driver 617.42, Windows x64.
Pasaron importación BYO repetida, render + NR/2x, procesamiento automático
Direct-to-File, imagen existente, cancelación/recuperación y preview.
El worker Full también pasó NR y Real-ESRGAN 2x/4x sin Python externo en PATH.
No se afirma compatibilidad con otras GPU/versiones de Daz ni equivalencia
general con DLSS de juegos. [Detalle de pruebas](docs/TESTING.md).

## Instalación y construcción

El paquete mantiene juntos `plugins/dsp_PuenteIrayPreview.dll` y la carpeta
`plugins/PuenteIrayPreview/`. Se instala con Daz cerrado y conservando copia de
la versión anterior. [Instrucciones de instalación](docs/installation-draft.md).

Para compilar se requieren MSVC 2022 x64, CMake, Qt 6.10.3 y el SDK oficial de
Daz Studio 6 que corresponda a la aplicación. Estos componentes no se incluyen.
[Construcción](docs/BUILD.md).

Nuestro código usa MIT. Los componentes de terceros conservan sus propias
licencias. [Avisos](THIRD_PARTY_NOTICES.md). Puente Labs no está afiliado ni
respaldado por NVIDIA o Daz 3D.
