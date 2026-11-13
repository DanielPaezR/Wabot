"""Solicitud de arrendamiento: los datos y documentos que cada negocio pide al cliente.

Una reserva hecha por el cliente nace como SOLICITUD (estado ``pendiente``): el vehículo queda apartado, el cliente
completa un formulario con enlace propio (``reservas_vehiculo.token``) y el propietario revisa la información y la
aprueba, pide una corrección o la rechaza.

Cada negocio edita su formulario (tabla ``alquiler_campos``): campos de texto, número, fecha, lista de opciones,
Sí/No y foto, obligatorios u opcionales, en el orden que quiera. Las respuestas se guardan como JSON en
``reservas_vehiculo.respuestas`` (las fotos son direcciones de imagen).
"""
import json
import re
import unicodedata
from datetime import datetime

import alquiler as A
import database as db

TIPOS = {
    'texto': 'Texto corto',
    'texto_largo': 'Texto largo',
    'numero': 'Número',
    'fecha': 'Fecha',
    'seleccion': 'Lista de opciones',
    'si_no': 'Sí / No',
    'foto': 'Foto o imagen',
}
MAX_CAMPOS = 25

# Lo que normalmente se pide para alquilar un vehículo (el propietario puede cambiarlo todo)
CAMPOS_BASE = (
    ('documento_numero', 'Número de documento de identidad', 'texto', True, None, 'Cédula, pasaporte o documento de tu país'),
    ('documento_foto', 'Foto del documento de identidad', 'foto', True, None, 'Una foto clara de la parte frontal'),
    ('licencia_numero', 'Número de licencia de conducir', 'texto', True, None, None),
    ('licencia_vencimiento', 'Vencimiento de la licencia', 'fecha', True, None, 'Debe estar vigente durante todo el alquiler'),
    ('licencia_foto', 'Foto de la licencia de conducir', 'foto', True, None, 'Una foto clara de la parte frontal'),
    ('direccion', 'Dirección de residencia', 'texto', False, None, None),
    ('lugar_entrega', 'Lugar de entrega del vehículo', 'seleccion', False, 'En la oficina\nEn el aeropuerto\nEn mi hotel o domicilio', None),
    ('comprobante_abono', 'Comprobante del abono', 'foto', False, None, 'Si el negocio te pidió un abono para apartar el vehículo, adjunta el comprobante'),
)


# ---------------------------------------------------------------------------
# Formulario del negocio
# ---------------------------------------------------------------------------

def _campo_dict(f):
    c = dict(f)
    c['opciones_lista'] = lista_opciones(c.get('opciones'))
    return c


def lista_opciones(texto):
    return [o.strip() for o in re.split(r'[\n;]', texto or '') if o.strip()]


def asegurar_formulario(negocio_id):
    """La primera vez que se consulta, el negocio recibe el formulario habitual. Después solo cambia por el propietario."""
    def q(cur):
        cur.execute("INSERT INTO alquiler_config (negocio_id) VALUES (%s) ON CONFLICT (negocio_id) DO NOTHING RETURNING negocio_id", (negocio_id,))
        if cur.fetchone():
            for orden, (clave, etiqueta, tipo, obligatorio, opciones, ayuda) in enumerate(CAMPOS_BASE, 1):
                cur.execute("""INSERT INTO alquiler_campos (negocio_id, clave, etiqueta, tipo, obligatorio, opciones, ayuda, orden)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (negocio_id, clave) DO NOTHING""",
                            (negocio_id, clave, etiqueta, tipo, obligatorio, opciones, ayuda, orden))
    A._con_cursor(q, escribir=True)


def campos(negocio_id, solo_activos=True):
    asegurar_formulario(negocio_id)

    def q(cur):
        cur.execute("SELECT * FROM alquiler_campos WHERE negocio_id = %s" + (" AND activo = TRUE" if solo_activos else "") + " ORDER BY orden, id", (negocio_id,))
        return [_campo_dict(f) for f in cur.fetchall()]
    return A._con_cursor(q)


def obtener_campo(campo_id, negocio_id):
    def q(cur):
        cur.execute("SELECT * FROM alquiler_campos WHERE id = %s AND negocio_id = %s", (campo_id, negocio_id))
        f = cur.fetchone()
        return _campo_dict(f) if f else None
    return A._con_cursor(q)


def _clave_nueva(etiqueta, existentes):
    base = unicodedata.normalize('NFKD', etiqueta).encode('ascii', 'ignore').decode().lower()
    base = re.sub(r'[^a-z0-9]+', '_', base).strip('_')[:30] or 'campo'
    clave, n = f'c_{base}', 2
    while clave in existentes:
        clave = f'c_{base}_{n}'
        n += 1
    return clave


def guardar_campo(negocio_id, datos, campo_id=None):
    """Crea o edita un campo. Lanza ValueError con un mensaje para el propietario."""
    etiqueta = (datos.get('etiqueta') or '').strip()
    tipo = (datos.get('tipo') or 'texto').strip()
    if not etiqueta:
        raise ValueError('Escribe qué quieres pedir (por ejemplo: "Número de licencia")')
    if len(etiqueta) > 80:
        raise ValueError('El nombre del campo es muy largo (máximo 80 caracteres)')
    if tipo not in TIPOS:
        raise ValueError('Tipo de campo no válido')
    opciones = None
    if tipo == 'seleccion':
        lista = lista_opciones(datos.get('opciones'))
        if len(lista) < 2:
            raise ValueError('Una lista necesita al menos 2 opciones (una por línea)')
        if len(lista) > 20 or any(len(o) > 60 for o in lista):
            raise ValueError('Máximo 20 opciones de hasta 60 caracteres')
        opciones = '\n'.join(lista)
    ayuda = (datos.get('ayuda') or '').strip()[:200] or None
    obligatorio = str(datos.get('obligatorio', '')).lower() in ('1', 'true', 'on', 'si', 'sí')
    existentes = {c['clave'] for c in campos(negocio_id, solo_activos=False)}

    def q(cur):
        if campo_id:
            cur.execute("""UPDATE alquiler_campos SET etiqueta = %s, tipo = %s, obligatorio = %s, opciones = %s, ayuda = %s
                           WHERE id = %s AND negocio_id = %s RETURNING id""", (etiqueta, tipo, obligatorio, opciones, ayuda, campo_id, negocio_id))
            if not cur.fetchone():
                raise ValueError('Ese campo ya no existe')
            return campo_id
        if len(existentes) >= MAX_CAMPOS:
            raise ValueError(f'Máximo {MAX_CAMPOS} campos en el formulario')
        cur.execute("SELECT COALESCE(MAX(orden), 0) + 1 AS n FROM alquiler_campos WHERE negocio_id = %s", (negocio_id,))
        orden = cur.fetchone()['n']
        cur.execute("""INSERT INTO alquiler_campos (negocio_id, clave, etiqueta, tipo, obligatorio, opciones, ayuda, orden)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (negocio_id, _clave_nueva(etiqueta, existentes), etiqueta, tipo, obligatorio, opciones, ayuda, orden))
        return cur.fetchone()['id']
    return A._con_cursor(q, escribir=True)


def activar_campo(campo_id, negocio_id, activo):
    def q(cur):
        cur.execute("UPDATE alquiler_campos SET activo = %s WHERE id = %s AND negocio_id = %s", (bool(activo), campo_id, negocio_id))
        return cur.rowcount > 0
    return A._con_cursor(q, escribir=True)


def eliminar_campo(campo_id, negocio_id):
    def q(cur):
        cur.execute("DELETE FROM alquiler_campos WHERE id = %s AND negocio_id = %s", (campo_id, negocio_id))
        return cur.rowcount > 0
    return A._con_cursor(q, escribir=True)


def mover_campo(campo_id, negocio_id, direccion):
    """direccion: -1 sube, +1 baja (intercambia la posición con el vecino)."""
    lista = campos(negocio_id, solo_activos=False)
    ids = [c['id'] for c in lista]
    if campo_id not in ids:
        return False
    i = ids.index(campo_id)
    j = i + (-1 if direccion < 0 else 1)
    if not (0 <= j < len(ids)):
        return False
    ids[i], ids[j] = ids[j], ids[i]

    def q(cur):
        for orden, cid in enumerate(ids, 1):
            cur.execute("UPDATE alquiler_campos SET orden = %s WHERE id = %s AND negocio_id = %s", (orden, cid, negocio_id))
    A._con_cursor(q, escribir=True)
    return True


def instrucciones(negocio_id):
    asegurar_formulario(negocio_id)

    def q(cur):
        cur.execute("SELECT instrucciones FROM alquiler_config WHERE negocio_id = %s", (negocio_id,))
        f = cur.fetchone()
        return (f['instrucciones'] or '') if f else ''
    return A._con_cursor(q)


def guardar_instrucciones(negocio_id, texto):
    asegurar_formulario(negocio_id)

    def q(cur):
        cur.execute("UPDATE alquiler_config SET instrucciones = %s WHERE negocio_id = %s", ((texto or '').strip()[:1500] or None, negocio_id))
    A._con_cursor(q, escribir=True)


# ---------------------------------------------------------------------------
# Respuestas del cliente
# ---------------------------------------------------------------------------

def respuestas_de(reserva):
    try:
        datos = json.loads(reserva.get('respuestas') or '{}')
        return datos if isinstance(datos, dict) else {}
    except ValueError:
        return {}


def _vacio(valor):
    return valor is None or str(valor).strip() == ''


def obligatorios_pendientes(negocio_id, respuestas):
    """Cuántos campos obligatorios activos siguen sin respuesta."""
    return sum(1 for c in campos(negocio_id) if c['obligatorio'] and _vacio(respuestas.get(c['clave'])))


def validar_respuestas(lista_campos, formulario, fotos_nuevas, previas):
    """Devuelve (respuestas, errores). ``fotos_nuevas``: clave -> dirección ya subida; ``previas``: respuestas ya guardadas."""
    respuestas, errores = {}, {}
    for c in lista_campos:
        clave, tipo = c['clave'], c['tipo']
        if tipo == 'foto':
            valor = fotos_nuevas.get(clave) or previas.get(clave)
        else:
            valor = (formulario.get(clave) or '').strip()
        if _vacio(valor):
            if c['obligatorio']:
                errores[clave] = 'Este dato es obligatorio'
            continue
        if tipo == 'texto' and len(valor) > 200:
            errores[clave] = 'Máximo 200 caracteres'
        elif tipo == 'texto_largo' and len(valor) > 1000:
            errores[clave] = 'Máximo 1000 caracteres'
        elif tipo == 'numero':
            limpio = valor.replace(' ', '').replace(',', '.')
            if not re.fullmatch(r'-?\d{1,15}(\.\d{1,6})?', limpio):
                errores[clave] = 'Escribe solo un número'
                continue
            valor = limpio
        elif tipo == 'fecha':
            try:
                valor = datetime.strptime(valor, '%Y-%m-%d').date().isoformat()
            except ValueError:
                errores[clave] = 'Elige una fecha válida'
                continue
        elif tipo == 'seleccion' and valor not in c['opciones_lista']:
            errores[clave] = 'Elige una de las opciones'
            continue
        elif tipo == 'si_no':
            if valor.lower() not in ('si', 'sí', 'no'):
                errores[clave] = 'Responde Sí o No'
                continue
            valor = 'Sí' if valor.lower() in ('si', 'sí') else 'No'
        respuestas[clave] = valor
    return respuestas, errores


def obtener_por_token(token):
    if not token or not re.fullmatch(r'[0-9a-f]{32}', token):
        return None

    def q(cur):
        cur.execute(A._SELECT_RESERVA + " WHERE r.token = %s", (token,))
        f = cur.fetchone()
        return A._reserva_dict(f) if f else None
    return A._con_cursor(q)


def guardar_respuestas(reserva, respuestas):
    """Guarda lo que el cliente completó y marca si ya están todos los obligatorios. Devuelve la reserva actualizada."""
    completos = obligatorios_pendientes(reserva['negocio_id'], respuestas) == 0

    def q(cur):
        cur.execute("""UPDATE reservas_vehiculo SET respuestas = %s, docs_completos = %s, docs_enviados = NOW(),
                       observacion = CASE WHEN %s THEN NULL ELSE observacion END, actualizado = NOW()
                       WHERE id = %s AND estado IN ('pendiente', 'confirmada') RETURNING id""",
                    (json.dumps(respuestas, ensure_ascii=False), completos, completos, reserva['id']))
        return cur.fetchone() is not None
    if not A._con_cursor(q, escribir=True):
        return None
    return A.obtener_reserva(reserva['id'], reserva['negocio_id'])


def vista_respuestas(reserva):
    """Lista (etiqueta, tipo, valor) con lo que respondió el cliente, en el orden del formulario del negocio."""
    respuestas = respuestas_de(reserva)
    filas = []
    for c in campos(reserva['negocio_id'], solo_activos=False):
        valor = respuestas.get(c['clave'])
        if not _vacio(valor) or (c['activo'] and c['obligatorio']):
            filas.append({'etiqueta': c['etiqueta'], 'tipo': c['tipo'], 'valor': valor, 'obligatorio': c['obligatorio'], 'activo': c['activo']})
    return filas


def estado_documentos(reserva):
    if reserva.get('docs_completos'):
        return 'completos'
    return 'pendientes' if reserva['estado'] in ('pendiente', 'confirmada') else 'no_aplica'


# ---------------------------------------------------------------------------
# Decisión del propietario y avisos
# ---------------------------------------------------------------------------

def observar(reserva_id, negocio_id, mensaje):
    """El propietario pide corregir o completar algo: el cliente recibe el aviso con el enlace a su formulario."""
    mensaje = (mensaje or '').strip()[:300]
    if not mensaje:
        return None

    def q(cur):
        cur.execute("""UPDATE reservas_vehiculo SET observacion = %s, docs_completos = FALSE, actualizado = NOW()
                       WHERE id = %s AND negocio_id = %s AND estado IN ('pendiente', 'confirmada') RETURNING id""", (mensaje, reserva_id, negocio_id))
        return cur.fetchone() is not None
    if not A._con_cursor(q, escribir=True):
        return None
    return A.obtener_reserva(reserva_id, negocio_id)


def guardar_motivo(reserva_id, negocio_id, motivo):
    motivo = (motivo or '').strip()[:300]
    if motivo:
        A._con_cursor(lambda cur: cur.execute("UPDATE reservas_vehiculo SET observacion = %s WHERE id = %s AND negocio_id = %s", (motivo, reserva_id, negocio_id)), escribir=True)


def enlace_cliente(reserva):
    return f"/alquiler/solicitud/{reserva['token']}"


def notificar_documentos_recibidos(reserva):
    try:
        from push_notifications import enviar_push_propietarios
        enviar_push_propietarios(reserva['negocio_id'], 'Documentos recibidos', f"{A._resumen_corto(reserva)}: lista para revisar",
                                 url=f"/negocio/reservas/{reserva['id']}")
    except Exception as e:
        print(f"⚠️ [ALQUILER] No se pudo avisar de los documentos: {type(e).__name__}: {e}")


def notificar_decision(reserva, accion, mensaje=''):
    """Aviso al cliente: aprobada, rechazada o con una corrección pedida. Nunca lanza excepciones."""
    try:
        from push_notifications import enviar_notificacion_cliente
        base = f"{reserva['vehiculo_nombre']} · {A.formatear_fecha(reserva['fecha_inicio'])} a {A.formatear_fecha(reserva['fecha_fin'])}"
        if accion == 'confirmar':
            titulo, texto, url = 'Solicitud aprobada', f"{base}. ¡Todo listo, te esperamos!", f"/cliente/{reserva['negocio_id']}"
        elif accion == 'observar':
            titulo, texto, url = 'Falta un dato en tu solicitud', f"{base}: {mensaje}", enlace_cliente(reserva)
        else:
            titulo, texto, url = 'Solicitud no aprobada', f"{base}" + (f": {mensaje}" if mensaje else ''), f"/cliente/{reserva['negocio_id']}"
        enviar_notificacion_cliente(reserva['cliente_telefono'], reserva['negocio_id'], titulo, texto, cita_id=reserva['id'], url=url)
    except Exception as e:
        print(f"⚠️ [ALQUILER] No se pudo avisar de la decisión: {type(e).__name__}: {e}")
