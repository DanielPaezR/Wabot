"""Negocio de demostración de alquiler de vehículos (para mostrar el sistema a dueños de este tipo de negocio).

Se puede ejecutar de dos formas (es idempotente: si ya existe, solo restablece la clave y repone los datos de ejemplo):
  * desde el panel de administración (botón "Crear demo de alquiler"), o
  * ``DATABASE_URL=... python alquiler_demo.py`` contra una base de datos.
Los datos de ejemplo son ficticios: clientes, teléfonos y documentos (imagen etiquetada "EJEMPLO").
"""
import json
import secrets
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

import alquiler as A
import alquiler_solicitud as AS
import database as db

NOMBRE = 'AutoRenta Demo - Alquiler de vehículos'
TELEFONO = 'whatsapp:+570000000099'
EMAIL = 'demo.alquiler@wabot.app'
DOCUMENTO_EJEMPLO = '/static/img/documento-ejemplo.svg'

FLOTA = (
    dict(nombre='Kia Picanto 2023', marca='Kia', modelo='Picanto', anio=2023, categoria='Económico', transmision='Manual', combustible='Gasolina',
         pasajeros=4, maletas=1, puertas=5, color='Rojo', placa='DEM-101', precio_dia=65000, deposito=300000,
         descripcion='Ideal para moverte por la ciudad: ágil, económico y fácil de parquear. Aire acondicionado y Bluetooth.'),
    dict(nombre='Renault Logan 2022', marca='Renault', modelo='Logan', anio=2022, categoria='Sedán', transmision='Manual', combustible='Gasolina',
         pasajeros=5, maletas=3, puertas=4, color='Gris', placa='DEM-102', precio_dia=85000, deposito=400000,
         descripcion='Sedán cómodo con baúl amplio, perfecto para viajes en familia por carretera.'),
    dict(nombre='Toyota Corolla 2024', marca='Toyota', modelo='Corolla', anio=2024, categoria='Sedán', transmision='Automática', combustible='Híbrido',
         pasajeros=5, maletas=3, puertas=4, color='Blanco', placa='DEM-103', precio_dia=135000, deposito=600000,
         descripcion='Automático e híbrido: confort y bajo consumo. Cámara de reversa y sensores de parqueo.'),
    dict(nombre='Renault Duster 2023', marca='Renault', modelo='Duster', anio=2023, categoria='SUV', transmision='Manual', combustible='Gasolina',
         pasajeros=5, maletas=3, puertas=5, color='Naranja', placa='DEM-104', precio_dia=150000, deposito=700000,
         descripcion='Camioneta robusta para carretera destapada y destinos de montaña.'),
    dict(nombre='Toyota Fortuner 2023', marca='Toyota', modelo='Fortuner', anio=2023, categoria='Camioneta', transmision='Automática', combustible='Diésel',
         pasajeros=7, maletas=4, puertas=5, color='Negro', placa='DEM-105', precio_dia=290000, deposito=1200000,
         descripcion='7 puestos, tracción 4x4 y gran espacio de carga para grupos y viajes largos.'),
    dict(nombre='Kia Carnival 2022', marca='Kia', modelo='Carnival', anio=2022, categoria='Van', transmision='Automática', combustible='Gasolina',
         pasajeros=8, maletas=5, puertas=5, color='Plata', placa='DEM-106', precio_dia=320000, deposito=1300000,
         descripcion='Van familiar de 8 pasajeros con puertas eléctricas y aire para todas las filas.'),
    dict(nombre='Mercedes-Benz C200 2024', marca='Mercedes-Benz', modelo='C200', anio=2024, categoria='Lujo', transmision='Automática', combustible='Gasolina',
         pasajeros=5, maletas=2, puertas=4, color='Azul', placa='DEM-107', precio_dia=480000, deposito=2500000,
         descripcion='Para ocasiones especiales: interior en cuero, techo panorámico y asistentes de conducción.'),
)


def _clave():
    return 'Demo-' + secrets.token_urlsafe(7).replace('_', 'x').replace('-', 'y')


def _asegurar_negocio():
    def q(cur):
        cur.execute("SELECT id FROM negocios WHERE nombre = %s AND tipo_negocio = %s ORDER BY id LIMIT 1", (NOMBRE, A.TIPO))
        f = cur.fetchone()
        return f['id'] if f else None
    negocio_id = A._con_cursor(q)
    if negocio_id:
        return negocio_id, False
    configuracion = {
        'saludo_personalizado': '¡Hola! Soy el asistente de AutoRenta. Te ayudo a reservar tu vehículo en minutos.',
        'horario_atencion': 'Lunes a sábado 8:00 AM - 6:00 PM',
        'direccion': 'Calle 10 # 5-20, Centro',
        'telefono_contacto': '+57 300 000 0099',
        'politica_cancelacion': 'Puedes cancelar sin costo hasta 24 horas antes de la recogida',
    }
    negocio_id = db.crear_negocio(nombre=NOMBRE, telefono_whatsapp=TELEFONO, tipo_negocio=A.TIPO, configuracion=json.dumps(configuracion), emoji='🚗',
                                  latitud=6.2442, longitud=-75.5812, direccion=configuracion['direccion'])
    if not negocio_id:
        raise RuntimeError('No se pudo crear el negocio de demostración')
    import localizacion
    localizacion.guardar(negocio_id, 'CO', 'America/Bogota')
    return negocio_id, True


def _propietario(negocio_id, clave):
    """Un propietario propio de la demo (el que crea el sistema por defecto usa una clave conocida)."""
    def q(cur):
        cur.execute("DELETE FROM usuarios WHERE negocio_id = %s AND email LIKE %s", (negocio_id, 'propietario%@negocio.com'))
        cur.execute("SELECT id FROM usuarios WHERE email = %s", (EMAIL,))
        f = cur.fetchone()
        h = generate_password_hash(clave)
        if f:
            cur.execute("UPDATE usuarios SET password_hash = %s, negocio_id = %s, activo = TRUE WHERE id = %s", (h, negocio_id, f['id']))
        else:
            cur.execute("INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol) VALUES (%s, %s, %s, %s, 'propietario')",
                        (negocio_id, 'Dueño de la demo', EMAIL, h))
    try:
        A._con_cursor(q, escribir=True)
    except Exception:
        # esquemas sin la columna "activo"
        def q2(cur):
            cur.execute("SELECT id FROM usuarios WHERE email = %s", (EMAIL,))
            f = cur.fetchone()
            h = generate_password_hash(clave)
            if f:
                cur.execute("UPDATE usuarios SET password_hash = %s, negocio_id = %s WHERE id = %s", (h, negocio_id, f['id']))
            else:
                cur.execute("INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol) VALUES (%s, %s, %s, %s, 'propietario')",
                            (negocio_id, 'Dueño de la demo', EMAIL, h))
        A._con_cursor(q2, escribir=True)


def _flota(negocio_id):
    def q(cur):
        cur.execute("DELETE FROM reservas_vehiculo WHERE negocio_id = %s", (negocio_id,))
        cur.execute("DELETE FROM vehiculos WHERE negocio_id = %s", (negocio_id,))
    A._con_cursor(q, escribir=True)
    return {v['nombre']: A.crear_vehiculo(negocio_id, {k: str(x) for k, x in v.items()}) for v in FLOTA}


def _formulario(negocio_id):
    def q(cur):
        cur.execute("DELETE FROM alquiler_campos WHERE negocio_id = %s", (negocio_id,))
        cur.execute("DELETE FROM alquiler_config WHERE negocio_id = %s", (negocio_id,))
    A._con_cursor(q, escribir=True)
    AS.asegurar_formulario(negocio_id)
    AS.guardar_instrucciones(negocio_id, "Para apartar el vehículo transfiere un abono del 30% del total a la cuenta de ahorros 000-000000-00 "
                                         "(ejemplo) y sube el comprobante en este formulario.\nEdad mínima: 21 años y licencia con más de 2 años de vigencia.")


def _reservas(negocio_id, ids):
    hoy = date.today()
    d = lambda n: (hoy + timedelta(days=n)).isoformat()
    respuestas = {'documento_numero': '1.234.567.890', 'documento_foto': DOCUMENTO_EJEMPLO, 'licencia_numero': 'LIC-0001-DEMO',
                  'licencia_vencimiento': d(900), 'licencia_foto': DOCUMENTO_EJEMPLO, 'direccion': 'Cra 43 # 12-34, Medellín',
                  'lugar_entrega': 'En el aeropuerto', 'comprobante_abono': DOCUMENTO_EJEMPLO}
    ejemplos = (   # vehículo, cliente, teléfono, inicio, días, estado, documentos, observación
        ('Toyota Corolla 2024', 'Camila Restrepo', '3001000001', d(3), 3, 'pendiente', True, None),
        ('Renault Duster 2023', 'Andrés Gómez', '3001000002', d(5), 4, 'pendiente', False, None),
        ('Kia Picanto 2023', 'Laura Mejía', '3001000003', d(1), 2, 'confirmada', True, None),
        ('Toyota Fortuner 2023', 'Familia Ospina', '3001000004', d(-1), 3, 'en_curso', True, None),
        ('Renault Logan 2022', 'Juan Pablo Torres', '3001000005', d(-9), 4, 'completada', True, None),
        ('Mercedes-Benz C200 2024', 'Sofía Herrera', '3001000006', d(8), 2, 'cancelada', True, 'No alcanzó la edad mínima requerida'),
    )

    def q(cur):
        for veh, cliente, tel, ini, dias, estado, docs, obs in ejemplos:
            vid = ids[veh]
            cur.execute("SELECT precio_dia, deposito FROM vehiculos WHERE id = %s", (vid,))
            v = cur.fetchone()
            precio = float(v['precio_dia'])
            cur.execute("""INSERT INTO reservas_vehiculo (negocio_id, vehiculo_id, cliente_telefono, cliente_nombre, fecha_inicio, fecha_fin, hora, dias,
                                                           precio_dia, total, deposito, estado, origen, token, respuestas, docs_completos, docs_enviados, observacion)
                           VALUES (%s, %s, %s, %s, %s, %s, '10:00', %s, %s, %s, %s, %s, 'chat', %s, %s, %s, %s, %s)""",
                        (negocio_id, vid, tel, cliente, ini, A.fecha_devolucion(ini, dias), dias, precio, precio * dias, float(v['deposito']), estado,
                         secrets.token_hex(16), json.dumps(respuestas if docs else {k: respuestas[k] for k in ('documento_numero',)}, ensure_ascii=False),
                         docs, 'now' if docs else None, obs))
    A._con_cursor(q, escribir=True)


def crear_demo():
    """Crea o repone la demo. Devuelve {'negocio_id', 'email', 'clave', 'nuevo', 'url_cliente'}."""
    negocio_id, nuevo = _asegurar_negocio()
    clave = _clave()
    _propietario(negocio_id, clave)
    ids = _flota(negocio_id)
    _formulario(negocio_id)
    _reservas(negocio_id, ids)
    return {'negocio_id': negocio_id, 'email': EMAIL, 'clave': clave, 'nuevo': nuevo, 'url_cliente': f'/cliente/{negocio_id}'}


if __name__ == '__main__':
    r = crear_demo()
    print(f"Negocio {r['negocio_id']} ({'creado' if r['nuevo'] else 'repuesto'}) · usuario {r['email']} · clave {r['clave']} · {r['url_cliente']}")
