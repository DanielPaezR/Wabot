"""Agenda del día para el equipo: la contraparte de la reserva directa.

Una sola pantalla (/agenda) para el barbero y para el dueño:
  * el barbero ve SU día: quién viene, a qué hora, huecos libres, y con un toque completa, marca
    "no vino", cancela, recuerda por WhatsApp, agenda a alguien que llegó sin cita o bloquea un rato;
  * el dueño ve a TODO el equipo: quién está atendiendo ahora, quién sigue, y lo que entra en caja.
Las notificaciones (nueva reserva, cancelación, recordatorios) llegan por push y quedan en la campana.

Reutiliza lo probado: ``database.agregar_cita`` (solapamientos), ``database.bloquear_horario_profesional``,
``disponibilidad.horarios_libres`` y ``push_notifications``.
"""
import re
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor

import database as db
import disponibilidad
import localizacion
import publico

bp = Blueprint('agenda', __name__)

ACTIVAS = ('confirmado', 'confirmada', 'pendiente')
_columnas_listas = False


def asegurar_columnas():
    """notificaciones_profesional.fecha_creacion tenía un valor por defecto fijo ('2025-12-12'): todas las
    notificaciones parecían de ese día. Se corrige el valor por defecto y se agrega la hora exacta (creada_en)."""
    global _columnas_listas
    if _columnas_listas:
        return
    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('ALTER TABLE notificaciones_profesional ALTER COLUMN fecha_creacion SET DEFAULT CURRENT_DATE')
        cur.execute('ALTER TABLE notificaciones_profesional ADD COLUMN IF NOT EXISTS creada_en TIMESTAMP DEFAULT now()')
        conn.commit()
        _columnas_listas = True
    except Exception as e:
        conn.rollback()
        print(f'⚠️ No se pudieron ajustar las columnas de notificaciones: {e}')
    finally:
        conn.close()
ESTADOS_PERMITIDOS = {'completado', 'no_asistio', 'cancelado', 'confirmado'}


# =============================================================================
# Quién está mirando
# =============================================================================

def _quien(api=True):
    """{'rol', 'negocio_id', 'profesional_id' (o None), 'usuario_id', 'nombre'} del usuario del panel."""
    rol = session.get('usuario_rol')
    negocio_id = session.get('negocio_id')
    if rol not in ('profesional', 'propietario', 'superadmin') or not negocio_id:
        if api:
            r = jsonify({'ok': False, 'error': 'Inicia sesión'})
            r.status_code = 401
            abort(r)
        abort(redirect(url_for('login')))
    profesional_id = session.get('profesional_id') if rol == 'profesional' else None
    if rol == 'profesional' and not profesional_id:
        if api:
            r = jsonify({'ok': False, 'error': 'Tu usuario no tiene un perfil de profesional'})
            r.status_code = 403
            abort(r)
        abort(redirect(url_for('profesional_dashboard')))
    localizacion.fijar_negocio(negocio_id)
    return {'rol': 'profesional' if rol == 'profesional' else 'dueno', 'negocio_id': int(negocio_id),
            'profesional_id': int(profesional_id) if profesional_id else None,
            'usuario_id': session.get('usuario_id'), 'nombre': session.get('usuario_nombre') or ''}


def _pros_visibles(q, todos):
    if q['rol'] == 'profesional':
        return [p for p in todos if p['id'] == q['profesional_id']]
    return todos


def _profesional_permitido(q, profesional_id):
    try:
        profesional_id = int(profesional_id)
    except (TypeError, ValueError):
        return None
    if q['rol'] == 'profesional' and profesional_id != q['profesional_id']:
        return None
    pros = publico.profesionales_de(q['negocio_id'])
    return next((p for p in pros if p['id'] == profesional_id), None)


def _cita_del_negocio(q, cita_id):
    conn = db.get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''SELECT c.*, s.nombre AS servicio, s.precio, COALESCE(s.moneda, 'COP') AS moneda,
                              p.nombre AS profesional
                       FROM citas c LEFT JOIN servicios s ON s.id = c.servicio_id
                       LEFT JOIN profesionales p ON p.id = c.profesional_id
                       WHERE c.id = %s AND c.negocio_id = %s''', (cita_id, q['negocio_id']))
        cita = cur.fetchone()
    finally:
        conn.close()
    if not cita or (q['rol'] == 'profesional' and cita['profesional_id'] != q['profesional_id']):
        return None
    return cita


# =============================================================================
# Utilidades
# =============================================================================

def _whatsapp(negocio, telefono):
    digitos = re.sub(r'\D', '', str(telefono or ''))
    if len(digitos) < 7:
        return ''
    prefijo = negocio['pais'].get('prefijo') or ''
    if prefijo and not digitos.startswith(prefijo) and len(digitos) <= 10:
        digitos = prefijo + digitos
    return digitos


def _mensaje_recordatorio(negocio, cita):
    nombre = (cita.get('cliente') or '').split(' ')[0]
    return (f"Hola {nombre} 👋 Te recordamos tu cita en {negocio['nombre']}: "
            f"{publico.fecha_larga(cita['fecha']).lower()} a las {cita['hora_txt']} con {cita['profesional']} "
            f"({cita['servicio']}). Si necesitas cancelar, puedes hacerlo aquí: "
            f"{request.host_url.rstrip('/')}/{negocio['slug']}/mis-citas ¡Te esperamos!")


def _minutos(valor):
    return disponibilidad.a_minutos(valor)


def _fecha_param(negocio_id):
    fecha = (request.args.get('fecha') or '')[:10]
    try:
        datetime.strptime(fecha, '%Y-%m-%d')
        return fecha
    except ValueError:
        return localizacion.ahora_en(negocio_id).date().isoformat()


# =============================================================================
# Página
# =============================================================================

@bp.route('/agenda')
def pagina():
    q = _quien(api=False)
    negocio = publico.negocio_por_id(q['negocio_id'])
    if not negocio:
        abort(404)
    if negocio['es_alquiler']:
        return redirect(url_for('alquiler.dashboard'))
    pros = publico.profesionales_de(q['negocio_id'])
    yo = next((p for p in pros if p['id'] == q['profesional_id']), None)
    datos = {
        'rol': q['rol'],
        'yo': yo['id'] if yo else None,
        'nombre': (yo['primer_nombre'] if yo else (q['nombre'] or '').split(' ')[0]),
        'negocio': {'id': negocio['id'], 'nombre': negocio['nombre'], 'slug': negocio['slug'],
                    'pro': negocio['vocab']['pro'], 'pros': negocio['vocab']['pros'],
                    'tel_ejemplo': negocio['pais']['ejemplo']},
        'profesionales': [{k: p[k] for k in ('id', 'nombre', 'primer_nombre', 'foto', 'iniciales', 'servicios')}
                          for p in _pros_visibles(q, pros)],
        'servicios': [{k: s[k] for k in ('id', 'nombre', 'duracion', 'duracion_txt', 'precio_txt')}
                      for s in publico.servicios_de(q['negocio_id'])],
        'enlace': request.host_url.rstrip('/') + '/' + (negocio['slug'] or ''),
        'cita': request.args.get('cita', type=int),
        'fecha_inicial': _fecha_de_cita(q, request.args.get('cita', type=int)),
    }
    return render_template('agenda/agenda.html', negocio=negocio, datos=datos, rol=q['rol'],
                           acento=negocio['acento'], acento_tinta=negocio['acento_tinta'])


def _fecha_de_cita(q, cita_id):
    """Al abrir un aviso push de una cita, la agenda arranca en el día de esa cita."""
    if not cita_id:
        return None
    cita = _cita_del_negocio(q, cita_id)
    return str(cita['fecha'])[:10] if cita else None


@bp.route('/manifest-agenda.json')
def manifest():
    """Permite instalar la agenda en el celular como una app (abre directo en /agenda)."""
    nombre = session.get('negocio_nombre') or 'Wabot'
    return jsonify({
        'name': f'Agenda · {nombre}', 'short_name': 'Agenda', 'start_url': '/agenda', 'scope': '/',
        'display': 'standalone', 'background_color': '#0b0b0e', 'theme_color': '#0b0b0e', 'orientation': 'portrait',
        'icons': [{'src': f'/static/icons/icon-{t}x{t}.png', 'sizes': f'{t}x{t}', 'type': 'image/png'} for t in (192, 512)]
        + [{'src': '/static/icons/icon-maskable-512x512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'}],
    })


# =============================================================================
# API: el día
# =============================================================================

def _citas_rango(negocio_id, desde, hasta, profesional_ids):
    conn = db.get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT c.id, c.fecha, c.hora, c.estado, c.cliente_nombre, c.cliente_telefono, c.profesional_id,
                   (c.created_at IS NOT NULL AND now() - c.created_at < interval '3 hours') AS reciente,
                   COALESCE(c.duracion_minutos, s.duracion, 30) AS duracion,
                   s.nombre AS servicio, s.precio, COALESCE(s.moneda, 'COP') AS moneda, p.nombre AS profesional
            FROM citas c
            LEFT JOIN servicios s ON s.id = c.servicio_id
            LEFT JOIN profesionales p ON p.id = c.profesional_id
            WHERE c.negocio_id = %s AND c.fecha >= %s AND c.fecha <= %s AND c.profesional_id = ANY(%s)
            ORDER BY c.fecha, c.hora
        ''', (negocio_id, desde, hasta, list(profesional_ids)))
        return cur.fetchall()
    finally:
        conn.close()


def _formatear(negocio, c):
    hora = publico._hhmm(c['hora']) or '00:00'
    inicio = _minutos(hora)
    duracion = int(c['duracion'] or 30)
    estado = (c['estado'] or 'confirmado').lower()
    bloqueo = estado == 'bloqueado'
    if estado in ('confirmada', 'pendiente'):
        estado = 'confirmado'
    if estado == 'cancelada':
        estado = 'cancelado'
    item = {
        'id': c['id'], 'fecha': str(c['fecha'])[:10], 'hora': hora, 'hora_txt': publico.hora_12(hora),
        'fin': disponibilidad.a_hhmm(inicio + duracion), 'fin_txt': publico.hora_12(disponibilidad.a_hhmm(inicio + duracion)),
        'inicio_min': inicio, 'duracion': duracion, 'duracion_txt': publico.duracion_legible(duracion),
        'estado': 'bloqueo' if bloqueo else estado, 'profesional_id': c['profesional_id'], 'profesional': c['profesional'],
    }
    if bloqueo:
        motivo = re.sub(r'^Bloqueado:\s*', '', (c['cliente_nombre'] or '').strip())
        item['motivo'] = 'Bloqueado' if not motivo or motivo == 'Horario no disponible' else motivo
        return item
    nombre = (c['cliente_nombre'] or 'Cliente').strip().title()
    item.update({
        'cliente': nombre, 'iniciales': publico.iniciales(nombre),
        'telefono': c['cliente_telefono'] or '', 'servicio': c['servicio'] or 'Servicio',
        'precio': float(c['precio'] or 0), 'precio_txt': publico.formatear_precio(c['precio'], c['moneda']),
        'nueva': bool(c.get('reciente')),
    })
    wa = _whatsapp(negocio, c['cliente_telefono'])
    if wa:
        item['whatsapp'] = wa
        item['recordatorio'] = 'https://wa.me/%s?text=%s' % (wa, quote(_mensaje_recordatorio(negocio, item)))
    return item


@bp.route('/api/agenda/dia')
def api_dia():
    q = _quien()
    negocio = publico.negocio_por_id(q['negocio_id'])
    fecha = _fecha_param(q['negocio_id'])
    pros = _pros_visibles(q, publico.profesionales_de(q['negocio_id']))
    ahora_local = localizacion.ahora_en(q['negocio_id'])
    filas = _citas_rango(q['negocio_id'], fecha, fecha, [p['id'] for p in pros]) if pros else []
    citas = [_formatear(negocio, c) for c in filas]

    horario = db.obtener_horarios_por_dia(q['negocio_id'], fecha)
    es_hoy = fecha == ahora_local.date().isoformat()
    ahora_min = ahora_local.hour * 60 + ahora_local.minute if es_hoy else None

    # Huecos libres por profesional (solo dentro del horario y, si es hoy, desde ahora)
    huecos = {}
    if horario and horario.get('activo'):
        ini_dia, fin_dia = _minutos(horario['hora_inicio']), _minutos(horario['hora_fin'])
        alm = (_minutos(horario.get('almuerzo_inicio')), _minutos(horario.get('almuerzo_fin')))
        for p in pros:
            ocupados = sorted((c['inicio_min'], c['inicio_min'] + c['duracion']) for c in citas
                              if c['profesional_id'] == p['id'] and c['estado'] in ('confirmado', 'completado', 'bloqueo'))
            if alm[0] is not None and alm[1] is not None and alm[1] > alm[0]:
                ocupados.append(alm)
                ocupados.sort()
            libres, cursor_min = [], max(ini_dia, ahora_min or 0)
            if ahora_min is not None and cursor_min % 15:
                cursor_min += 15 - cursor_min % 15
            for a, b in ocupados:
                if a - cursor_min >= 30:
                    libres.append({'desde': disponibilidad.a_hhmm(cursor_min), 'hasta': disponibilidad.a_hhmm(a),
                                   'desde_min': cursor_min, 'txt': f"{publico.hora_12(disponibilidad.a_hhmm(cursor_min))} – {publico.hora_12(disponibilidad.a_hhmm(a))}",
                                   'minutos': a - cursor_min})
                cursor_min = max(cursor_min, b)
            if fin_dia - cursor_min >= 30:
                libres.append({'desde': disponibilidad.a_hhmm(cursor_min), 'hasta': disponibilidad.a_hhmm(fin_dia),
                               'desde_min': cursor_min, 'txt': f"{publico.hora_12(disponibilidad.a_hhmm(cursor_min))} – {publico.hora_12(disponibilidad.a_hhmm(fin_dia))}",
                               'minutos': fin_dia - cursor_min})
            huecos[p['id']] = libres

    # Estado del equipo ahora mismo (solo hoy)
    equipo = []
    for p in pros:
        mias = [c for c in citas if c['profesional_id'] == p['id'] and c['estado'] in ('confirmado', 'completado')]
        actual = next((c for c in mias if ahora_min is not None and c['inicio_min'] <= ahora_min < c['inicio_min'] + c['duracion']), None)
        siguiente = next((c for c in mias if ahora_min is not None and c['inicio_min'] > ahora_min and c['estado'] == 'confirmado'), None)
        bloqueo = next((c for c in citas if c['profesional_id'] == p['id'] and c['estado'] == 'bloqueo' and ahora_min is not None
                        and c['inicio_min'] <= ahora_min < c['inicio_min'] + c['duracion']), None)
        if actual:
            estado = {'tipo': 'ocupado', 'txt': f"Con {actual['cliente'].split(' ')[0]} hasta las {actual['fin_txt']}"}
        elif bloqueo:
            estado = {'tipo': 'bloqueado', 'txt': f"{bloqueo['motivo']} hasta las {bloqueo['fin_txt']}"}
        elif es_hoy:
            estado = {'tipo': 'libre', 'txt': 'Libre ahora'}
        else:
            estado = {'tipo': 'dia', 'txt': f"{len(mias)} cita{'s' if len(mias) != 1 else ''}"}
        equipo.append({'id': p['id'], 'nombre': p['nombre'], 'primer_nombre': p['primer_nombre'], 'foto': p['foto'],
                       'iniciales': p['iniciales'], 'estado': estado,
                       'siguiente': {'hora_txt': siguiente['hora_txt'], 'cliente': siguiente['cliente']} if siguiente else None,
                       'citas': len([c for c in mias if c['estado'] != 'cancelado'])})

    activas = [c for c in citas if c['estado'] in ('confirmado', 'completado')]
    moneda = 'COP'
    resumen = {
        'citas': len(activas),
        'completadas': len([c for c in citas if c['estado'] == 'completado']),
        'pendientes': len([c for c in citas if c['estado'] == 'confirmado']),
        'canceladas': len([c for c in citas if c['estado'] == 'cancelado']),
        'esperado_txt': publico.formatear_precio(sum(c['precio'] for c in activas), moneda),
        'cobrado_txt': publico.formatear_precio(sum(c['precio'] for c in citas if c['estado'] == 'completado'), moneda),
    }
    proxima = None
    if ahora_min is not None:
        prox = next((c for c in citas if c['estado'] == 'confirmado' and c['inicio_min'] + c['duracion'] > ahora_min), None)
        if prox:
            proxima = {'id': prox['id'], 'en_minutos': prox['inicio_min'] - ahora_min}

    return jsonify({
        'ok': True, 'fecha': fecha, 'fecha_txt': publico.fecha_larga(fecha), 'es_hoy': es_hoy, 'ahora_min': ahora_min,
        'horario': {'abierto': bool(horario and horario.get('activo')),
                    'txt': (f"{publico.hora_12(horario['hora_inicio'])} – {publico.hora_12(horario['hora_fin'])}"
                            if horario and horario.get('activo') else 'Cerrado')},
        'citas': citas, 'huecos': huecos, 'equipo': equipo, 'resumen': resumen, 'proxima': proxima,
    })


@bp.route('/api/agenda/semana')
def api_semana():
    """Citas activas por día en los próximos 21 días (para los puntos de la tira de fechas)."""
    q = _quien()
    pros = _pros_visibles(q, publico.profesionales_de(q['negocio_id']))
    hoy = localizacion.ahora_en(q['negocio_id']).date()
    desde = hoy - timedelta(days=7)
    hasta = hoy + timedelta(days=21)
    conteo = {}
    if pros:
        conn = db.get_db_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('''SELECT fecha::text AS fecha, COUNT(*) AS n FROM citas
                           WHERE negocio_id = %s AND profesional_id = ANY(%s) AND fecha >= %s AND fecha <= %s
                             AND estado IN ('confirmado', 'confirmada', 'pendiente', 'completado')
                           GROUP BY fecha''', (q['negocio_id'], [p['id'] for p in pros], desde.isoformat(), hasta.isoformat()))
            conteo = {f['fecha'][:10]: f['n'] for f in cur.fetchall()}
        finally:
            conn.close()
    semana, _ = publico.horario_semana(q['negocio_id'])
    dias = []
    for i in range((hasta - desde).days + 1):
        d = desde + timedelta(days=i)
        dias.append({'fecha': d.isoformat(), 'dia': 'Hoy' if d == hoy else publico.DIAS_CORTOS[d.weekday()], 'num': d.day,
                     'mes': publico.MESES_CORTOS[d.month - 1], 'citas': conteo.get(d.isoformat(), 0),
                     'abierto': semana[d.weekday()]['abierto'], 'hoy': d == hoy})
    return jsonify({'ok': True, 'dias': dias})


# =============================================================================
# API: acciones
# =============================================================================

def _avisar_cliente(cita, negocio, titulo, mensaje, url=None):
    try:
        from push_notifications import enviar_notificacion_cliente
        enviar_notificacion_cliente(cita['cliente_telefono'], negocio['id'], titulo, mensaje, cita_id=cita['id'],
                                    url=url or f"/{negocio['slug']}/mis-citas")
    except Exception as e:
        print(f'⚠️ No se pudo avisar al cliente: {type(e).__name__}: {e}')


@bp.route('/api/agenda/citas/<int:cita_id>/estado', methods=['POST'])
def api_estado(cita_id):
    q = _quien()
    datos = request.get_json(silent=True) or {}
    estado = str(datos.get('estado') or '')
    if estado not in ESTADOS_PERMITIDOS:
        return jsonify({'ok': False, 'error': 'Estado inválido'}), 400
    cita = _cita_del_negocio(q, cita_id)
    if not cita or cita['estado'] == 'bloqueado':
        return jsonify({'ok': False, 'error': 'Cita no encontrada'}), 404
    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('UPDATE citas SET estado = %s WHERE id = %s', (estado, cita_id))
        conn.commit()
    finally:
        conn.close()
    negocio = publico.negocio_por_id(q['negocio_id'])
    hora = publico.hora_12(cita['hora'])
    if estado == 'completado':
        _avisar_cliente(cita, negocio, '¿Cómo te fue?', f"Gracias por venir a {negocio['nombre']}. Califica tu experiencia con {cita['profesional']}.",
                        url=f'/calificar/{cita_id}')
    elif estado == 'cancelado':
        _avisar_cliente(cita, negocio, 'Tu cita fue cancelada',
                        f"{negocio['nombre']} canceló tu cita de las {hora}. Reserva otro horario cuando quieras.", url=f"/{negocio['slug']}")
        if q['rol'] == 'profesional':
            _avisar_duenos(negocio['id'], 'Cita cancelada', f"{cita['profesional']} canceló la cita de {cita['cliente_nombre'] or 'un cliente'} ({hora}).")
    return jsonify({'ok': True})


def _avisar_duenos(negocio_id, titulo, mensaje):
    try:
        from push_notifications import enviar_push_propietarios
        enviar_push_propietarios(negocio_id, titulo, mensaje, url='/agenda')
    except Exception as e:
        print(f'⚠️ No se pudo avisar a los dueños: {type(e).__name__}: {e}')


@bp.route('/api/agenda/horarios')
def api_horarios():
    q = _quien()
    pro = _profesional_permitido(q, request.args.get('profesional_id'))
    servicio = next((s for s in publico.servicios_de(q['negocio_id']) if s['id'] == request.args.get('servicio_id', type=int)), None)
    if not pro or not servicio:
        return jsonify({'ok': False, 'error': 'Datos incompletos'}), 400
    fecha = _fecha_param(q['negocio_id'])
    libres = disponibilidad.horarios_libres(q['negocio_id'], pro['id'], fecha, duracion=servicio['duracion'])
    return jsonify({'ok': True, 'horarios': [{'hora': h, 'txt': publico.hora_12(h)} for h in libres]})


@bp.route('/api/agenda/citas', methods=['POST'])
def api_nueva_cita():
    """Cita creada por el equipo (cliente que llama o llega sin cita). El teléfono es opcional."""
    q = _quien()
    datos = request.get_json(silent=True) or {}
    pro = _profesional_permitido(q, datos.get('profesional_id'))
    servicio = next((s for s in publico.servicios_de(q['negocio_id']) if s['id'] == _entero(datos.get('servicio_id'))), None)
    fecha = str(datos.get('fecha') or '')[:10]
    hora = publico._hhmm(datos.get('hora'))
    nombre = re.sub(r'\s+', ' ', str(datos.get('nombre') or '')).strip()[:60].title()
    telefono_txt = str(datos.get('telefono') or '').strip()
    if not pro or not servicio or not hora:
        return jsonify({'ok': False, 'error': 'Elige profesional, servicio y hora'}), 400
    try:
        datetime.strptime(fecha, '%Y-%m-%d')
    except ValueError:
        return jsonify({'ok': False, 'error': 'Fecha inválida'}), 400
    if len(nombre) < 2:
        return jsonify({'ok': False, 'campo': 'nombre', 'error': 'Escribe el nombre del cliente'}), 400
    telefono = ''
    if telefono_txt:
        telefono = localizacion.normalizar_telefono(telefono_txt, q['negocio_id'], permisivo=True)
        if not telefono:
            return jsonify({'ok': False, 'campo': 'telefono', 'error': 'Teléfono inválido'}), 400
    cita_id = db.agregar_cita(q['negocio_id'], pro['id'], telefono, fecha, hora, servicio['id'], nombre)
    if not cita_id:
        return jsonify({'ok': False, 'error': 'Ese horario se cruza con otra cita o un bloqueo'}), 409
    if telefono:
        publico._guardar_cliente(q['negocio_id'], telefono, nombre)
    if q['rol'] == 'dueno' or pro['id'] != q['profesional_id']:
        publico._avisar_profesional(pro['id'], 'Nueva cita', f"{nombre} · {servicio['nombre']} · {publico.fecha_larga(fecha)} a las {publico.hora_12(hora)}", cita_id)
    return jsonify({'ok': True, 'id': cita_id})


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


@bp.route('/api/agenda/bloqueos', methods=['POST'])
def api_bloquear():
    q = _quien()
    datos = request.get_json(silent=True) or {}
    pro = _profesional_permitido(q, datos.get('profesional_id'))
    fecha = str(datos.get('fecha') or '')[:10]
    hora = publico._hhmm(datos.get('hora'))
    duracion = _entero(datos.get('duracion')) or 60
    motivo = re.sub(r'\s+', ' ', str(datos.get('motivo') or '')).strip()[:60] or 'Bloqueado'
    if not pro or not hora or not (15 <= duracion <= 720):
        return jsonify({'ok': False, 'error': 'Datos incompletos'}), 400
    try:
        datetime.strptime(fecha, '%Y-%m-%d')
    except ValueError:
        return jsonify({'ok': False, 'error': 'Fecha inválida'}), 400
    r = db.bloquear_horario_profesional(q['negocio_id'], pro['id'], fecha, hora, duracion_minutos=duracion, motivo=motivo)
    if not r.get('success'):
        return jsonify({'ok': False, 'error': r.get('error') or r.get('message') or 'No se pudo bloquear'}), 409
    return jsonify({'ok': True})


@bp.route('/api/agenda/bloqueos/<int:bloqueo_id>', methods=['DELETE'])
def api_desbloquear(bloqueo_id):
    q = _quien()
    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        if q['rol'] == 'profesional':
            cur.execute("DELETE FROM citas WHERE id = %s AND negocio_id = %s AND profesional_id = %s AND estado = 'bloqueado'",
                        (bloqueo_id, q['negocio_id'], q['profesional_id']))
        else:
            cur.execute("DELETE FROM citas WHERE id = %s AND negocio_id = %s AND estado = 'bloqueado'", (bloqueo_id, q['negocio_id']))
        borrados = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return jsonify({'ok': bool(borrados)}), (200 if borrados else 404)


# =============================================================================
# API: notificaciones (campana)
# =============================================================================

@bp.route('/api/agenda/notificaciones')
def api_notificaciones():
    q = _quien()
    asegurar_columnas()
    conn = db.get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if q['rol'] == 'profesional':
            cur.execute('''SELECT n.id, n.titulo, n.mensaje, n.leida, n.cita_id, n.fecha_creacion, n.creada_en,
                                  EXTRACT(EPOCH FROM (now() - n.creada_en))::int AS segundos, p.nombre AS profesional
                           FROM notificaciones_profesional n JOIN profesionales p ON p.id = n.profesional_id
                           WHERE n.profesional_id = %s ORDER BY n.id DESC LIMIT 30''', (q['profesional_id'],))
        else:
            cur.execute('''SELECT n.id, n.titulo, n.mensaje, n.leida, n.cita_id, n.fecha_creacion, n.creada_en,
                                  EXTRACT(EPOCH FROM (now() - n.creada_en))::int AS segundos, p.nombre AS profesional
                           FROM notificaciones_profesional n JOIN profesionales p ON p.id = n.profesional_id
                           WHERE p.negocio_id = %s ORDER BY n.id DESC LIMIT 40''', (q['negocio_id'],))
        filas = cur.fetchall()
    finally:
        conn.close()
    hoy = localizacion.ahora_en(q['negocio_id']).date()
    items = []
    for n in filas:
        f = n.get('fecha_creacion')
        cuando = ''
        seg = n.get('segundos')
        if seg is not None and seg < 86400:
            cuando = 'Ahora' if seg < 60 else (f'Hace {seg // 60} min' if seg < 3600 else f'Hace {seg // 3600} h')
        elif f:
            d = f if not hasattr(f, 'date') else f.date()
            cuando = 'Hoy' if d == hoy else ('Ayer' if d == hoy - timedelta(days=1) else f'{d.day} {publico.MESES_CORTOS[d.month - 1]}')
        items.append({'id': n['id'], 'titulo': n['titulo'], 'mensaje': n['mensaje'], 'leida': bool(n['leida']),
                      'cita_id': n['cita_id'], 'cuando': cuando,
                      'profesional': n['profesional'] if q['rol'] == 'dueno' else None})
    # El dueño lleva su propio "visto" en el navegador para no marcar como leídas las notificaciones de su equipo
    return jsonify({'ok': True, 'notificaciones': items, 'rol': q['rol'],
                    'sin_leer': len([i for i in items if not i['leida']]) if q['rol'] == 'profesional' else None})


@bp.route('/api/agenda/notificaciones/leidas', methods=['POST'])
def api_notificaciones_leidas():
    q = _quien()
    if q['rol'] != 'profesional':
        return jsonify({'ok': True})
    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('UPDATE notificaciones_profesional SET leida = TRUE, fecha_leida = CURRENT_DATE WHERE profesional_id = %s AND NOT leida',
                    (q['profesional_id'],))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'ok': True})
