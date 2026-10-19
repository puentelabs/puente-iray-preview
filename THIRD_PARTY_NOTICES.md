# Componentes de terceros

La licencia MIT raíz cubre el código de Puente Labs, no los SDK, aplicaciones,
drivers, runtimes ni modelos de terceros.

- Backend de referencia: [ComfyUI-DLSS5-NR](https://github.com/lisitskyaa/ComfyUI-DLSS5-NR),
  commit `41dcdfa593cb61b6a98c65bb8ed27606260bb598`, MIT. El paquete conserva
  LICENSE y THIRD_PARTY_NOTICES del backend, incluido el aviso NIGos/dlss5-bridge.
- El runtime NR y el driver NVIDIA no se incluyen. Sus derechos son separados.
- El worker incluye Python, NumPy, Pillow y, en Full, PyTorch/torchvision,
  spandrel y dependencias. Cada paquete conserva sus avisos exactos bajo
  `plugins/PuenteIrayPreview/licenses/` e inventario de versiones/licencias.
- PyInstaller utiliza su excepción de bootloader; se conserva COPYING.
- [spandrel](https://github.com/chaiNNer-org/spandrel) usa MIT, copyright 2024
  The ChaiNNer Organization.
- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) publica su código bajo
  BSD-3-Clause, copyright 2021 Xintao Wang. Los pesos Full provienen de los
  releases oficiales x2plus v0.2.1 y x4plus v0.1.0, con SHA-256 fijados en
  `src/render_worker.py`. No se atribuye a los pesos una licencia separada no
  publicada; las condiciones exactas se mantienen como revisión pendiente.

El SDK y la aplicación Daz y el kit de desarrollo Qt no se redistribuyen aquí.
La revisión de licencias nativas transitivas de Full y los permisos del contrato
NR/IDs/helper siguen abiertos. Este aviso no declara cerrada esa revisión.
