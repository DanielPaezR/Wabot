# Pruebas de Wabot

Son scripts independientes (sin framework): cada uno imprime `OK ...` / `FALLO ...` y termina con
`RESULTADO: TODO OK` o `RESULTADO: HAY FALLOS`. El ejecutor `run_all.py` los corre todos y resume.

## Cómo correrlas

```bash
pip install -r services/wabot_chat/requirements.txt

python tests/run_all.py            # pruebas sin base de datos (las de PostgreSQL salen como "saltadas")
python tests/run_all.py --pg       # TODAS: levanta un PostgreSQL temporal, carga schema.sql y datos de ejemplo
python tests/run_all.py renta      # solo las pruebas cuyo nombre contiene "renta"
python tests/test_pg_renta_autos.py   # una prueba suelta (las pg_ necesitan TEST_DATABASE_URL)
```

`--pg` necesita PostgreSQL **instalado** (`initdb`, `postgres` y `pg_ctl`); no hace falta que esté corriendo.
Si ya tienes una base local **vacía**: `python tests/run_all.py --pg-url postgresql://usuario@127.0.0.1:5432/nombre`
(el ejecutor carga `schema.sql` y los datos de ejemplo).

> Las pruebas `test_pg_*` **borran filas** (citas, conversaciones, negocios de prueba…). Por eso se niegan a
> correr contra cualquier base que no sea local. Nunca apuntes `TEST_DATABASE_URL` a producción.

## Qué cubre cada una

| Prueba | Qué verifica |
|---|---|
| `test_pg_disponibilidad` | horarios libres (citas, almuerzo, bloqueos, recurrentes, hoy), API y herramienta de IA |
| `test_pg_bloqueos` | duración de los bloqueos, solapamientos, bloquear sobre citas |
| `test_pg_renta_autos` | renta por varios días: flujo del chat, disponibilidad, IA, "mis reservas" |
| `test_pg_estado_chat` | el estado de la conversación sobrevive a reinicios; IP real detrás del proxy |
| `test_pg_push` | notificaciones push con `pywebpush` real (varios servicios, dispositivos caducados, rutas protegidas, cancelaciones) |
| `test_pg_monitoreo` | `/health`, `/health/completo`, latido del programador, registro de errores, `/admin/errores` |
| `test_pg_numeros_whatsapp` | números de la API de WhatsApp por negocio |
| `test_mis_citas` | filtro Próximas / Anteriores y estado de las citas |
| `test_flujo_aruba`, `test_localizacion`, `test_scheduler_aruba` | país, zona horaria y teléfonos por negocio (Aruba/Colombia) |
| `test_webhook_n8n`, `test_whatsapp_meta`, `test_sin_whatsapp` | endpoints de WhatsApp (hoy suspendidos) |
| `test_plantillas`, `test_plantillas_validas`, `test_prompt`, `test_prompt_editor`, `test_diseno` | plantillas (Jinja y JavaScript válidos), editor del prompt, diseño |

## Integración continua

`.github/workflows/pruebas.yml` corre todo (con PostgreSQL y Python 3.9, la versión de producción) en cada pull request.

## Agregar una prueba

Copia una existente: importa los módulos con `sys.path` apuntando a `services/wabot_chat` (ya resuelto con
`_SERVICIO`), usa `check(nombre, condicion)` y termina imprimiendo `RESULTADO: TODO OK`. Si necesita base de datos,
llámala `test_pg_*.py` y usa `_url_bd_pg()` (ver cualquier `test_pg_*`).
