# Revision de mensajes cortos en espanol

Estado: redaccion y etiquetas aprobadas por el propietario el 4 de octubre de 2026, despues de puntuar los diagnosticos. La revision fluida de portugues sigue pendiente.

Revisa 64 mensajes y sus etiquetas, mas cuatro casos de conversacion sin etiqueta de intent.
Los errores de escritura son intencionales. Las referencias como 'esto' o 'este cargo'
suponen un movimiento existente seleccionado; sin contexto, se debe aclarar cual.
Solicitar revision no autoriza guardar un ticket, devolver dinero ni resolver una disputa.

No se muestran predicciones del modelo. La revision de portugues por una persona fluida sigue pendiente.

## 24 mensajes nuevos de entrenamiento

| ID | Mensaje | Etiqueta |
|---|---|---|
| SHORT-TRAIN-INQUIRY-01-ES-A | ¿Se registró ese pago? | Consultar movimiento |
| SHORT-TRAIN-INQUIRY-01-ES-B | ¿Entró mi pago anterior? | Consultar movimiento |
| SHORT-TRAIN-INQUIRY-02-ES-A | Muéstrame ese pago. | Consultar movimiento |
| SHORT-TRAIN-INQUIRY-02-ES-B | Busca mi pago anterior. | Consultar movimiento |
| SHORT-TRAIN-INQUIRY-03-ES-A | Explícame este pago. | Consultar movimiento |
| SHORT-TRAIN-INQUIRY-03-ES-B | Aclárame ese pago. | Consultar movimiento |
| SHORT-TRAIN-DISPUTE-01-ES-A | Yo no compré eso. | Solicitar revision de un cargo |
| SHORT-TRAIN-DISPUTE-01-ES-B | No reconosco esa compra. | Solicitar revision de un cargo |
| SHORT-TRAIN-DISPUTE-02-ES-A | Me cobraron doble. | Solicitar revision de un cargo |
| SHORT-TRAIN-DISPUTE-02-ES-B | Ese cobro está duplicado. | Solicitar revision de un cargo |
| SHORT-TRAIN-DISPUTE-03-ES-A | Ese cargo está mal. | Solicitar revision de un cargo |
| SHORT-TRAIN-DISPUTE-03-ES-B | Me cargaron de más. | Solicitar revision de un cargo |
| SHORT-TRAIN-HUMAN-01-ES-A | Pásame con una persona. | Pedir atencion humana |
| SHORT-TRAIN-HUMAN-01-ES-B | Quiero atención de una persona. | Pedir atencion humana |
| SHORT-TRAIN-HUMAN-02-ES-A | Pido un asesor humano. | Pedir atencion humana |
| SHORT-TRAIN-HUMAN-02-ES-B | Solicito un agente humano. | Pedir atencion humana |
| SHORT-TRAIN-HUMAN-03-ES-A | Comunícame con un operador. | Pedir atencion humana |
| SHORT-TRAIN-HUMAN-03-ES-B | Pásame con una operadora. | Pedir atencion humana |
| SHORT-TRAIN-UNSUPPORTED-01-ES-A | Haz un pago nuevo. | Servicio fuera del alcance |
| SHORT-TRAIN-UNSUPPORTED-01-ES-B | Inicia una transferencia. | Servicio fuera del alcance |
| SHORT-TRAIN-UNSUPPORTED-02-ES-A | Consígueme un préstamo. | Servicio fuera del alcance |
| SHORT-TRAIN-UNSUPPORTED-02-ES-B | Tramita un préstamo. | Servicio fuera del alcance |
| SHORT-TRAIN-UNSUPPORTED-03-ES-A | Reembolsa ese pago. | Servicio fuera del alcance |
| SHORT-TRAIN-UNSUPPORTED-03-ES-B | Devuélveme ese dinero. | Servicio fuera del alcance |

## 24 mensajes del diagnostico de cobertura

| ID | Mensaje | Etiqueta |
|---|---|---|
| short-es-01 | quiero ver un pago | Consultar movimiento |
| short-es-02 | muestrame mis compras | Consultar movimiento |
| short-es-03 | q pago hice? | Consultar movimiento |
| short-es-04 | ver mis movimietos | Consultar movimiento |
| short-es-05 | buscame un cobro | Consultar movimiento |
| short-es-06 | detalles de este cargo? | Consultar movimiento |
| short-es-07 | yo no hize esto | Solicitar revision de un cargo |
| short-es-08 | ese cargo no fui yo | Solicitar revision de un cargo |
| short-es-09 | esa compra no es mia | Solicitar revision de un cargo |
| short-es-10 | me cobraron doble | Solicitar revision de un cargo |
| short-es-11 | quiero reclamar este pago | Solicitar revision de un cargo |
| short-es-12 | no reconosco ese cobro | Solicitar revision de un cargo |
| short-es-13 | quiero una persona | Pedir atencion humana |
| short-es-14 | pasame con un asesor | Pedir atencion humana |
| short-es-15 | necesito hablar con alguien del banco | Pedir atencion humana |
| short-es-16 | que me atienda un humano | Pedir atencion humana |
| short-es-17 | puedo hablar con una agente? | Pedir atencion humana |
| short-es-18 | quiero un asesor porfavor | Pedir atencion humana |
| short-es-19 | bloquea mi tarjeta | Servicio fuera del alcance |
| short-es-20 | quiero pedir un prestamo | Servicio fuera del alcance |
| short-es-21 | quiero hacer un pago | Servicio fuera del alcance |
| short-es-22 | manda dinero | Servicio fuera del alcance |
| short-es-23 | devuelveme el dinero | Servicio fuera del alcance |
| short-es-24 | cuanto saldo tengo? | Servicio fuera del alcance |

## 16 mensajes del diagnostico posterior

| ID | Mensaje | Etiqueta |
|---|---|---|
| short_followup_es_001 | Explícame los detalles de este pago. | Consultar movimiento |
| short_followup_es_002 | Quiero saber cuándo se registró este pago. | Consultar movimiento |
| short_followup_es_003 | Busca el registro de este pago. | Consultar movimiento |
| short_followup_es_004 | Nesesito ver el pago que ya seleccioné. | Consultar movimiento |
| short_followup_es_005 | No reconozco este cargo. | Solicitar revision de un cargo |
| short_followup_es_006 | Este cargo no es mío, quiero que lo revisen. | Solicitar revision de un cargo |
| short_followup_es_007 | El importe de este cargo está incorrecto. | Solicitar revision de un cargo |
| short_followup_es_008 | Revisen este cargo, el monto está mal. | Solicitar revision de un cargo |
| short_followup_es_009 | Quiero hablar con una persona. | Pedir atencion humana |
| short_followup_es_010 | Pásame con alguien humano, por favor. | Pedir atencion humana |
| short_followup_es_011 | Necesito hablar con un agente humano. | Pedir atencion humana |
| short_followup_es_012 | Conéctame con un asesor humano. | Pedir atencion humana |
| short_followup_es_013 | ¿Cuál es mi saldo actual? | Servicio fuera del alcance |
| short_followup_es_014 | Muéstrame cuánto dinero tengo en la cuenta. | Servicio fuera del alcance |
| short_followup_es_015 | Bloquea mi tarjeta, por favor. | Servicio fuera del alcance |
| short_followup_es_016 | Quiero que bloqueen mi tarjeta ahora. | Servicio fuera del alcance |

## Cuatro casos de conversacion, fuera de la puntuacion de intent

| ID | Mensaje | Comportamiento esperado |
|---|---|---|
| short-state-es-01 | buenas | Saludar; no preparar ni guardar una solicitud. |
| short-state-es-02 | tengo hambre | Aclarar el alcance; no inventar un problema de transaccion ni crear una solicitud. |
| short-state-es-03 | no quiero reclamar | Respetar que no desea reclamar; no preparar ni guardar una solicitud. |
| short-state-es-04 | si | Sin pregunta de consentimiento activa, pedir contexto; no interpretar 'si' como permiso para guardar. |

Identidad exacta de esta revision: 0d0ad3372614972d55dd2b578ba7de7900c37204d5d73e5f7ac42362659591f6
