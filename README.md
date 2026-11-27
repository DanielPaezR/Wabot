# Wabot

Reservas para barberías y salones, sin fricción.

Cada negocio tiene **un enlace corto** (`/nacho`) con su perfil: portada, servicios con precios, equipo, trabajos,
opiniones y horario. El cliente reserva en cuatro toques — **servicio → profesional (o "primer disponible") → día y
hora → nombre y WhatsApp** — y el profesional recibe la cita al instante en su celular.

- **Perfil y reserva** (`services/wabot_chat/publico.py`, `templates/publico/`, `static/js/reserva.js`):
  `/` directorio, `/<enlace>` perfil del negocio, `/<enlace>/<profesional>` perfil del profesional,
  `/<enlace>/mis-citas` citas del cliente (cancelar, calificar). API en `/api/reserva/<negocio_id>/...`.
- **Asistente** (`asistente.py`): responde dudas (precios, horario, ubicación, disponibilidad real) y, si la
  conversación termina en una reserva, abre el formulario ya lleno. Usa OpenAI si hay `OPENAI_API_KEY`; si no,
  responde con reglas.
- **Paneles** del negocio, del profesional y del administrador (agenda, bloqueos, estadísticas, equipo, servicios).
  En el inicio del panel el negocio ve su enlace, lo copia, lo envía por WhatsApp, lo cambia y descarga su QR.
- Los enlaces antiguos (`/cliente/<id>`, `/negocio/<id>`, el directorio aparte) redirigen al perfil nuevo.
  Los negocios de alquiler de vehículos conservan su flujo propio.

## Base de datos

`services/wabot_chat/schema.sql` es el esquema (solo estructura) de producción. Para una base nueva:

```bash
psql "$DATABASE_URL" -f services/wabot_chat/schema.sql
```

Después, `python -c "import database; database.init_db()"` (desde `services/wabot_chat`) inserta datos de ejemplo.
Si cambias el esquema en producción, vuelve a generar el archivo con `pg_dump --schema-only --no-owner --no-privileges`.

## Pruebas

```bash
python tests/run_all.py --pg   # ver tests/README.md
```
