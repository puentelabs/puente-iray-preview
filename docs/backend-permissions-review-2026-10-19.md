# Revisión de permisos del backend para la beta BYO DLL

Fecha: 19 de octubre de 2026. Estado: revisión técnica/documental; no equivale
a autorización de NVIDIA sobre el runtime experimental.

## Lo que sí está establecido

El backend utilizado es `lisitskyaa/ComfyUI-DLSS5-NR`, commit
`41dcdfa593cb61b6a98c65bb8ed27606260bb598`, verificado en el checkout local.
Su archivo LICENSE concede MIT a su código. Las notas del autor incluyen
expresamente el bridge y el helper entre los materiales propios redistribuibles,
con la salvedad separada sobre el uso del runtime. Por tanto, no falta una
licencia nueva del mantenedor para copiar su código MIT conservando los avisos.

Se deben conservar LICENSE, THIRD_PARTY_NOTICES y el aviso MIT de
`NIGos/dlss5-bridge` que el backend incorpora. Nuestro código conserva la licencia
MIT de Puente Labs. No se atribuyen a MIT los derechos de NVIDIA ni los de Daz.

Las [notas actuales del backend](https://github.com/lisitskyaa/ComfyUI-DLSS5-NR/blob/main/docs/LEGAL_NOTES.md)
recomiendan fuente más bridge/helper propios, runtime aportado por el usuario y
GitHub Releases experimental. Eso describe la postura del mantenedor; no es una
aprobación contractual de NVIDIA para la integración.

## Qué resuelve BYO DLL

La beta excluye `nvngx_dlssnr.dll`, `_nvngx.dll`, otros runtimes DLSS, DLL de
driver, SDK de NVIDIA y archivos del programa Daz. El usuario aporta una copia
compatible que tiene derecho a usar. Se copia sin parchearla, en una carpeta
con identificador compacto y verificación SHA-256 junto con el helper. No hay descarga automática ni enlaces a copias
filtradas/modificadas. El core NGX se obtiene del driver instalado.

Esto resuelve la redistribución de esos binarios por nuestra parte. No acredita
que cualquier DLL obtenido de Internet tenga una licencia válida, ni establece
que todos los usos del runtime estén autorizados.

## Cuestiones que siguen abiertas

| Cuestión | Evidencia concreta | Qué falta resolver |
| --- | --- | --- |
| Identificador de aplicación/proyecto | El bridge fijado usa IDs observados y feature ID 18. | Obtener registro/ID de Puente Labs o confirmación de que ese contrato de inicialización es admisible. No sustituirlo por un ID inventado. |
| Comprobación del caller | El helper está diseñado para que la llamada/retorno se atribuya a su módulo; los comentarios documentan un error cuando no se hace así. | Aclarar si esa integración está autorizada y cómo se relaciona con las restricciones contractuales del runtime. La licencia MIT del helper no responde esa pregunta. |
| Acuerdo del runtime exacto | La copia usada localmente es aportada por el usuario; no se acreditó una entrega SDK NR a Puente Labs. | Identificar el acuerdo aplicable y el origen autorizado del binario; confirmar uso para imágenes fijas, offline y Daz Studio. |
| Plataforma/GPU | La prueba local es Windows x64/RTX 4090. | Confirmar soporte autorizado para esa GPU/runtime y validar otras combinaciones antes de anunciarlas. |
| Aviso de lanzamiento y marcas | La licencia pública RTX/NGX contiene restricciones de marca y un aviso previo para lanzamientos comerciales, incluidos plugins. | Confirmar la aplicabilidad a esta beta gratuita. No asumir que gratuito elimina todas las obligaciones. No usar logotipos ni alegar afiliación/aprobación. |

La [licencia pública RTX/NGX](https://github.com/NVIDIA/DLSS/blob/main/LICENSE.txt)
restringe la elusión de limitaciones y mecanismos de autenticación. Es necesario
aclarar su aplicación al contrato experimental y a la comprobación del caller;
no se presenta aquí una conclusión jurídica de infracción ni de autorización.

## Decisión práctica para esta preparación

Se puede preparar y probar localmente la beta, su repositorio, avisos y archivos
de distribución. La documentación debe mantener visibles las cuestiones
anteriores. No se marcará «permisos resueltos» por excluir el DLL propietario.

El contacto prioritario para cerrar la cuestión del runtime/ID/helper es NVIDIA,
mediante el canal de licencias que figura en su propia licencia. El mantenedor
puede aportar contexto técnico y cualquier autorización recibida, pero no puede
conceder por MIT derechos sobre software o contratos de NVIDIA.

Se prepararon borradores de consulta separados de este repositorio. No se enviaron
mensajes, correos ni issues a terceros durante esta revisión.

## Otros componentes del paquete completo

El paquete Full conserva Real-ESRGAN y CUDA PyTorch. Se recopilan los avisos de
las versiones exactas de todas las distribuciones Python incluidas. Esto no se
confunde con permisos del NR. Hay que revisar además las bibliotecas nativas
transitivas y los avisos CUDA/cuDNN y documentar los dos pesos oficiales por URL
y SHA-256. El código de Real-ESRGAN es BSD-3-Clause; la procedencia oficial de
los pesos se documenta sin atribuirles una licencia separada no publicada.
