# Puente Iray Preview 0.3.0-beta.1 — borrador

Primera beta gratuita para Windows x64/Daz Studio 6. Incluye plugin compilado y
worker Full con Python/dependencias; no requiere seleccionar un entorno externo.
NR se configura mediante **Importar DLL NR...** usando una copia compatible que
el usuario tiene derecho a utilizar. El paquete no incluye el runtime NR ni DLL
de driver. Full sí incluye bibliotecas CUDA de PyTorch y modelos Real-ESRGAN.

Probado: Daz 6.25.2026.14722, RTX 4090, driver 617.42. Pasaron BYO, preview,
render + proceso, Direct-to-File, imagen existente, cancelación y recuperación.
Solo esa combinación está verificada. Conservar la instalación anterior.

Este release permanece en borrador mientras se cierran las cuestiones de
runtime/IDs/helper y la revisión final de licencias nativas/pesos Full. BYO no
equivale a aprobación de NVIDIA. Leer README, TESTING y revisión de permisos.
