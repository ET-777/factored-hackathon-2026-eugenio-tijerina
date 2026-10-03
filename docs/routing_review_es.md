# Revisión humana del español: solicitudes de enrutamiento

Estado: **redacción y etiquetas de intención en español aprobadas por el propietario el 2026-10-03**. Hay 64 mensajes en español: 48 de entrenamiento y 16 de desarrollo. Son textos redactados por Codex; no son conversaciones reales ni contienen valores copiados de registros bancarios. No se muestran predicciones ni puntuaciones. El [registro de revisión](../evidence/routing_language_review.json) vincula la aprobación a los hashes exactos de ambos archivos y de sus filas en español.

Esta revisión cubre solo el español. El portugués tuvo una revisión adicional de Codex y sigue pendiente de revisión humana por una persona competente en ese idioma.

La aprobación cubre la redacción y las etiquetas de intención; no demuestra independencia semántica entre familias, calidad del modelo ni validación del portugués. Los textos, etiquetas e IDs de entrenamiento y desarrollo permanecen intactos. Su estado JSON original se conserva como metadato histórico; el registro separado determina el estado actual de revisión lingüística de estos archivos exactos.

## Qué revisar

- `inquiry`: pide consultar o explicar datos de una transacción existente.
- `dispute_intake`: desconoce un cargo, lo considera incorrecto o pide revisarlo/impugnarlo. No autoriza una acción ni promete un reembolso.
- `human_request`: pide explícitamente atención o revisión de una persona. No implica consentimiento para compartir datos.
- `unsupported`: pide otro servicio o una acción fuera del alcance, como consultar saldo, transferir dinero, bloquear una tarjeta o cambiar una contraseña.

Para cada mensaje, comprueba que la intención sea clara y que la redacción suene natural. Señala por ID los textos mal etiquetados, vagos, ambiguos o poco naturales, e indica tu corrección sugerida. También señala si una familia de desarrollo solo repite una familia de entrenamiento. Puedes aprobar el español completo si no encuentras problemas, o enumerar únicamente los IDs que necesitan cambios. No uses respuestas del clasificador para decidir la etiqueta.

Las expresiones como «esta operación» suponen una transacción ya seleccionada en la interfaz; no autentican al usuario. Las afirmaciones sobre cargos incorrectos son alegaciones redactadas, no hechos verificados en los datos.

## Entrenamiento: 48 mensajes

### tr-inquiry-original-amount

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-inquiry-original-amount-es-01` | `inquiry` | ¿Cuál fue el importe original de esta operación y en qué moneda está registrado? |
| `tr-inquiry-original-amount-es-02` | `inquiry` | Quiero consultar cuánto se cobró en este movimiento, con su divisa original. |
| `tr-inquiry-original-amount-es-03` | `inquiry` | Indícame la cantidad y la moneda que figuran en el cargo seleccionado. |
| `tr-inquiry-original-amount-es-04` | `inquiry` | Para revisar mis gastos, necesito el monto registrado de esta transacción y su moneda. |

### tr-inquiry-recorded-status

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-inquiry-recorded-status-es-01` | `inquiry` | ¿Qué estado tiene actualmente la transacción que estoy viendo? |
| `tr-inquiry-recorded-status-es-02` | `inquiry` | Consulta si este movimiento figura como pendiente o completado en el registro. |
| `tr-inquiry-recorded-status-es-03` | `inquiry` | Quisiera saber cómo aparece el estado de esta operación en los datos disponibles. |
| `tr-inquiry-recorded-status-es-04` | `inquiry` | Dime si el cargo seleccionado está registrado como rechazado o aprobado. |

### tr-inquiry-merchant-identity

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-inquiry-merchant-identity-es-01` | `inquiry` | ¿Qué nombre de comercio aparece asociado a esta compra? |
| `tr-inquiry-merchant-identity-es-02` | `inquiry` | Quiero consultar a qué establecimiento corresponde el movimiento seleccionado. |
| `tr-inquiry-merchant-identity-es-03` | `inquiry` | Muéstrame el comercio que figura en el registro de esta transacción. |
| `tr-inquiry-merchant-identity-es-04` | `inquiry` | Necesito identificar al vendedor indicado en los datos de esta compra. |

### tr-dispute-unrecognized-purchase

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-dispute-unrecognized-purchase-es-01` | `dispute_intake` | No reconozco esta compra y quiero iniciar una reclamación por el cargo. |
| `tr-dispute-unrecognized-purchase-es-02` | `dispute_intake` | Esta operación no la autoricé; necesito reportarla para que la revisen. |
| `tr-dispute-unrecognized-purchase-es-03` | `dispute_intake` | El movimiento seleccionado no es mío. Quiero preparar una solicitud para impugnarlo. |
| `tr-dispute-unrecognized-purchase-es-04` | `dispute_intake` | Quiero registrar que desconozco este cargo y pedir su revisión. |

### tr-dispute-duplicate-charge

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-dispute-duplicate-charge-es-01` | `dispute_intake` | Me cobraron dos veces la misma compra y quiero reclamar el cargo repetido. |
| `tr-dispute-duplicate-charge-es-02` | `dispute_intake` | Creo que esta operación está duplicada; prepara una solicitud de revisión. |
| `tr-dispute-duplicate-charge-es-03` | `dispute_intake` | Quisiera presentar una reclamación porque este movimiento repite un cobro anterior. |
| `tr-dispute-duplicate-charge-es-04` | `dispute_intake` | Pagué una sola vez, pero veo un segundo cargo por lo mismo. Quiero reportarlo. |

### tr-dispute-cancelled-subscription

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-dispute-cancelled-subscription-es-01` | `dispute_intake` | Cancelé la suscripción antes de este cobro y quiero presentar una reclamación. |
| `tr-dispute-cancelled-subscription-es-02` | `dispute_intake` | Quiero impugnar este cargo de un servicio que ya había dado de baja. |
| `tr-dispute-cancelled-subscription-es-03` | `dispute_intake` | Me siguen cobrando una membresía cancelada; necesito reportar esta operación. |
| `tr-dispute-cancelled-subscription-es-04` | `dispute_intake` | Este cobro se hizo después de mi cancelación. Prepara una solicitud para revisarlo. |

### tr-human-person-preference

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-human-person-preference-es-01` | `human_request` | Prefiero hablar con una persona sobre esta transacción. |
| `tr-human-person-preference-es-02` | `human_request` | ¿Puedes ponerme en contacto con un agente para continuar esta consulta? |
| `tr-human-person-preference-es-03` | `human_request` | Quiero que un asesor humano me atienda con este movimiento. |
| `tr-human-person-preference-es-04` | `human_request` | Necesito conversar directamente con alguien del equipo de atención. |

### tr-human-repeated-self-service

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-human-repeated-self-service-es-01` | `human_request` | Ya intenté resolverlo varias veces en la aplicación; quiero que me atienda una persona. |
| `tr-human-repeated-self-service-es-02` | `human_request` | He repetido esta consulta sin lograr una solución. Necesito hablar con un agente. |
| `tr-human-repeated-self-service-es-03` | `human_request` | Llevo varios intentos con el asistente automático y quiero continuar con un asesor. |
| `tr-human-repeated-self-service-es-04` | `human_request` | Las respuestas automáticas no me han servido; pásame con alguien de atención. |

### tr-human-guided-conversation

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-human-guided-conversation-es-01` | `human_request` | Necesito que una persona me explique esto con calma, paso a paso. |
| `tr-human-guided-conversation-es-02` | `human_request` | Me resulta difícil seguir la información escrita; quiero conversar con un asesor. |
| `tr-human-guided-conversation-es-03` | `human_request` | Prefiero que un agente me acompañe mientras reviso este movimiento. |
| `tr-human-guided-conversation-es-04` | `human_request` | Quiero hacer mis preguntas directamente a una persona que pueda guiarme. |

### tr-unsupported-account-balance

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-unsupported-account-balance-es-01` | `unsupported` | ¿Cuánto saldo disponible tengo ahora en mi cuenta? |
| `tr-unsupported-account-balance-es-02` | `unsupported` | Quiero consultar el saldo total de mi cuenta de ahorros. |
| `tr-unsupported-account-balance-es-03` | `unsupported` | Dime cuánto dinero me queda disponible para gastar en la cuenta. |
| `tr-unsupported-account-balance-es-04` | `unsupported` | Muéstrame mi saldo bancario actual. |

### tr-unsupported-new-transfer

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-unsupported-new-transfer-es-01` | `unsupported` | Haz una transferencia nueva a la cuenta de mi proveedor. |
| `tr-unsupported-new-transfer-es-02` | `unsupported` | Quiero enviar dinero a otro banco; ejecuta la transferencia. |
| `tr-unsupported-new-transfer-es-03` | `unsupported` | Mueve dinero de mi cuenta a la de un familiar ahora. |
| `tr-unsupported-new-transfer-es-04` | `unsupported` | Realiza un pago nuevo mediante transferencia bancaria. |

### tr-unsupported-card-suspension

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `tr-unsupported-card-suspension-es-01` | `unsupported` | Bloquea mi tarjeta porque la perdí. |
| `tr-unsupported-card-suspension-es-02` | `unsupported` | Quiero que suspendas el uso de mi tarjeta de inmediato. |
| `tr-unsupported-card-suspension-es-03` | `unsupported` | Desactiva mi tarjeta para que no puedan hacer nuevas compras. |
| `tr-unsupported-card-suspension-es-04` | `unsupported` | Apaga temporalmente mi tarjeta bancaria. |

## Desarrollo: 16 mensajes

Estas familias se reservan para desarrollo. Sus mensajes no se usan para ajustar los pesos del modelo. Todavía no se han puntuado.

### dev-inquiry-time-and-channel

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `dev-inquiry-time-and-channel-es-01` | `inquiry` | Para ordenar mis comprobantes, busca la fecha y la hora registradas para esta operación. |
| `dev-inquiry-time-and-channel-es-02` | `inquiry` | ¿Por qué canal se realizó el movimiento seleccionado según sus datos? |

### dev-inquiry-operation-summary

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `dev-inquiry-operation-summary-es-01` | `inquiry` | Necesito un resumen de los datos disponibles de esta transacción para anotarlos. |
| `dev-inquiry-operation-summary-es-02` | `inquiry` | Explícame la información registrada en el movimiento que tengo abierto. |

### dev-dispute-cash-not-dispensed

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `dev-dispute-cash-not-dispensed-es-01` | `dispute_intake` | El cajero descontó el retiro, pero no me entregó efectivo; quiero abrir una reclamación. |
| `dev-dispute-cash-not-dispensed-es-02` | `dispute_intake` | Quiero impugnar este retiro porque el dinero no salió del cajero. |

### dev-dispute-goods-not-received

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `dev-dispute-goods-not-received-es-01` | `dispute_intake` | Pagué este pedido y nunca lo recibí. Solicito que se revise el cargo. |
| `dev-dispute-goods-not-received-es-02` | `dispute_intake` | Quiero iniciar una reclamación por esta compra: la mercancía no fue entregada. |

### dev-human-written-packet

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `dev-human-written-packet-es-01` | `human_request` | Prepara un resumen de esta consulta para que lo revise una persona del equipo. |
| `dev-human-written-packet-es-02` | `human_request` | Quisiera enviar la información de este movimiento a un asesor humano para su revisión. |

### dev-human-case-continuity

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `dev-human-case-continuity-es-01` | `human_request` | Tengo una solicitud iniciada y quiero que un agente retome mi caso. |
| `dev-human-case-continuity-es-02` | `human_request` | Necesito seguimiento de una persona para la gestión que dejé pendiente. |

### dev-unsupported-credit-limit

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `dev-unsupported-credit-limit-es-01` | `unsupported` | Aumenta el límite de crédito de mi tarjeta. |
| `dev-unsupported-credit-limit-es-02` | `unsupported` | Quiero ampliar mi línea de crédito; aprueba el incremento. |

### dev-unsupported-login-credentials

| ID | Intención propuesta | Texto redactado |
|---|---|---|
| `dev-unsupported-login-credentials-es-01` | `unsupported` | Olvidé mi contraseña de acceso; restablécela. |
| `dev-unsupported-login-credentials-es-02` | `unsupported` | Quiero cambiar la clave con la que entro a la banca digital. |

## Registro de esta revisión

La aprobación explícita del español recibida el 2026-10-03 está registrada en [routing_language_review.json](../evidence/routing_language_review.json); el portugués sigue pendiente de revisión humana competente. Los dos archivos JSON conservan `draft_pending_owner_and_portuguese_review` como metadato histórico sin modificar sus bytes. El registro separado vincula el estado actual a los archivos y filas exactos. Una revisión de Codex no equivale a una revisión humana. Ningún caso final se abrió, redactó ni modificó para preparar esta tabla o registrar la aprobación.
