"""Panel del propietario y API pública del alquiler de vehículos."""
import os
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for)

import alquiler as A
import alquiler_solicitud as AS
import database as db
from localizacion import tz_negocio

bp = Blueprint('alquiler', __name__)

_cache_tipos = {}          # negocio_id -> (tipo, vence)
_TTL_TIPO = 60


def es_alquiler(negocio_id):
    """¿El negocio es de alquiler de vehículos? (consulta cacheada 60 s)"""
    if not negocio_id:
        return False
    ahora = time.time()
    hit = _cache_tipos.get(negocio_id)
    if hit and hit[1] > ahora:
        return hit[0] == A.TIPO
    try:
        tipo = dict(db.obtener_negocio_por_id(negocio_id) or {}).get('tipo_negocio')
    except Exception:
        return False
    _cache_tipos[negocio_id] = (tipo, ahora + _TTL_TIPO)
    return tipo == A.TIPO


def _propietario(f):
    """Solo propietarios (o superadmin con un negocio en sesión) de un negocio de alquiler."""
    @wraps(f)
    def envoltura(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        if session.get('usuario_rol') not in ('propietario', 'superadmin'):
            flash('No tienes permisos para acceder a esta página', 'error')
            return redirect(url_for('login'))
        negocio_id = session.get('negocio_id')
        if not es_alquiler(negocio_id):
            return redirect(url_for('negocio_dashboard'))
        return f(negocio_id, *args, **kwargs)
    return envoltura


def _csrf_valido():
    return secrets.compare_digest(session.get('csrf_token', ''), request.form.get('csrf_token', ''))


def _ahora():
    return datetime.now(tz_negocio)


def _hoy():
    return _ahora().date()


def _contexto_comun():
    return {'categorias': A.CATEGORIAS, 'transmisiones': A.TRANSMISIONES, 'combustibles': A.COMBUSTIBLES,
            'dinero': A.dinero, 'fmt': A.formatear_fecha, 'etiquetas': A.ETIQUETAS_ESTADO}


# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------

@bp.route('/negocio/alquiler')
@_propietario
def dashboard(negocio_id):
    hoy = _hoy()
    hoy_s = hoy.isoformat()
    movimiento = A.reservas_negocio(negocio_id, 'hoy', hoy)
    for r in movimiento:
        r['tipo_movimiento'] = 'Recoge' if r['fecha_inicio'] == hoy_s else 'Devuelve'
    actividad = A.actividad_reciente(negocio_id)
    for r in actividad + movimiento:
        r['estado_vista'] = A.estado_efectivo(r, hoy)
    negocio = db.obtener_negocio_por_id(negocio_id)
    return render_template('negocio/alquiler_dashboard.html', resumen=A.resumen_negocio(negocio_id, hoy), movimiento=movimiento,
                           actividad=actividad, negocio=negocio, url_cliente=url_for('chat_index', negocio_id=negocio_id, _external=True),
                           **_contexto_comun())


# ---------------------------------------------------------------------------
# Vehículos
# ---------------------------------------------------------------------------

@bp.route('/negocio/vehiculos')
@_propietario
def vehiculos(negocio_id):
    return render_template('negocio/vehiculos.html', vehiculos=A.listar_vehiculos(negocio_id, solo_activos=False), **_contexto_comun())


def _datos_formulario():
    return {k: request.form.get(k, '') for k in A._CAMPOS_VEHICULO}


@bp.route('/negocio/vehiculos/nuevo', methods=['GET', 'POST'])
@_propietario
def vehiculo_nuevo(negocio_id):
    datos = {'categoria': 'Compacto', 'transmision': 'Automática', 'combustible': 'Gasolina', 'pasajeros': 5, 'maletas': 2, 'puertas': 4}
    if request.method == 'POST':
        datos = _datos_formulario()
        if not _csrf_valido():
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        else:
            try:
                A.crear_vehiculo(negocio_id, datos)
                flash('Vehículo agregado', 'success')
                return redirect(url_for('alquiler.vehiculos'))
            except ValueError as e:
                flash(str(e), 'error')
    return render_template('negocio/vehiculo_form.html', vehiculo=datos, nuevo=True, **_contexto_comun())


@bp.route('/negocio/vehiculos/<int:vehiculo_id>/editar', methods=['GET', 'POST'])
@_propietario
def vehiculo_editar(negocio_id, vehiculo_id):
    vehiculo = A.obtener_vehiculo(vehiculo_id, negocio_id)
    if not vehiculo:
        abort(404)
    if request.method == 'POST':
        datos = _datos_formulario()
        if not _csrf_valido():
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        else:
            try:
                A.actualizar_vehiculo(vehiculo_id, negocio_id, datos)
                flash('Vehículo actualizado', 'success')
                return redirect(url_for('alquiler.vehiculos'))
            except ValueError as e:
                flash(str(e), 'error')
                vehiculo = dict(vehiculo, **datos)
    return render_template('negocio/vehiculo_form.html', vehiculo=vehiculo, nuevo=False, vehiculo_id=vehiculo_id, **_contexto_comun())


@bp.route('/negocio/vehiculos/<int:vehiculo_id>/estado', methods=['POST'])
@_propietario
def vehiculo_estado(negocio_id, vehiculo_id):
    if not _csrf_valido():
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
    else:
        activo = request.form.get('activo') == '1'
        if A.activar_vehiculo(vehiculo_id, negocio_id, activo):
            flash('Vehículo activado' if activo else 'Vehículo desactivado: ya no aparece para los clientes', 'success')
    return redirect(url_for('alquiler.vehiculos'))


@bp.route('/negocio/vehiculos/subir-foto', methods=['POST'])
@_propietario
def vehiculo_subir_foto(negocio_id):
    """Sube la foto a Cloudinary (si está configurado) y devuelve su dirección."""
    if not _csrf_valido():
        return jsonify({'success': False, 'error': 'Error de seguridad'}), 400
    if not os.getenv('CLOUDINARY_CLOUD_NAME'):
        return jsonify({'success': False, 'error': 'La subida de fotos aún no está configurada: pega la dirección (URL) de una imagen.'}), 503
    archivo = request.files.get('foto')
    if not archivo or not archivo.filename:
        return jsonify({'success': False, 'error': 'Elige una imagen'}), 400
    if archivo.mimetype not in ('image/jpeg', 'image/png', 'image/webp'):
        return jsonify({'success': False, 'error': 'Solo se admiten imágenes JPG, PNG o WebP'}), 400
    archivo.seek(0, os.SEEK_END)
    if archivo.tell() > 5 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'La imagen no puede pesar más de 5 MB'}), 400
    archivo.seek(0)
    try:
        import cloudinary.uploader
        r = cloudinary.uploader.upload(archivo, folder=f'wabot/negocio_{negocio_id}/vehiculos', resource_type='image')
        return jsonify({'success': True, 'url': r['secure_url']})
    except Exception as e:
        print(f"❌ [ALQUILER] Error subiendo foto: {type(e).__name__}: {e}")
        return jsonify({'success': False, 'error': 'No se pudo subir la imagen'}), 500


# ---------------------------------------------------------------------------
# Reservas
# ---------------------------------------------------------------------------

VISTAS = (('proximas', 'Próximas'), ('en_curso', 'En curso'), ('hoy', 'Hoy'), ('historial', 'Historial'), ('todas', 'Todas'))


@bp.route('/negocio/reservas')
@_propietario
def reservas(negocio_id):
    vista = request.args.get('vista', 'proximas')
    if vista not in dict(VISTAS):
        vista = 'proximas'
    hoy = _hoy()
    lista = A.reservas_negocio(negocio_id, vista, hoy)
    for r in lista:
        r['estado_vista'] = A.estado_efectivo(r, hoy)
    return render_template('negocio/reservas.html', reservas=lista, vista=vista, vistas=VISTAS, **_contexto_comun())


@bp.route('/negocio/reservas/<int:reserva_id>/accion', methods=['POST'])
@_propietario
def reserva_accion(negocio_id, reserva_id):
    accion = request.form.get('accion', '')
    destino = redirect(request.form.get('volver') if (request.form.get('volver') or '').startswith('/negocio/') else url_for('alquiler.reservas'))
    if not _csrf_valido():
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        return destino
    mensaje = (request.form.get('mensaje') or '').strip()
    if accion == 'observar':
        if not mensaje:
            flash('Escribe qué debe corregir o completar el cliente', 'error')
            return destino
        reserva = AS.observar(reserva_id, negocio_id, mensaje)
        if not reserva:
            flash('Esa acción ya no procede para esta reserva', 'error')
            return destino
        AS.notificar_decision(reserva, 'observar', mensaje)
        flash('Se le pidió la corrección al cliente y recibió un aviso', 'success')
        return destino
    if accion == 'cancelar' and mensaje:
        AS.guardar_motivo(reserva_id, negocio_id, mensaje)
    reserva = A.aplicar_accion(reserva_id, negocio_id, accion)
    if not reserva:
        flash('Esa acción ya no procede para esta reserva', 'error')
        return destino
    if accion == 'cancelar':
        A.notificar_cancelacion(reserva, por='propietario')
        if mensaje:
            AS.notificar_decision(reserva, 'cancelar', mensaje)
    elif accion == 'confirmar':
        AS.notificar_decision(reserva, 'confirmar')
    flash({'confirmar': 'Solicitud aprobada: el cliente recibió el aviso', 'entregar': 'Vehículo entregado: la reserva está en curso',
           'devolver': 'Vehículo devuelto: reserva completada', 'cancelar': 'Reserva cancelada y cliente avisado'}[accion], 'success')
    return destino


@bp.route('/negocio/reservas/<int:reserva_id>')
@_propietario
def reserva_detalle(negocio_id, reserva_id):
    reserva = A.obtener_reserva(reserva_id, negocio_id)
    if not reserva:
        abort(404)
    reserva['estado_vista'] = A.estado_efectivo(reserva, _hoy())
    return render_template('negocio/reserva_detalle.html', r=reserva, respuestas=AS.vista_respuestas(reserva), **_contexto_comun())


# ---------------------------------------------------------------------------
# Formulario de solicitud (lo que el negocio pide a sus clientes)
# ---------------------------------------------------------------------------

@bp.route('/negocio/alquiler/formulario')
@_propietario
def formulario(negocio_id):
    return render_template('negocio/alquiler_formulario.html', campos=AS.campos(negocio_id, solo_activos=False), tipos=AS.TIPOS,
                           instrucciones=AS.instrucciones(negocio_id), editar=request.args.get('editar', type=int), max_campos=AS.MAX_CAMPOS,
                           **_contexto_comun())


@bp.route('/negocio/alquiler/formulario/campo', methods=['POST'])
@_propietario
def formulario_campo(negocio_id):
    campo_id = request.form.get('campo_id', type=int)
    if not _csrf_valido():
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
    else:
        try:
            AS.guardar_campo(negocio_id, request.form, campo_id)
            flash('Campo actualizado' if campo_id else 'Campo agregado', 'success')
        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('alquiler.formulario', editar=campo_id) if campo_id else url_for('alquiler.formulario'))
    return redirect(url_for('alquiler.formulario'))


@bp.route('/negocio/alquiler/formulario/campo/<int:campo_id>/accion', methods=['POST'])
@_propietario
def formulario_campo_accion(negocio_id, campo_id):
    accion = request.form.get('accion')
    if not _csrf_valido():
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
    elif accion in ('subir', 'bajar'):
        AS.mover_campo(campo_id, negocio_id, -1 if accion == 'subir' else 1)
    elif accion in ('activar', 'desactivar'):
        AS.activar_campo(campo_id, negocio_id, accion == 'activar')
    elif accion == 'eliminar':
        if AS.eliminar_campo(campo_id, negocio_id):
            flash('Campo eliminado. Las respuestas ya guardadas se conservan.', 'success')
    return redirect(url_for('alquiler.formulario'))


@bp.route('/negocio/alquiler/formulario/instrucciones', methods=['POST'])
@_propietario
def formulario_instrucciones(negocio_id):
    if _csrf_valido():
        AS.guardar_instrucciones(negocio_id, request.form.get('instrucciones'))
        flash('Indicaciones guardadas', 'success')
    else:
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
    return redirect(url_for('alquiler.formulario'))


# ---------------------------------------------------------------------------
# Formulario público del cliente (enlace con token propio de cada solicitud)
# ---------------------------------------------------------------------------

_TIPOS_IMAGEN = ('image/jpeg', 'image/png', 'image/webp')
_MAX_FOTO = 8 * 1024 * 1024


def _subir_documento(archivo, negocio_id, reserva_id):
    """Sube una foto de documento a Cloudinary. Devuelve (url, error)."""
    if not os.getenv('CLOUDINARY_CLOUD_NAME'):
        return None, 'La subida de fotos no está disponible por ahora. Inténtalo más tarde o entrega el documento al recoger el vehículo.'
    if archivo.mimetype not in _TIPOS_IMAGEN:
        return None, 'Solo se admiten imágenes JPG, PNG o WebP'
    archivo.seek(0, os.SEEK_END)
    if archivo.tell() > _MAX_FOTO:
        return None, 'La imagen no puede pesar más de 8 MB'
    archivo.seek(0)
    try:
        import cloudinary.uploader
        r = cloudinary.uploader.upload(archivo, folder=f'wabot/negocio_{negocio_id}/documentos', resource_type='image',
                                       public_id=f'reserva_{reserva_id}_{secrets.token_hex(6)}')
        return r['secure_url'], None
    except Exception as e:
        print(f"❌ [ALQUILER] Error subiendo documento: {type(e).__name__}: {e}")
        return None, 'No se pudo subir la imagen. Intenta de nuevo.'


@bp.route('/alquiler/solicitud/<token>', methods=['GET', 'POST'])
def solicitud(token):
    reserva = AS.obtener_por_token(token)
    if not reserva:
        abort(404)
    negocio_id = reserva['negocio_id']
    lista = AS.campos(negocio_id)
    previas = AS.respuestas_de(reserva)
    editable = reserva['estado'] in ('pendiente', 'confirmada') and reserva['fecha_fin'] >= _hoy().isoformat()
    errores, valores = {}, previas
    if request.method == 'POST' and editable:
        valores = {k: request.form.get(k, '') for k in (c['clave'] for c in lista)}
        if not _csrf_valido():
            flash('Error de seguridad. Recarga la página e intenta de nuevo.', 'error')
        else:
            fotos = {}
            for c in lista:
                archivo = request.files.get(c['clave']) if c['tipo'] == 'foto' else None
                if archivo and archivo.filename:
                    url, error = _subir_documento(archivo, negocio_id, reserva['id'])
                    if error:
                        errores[c['clave']] = error
                    else:
                        fotos[c['clave']] = url
            respuestas, errores_v = AS.validar_respuestas(lista, request.form, fotos, previas)
            errores.update({k: v for k, v in errores_v.items() if k not in errores})
            if errores:
                flash('Revisa los datos marcados en rojo', 'error')
                valores = dict(previas, **{k: v for k, v in valores.items() if k not in fotos})
            else:
                # lo que ya estaba guardado y el formulario actual no pide se conserva
                respuestas = dict({k: v for k, v in previas.items() if k not in {c['clave'] for c in lista}}, **respuestas)
                actualizada = AS.guardar_respuestas(reserva, respuestas)
                if actualizada and actualizada['docs_completos']:
                    AS.notificar_documentos_recibidos(actualizada)
                flash('¡Listo! Recibimos tu información. El negocio la revisará y te avisará.', 'success')
                return redirect(url_for('alquiler.solicitud', token=token))
    negocio = db.obtener_negocio_por_id(negocio_id)
    return render_template('alquiler/solicitud.html', r=reserva, campos=lista, valores=valores, errores=errores, editable=editable, negocio=negocio,
                           instrucciones=AS.instrucciones(negocio_id), **_contexto_comun())


@bp.route('/negocio/reservas/nueva', methods=['GET', 'POST'])
@_propietario
def reserva_nueva(negocio_id):
    """Reserva tomada por teléfono o en mostrador."""
    hoy = _hoy()
    datos = {'fecha': hoy.isoformat(), 'dias': 1, 'hora': '09:00'}
    if request.method == 'POST':
        datos = {k: request.form.get(k, '').strip() for k in ('vehiculo_id', 'nombre', 'telefono', 'fecha', 'dias', 'hora', 'notas')}
        if not _csrf_valido():
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        else:
            try:
                import localizacion
                telefono = localizacion.normalizar_telefono(datos['telefono'], negocio_id, permisivo=True) or ''.join(c for c in datos['telefono'] if c.isdigit())
                if len(telefono) < 7:
                    raise ValueError('Escribe un teléfono válido del cliente')
                if not datos['nombre']:
                    raise ValueError('Escribe el nombre del cliente')
                reserva = A.crear_reserva(negocio_id, int(datos['vehiculo_id'] or 0), telefono, datos['nombre'].title(), datos['fecha'],
                                          int(datos['dias'] or 0), datos['hora'] or '09:00', hoy, notas=datos['notas'], origen='panel')
                A.notificar_nueva_reserva(reserva)
                flash('Reserva creada', 'success')
                return redirect(url_for('alquiler.reservas'))
            except A.ReservaError as e:
                flash({'no_disponible': 'Ese vehículo ya está reservado en esas fechas', 'dias_invalidos': f'Los días deben estar entre 1 y {A.MAX_DIAS}',
                       'fecha_pasada': 'La fecha de recogida ya pasó', 'cerrado_recogida': 'El negocio no abre el día de recogida',
                       'cerrado_devolucion': 'El negocio no abre el día de devolución', 'vehiculo_invalido': 'Elige un vehículo'}.get(e.codigo, str(e)), 'error')
            except ValueError as e:
                flash(str(e), 'error')
    return render_template('negocio/reserva_nueva.html', datos=datos, vehiculos=A.listar_vehiculos(negocio_id), hoy=hoy.isoformat(), max_dias=A.MAX_DIAS, **_contexto_comun())


@bp.route('/negocio/api/alquiler/disponibles')
@_propietario
def api_disponibles(negocio_id):
    """Vehículos libres en un rango (para el formulario de nueva reserva)."""
    try:
        fecha = datetime.strptime(request.args.get('fecha', ''), '%Y-%m-%d').date().isoformat()
        dias = int(request.args.get('dias', 1))
    except ValueError:
        return jsonify({'success': False, 'error': 'Fecha o días inválidos'}), 400
    if not (1 <= dias <= A.MAX_DIAS):
        return jsonify({'success': False, 'error': f'Los días deben estar entre 1 y {A.MAX_DIAS}'}), 400
    libres = A.vehiculos_disponibles(negocio_id, fecha, dias)
    return jsonify({'success': True, 'devolucion': A.fecha_devolucion(fecha, dias),
                    'vehiculos': [{'id': v['id'], 'nombre': v['nombre'], 'total': v['total'], 'precio_dia': v['precio_dia']} for v in libres]})


# ---------------------------------------------------------------------------
# API pública (catálogo para los clientes)
# ---------------------------------------------------------------------------

@bp.route('/api/negocio/<int:negocio_id>/vehiculos')
def api_catalogo(negocio_id):
    """Vehículos activos del negocio. Con ?fecha=YYYY-MM-DD&dias=N marca cuáles están libres en ese rango."""
    if not es_alquiler(negocio_id):
        return jsonify({'success': False, 'error': 'Negocio no encontrado'}), 404
    lista = A.listar_vehiculos(negocio_id)
    libres = None
    fecha = request.args.get('fecha')
    if fecha:
        try:
            dias = int(request.args.get('dias', 1))
            fecha = datetime.strptime(fecha, '%Y-%m-%d').date().isoformat()
            if 1 <= dias <= A.MAX_DIAS:
                libres = {v['id'] for v in A.vehiculos_disponibles(negocio_id, fecha, dias)}
        except ValueError:
            pass
    publico = []
    for v in lista:
        publico.append({k: v.get(k) for k in ('id', 'nombre', 'marca', 'modelo', 'anio', 'categoria', 'transmision', 'combustible', 'pasajeros',
                                              'maletas', 'puertas', 'color', 'precio_dia', 'deposito', 'descripcion', 'foto_url')})
        publico[-1]['disponible'] = True if libres is None else (v['id'] in libres)
    return jsonify({'success': True, 'vehiculos': publico})
