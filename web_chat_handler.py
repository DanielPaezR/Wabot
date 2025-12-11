"""
Manejador de chat web para agendamiento de citas
Versión refactorizada con sistema de botones para el chat web
"""

from flask import Blueprint, request, jsonify, session
from datetime import datetime, timedelta
import database as db
import json
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

web_chat_bp = Blueprint('web_chat', __name__)

# Estados de conversación para sesiones web
# NOTA: Usamos la sesión de Flask en lugar de un diccionario global

# =============================================================================
# FUNCIONES AUXILIARES PARA RENDERIZAR INTERFACES CON BOTONES
# =============================================================================

def crear_botones(opciones):
    """
    Crear estructura de botones para el chat web
    Formato: [{'text': 'Texto botón', 'value': 'valor'}, ...]
    """
    return [{'text': opcion['text'], 'value': opcion['value']} for opcion in opciones]

def menu_principal_con_botones(negocio_id, nombre_cliente=None):
    """Mostrar menú principal con botones"""
    negocio = db.obtener_negocio_por_id(negocio_id)
    config = json.loads(negocio['configuracion']) if negocio['configuracion'] else {}
    
    saludo = config.get('saludo_personalizado', '¡Hola! Soy tu asistente virtual para agendar citas.')
    
    if nombre_cliente:
        mensaje = f"👋 *Hola {nombre_cliente}!* {saludo}"
    else:
        mensaje = f"👋 {saludo}"
    
    botones = [
        {'text': '📅 Agendar nueva cita', 'value': '1'},
        {'text': '📋 Ver mis citas', 'value': '2'},
        {'text': '❌ Cancelar cita', 'value': '3'},
        {'text': '❓ Ayuda / Información', 'value': '4'}
    ]
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones),
        'step': 'menu_principal'
    }

def seleccionar_profesionales_con_botones(profesionales, negocio_id):
    """Mostrar lista de profesionales con botones"""
    mensaje = "👨‍💼 *Selecciona un profesional:*\n\n"
    
    botones = []
    for i, prof in enumerate(profesionales, 1):
        mensaje += f"{i}. *{prof['nombre']}* - {prof['especialidad']}\n"
        botones.append({
            'text': f"{i}. {prof['nombre'][:15]}...",
            'value': str(i)
        })
    
    botones.append({'text': '🔙 Volver al menú', 'value': '0'})
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones),
        'step': 'seleccionando_profesional'
    }

def seleccionar_servicios_con_botones(servicios, profesional_nombre, negocio_id):
    """Mostrar lista de servicios con botones"""
    mensaje = f"📋 *Servicios con {profesional_nombre}:*\n\n"
    
    botones = []
    for i, servicio in enumerate(servicios, 1):
        precio_formateado = f"${servicio['precio']:,.0f}".replace(',', '.')
        mensaje += f"{i}. *{servicio['nombre']}* - {precio_formateado}\n"
        mensaje += f"   ⏰ {servicio['duracion']} minutos\n"
        if servicio.get('descripcion'):
            mensaje += f"   📝 {servicio['descripcion'][:50]}...\n"
        mensaje += "\n"
        
        botones.append({
            'text': f"{i}. {servicio['nombre'][:12]}...",
            'value': str(i)
        })
    
    botones.append({'text': '🔙 Volver atrás', 'value': 'back'})
    botones.append({'text': '🏠 Menú principal', 'value': '0'})
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones),
        'step': 'seleccionando_servicio'
    }

def seleccionar_fechas_con_botones(fechas_disponibles, negocio_id):
    """Mostrar fechas disponibles con botones"""
    mensaje = "📅 *Selecciona una fecha:*\n\n"
    
    botones = []
    for i, fecha_info in enumerate(fechas_disponibles, 1):
        mensaje += f"{i}. {fecha_info['mostrar']}\n"
        botones.append({
            'text': fecha_info['mostrar'][:20],
            'value': str(i)
        })
    
    botones.append({'text': '🔙 Volver atrás', 'value': 'back'})
    botones.append({'text': '🏠 Menú principal', 'value': '0'})
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones),
        'step': 'seleccionando_fecha'
    }

def seleccionar_horas_con_botones(horarios_disponibles, pagina_actual, total_paginas, datos_cita, negocio_id):
    """Mostrar horarios disponibles con botones y navegación"""
    profesional_nombre = datos_cita['profesional_nombre']
    servicio_nombre = datos_cita['servicio_nombre']
    precio_formateado = datos_cita['precio_formateado']
    fecha_formateada = datos_cita['fecha_formateada']
    
    mensaje = f"📅 *Horarios disponibles con {profesional_nombre}* ({fecha_formateada})\n"
    mensaje += f"💼 *Servicio:* {servicio_nombre} - {precio_formateado}\n\n"
    
    # Mostrar horarios de la página actual
    horarios_por_pagina = 6
    inicio = pagina_actual * horarios_por_pagina
    fin = inicio + horarios_por_pagina
    horarios_pagina = horarios_disponibles[inicio:fin]
    
    botones = []
    for i, hora in enumerate(horarios_pagina, 1):
        mensaje += f"{i}. *{hora}*\n"
        botones.append({
            'text': f"{hora}",
            'value': str(i)
        })
    
    # Botones de navegación
    botones_navegacion = []
    
    if pagina_actual > 0:
        botones_navegacion.append({'text': '⬅️ Anterior', 'value': 'prev'})
    
    if pagina_actual < total_paginas - 1:
        botones_navegacion.append({'text': 'Siguiente ➡️', 'value': 'next'})
    
    botones_navegacion.append({'text': '📅 Cambiar fecha', 'value': 'change_date'})
    botones_navegacion.append({'text': '🔙 Volver atrás', 'value': 'back'})
    botones_navegacion.append({'text': '🏠 Menú principal', 'value': '0'})
    
    mensaje += f"\n📄 Página {pagina_actual + 1} de {total_paginas}"
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones + botones_navegacion),
        'step': 'seleccionando_hora',
        'pagination': {
            'current': pagina_actual,
            'total': total_paginas
        }
    }

def confirmar_cita_con_botones(datos_cita, negocio_id):
    """Mostrar confirmación de cita con botones"""
    nombre_cliente = datos_cita['nombre_cliente']
    profesional_nombre = datos_cita['profesional_nombre']
    servicio_nombre = datos_cita['servicio_nombre']
    precio_formateado = datos_cita['precio_formateado']
    fecha_formateada = datos_cita['fecha_formateada']
    hora = datos_cita['hora']
    
    mensaje = f"✅ *Confirmar cita*\n\n"
    mensaje += f"Hola *{nombre_cliente}*, ¿confirmas tu cita?\n\n"
    mensaje += f"👨‍💼 *Profesional:* {profesional_nombre}\n"
    mensaje += f"💼 *Servicio:* {servicio_nombre}\n"
    mensaje += f"💰 *Precio:* {precio_formateado}\n"
    mensaje += f"📅 *Fecha:* {fecha_formateada}\n"
    mensaje += f"⏰ *Hora:* {hora}\n"
    
    botones = [
        {'text': '✅ Confirmar cita', 'value': 'confirm'},
        {'text': '❌ Cancelar', 'value': 'cancel'},
        {'text': '🔙 Volver atrás', 'value': 'back'},
        {'text': '🏠 Menú principal', 'value': '0'}
    ]
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones),
        'step': 'confirmando_cita'
    }

def solicitar_telefono_con_botones(negocio_id):
    """Solicitar teléfono con botones"""
    mensaje = "📱 *Para enviarte recordatorios de tu cita, necesitamos tu número de teléfono.*\n\n"
    mensaje += "Por favor, ingresa tu número de 10 dígitos (ej: 3101234567):\n\n"
    mensaje += "💡 *También puedes:*"
    
    botones = [
        {'text': '📋 Ver información del negocio', 'value': 'info'},
        {'text': '🔙 Volver atrás', 'value': 'back'},
        {'text': '🏠 Menú principal', 'value': '0'}
    ]
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones),
        'step': 'solicitando_telefono',
        'requires_input': True
    }

def mostrar_citas_con_botones(citas, negocio_id):
    """Mostrar citas del cliente con botones"""
    # Obtener session_id de alguna manera (aquí asumimos que está en los datos de sesión)
    # En la práctica, necesitarías pasar el session_id
    nombre_cliente = "Cliente"  # Valor por defecto
    
    if not citas:
        mensaje = f"📋 *No tienes citas programadas*\n\n"
        mensaje += f"Hola *{nombre_cliente}*, no tienes citas programadas para el futuro."
    else:
        mensaje = f"📋 *Tus citas programadas* - {nombre_cliente}:\n\n"
        
        for cita in citas:
            id_cita, fecha, hora, servicio, estado, profesional_nombre = cita
            fecha_str = datetime.strptime(str(fecha), '%Y-%m-%d').strftime('%d/%m')
            emoji = "✅" if estado == 'confirmado' else "❌"
            mensaje += f"{emoji} *{fecha_str}* - {hora}\n"
            mensaje += f"   👨‍💼 {profesional_nombre} - {servicio}\n"
            mensaje += f"   🎫 ID: #{id_cita}\n\n"
    
    botones = [
        {'text': '📅 Agendar nueva cita', 'value': '1'},
        {'text': '❌ Cancelar una cita', 'value': '3'},
        {'text': '🔙 Volver al menú', 'value': 'back'}
    ]
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones),
        'step': 'mostrando_citas'
    }

def cancelar_cita_con_botones(citas, negocio_id):
    """Mostrar citas para cancelar con botones"""
    if not citas:
        return menu_principal_con_botones(negocio_id)
    
    if len(citas) == 1:
        # Solo una cita, mostrar confirmación directa
        cita_id = citas[0][0]
        return confirmar_cancelacion_con_botones(citas[0], negocio_id)
    
    mensaje = "❌ *Citas para cancelar:*\n\n"
    
    botones = []
    for i, cita in enumerate(citas, 1):
        id_cita, fecha, hora, profesional_nombre, servicio_nombre = cita
        fecha_str = datetime.strptime(str(fecha), '%Y-%m-%d').strftime('%d/%m')
        mensaje += f"{i}. 📅 {fecha_str} - {hora}\n"
        mensaje += f"   👨‍💼 {profesional_nombre} - {servicio_nombre}\n"
        mensaje += f"   🎫 ID: #{id_cita}\n\n"
        
        botones.append({
            'text': f"{fecha_str} - {hora}",
            'value': str(id_cita)
        })
    
    botones.append({'text': '🔙 Volver al menú', 'value': 'back'})
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones),
        'step': 'cancelando_cita'
    }

def confirmar_cancelacion_con_botones(cita, negocio_id):
    """Confirmar cancelación de cita con botones"""
    id_cita, fecha, hora, profesional_nombre, servicio_nombre = cita
    fecha_str = datetime.strptime(str(fecha), '%Y-%m-%d').strftime('%d/%m/%Y')
    
    mensaje = f"❌ *¿Confirmas la cancelación?*\n\n"
    mensaje += f"📅 *Fecha:* {fecha_str}\n"
    mensaje += f"⏰ *Hora:* {hora}\n"
    mensaje += f"👨‍💼 *Profesional:* {profesional_nombre}\n"
    mensaje += f"💼 *Servicio:* {servicio_nombre}\n"
    mensaje += f"🎫 *ID:* #{id_cita}\n\n"
    mensaje += "Esta acción no se puede deshacer."
    
    botones = [
        {'text': '✅ Sí, cancelar cita', 'value': 'confirm_cancel'},
        {'text': '❌ No, mantener cita', 'value': 'keep'},
        {'text': '🔙 Volver a mis citas', 'value': 'back'}
    ]
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones),
        'step': 'confirmando_cancelacion',
        'cita_id': id_cita
    }

def mostrar_ayuda_con_botones(negocio_id):
    """Mostrar ayuda e información con botones"""
    negocio = db.obtener_negocio_por_id(negocio_id)
    config = json.loads(negocio['configuracion']) if negocio['configuracion'] else {}
    
    mensaje = f"❓ *Ayuda e Información*\n\n"
    mensaje += f"🏢 *{negocio['nombre']}*\n"
    mensaje += f"📍 {config.get('direccion', 'Dirección no especificada')}\n"
    mensaje += f"📞 {config.get('telefono_contacto', 'Teléfono no especificado')}\n"
    mensaje += f"⏰ {config.get('horario_atencion', 'Horario no especificado')}\n\n"
    mensaje += f"📋 *Política de cancelación:*\n"
    mensaje += f"{config.get('politica_cancelacion', 'Consulta con el negocio')}\n\n"
    mensaje += "💡 *Con este sistema puedes:*\n"
    mensaje += "• Agendar citas\n• Ver tus reservas\n• Cancelar citas\n• Recibir recordatorios"
    
    botones = [
        {'text': '📅 Agendar cita', 'value': '1'},
        {'text': '📋 Ver mis citas', 'value': '2'},
        {'text': '🔙 Volver al menú', 'value': 'back'}
    ]
    
    return {
        'message': mensaje,
        'buttons': crear_botones(botones),
        'step': 'mostrando_ayuda'
    }

# =============================================================================
# FUNCION PRINCIPAL PARA PROCESAR MENSAJES DEL CHAT WEB
# =============================================================================

def procesar_mensaje_chat(user_message, session_id, negocio_id):
    """
    Función principal que procesa mensajes del chat web con sistema de botones
    """
    try:
        user_message = user_message.strip()
        
        print(f"🔧 [CHAT WEB] Mensaje recibido: '{user_message}' de sesión {session_id}")
        
        # Verificar que el negocio existe y está activo
        negocio = db.obtener_negocio_por_id(negocio_id)
        if not negocio:
            return {
                'message': '❌ Este negocio no está configurado en el sistema.',
                'buttons': crear_botones([{'text': 'Reintentar', 'value': 'retry'}]),
                'step': 'error'
            }
        
        if not negocio['activo']:
            return {
                'message': '❌ Este negocio no está activo actualmente.',
                'buttons': crear_botones([{'text': 'Volver', 'value': 'back'}]),
                'step': 'error'
            }
        
        # Usar session_id como identificador único
        numero = session_id
        
        # Inicializar sesión si no existe en la sesión de Flask
        session_key = f'chat_{session_id}_{negocio_id}'
        if session_key not in session:
            session[session_key] = {
                'negocio_id': negocio_id,
                'numero': numero,
                'step': 'inicio',
                'data': {}
            }
        
        # Procesar mensaje según el paso actual
        paso_actual = session[session_key].get('step', 'inicio')
        datos_sesion = session[session_key].get('data', {})
        
        print(f"🔧 [CHAT WEB] Paso actual: {paso_actual}")
        
        if paso_actual == 'inicio':
            return procesar_inicio(numero, negocio_id, session_key)
        elif paso_actual == 'menu_principal':
            return procesar_menu_principal(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'seleccionando_profesional':
            return procesar_seleccion_profesional(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'seleccionando_servicio':
            return procesar_seleccion_servicio(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'seleccionando_fecha':
            return procesar_seleccion_fecha(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'seleccionando_hora':
            return procesar_seleccion_hora(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'confirmando_cita':
            return procesar_confirmacion_cita(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'solicitando_telefono':
            return procesar_solicitud_telefono(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'mostrando_citas':
            return procesar_mostrar_citas(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'cancelando_cita':
            return procesar_cancelar_cita(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'confirmando_cancelacion':
            return procesar_confirmar_cancelacion(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'mostrando_ayuda':
            return procesar_ayuda(user_message, numero, negocio_id, session_key)
        elif paso_actual == 'solicitando_nombre':
            return procesar_solicitud_nombre(user_message, numero, negocio_id, session_key)
        else:
            # Paso desconocido, reiniciar
            session[session_key]['step'] = 'inicio'
            return procesar_inicio(numero, negocio_id, session_key)
        
    except Exception as e:
        print(f"❌ [CHAT WEB] Error procesando mensaje: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'message': '❌ Ocurrió un error al procesar tu mensaje. Por favor, intenta nuevamente.',
            'buttons': crear_botones([{'text': 'Reiniciar', 'value': 'restart'}]),
            'step': 'error'
        }

# =============================================================================
# FUNCIONES PARA PROCESAR CADA PASO DEL FLUJO
# =============================================================================

def procesar_inicio(numero, negocio_id, session_key):
    """Procesar inicio de la conversación"""
    # Verificar si es cliente existente
    nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id)
    
    if nombre_cliente:
        # Cliente existente, mostrar menú personalizado
        session[session_key]['step'] = 'menu_principal'
        session[session_key]['data']['nombre_cliente'] = nombre_cliente
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    else:
        # Cliente nuevo, solicitar nombre
        session[session_key]['step'] = 'solicitando_nombre'
        return {
            'message': '👋 ¡Hola! Soy tu asistente virtual para agendar citas.\n\nPara personalizar tu experiencia, por favor ingresa tu nombre:',
            'buttons': crear_botones([{'text': 'Omitir', 'value': 'skip'}]),
            'step': 'solicitando_nombre',
            'requires_input': True
        }

def procesar_solicitud_nombre(user_message, numero, negocio_id, session_key):
    """Procesar solicitud de nombre"""
    datos_sesion = session[session_key].get('data', {})
    
    if user_message == 'skip':
        # Omitir nombre
        nombre_cliente = None
        session[session_key]['step'] = 'menu_principal'
        session[session_key]['data']['nombre_cliente'] = nombre_cliente
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    # Validar nombre
    nombre = user_message.strip()
    if len(nombre) < 2:
        return {
            'message': '❌ Por favor, ingresa un nombre válido (mínimo 2 caracteres):',
            'buttons': crear_botones([{'text': 'Omitir', 'value': 'skip'}]),
            'step': 'solicitando_nombre',
            'requires_input': True
        }
    
    # Guardar nombre y mostrar menú principal
    session[session_key]['step'] = 'menu_principal'
    session[session_key]['data']['nombre_cliente'] = nombre
    
    # También guardar en la base de datos
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO clientes (negocio_id, telefono, nombre, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            ON CONFLICT (negocio_id, telefono) 
            DO UPDATE SET nombre = EXCLUDED.nombre, updated_at = NOW()
        ''', (negocio_id, numero, nombre))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Error guardando cliente: {e}")
        # Continuar aunque falle
    
    return menu_principal_con_botones(negocio_id, nombre)

def procesar_menu_principal(user_message, numero, negocio_id, session_key):
    """Procesar selección en el menú principal"""
    datos_sesion = session[session_key].get('data', {})
    nombre_cliente = datos_sesion.get('nombre_cliente')
    
    if user_message == '1':
        # Agendar nueva cita
        session[session_key]['step'] = 'seleccionando_profesional'
        return mostrar_profesionales_para_seleccion(numero, negocio_id, session_key)
    
    elif user_message == '2':
        # Ver mis citas
        session[session_key]['step'] = 'mostrando_citas'
        return mostrar_citas_del_cliente(numero, negocio_id, session_key)
    
    elif user_message == '3':
        # Cancelar cita
        session[session_key]['step'] = 'cancelando_cita'
        return mostrar_citas_para_cancelar_cliente(numero, negocio_id, session_key)
    
    elif user_message == '4':
        # Ayuda
        session[session_key]['step'] = 'mostrando_ayuda'
        return mostrar_ayuda_con_botones(negocio_id)
    
    elif user_message == 'back' or user_message == '0':
        # Volver al inicio
        session[session_key]['step'] = 'inicio'
        return procesar_inicio(numero, negocio_id, session_key)
    
    else:
        # Mensaje no reconocido, mostrar menú de nuevo
        return menu_principal_con_botones(negocio_id, nombre_cliente)

def mostrar_profesionales_para_seleccion(numero, negocio_id, session_key):
    """Obtener y mostrar profesionales con botones"""
    try:
        profesionales = db.obtener_profesionales(negocio_id)
        profesionales_activos = [p for p in profesionales if p.get('activo', True)]
        
        if not profesionales_activos:
            return {
                'message': '❌ No hay profesionales disponibles en este momento.',
                'buttons': crear_botones([
                    {'text': '🔙 Volver al menú', 'value': 'back'},
                    {'text': '🔄 Reintentar', 'value': 'retry'}
                ]),
                'step': 'seleccionando_profesional'
            }
        
        # Guardar profesionales en sesión
        session[session_key]['data']['profesionales'] = profesionales_activos
        
        return seleccionar_profesionales_con_botones(profesionales_activos, negocio_id)
        
    except Exception as e:
        print(f"❌ Error obteniendo profesionales: {e}")
        return {
            'message': '❌ Error al cargar profesionales.',
            'buttons': crear_botones([{'text': '🔙 Volver al menú', 'value': 'back'}]),
            'step': 'error'
        }

def procesar_seleccion_profesional(user_message, numero, negocio_id, session_key):
    """Procesar selección de profesional"""
    datos_sesion = session[session_key].get('data', {})
    profesionales = datos_sesion.get('profesionales', [])
    
    if user_message == '0' or user_message == 'back':
        # Volver al menú principal
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    if not user_message.isdigit() or int(user_message) < 1 or int(user_message) > len(profesionales):
        return {
            'message': f'❌ Selección inválida. Por favor, elige entre 1 y {len(profesionales)}',
            'buttons': crear_botones([{'text': '🔙 Volver atrás', 'value': 'back'}]),
            'step': 'seleccionando_profesional'
        }
    
    # Guardar profesional seleccionado
    index = int(user_message) - 1
    profesional = profesionales[index]
    
    session[session_key]['data']['profesional_seleccionado'] = profesional
    session[session_key]['data']['profesional_id'] = profesional['id']
    session[session_key]['data']['profesional_nombre'] = profesional['nombre']
    session[session_key]['step'] = 'seleccionando_servicio'
    
    return mostrar_servicios_para_seleccion(numero, negocio_id, session_key)

def mostrar_servicios_para_seleccion(numero, negocio_id, session_key):
    """Obtener y mostrar servicios con botones"""
    try:
        servicios = db.obtener_servicios(negocio_id)
        servicios_activos = [s for s in servicios if s.get('activo', True)]
        
        if not servicios_activos:
            return {
                'message': '❌ No hay servicios disponibles en este momento.',
                'buttons': crear_botones([{'text': '🔙 Volver atrás', 'value': 'back'}]),
                'step': 'seleccionando_servicio'
            }
        
        datos_sesion = session[session_key].get('data', {})
        profesional_nombre = datos_sesion.get('profesional_nombre', 'el profesional')
        
        # Guardar servicios en sesión
        session[session_key]['data']['servicios'] = servicios_activos
        
        return seleccionar_servicios_con_botones(servicios_activos, profesional_nombre, negocio_id)
        
    except Exception as e:
        print(f"❌ Error obteniendo servicios: {e}")
        return {
            'message': '❌ Error al cargar servicios.',
            'buttons': crear_botones([{'text': '🔙 Volver atrás', 'value': 'back'}]),
            'step': 'error'
        }

def procesar_seleccion_servicio(user_message, numero, negocio_id, session_key):
    """Procesar selección de servicio"""
    datos_sesion = session[session_key].get('data', {})
    servicios = datos_sesion.get('servicios', [])
    
    if user_message == '0':
        # Volver al menú principal
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    if user_message == 'back':
        # Volver a selección de profesional
        session[session_key]['step'] = 'seleccionando_profesional'
        return mostrar_profesionales_para_seleccion(numero, negocio_id, session_key)
    
    if not user_message.isdigit() or int(user_message) < 1 or int(user_message) > len(servicios):
        return {
            'message': f'❌ Selección inválida. Por favor, elige entre 1 y {len(servicios)}',
            'buttons': crear_botones([{'text': '🔙 Volver atrás', 'value': 'back'}]),
            'step': 'seleccionando_servicio'
        }
    
    # Guardar servicio seleccionado
    index = int(user_message) - 1
    servicio = servicios[index]
    
    session[session_key]['data']['servicio_seleccionado'] = servicio
    session[session_key]['data']['servicio_id'] = servicio['id']
    session[session_key]['data']['servicio_nombre'] = servicio['nombre']
    session[session_key]['data']['servicio_precio'] = servicio['precio']
    session[session_key]['data']['servicio_duracion'] = servicio['duracion']
    session[session_key]['step'] = 'seleccionando_fecha'
    
    return mostrar_fechas_para_seleccion(numero, negocio_id, session_key)

def mostrar_fechas_para_seleccion(numero, negocio_id, session_key):
    """Obtener y mostrar fechas disponibles con botones"""
    try:
        fechas_disponibles = obtener_proximas_fechas_disponibles(negocio_id)
        
        if not fechas_disponibles:
            return {
                'message': '❌ No hay fechas disponibles en los próximos días.',
                'buttons': crear_botones([
                    {'text': '🔙 Volver atrás', 'value': 'back'},
                    {'text': '🔄 Reintentar', 'value': 'retry'}
                ]),
                'step': 'seleccionando_fecha'
            }
        
        # Guardar fechas en sesión
        session[session_key]['data']['fechas_disponibles'] = fechas_disponibles
        
        return seleccionar_fechas_con_botones(fechas_disponibles, negocio_id)
        
    except Exception as e:
        print(f"❌ Error obteniendo fechas: {e}")
        return {
            'message': '❌ Error al cargar fechas disponibles.',
            'buttons': crear_botones([{'text': '🔙 Volver atrás', 'value': 'back'}]),
            'step': 'error'
        }

def procesar_seleccion_fecha(user_message, numero, negocio_id, session_key):
    """Procesar selección de fecha"""
    datos_sesion = session[session_key].get('data', {})
    fechas_disponibles = datos_sesion.get('fechas_disponibles', [])
    
    if user_message == '0':
        # Volver al menú principal
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    if user_message == 'back':
        # Volver a selección de servicio
        session[session_key]['step'] = 'seleccionando_servicio'
        return mostrar_servicios_para_seleccion(numero, negocio_id, session_key)
    
    if not user_message.isdigit() or int(user_message) < 1 or int(user_message) > len(fechas_disponibles):
        return {
            'message': f'❌ Selección inválida. Por favor, elige entre 1 y {len(fechas_disponibles)}',
            'buttons': crear_botones([{'text': '🔙 Volver atrás', 'value': 'back'}]),
            'step': 'seleccionando_fecha'
        }
    
    # Guardar fecha seleccionada
    index = int(user_message) - 1
    fecha_info = fechas_disponibles[index]
    
    session[session_key]['data']['fecha_seleccionada'] = fecha_info['fecha']
    session[session_key]['data']['fecha_formateada'] = datetime.strptime(fecha_info['fecha'], '%Y-%m-%d').strftime('%d/%m/%Y')
    session[session_key]['step'] = 'seleccionando_hora'
    session[session_key]['data']['pagina_horarios'] = 0
    
    return mostrar_horarios_para_seleccion(numero, negocio_id, session_key)

def mostrar_horarios_para_seleccion(numero, negocio_id, session_key):
    """Obtener y mostrar horarios disponibles con botones"""
    try:
        datos_sesion = session[session_key].get('data', {})
        
        fecha_seleccionada = datos_sesion.get('fecha_seleccionada')
        profesional_id = datos_sesion.get('profesional_id')
        servicio_id = datos_sesion.get('servicio_id')
        
        # Generar horarios disponibles
        horarios_disponibles = generar_horarios_disponibles_actualizado(
            negocio_id, profesional_id, fecha_seleccionada, servicio_id
        )
        
        if not horarios_disponibles:
            fecha_formateada = datos_sesion.get('fecha_formateada', fecha_seleccionada)
            return {
                'message': f'❌ No hay horarios disponibles para el {fecha_formateada}.',
                'buttons': crear_botones([
                    {'text': '📅 Cambiar fecha', 'value': 'change_date'},
                    {'text': '🔙 Volver atrás', 'value': 'back'}
                ]),
                'step': 'seleccionando_hora'
            }
        
        # Guardar horarios en sesión
        session[session_key]['data']['horarios_disponibles'] = horarios_disponibles
        pagina_actual = datos_sesion.get('pagina_horarios', 0)
        horarios_por_pagina = 6
        total_paginas = (len(horarios_disponibles) + horarios_por_pagina - 1) // horarios_por_pagina
        
        # Preparar datos para mostrar
        datos_cita = {
            'profesional_nombre': datos_sesion.get('profesional_nombre'),
            'servicio_nombre': datos_sesion.get('servicio_nombre'),
            'precio_formateado': f"${datos_sesion.get('servicio_precio', 0):,.0f}".replace(',', '.'),
            'fecha_formateada': datos_sesion.get('fecha_formateada'),
            'nombre_cliente': datos_sesion.get('nombre_cliente', 'Cliente')
        }
        
        return seleccionar_horas_con_botones(
            horarios_disponibles, 
            pagina_actual, 
            total_paginas, 
            datos_cita, 
            negocio_id
        )
        
    except Exception as e:
        print(f"❌ Error obteniendo horarios: {e}")
        return {
            'message': '❌ Error al cargar horarios disponibles.',
            'buttons': crear_botones([{'text': '🔙 Volver atrás', 'value': 'back'}]),
            'step': 'error'
        }

def procesar_seleccion_hora(user_message, numero, negocio_id, session_key):
    """Procesar selección de hora"""
    datos_sesion = session[session_key].get('data', {})
    horarios_disponibles = datos_sesion.get('horarios_disponibles', [])
    pagina_actual = datos_sesion.get('pagina_horarios', 0)
    horarios_por_pagina = 6
    
    if user_message == '0':
        # Volver al menú principal
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    if user_message == 'back':
        # Volver a selección de fecha
        session[session_key]['step'] = 'seleccionando_fecha'
        return mostrar_fechas_para_seleccion(numero, negocio_id, session_key)
    
    if user_message == 'change_date':
        # Cambiar fecha
        session[session_key]['step'] = 'seleccionando_fecha'
        return mostrar_fechas_para_seleccion(numero, negocio_id, session_key)
    
    if user_message == 'prev':
        # Página anterior
        if pagina_actual > 0:
            session[session_key]['data']['pagina_horarios'] = pagina_actual - 1
        return mostrar_horarios_para_seleccion(numero, negocio_id, session_key)
    
    if user_message == 'next':
        # Página siguiente
        total_paginas = (len(horarios_disponibles) + horarios_por_pagina - 1) // horarios_por_pagina
        if pagina_actual < total_paginas - 1:
            session[session_key]['data']['pagina_horarios'] = pagina_actual + 1
        return mostrar_horarios_para_seleccion(numero, negocio_id, session_key)
    
    # Verificar si es selección de hora
    if not user_message.isdigit():
        return {
            'message': '❌ Selección inválida. Por favor, selecciona un horario de la lista.',
            'buttons': crear_botones([{'text': '🔙 Volver atrás', 'value': 'back'}]),
            'step': 'seleccionando_hora'
        }
    
    # Obtener horarios de la página actual
    inicio = pagina_actual * horarios_por_pagina
    fin = inicio + horarios_por_pagina
    horarios_pagina = horarios_disponibles[inicio:fin]
    
    index = int(user_message) - 1
    if index < 0 or index >= len(horarios_pagina):
        return {
            'message': f'❌ Selección inválida. Por favor, elige entre 1 y {len(horarios_pagina)}',
            'buttons': crear_botones([{'text': '🔙 Volver atrás', 'value': 'back'}]),
            'step': 'seleccionando_hora'
        }
    
    # Guardar hora seleccionada
    hora_seleccionada = horarios_pagina[index]
    session[session_key]['data']['hora_seleccionada'] = hora_seleccionada
    session[session_key]['step'] = 'confirmando_cita'
    
    # Mostrar confirmación
    datos_cita = {
        'nombre_cliente': datos_sesion.get('nombre_cliente', 'Cliente'),
        'profesional_nombre': datos_sesion.get('profesional_nombre'),
        'servicio_nombre': datos_sesion.get('servicio_nombre'),
        'precio_formateado': f"${datos_sesion.get('servicio_precio', 0):,.0f}".replace(',', '.'),
        'fecha_formateada': datos_sesion.get('fecha_formateada'),
        'hora': hora_seleccionada
    }
    
    return confirmar_cita_con_botones(datos_cita, negocio_id)

def procesar_confirmacion_cita(user_message, numero, negocio_id, session_key):
    """Procesar confirmación de cita"""
    datos_sesion = session[session_key].get('data', {})
    
    if user_message == '0':
        # Volver al menú principal
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    if user_message == 'back':
        # Volver a selección de hora
        session[session_key]['step'] = 'seleccionando_hora'
        return mostrar_horarios_para_seleccion(numero, negocio_id, session_key)
    
    if user_message == 'cancel':
        # Cancelar agendamiento
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return {
            'message': '❌ Agendamiento cancelado.',
            'buttons': crear_botones([{'text': '🏠 Menú principal', 'value': 'menu'}]),
            'step': 'cancelado'
        }
    
    if user_message == 'confirm':
        # Confirmar cita - solicitar teléfono si no está guardado
        if not datos_sesion.get('telefono_cliente'):
            session[session_key]['step'] = 'solicitando_telefono'
            return solicitar_telefono_con_botones(negocio_id)
        else:
            # Ya tiene teléfono, proceder a crear la cita
            return crear_cita_final(numero, negocio_id, session_key)
    
    return {
        'message': '❌ Opción no válida.',
        'buttons': crear_botones([
            {'text': '✅ Confirmar', 'value': 'confirm'},
            {'text': '❌ Cancelar', 'value': 'cancel'},
            {'text': '🔙 Volver', 'value': 'back'}
        ]),
        'step': 'confirmando_cita'
    }

def procesar_solicitud_telefono(user_message, numero, negocio_id, session_key):
    """Procesar solicitud de teléfono"""
    datos_sesion = session[session_key].get('data', {})
    
    if user_message == '0':
        # Volver al menú principal
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    if user_message == 'back':
        # Volver a confirmación de cita
        session[session_key]['step'] = 'confirmando_cita'
        datos_cita = {
            'nombre_cliente': datos_sesion.get('nombre_cliente', 'Cliente'),
            'profesional_nombre': datos_sesion.get('profesional_nombre'),
            'servicio_nombre': datos_sesion.get('servicio_nombre'),
            'precio_formateado': f"${datos_sesion.get('servicio_precio', 0):,.0f}".replace(',', '.'),
            'fecha_formateada': datos_sesion.get('fecha_formateada'),
            'hora': datos_sesion.get('hora_seleccionada')
        }
        return confirmar_cita_con_botones(datos_cita, negocio_id)
    
    if user_message == 'info':
        # Mostrar información del negocio
        return mostrar_ayuda_con_botones(negocio_id)
    
    # Validar teléfono
    telefono = user_message.strip()
    if not telefono.isdigit() or len(telefono) != 10:
        return {
            'message': '❌ Número inválido. Por favor ingresa 10 dígitos (ej: 3101234567):',
            'buttons': crear_botones([{'text': '🔙 Volver', 'value': 'back'}]),
            'step': 'solicitando_telefono',
            'requires_input': True
        }
    
    # Guardar teléfono y crear cita
    session[session_key]['data']['telefono_cliente'] = telefono
    return crear_cita_final(numero, negocio_id, session_key)

def crear_cita_final(numero, negocio_id, session_key):
    """Crear la cita final en la base de datos"""
    try:
        datos_sesion = session[session_key].get('data', {})
        
        # Obtener datos necesarios
        nombre_cliente = datos_sesion.get('nombre_cliente', 'Cliente')
        telefono_cliente = datos_sesion.get('telefono_cliente', numero)
        profesional_id = datos_sesion.get('profesional_id')
        servicio_id = datos_sesion.get('servicio_id')
        fecha = datos_sesion.get('fecha_seleccionada')
        hora = datos_sesion.get('hora_seleccionada')
        
        # Crear cita en la base de datos
        cita_id = db.agregar_cita_con_telefono(
            negocio_id, profesional_id, telefono_cliente, fecha, hora, 
            servicio_id, nombre_cliente
        )
        
        if cita_id:
            # Limpiar sesión
            session[session_key] = {
                'negocio_id': negocio_id,
                'numero': numero,
                'step': 'menu_principal',
                'data': {'nombre_cliente': nombre_cliente}
            }
            
            # Preparar mensaje de confirmación
            profesional_nombre = datos_sesion.get('profesional_nombre')
            servicio_nombre = datos_sesion.get('servicio_nombre')
            precio_formateado = f"${datos_sesion.get('servicio_precio', 0):,.0f}".replace(',', '.')
            fecha_formateada = datos_sesion.get('fecha_formateada')
            
            mensaje = f'''✅ *Cita confirmada*

Hola *{nombre_cliente}*, tu cita ha sido agendada:

👨‍💼 *Profesional:* {profesional_nombre}
💼 *Servicio:* {servicio_nombre}
💰 *Precio:* {precio_formateado}
📅 *Fecha:* {fecha_formateada}
⏰ *Hora:* {hora}
🎫 *ID:* #{cita_id}

Recibirás recordatorios por mensaje. ¡Te esperamos!'''
            
            return {
                'message': mensaje,
                'buttons': crear_botones([
                    {'text': '📅 Agendar otra cita', 'value': '1'},
                    {'text': '📋 Ver mis citas', 'value': '2'},
                    {'text': '🏠 Menú principal', 'value': 'menu'}
                ]),
                'step': 'cita_confirmada',
                'cita_id': cita_id
            }
        else:
            return {
                'message': '❌ Error al crear la cita. Intenta nuevamente.',
                'buttons': crear_botones([{'text': '🔄 Reintentar', 'value': 'retry'}]),
                'step': 'error'
            }
            
    except Exception as e:
        print(f"❌ Error creando cita: {e}")
        return {
            'message': '❌ Error al crear la cita. Intenta nuevamente.',
            'buttons': crear_botones([{'text': '🔄 Reintentar', 'value': 'retry'}]),
            'step': 'error'
        }

def mostrar_citas_del_cliente(numero, negocio_id, session_key):
    """Mostrar citas del cliente"""
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora, s.nombre as servicio, c.estado, p.nombre as profesional_nombre
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            JOIN profesionales p ON c.profesional_id = p.id
            WHERE c.cliente_telefono = %s AND c.negocio_id = %s AND c.fecha >= CURRENT_DATE
            ORDER BY c.fecha, c.hora
        ''', (numero, negocio_id))
        
        citas = cursor.fetchall()
        conn.close()
        
        return mostrar_citas_con_botones(citas, negocio_id)
        
    except Exception as e:
        print(f"❌ Error obteniendo citas: {e}")
        return {
            'message': '❌ Error al cargar tus citas.',
            'buttons': crear_botones([{'text': '🔙 Volver al menú', 'value': 'back'}]),
            'step': 'error'
        }

def procesar_mostrar_citas(user_message, numero, negocio_id, session_key):
    """Procesar acciones en la vista de citas"""
    datos_sesion = session[session_key].get('data', {})
    
    if user_message == '1':
        # Agendar nueva cita
        session[session_key]['step'] = 'seleccionando_profesional'
        return mostrar_profesionales_para_seleccion(numero, negocio_id, session_key)
    
    elif user_message == '3':
        # Cancelar cita
        session[session_key]['step'] = 'cancelando_cita'
        return mostrar_citas_para_cancelar_cliente(numero, negocio_id, session_key)
    
    elif user_message == 'back':
        # Volver al menú principal
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    else:
        # Mostrar citas de nuevo
        return mostrar_citas_del_cliente(numero, negocio_id, session_key)

def mostrar_citas_para_cancelar_cliente(numero, negocio_id, session_key):
    """Mostrar citas para cancelar"""
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora, p.nombre as profesional_nombre, s.nombre as servicio_nombre
            FROM citas c
            JOIN profesionales p ON c.profesional_id = p.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.cliente_telefono = %s AND c.negocio_id = %s AND c.fecha >= CURRENT_DATE AND c.estado = 'confirmado'
            ORDER BY c.fecha, c.hora
        ''', (numero, negocio_id))
        
        citas = cursor.fetchall()
        conn.close()
        
        return cancelar_cita_con_botones(citas, negocio_id)
        
    except Exception as e:
        print(f"❌ Error obteniendo citas para cancelar: {e}")
        return {
            'message': '❌ Error al cargar citas para cancelar.',
            'buttons': crear_botones([{'text': '🔙 Volver al menú', 'value': 'back'}]),
            'step': 'error'
        }

def procesar_cancelar_cita(user_message, numero, negocio_id, session_key):
    """Procesar selección de cita para cancelar"""
    datos_sesion = session[session_key].get('data', {})
    
    if user_message == 'back':
        # Volver al menú principal
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    # Obtener citas de la sesión
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora, p.nombre as profesional_nombre, s.nombre as servicio_nombre
            FROM citas c
            JOIN profesionales p ON c.profesional_id = p.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.cliente_telefono = %s AND c.negocio_id = %s AND c.fecha >= CURRENT_DATE AND c.estado = 'confirmado'
            ORDER BY c.fecha, c.hora
        ''', (numero, negocio_id))
        
        citas = cursor.fetchall()
        conn.close()
        
        # Buscar la cita seleccionada
        cita_seleccionada = None
        for cita in citas:
            if str(cita[0]) == user_message:
                cita_seleccionada = cita
                break
        
        if not cita_seleccionada:
            return {
                'message': '❌ Cita no encontrada.',
                'buttons': crear_botones([{'text': '🔙 Volver', 'value': 'back'}]),
                'step': 'error'
            }
        
        # Guardar cita seleccionada y mostrar confirmación
        session[session_key]['data']['cita_a_cancelar'] = cita_seleccionada
        session[session_key]['step'] = 'confirmando_cancelacion'
        
        return confirmar_cancelacion_con_botones(cita_seleccionada, negocio_id)
        
    except Exception as e:
        print(f"❌ Error procesando cancelación: {e}")
        return {
            'message': '❌ Error al procesar la cancelación.',
            'buttons': crear_botones([{'text': '🔙 Volver', 'value': 'back'}]),
            'step': 'error'
        }

def procesar_confirmar_cancelacion(user_message, numero, negocio_id, session_key):
    """Procesar confirmación de cancelación"""
    datos_sesion = session[session_key].get('data', {})
    cita_seleccionada = datos_sesion.get('cita_a_cancelar')
    
    if not cita_seleccionada:
        return {
            'message': '❌ No se encontró la cita a cancelar.',
            'buttons': crear_botones([{'text': '🔙 Volver al menú', 'value': 'back'}]),
            'step': 'error'
        }
    
    if user_message == 'confirm_cancel':
        # Cancelar la cita
        try:
            cita_id = cita_seleccionada[0]
            
            from database import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('UPDATE citas SET estado = %s WHERE id = %s AND negocio_id = %s', 
                          ('cancelado', cita_id, negocio_id))
            
            conn.commit()
            conn.close()
            
            # Limpiar datos de la cita
            if 'cita_a_cancelar' in session[session_key]['data']:
                del session[session_key]['data']['cita_a_cancelar']
            
            session[session_key]['step'] = 'menu_principal'
            
            # Mostrar mensaje de confirmación
            fecha_str = datetime.strptime(str(cita_seleccionada[1]), '%Y-%m-%d').strftime('%d/%m/%Y')
            hora = cita_seleccionada[2]
            
            return {
                'message': f'✅ *Cita cancelada*\n\nHas cancelado tu cita del {fecha_str} a las {hora}.\n\nEsperamos verte pronto en otra ocasión.',
                'buttons': crear_botones([
                    {'text': '📅 Agendar nueva cita', 'value': '1'},
                    {'text': '📋 Ver mis citas', 'value': '2'},
                    {'text': '🏠 Menú principal', 'value': 'menu'}
                ]),
                'step': 'cita_cancelada'
            }
            
        except Exception as e:
            print(f"❌ Error cancelando cita: {e}")
            return {
                'message': '❌ Error al cancelar la cita.',
                'buttons': crear_botones([{'text': '🔙 Volver', 'value': 'back'}]),
                'step': 'error'
            }
    
    elif user_message == 'keep':
        # Mantener la cita, volver a menú principal
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    elif user_message == 'back':
        # Volver a la lista de citas para cancelar
        session[session_key]['step'] = 'cancelando_cita'
        return mostrar_citas_para_cancelar_cliente(numero, negocio_id, session_key)
    
    else:
        # Opción no válida
        return confirmar_cancelacion_con_botones(cita_seleccionada, negocio_id)

def procesar_ayuda(user_message, numero, negocio_id, session_key):
    """Procesar ayuda"""
    datos_sesion = session[session_key].get('data', {})
    
    if user_message == '1':
        # Agendar cita
        session[session_key]['step'] = 'seleccionando_profesional'
        return mostrar_profesionales_para_seleccion(numero, negocio_id, session_key)
    
    elif user_message == '2':
        # Ver citas
        session[session_key]['step'] = 'mostrando_citas'
        return mostrar_citas_del_cliente(numero, negocio_id, session_key)
    
    elif user_message == 'back':
        # Volver al menú principal
        session[session_key]['step'] = 'menu_principal'
        nombre_cliente = datos_sesion.get('nombre_cliente')
        return menu_principal_con_botones(negocio_id, nombre_cliente)
    
    else:
        # Mostrar ayuda de nuevo
        return mostrar_ayuda_con_botones(negocio_id)

# =============================================================================
# FUNCIONES AUXILIARES REUTILIZADAS (DE TU CÓDIGO ORIGINAL)
# =============================================================================

def obtener_proximas_fechas_disponibles(negocio_id, dias_a_mostrar=7):
    """Obtener las próximas fechas donde el negocio está activo"""
    fechas_disponibles = []
    fecha_actual = datetime.now()
    
    for i in range(dias_a_mostrar):
        fecha = fecha_actual + timedelta(days=i)
        fecha_str = fecha.strftime('%Y-%m-%d')
        
        # Verificar si el día está activo
        horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha_str)
        
        if horarios_dia and horarios_dia['activo']:
            if i == 0:  # Es hoy
                if verificar_disponibilidad_basica(negocio_id, fecha_str):
                    fechas_disponibles.append({
                        'fecha': fecha_str,
                        'mostrar': "Hoy"
                    })
            else:
                fecha_formateada = fecha.strftime('%A %d/%m').title()
                fecha_formateada = fecha_formateada.replace('Monday', 'Lunes')\
                                                  .replace('Tuesday', 'Martes')\
                                                  .replace('Wednesday', 'Miércoles')\
                                                  .replace('Thursday', 'Jueves')\
                                                  .replace('Friday', 'Viernes')\
                                                  .replace('Saturday', 'Sábado')\
                                                  .replace('Sunday', 'Domingo')
                
                if i == 1:
                    fecha_formateada = "Mañana"
                
                fechas_disponibles.append({
                    'fecha': fecha_str,
                    'mostrar': fecha_formateada
                })
    
    return fechas_disponibles

def generar_horarios_disponibles_actualizado(negocio_id, profesional_id, fecha, servicio_id):
    """Generar horarios disponibles considerando la configuración por días"""
    horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha)
    
    if not horarios_dia or not horarios_dia['activo']:
        return []
    
    fecha_actual = datetime.now()
    fecha_cita = datetime.strptime(fecha, '%Y-%m-%d')
    es_hoy = fecha_cita.date() == fecha_actual.date()
    
    # Obtener citas ya agendadas
    citas_ocupadas = db.obtener_citas_dia(negocio_id, profesional_id, fecha)
    
    # Obtener duración del servicio
    duracion_servicio = db.obtener_duracion_servicio(negocio_id, servicio_id)
    if not duracion_servicio:
        return []
    
    # Generar horarios disponibles
    horarios = []
    hora_actual = datetime.strptime(horarios_dia['hora_inicio'], '%H:%M')
    hora_fin = datetime.strptime(horarios_dia['hora_fin'], '%H:%M')
    
    while hora_actual < hora_fin:
        hora_str = hora_actual.strftime('%H:%M')
        
        # Si es hoy, aplicar margen mínimo de 1 hora
        if es_hoy:
            hora_actual_completa = datetime.combine(fecha_actual.date(), hora_actual.time())
            tiempo_hasta_horario = hora_actual_completa - fecha_actual
            
            margen_minimo_minutos = 60
            if tiempo_hasta_horario.total_seconds() < (margen_minimo_minutos * 60):
                hora_actual += timedelta(minutes=30)
                continue
        
        # Verificar si no es horario de almuerzo y está disponible
        if not es_horario_almuerzo(hora_actual, horarios_dia):
            if esta_disponible(hora_actual, duracion_servicio, citas_ocupadas, horarios_dia):
                horarios.append(hora_str)
        
        hora_actual += timedelta(minutes=30)
    
    return horarios

def verificar_disponibilidad_basica(negocio_id, fecha):
    """Verificación rápida de disponibilidad para una fecha"""
    try:
        horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha)
        if not horarios_dia or not horarios_dia['activo']:
            return False
        
        fecha_actual = datetime.now()
        fecha_cita = datetime.strptime(fecha, '%Y-%m-%d')
        
        if fecha_cita.date() == fecha_actual.date():
            hora_actual = datetime.strptime(horarios_dia['hora_inicio'], '%H:%M')
            hora_fin = datetime.strptime(horarios_dia['hora_fin'], '%H:%M')
            
            while hora_actual < hora_fin:
                hora_actual_completa = datetime.combine(fecha_actual.date(), hora_actual.time())
                if hora_actual_completa >= (fecha_actual + timedelta(minutes=60)):
                    return True
                hora_actual += timedelta(minutes=30)
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error en verificación básica: {e}")
        return False

def es_horario_almuerzo(hora, config_dia):
    """Verificar si es horario de almuerzo"""
    if not config_dia.get('almuerzo_inicio') or not config_dia.get('almuerzo_fin'):
        return False
    
    try:
        almuerzo_ini = datetime.strptime(config_dia['almuerzo_inicio'], '%H:%M')
        almuerzo_fin = datetime.strptime(config_dia['almuerzo_fin'], '%H:%M')
        hora_time = hora.time()
        
        return almuerzo_ini.time() <= hora_time < almuerzo_fin.time()
    except Exception as e:
        print(f"❌ Error verificando horario almuerzo: {e}")
        return False

def esta_disponible(hora_inicio, duracion_servicio, citas_ocupadas, config_dia):
    """Verificar si un horario está disponible"""
    hora_fin_servicio = hora_inicio + timedelta(minutes=duracion_servicio)
    
    try:
        hora_fin_jornada = datetime.strptime(config_dia['hora_fin'], '%H:%M')
        if hora_fin_servicio.time() > hora_fin_jornada.time():
            return False
    except Exception as e:
        print(f"❌ Error verificando horario cierre: {e}")
        return False
    
    if se_solapa_con_almuerzo(hora_inicio, hora_fin_servicio, config_dia):
        return False
    
    for cita_ocupada in citas_ocupadas:
        try:
            hora_cita = datetime.strptime(cita_ocupada[0], '%H:%M')
            duracion_cita = cita_ocupada[1]
            hora_fin_cita = hora_cita + timedelta(minutes=duracion_cita)
            
            if se_solapan(hora_inicio, hora_fin_servicio, hora_cita, hora_fin_cita):
                return False
        except Exception as e:
            print(f"❌ Error verificando cita ocupada: {e}")
            continue
    
    return True

def se_solapa_con_almuerzo(hora_inicio, hora_fin, config_dia):
    """Verificar si un horario se solapa con el almuerzo del día"""
    if not config_dia.get('almuerzo_inicio') or not config_dia.get('almuerzo_fin'):
        return False
    
    try:
        almuerzo_ini = datetime.strptime(config_dia['almuerzo_inicio'], '%H:%M')
        almuerzo_fin = datetime.strptime(config_dia['almuerzo_fin'], '%H:%M')
        
        return (hora_inicio.time() < almuerzo_fin.time() and 
                hora_fin.time() > almuerzo_ini.time())
    except Exception as e:
        print(f"❌ Error verificando solapamiento almuerzo: {e}")
        return False

def se_solapan(inicio1, fin1, inicio2, fin2):
    """Verificar si dos intervalos de tiempo se solapan"""
    return (inicio1.time() < fin2.time() and 
            fin1.time() > inicio2.time())

# =============================================================================
# ENDPOINTS FLASK PARA EL CHAT WEB
# =============================================================================

@web_chat_bp.route('/chat/message', methods=['POST'])
def chat_message():
    """Endpoint para recibir mensajes del chat web"""
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id')
        negocio_id = data.get('negocio_id')
        
        if not all([user_message, session_id, negocio_id]):
            return jsonify({'error': 'Faltan parámetros requeridos'}), 400
        
        # Procesar mensaje
        respuesta = procesar_mensaje_chat(user_message, session_id, negocio_id)
        
        return jsonify(respuesta)
        
    except Exception as e:
        print(f"❌ Error en endpoint chat_message: {e}")
        return jsonify({
            'message': '❌ Error interno del servidor.',
            'buttons': [{'text': 'Reiniciar chat', 'value': 'restart'}],
            'step': 'error'
        }), 500

@web_chat_bp.route('/chat/start', methods=['POST'])
def chat_start():
    """Endpoint para iniciar una sesión de chat"""
    try:
        data = request.json
        negocio_id = data.get('negocio_id')
        
        if not negocio_id:
            return jsonify({'error': 'negocio_id es requerido'}), 400
        
        # Generar session_id único
        session_id = str(uuid.uuid4())
        
        # Inicializar sesión en la sesión de Flask
        session_key = f'chat_{session_id}_{negocio_id}'
        session[session_key] = {
            'negocio_id': negocio_id,
            'numero': session_id,
            'step': 'inicio',
            'data': {}
        }
        
        # Procesar inicio
        respuesta = procesar_inicio(session_id, negocio_id, session_key)
        
        respuesta['session_id'] = session_id
        
        return jsonify(respuesta)
        
    except Exception as e:
        print(f"❌ Error en endpoint chat_start: {e}")
        return jsonify({
            'message': '❌ Error al iniciar el chat.',
            'buttons': [],
            'step': 'error'
        }), 500

@web_chat_bp.route('/chat/restart/<session_id>', methods=['POST'])
def chat_restart(session_id):
    """Endpoint para reiniciar una sesión de chat"""
    try:
        data = request.json
        negocio_id = data.get('negocio_id')
        
        if not negocio_id:
            return jsonify({'error': 'negocio_id es requerido'}), 400
        
        session_key = f'chat_{session_id}_{negocio_id}'
        
        if session_key not in session:
            return jsonify({'error': 'Sesión no encontrada'}), 404
        
        # Reiniciar sesión
        session[session_key] = {
            'negocio_id': negocio_id,
            'numero': session_id,
            'step': 'inicio',
            'data': {}
        }
        
        # Procesar inicio
        respuesta = procesar_inicio(session_id, negocio_id, session_key)
        
        return jsonify(respuesta)
        
    except Exception as e:
        print(f"❌ Error en endpoint chat_restart: {e}")
        return jsonify({
            'message': '❌ Error al reiniciar el chat.',
            'buttons': [],
            'step': 'error'
        }), 500

# =============================================================================
# CONFIGURACIÓN PARA USAR EN APP FLASK
# =============================================================================

def init_web_chat(app):
    """Inicializar el módulo de chat web en la app Flask"""
    app.register_blueprint(web_chat_bp, url_prefix='/web-chat')
    print("✅ Módulo de chat web inicializado correctamente")