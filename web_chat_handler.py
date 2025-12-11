"""
Manejador de chat web para agendamiento de citas
Versión con botones para interfaz web - COMPLETO
"""

from flask import Blueprint, request, jsonify, session
from datetime import datetime, timedelta
import database as db
import json
import os
from dotenv import load_dotenv

load_dotenv()

web_chat_bp = Blueprint('web_chat', __name__)

# Estados de conversación para sesiones web
conversaciones_activas = {}

# =============================================================================
# MOTOR DE PLANTILLAS - ADAPTADO PARA BOTONES WEB
# =============================================================================

def format_message_for_web(texto):
    """
    Formatear mensaje para mostrar en chat web con botones
    """
    if not texto:
        return texto
    
    # Reemplazar formato WhatsApp por HTML básico
    texto = texto.replace('*', '<strong>', 1)
    texto = texto.replace('*', '</strong>', 1)
    texto = texto.replace('*', '<strong>', 1)
    texto = texto.replace('*', '</strong>', 1)
    
    # Reemplazar emojis por iconos FontAwesome
    emoji_map = {
        '👨‍💼': '<i class="fas fa-user-tie"></i>',
        '💼': '<i class="fas fa-briefcase"></i>',
        '💰': '<i class="fas fa-money-bill-wave"></i>',
        '📅': '<i class="fas fa-calendar-alt"></i>',
        '⏰': '<i class="fas fa-clock"></i>',
        '🎫': '<i class="fas fa-ticket-alt"></i>',
        '✅': '<i class="fas fa-check-circle text-success"></i>',
        '❌': '<i class="fas fa-times-circle text-danger"></i>',
        '💡': '<i class="fas fa-lightbulb text-warning"></i>',
        '📋': '<i class="fas fa-clipboard-list"></i>',
        '👤': '<i class="fas fa-user"></i>',
        '📍': '<i class="fas fa-map-marker-alt"></i>',
        '📱': '<i class="fas fa-mobile-alt"></i>',
        'ℹ️': '<i class="fas fa-info-circle"></i>',
        '👩‍💼': '<i class="fas fa-user-tie"></i>',
        '✂️': '<i class="fas fa-cut"></i>',
        '💅': '<i class="fas fa-hand-sparkles"></i>',
        '⬅️': '<i class="fas fa-arrow-left"></i>',
        '➡️': '<i class="fas fa-arrow-right"></i>',
        '↩️': '<i class="fas fa-reply"></i>',
        '📄': '<i class="fas fa-file"></i>',
        '🔔': '<i class="fas fa-bell"></i>',
        '🔧': '<i class="fas fa-tools"></i>',
        '🔍': '<i class="fas fa-search"></i>',
        '🎯': '<i class="fas fa-bullseye"></i>',
        '⏱️': '<i class="fas fa-stopwatch"></i>',
        '📧': '<i class="fas fa-envelope"></i>',
    }
    
    for emoji, icon in emoji_map.items():
        texto = texto.replace(emoji, f'{icon} ')
    
    # Convertir saltos de línea a HTML
    texto = texto.replace('\n', '<br>')
    
    return texto

def renderizar_plantilla_web(nombre_plantilla, negocio_id, variables_extra=None):
    """Motor de plantillas para web chat"""
    try:
        # Obtener plantilla de la base de datos
        plantilla_data = db.obtener_plantilla(negocio_id, nombre_plantilla)
        
        if not plantilla_data:
            print(f"❌ Plantilla '{nombre_plantilla}' no encontrada para negocio {negocio_id}")
            return format_message_for_web(f"❌ Error: Plantilla '{nombre_plantilla}' no encontrada")
        
        if isinstance(plantilla_data, dict) and 'plantilla' in plantilla_data:
            plantilla_texto = plantilla_data['plantilla']
        else:
            print(f"❌ Estructura de plantilla inválida: {type(plantilla_data)}")
            return format_message_for_web(f"❌ Error: Estructura de plantilla inválida")
        
        if not plantilla_texto:
            return format_message_for_web(f"❌ Error: Plantilla '{nombre_plantilla}' está vacía")
        
        # Obtener información del negocio
        negocio = db.obtener_negocio_por_id(negocio_id)
        if not negocio:
            return format_message_for_web("❌ Error: Negocio no encontrado")
        
        # Cargar configuración del negocio
        config_json = negocio['configuracion'] if 'configuracion' in negocio else '{}'
        try:
            config = json.loads(config_json)
        except:
            config = {}

        # Variables base disponibles para todas las plantillas
        variables_base = {
            # Información del negocio
            'nombre_negocio': negocio['nombre'],
            'tipo_negocio': negocio['tipo_negocio'],
            
            # Emojis dinámicos según tipo de negocio
            'emoji_negocio': '💅' if negocio['tipo_negocio'] == 'spa_unas' else '✂️',
            'emoji_servicio': '💅' if negocio['tipo_negocio'] == 'spa_unas' else '👨‍💼',
            'emoji_profesional': '👩‍💼' if negocio['tipo_negocio'] == 'spa_unas' else '👨‍💼',
            
            # Textos dinámicos según tipo de negocio
            'texto_profesional': 'estilista' if negocio['tipo_negocio'] == 'spa_unas' else 'profesional',
            'texto_profesional_title': 'Estilista' if negocio['tipo_negocio'] == 'spa_unas' else 'Profesional',
            'texto_profesional_plural': 'estilistas' if negocio['tipo_negocio'] == 'spa_unas' else 'profesionales',
            'texto_profesional_plural_title': 'Estilistas' if negocio['tipo_negocio'] == 'spa_unas' else 'Profesionales',
            
            # Configuración del negocio
            'saludo_personalizado': config.get('saludo_personalizado', '¡Hola! Soy tu asistente virtual para agendar citas.'),
            'horario_atencion': config.get('horario_atencion', 'Lunes a Sábado 9:00 AM - 7:00 PM'),
            'direccion': config.get('direccion', 'Calle Principal #123'),
            'telefono_contacto': config.get('telefono_contacto', '+573001234567'),
            'politica_cancelacion': config.get('politica_cancelacion', 'Puedes cancelar hasta 2 horas antes'),
            
            # Fecha y hora actual
            'fecha_actual': datetime.now().strftime('%d/%m/%Y'),
            'hora_actual': datetime.now().strftime('%H:%M')
        }
        
        # Combinar con variables adicionales
        todas_variables = {**variables_base, **(variables_extra or {})}
        
        # Renderizar plantilla (reemplazar variables)
        mensaje_final = plantilla_texto
        for key, value in todas_variables.items():
            placeholder = f"{{{key}}}"
            if placeholder in mensaje_final:
                mensaje_final = mensaje_final.replace(placeholder, str(value))
        
        # Formatear para web
        return format_message_for_web(mensaje_final)
        
    except Exception as e:
        print(f"❌ Error en renderizar_plantilla_web: {e}")
        return format_message_for_web(f"❌ Error al procesar plantilla '{nombre_plantilla}'")

# =============================================================================
# FUNCIÓN PRINCIPAL PARA PROCESAR MENSAJES DEL CHAT WEB
# =============================================================================

def procesar_mensaje_chat(user_message, session_id, negocio_id, session):
    """
    Función principal que procesa mensajes del chat web con botones
    """
    try:
        user_message = user_message.strip()
        
        print(f"🔧 [CHAT WEB] Mensaje recibido: '{user_message}'")
        
        # Verificar que el negocio existe y está activo
        negocio = db.obtener_negocio_por_id(negocio_id)
        if not negocio:
            return {
                'message': format_message_for_web('❌ Este negocio no está configurado en el sistema.'),
                'step': 'error',
                'buttons': []
            }
        
        if not negocio['activo']:
            return {
                'message': format_message_for_web('❌ Este negocio no está activo actualmente.'),
                'step': 'error',
                'buttons': []
            }
        
        # Usar session_id como identificador único
        numero = session_id
        
        # Procesar mensaje usando la lógica existente pero adaptada para web
        respuesta = procesar_mensaje_web(user_message, numero, negocio_id)
        
        return respuesta
        
    except Exception as e:
        print(f"❌ [CHAT WEB] Error procesando mensaje: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'message': format_message_for_web('❌ Ocurrió un error al procesar tu mensaje. Por favor, intenta nuevamente.'),
            'step': 'error',
            'buttons': [{'text': '🏠 Menú Principal', 'value': '0'}]
        }

# =============================================================================
# LÓGICA PRINCIPAL ADAPTADA PARA BOTONES WEB
# =============================================================================

def procesar_mensaje_web(mensaje, numero, negocio_id):
    """Procesar mensajes para web con botones"""
    mensaje = mensaje.lower().strip()
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [WEB] PROCESANDO MENSAJE: '{mensaje}' de {numero}")
    
    # Comando especial para volver al menú principal
    if mensaje == '0':
        print(f"🔧 [WEB] Comando '0' detectado - Volviendo al menú principal")
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial_web(numero, negocio_id)
    
    # Reiniciar conversación si ha pasado mucho tiempo
    reiniciar_conversacion_si_es_necesario(numero, negocio_id)
    
    # Si hay conversación activa, continuarla
    if clave_conversacion in conversaciones_activas:
        estado_actual = conversaciones_activas[clave_conversacion]['estado']
        print(f"🔧 [WEB] Conversación activa encontrada - Estado: {estado_actual}")
        return continuar_conversacion_web(numero, mensaje, negocio_id)
    
    print(f"🔧 [WEB] No hay conversación activa - Procesando comando del menú")
    
    # Procesar comandos del menú principal
    if mensaje == '1':
        print(f"🔧 [WEB] Comando '1' detectado - Mostrando profesionales")
        return mostrar_profesionales_web(numero, negocio_id)
    elif mensaje == '2':
        print(f"🔧 [WEB] Comando '2' detectado - Mostrando citas")
        return mostrar_mis_citas_web(numero, negocio_id)
    elif mensaje == '3':
        print(f"🔧 [WEB] Comando '3' detectado - Cancelando reserva")
        conversaciones_activas[clave_conversacion] = {'estado': 'cancelando', 'timestamp': datetime.now()}
        return mostrar_citas_para_cancelar_web(numero, negocio_id)
    elif mensaje == '4':
        print(f"🔧 [WEB] Comando '4' detectado - Mostrando ayuda")
        return mostrar_ayuda_web(negocio_id)
    elif mensaje in ['hola', 'hi', 'hello', 'buenas', 'inicio', 'menu']:
        print(f"🔧 [WEB] Saludo detectado - Mostrando menú inicial")
        return saludo_inicial_web(numero, negocio_id)
    else:
        # Mensaje no reconocido - mostrar menú principal
        print(f"🔧 [WEB] Mensaje no reconocido - Mostrando menú principal")
        return generar_respuesta_web(
            mensaje=renderizar_plantilla_web('menu_principal', negocio_id),
            buttons=[
                {'text': '👨‍💼 Agendar Cita', 'value': '1'},
                {'text': '📋 Ver Mis Citas', 'value': '2'},
                {'text': '❌ Cancelar Cita', 'value': '3'},
                {'text': '💡 Ayuda', 'value': '4'}
            ],
            step='menu_principal'
        )

# =============================================================================
# FUNCIONES WEB CON BOTONES
# =============================================================================

def saludo_inicial_web(numero, negocio_id):
    """Saludo inicial con botones"""
    try:
        # Verificar si es cliente existente con nombre válido
        nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id)
        
        if nombre_cliente:
            # Cliente existente - mostrar menú personalizado
            mensaje = renderizar_plantilla_web('saludo_inicial_existente', negocio_id, {
                'cliente_nombre': nombre_cliente
            })
            buttons = [
                {'text': '👨‍💼 Agendar Cita', 'value': '1'},
                {'text': '📋 Ver Mis Citas', 'value': '2'},
                {'text': '❌ Cancelar Cita', 'value': '3'},
                {'text': '💡 Ayuda', 'value': '4'}
            ]
        else:
            # Cliente nuevo - pedir nombre
            clave_conversacion = f"{numero}_{negocio_id}"
            conversaciones_activas[clave_conversacion] = {
                'estado': 'solicitando_nombre',
                'timestamp': datetime.now()
            }
            mensaje = renderizar_plantilla_web('saludo_inicial_nuevo', negocio_id)
            buttons = [
                {'text': '↩️ Cancelar', 'value': '0'}
            ]
        
        return generar_respuesta_web(
            mensaje=mensaje,
            buttons=buttons,
            step='inicio'
        )
            
    except Exception as e:
        print(f"❌ Error en saludo_inicial_web: {e}")
        # En caso de error, mostrar menú genérico
        return generar_respuesta_web(
            mensaje=renderizar_plantilla_web('menu_principal', negocio_id),
            buttons=[
                {'text': '👨‍💼 Agendar Cita', 'value': '1'},
                {'text': '📋 Ver Mis Citas', 'value': '2'},
                {'text': '❌ Cancelar Cita', 'value': '3'},
                {'text': '💡 Ayuda', 'value': '4'}
            ],
            step='menu_principal'
        )

def mostrar_profesionales_web(numero, negocio_id):
    """Mostrar lista de profesionales con botones"""
    try:
        profesionales = db.obtener_profesionales(negocio_id)
        
        # Filtrar solo profesionales activos
        profesionales_activos = []
        for prof in profesionales:
            if prof.get('activo', True):
                profesionales_activos.append(prof)
        
        profesionales = profesionales_activos
        
        if not profesionales:
            return generar_respuesta_web(
                mensaje=format_message_for_web("❌ No hay profesionales disponibles en este momento."),
                buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
                step='error'
            )
        
        # Construir mensaje
        mensaje = format_message_for_web("👨‍💼 <strong>Selecciona un profesional:</strong><br><br>")
        
        # Crear botones para cada profesional
        buttons = []
        for i, prof in enumerate(profesionales, 1):
            buttons.append({
                'text': f"{prof['nombre']} - {prof['especialidad']}",
                'value': str(i)
            })
        
        # Agregar botón para volver
        buttons.append({'text': '↩️ Volver al Menú', 'value': '0'})
        
        # Guardar en conversación activa
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion] = {
            'estado': 'seleccionando_profesional',
            'profesionales': profesionales,
            'timestamp': datetime.now()
        }
        
        return generar_respuesta_web(
            mensaje=mensaje,
            buttons=buttons,
            step='seleccionando_profesional'
        )
        
    except Exception as e:
        print(f"❌ Error en mostrar_profesionales_web: {e}")
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Error al cargar profesionales."),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='error'
        )

def mostrar_servicios_web(numero, profesional_nombre, negocio_id):
    """Mostrar servicios con botones"""
    try:
        servicios = db.obtener_servicios(negocio_id)
        
        # Filtrar servicios activos manualmente
        servicios_activos = []
        for servicio in servicios:
            if servicio.get('activo', True):
                servicios_activos.append(servicio)
        
        servicios = servicios_activos
        
        if not servicios:
            return generar_respuesta_web(
                mensaje=format_message_for_web("❌ No hay servicios disponibles en este momento."),
                buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
                step='error'
            )
        
        # Construir mensaje
        mensaje = format_message_for_web(f"📋 <strong>Servicios con {profesional_nombre}</strong><br><br>")
        
        # Crear botones para cada servicio
        buttons = []
        for i, servicio in enumerate(servicios, 1):
            precio_formateado = f"${servicio['precio']:,.0f}".replace(',', '.')
            button_text = f"{servicio['nombre']} - {precio_formateado}"
            if len(button_text) > 30:  # Limitar longitud
                button_text = servicio['nombre'][:27] + "..."
            buttons.append({
                'text': button_text,
                'value': str(i)
            })
        
        # Agregar botón para volver
        buttons.append({'text': '↩️ Volver al Menú', 'value': '0'})
        
        # Guardar en conversación activa
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion]['servicios'] = servicios
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_servicio'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
        
        return generar_respuesta_web(
            mensaje=mensaje,
            buttons=buttons,
            step='seleccionando_servicio'
        )
        
    except Exception as e:
        print(f"❌ Error en mostrar_servicios_web: {e}")
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Error al cargar servicios."),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='error'
        )

def mostrar_fechas_disponibles_web(numero, negocio_id):
    """Mostrar fechas disponibles con botones"""
    try:
        # Obtener próximas fechas donde el negocio está activo
        fechas_disponibles = obtener_proximas_fechas_disponibles(negocio_id)
        
        if not fechas_disponibles:
            return generar_respuesta_web(
                mensaje=format_message_for_web("❌ No hay fechas disponibles en los próximos días."),
                buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
                step='error'
            )
        
        # Construir mensaje
        mensaje = format_message_for_web("📅 <strong>Selecciona una fecha:</strong><br><br>")
        
        # Crear botones para cada fecha
        buttons = []
        for i, fecha_info in enumerate(fechas_disponibles, 1):
            buttons.append({
                'text': fecha_info['mostrar'],
                'value': str(i)
            })
        
        # Agregar botón para volver
        buttons.append({'text': '↩️ Volver al Menú', 'value': '0'})
        
        # Guardar en conversación activa
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion]['fechas_disponibles'] = fechas_disponibles
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
        
        return generar_respuesta_web(
            mensaje=mensaje,
            buttons=buttons,
            step='seleccionando_fecha'
        )
        
    except Exception as e:
        print(f"❌ Error en mostrar_fechas_disponibles_web: {e}")
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Error al cargar fechas."),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='error'
        )

def mostrar_disponibilidad_web(numero, negocio_id, fecha_seleccionada=None):
    """Mostrar horarios disponibles con botones"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if not fecha_seleccionada:
        fecha_seleccionada = conversaciones_activas[clave_conversacion].get('fecha_seleccionada', datetime.now().strftime('%Y-%m-%d'))
    
    # Verificar disponibilidad básica
    if not verificar_disponibilidad_basica(negocio_id, fecha_seleccionada):
        fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
        mensaje = format_message_for_web(f"❌ No hay horarios disponibles para el {fecha_formateada}.<br><br>Por favor, selecciona otra fecha.")
        
        # Volver a mostrar fechas
        return mostrar_fechas_disponibles_web(numero, negocio_id)
    
    # Obtener datos de la conversación
    profesional_id = conversaciones_activas[clave_conversacion]['profesional_id']
    servicio_id = conversaciones_activas[clave_conversacion]['servicio_id']
    pagina = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
    
    # Generar horarios disponibles
    horarios_disponibles = generar_horarios_disponibles_actualizado(negocio_id, profesional_id, fecha_seleccionada, servicio_id)
    
    if not horarios_disponibles:
        fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
        return generar_respuesta_web(
            mensaje=format_message_for_web(f"❌ No hay horarios disponibles para el {fecha_formateada}."),
            buttons=[{'text': '📅 Cambiar Fecha', 'value': '7'}, {'text': '🏠 Menú Principal', 'value': '0'}],
            step='agendando_hora'
        )
    
    # Datos para el mensaje
    profesional_nombre = conversaciones_activas[clave_conversacion]['profesional_nombre']
    servicio_nombre = conversaciones_activas[clave_conversacion]['servicio_nombre']
    servicio_precio = conversaciones_activas[clave_conversacion]['servicio_precio']
    precio_formateado = f"${servicio_precio:,.0f}".replace(',', '.')
    fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
    
    # Paginación
    horarios_por_pagina = 6
    inicio = pagina * horarios_por_pagina
    fin = inicio + horarios_por_pagina
    horarios_pagina = horarios_disponibles[inicio:fin]
    
    # Construir mensaje
    mensaje = format_message_for_web(
        f"📅 <strong>Horarios disponibles con {profesional_nombre} ({fecha_formateada}):</strong><br>"
        f"💼 Servicio: {servicio_nombre} - {precio_formateado}<br><br>"
    )
    
    # Crear botones para horarios
    buttons = []
    for i, hora in enumerate(horarios_pagina, 1):
        buttons.append({
            'text': hora,
            'value': str(i)
        })
    
    # Agregar botones de navegación
    total_paginas = (len(horarios_disponibles) + horarios_por_pagina - 1) // horarios_por_pagina
    pagina_actual = pagina + 1
    
    navegacion_buttons = []
    if pagina > 0:
        navegacion_buttons.append({'text': '⬅️ Anterior', 'value': '8'})
    if pagina_actual < total_paginas:
        navegacion_buttons.append({'text': '➡️ Siguiente', 'value': '9'})
    
    navegacion_buttons.append({'text': '📅 Cambiar Fecha', 'value': '7'})
    navegacion_buttons.append({'text': '🏠 Menú Principal', 'value': '0'})
    
    # Guardar datos para paginación
    conversaciones_activas[clave_conversacion]['todos_horarios'] = horarios_disponibles
    conversaciones_activas[clave_conversacion]['fecha_seleccionada'] = fecha_seleccionada
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    return generar_respuesta_web(
        mensaje=mensaje,
        buttons=buttons,
        extra_buttons=navegacion_buttons,
        step='agendando_hora',
        metadata={'pagina_actual': pagina_actual, 'total_paginas': total_paginas}
    )

def mostrar_mis_citas_web(numero, negocio_id):
    """Mostrar citas del cliente con botones"""
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
        
        if not citas:
            mensaje = renderizar_plantilla_web('sin_citas', negocio_id)
            buttons = [
                {'text': '👨‍💼 Agendar Cita', 'value': '1'},
                {'text': '🏠 Menú Principal', 'value': '0'}
            ]
        else:
            nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id) or 'Cliente'
            mensaje = format_message_for_web(f"📋 <strong>Tus citas programadas - {nombre_cliente}:</strong><br><br>")
            
            for cita in citas:
                id_cita, fecha, hora, servicio, estado, profesional_nombre = cita
                fecha_str = datetime.strptime(str(fecha), '%Y-%m-%d').strftime('%d/%m')
                emoji = "✅" if estado == 'confirmado' else "❌"
                mensaje += format_message_for_web(f"{emoji} <strong>{fecha_str}</strong> - {hora}<br>")
                mensaje += format_message_for_web(f"   👨‍💼 {profesional_nombre} - {servicio}<br>")
                mensaje += format_message_for_web(f"   🎫 ID: #{id_cita}<br><br>")
            
            buttons = [
                {'text': '❌ Cancelar Cita', 'value': '3'},
                {'text': '👨‍💼 Nueva Cita', 'value': '1'},
                {'text': '🏠 Menú Principal', 'value': '0'}
            ]
        
        return generar_respuesta_web(
            mensaje=mensaje,
            buttons=buttons,
            step='mostrando_citas'
        )
        
    except Exception as e:
        print(f"❌ Error mostrando citas web: {e}")
        return generar_respuesta_web(
            mensaje=renderizar_plantilla_web('error_generico', negocio_id),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='error'
        )

def mostrar_citas_para_cancelar_web(numero, negocio_id):
    """Mostrar citas para cancelar con botones"""
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
        
        if not citas:
            clave_conversacion = f"{numero}_{negocio_id}"
            if clave_conversacion in conversaciones_activas:
                del conversaciones_activas[clave_conversacion]
            return generar_respuesta_web(
                mensaje=format_message_for_web("❌ No tienes citas para cancelar."),
                buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
                step='menu_principal'
            )
        
        if len(citas) == 1:
            # Solo una cita, mostrar opción de cancelar directamente
            cita_id = citas[0][0]
            return mostrar_confirmacion_cancelacion_web(numero, str(cita_id), negocio_id)
        
        # Construir mensaje con múltiples citas
        nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id) or 'Cliente'
        mensaje = format_message_for_web(f"❌ <strong>Citas para cancelar - {nombre_cliente}:</strong><br><br>")
        
        # Crear botones para cada cita
        buttons = []
        for cita in citas:
            id_cita, fecha, hora, profesional_nombre, servicio_nombre = cita
            fecha_str = datetime.strptime(str(fecha), '%Y-%m-%d').strftime('%d/%m')
            button_text = f"{fecha_str} {hora} - {servicio_nombre}"
            if len(button_text) > 30:
                button_text = button_text[:27] + "..."
            buttons.append({
                'text': button_text,
                'value': str(id_cita)
            })
        
        # Agregar botón para volver
        buttons.append({'text': '↩️ Volver al Menú', 'value': '0'})
        
        # Guardar citas disponibles para cancelación
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion]['citas_disponibles'] = {str(t[0]): t for t in citas}
        
        return generar_respuesta_web(
            mensaje=mensaje,
            buttons=buttons,
            step='cancelando'
        )
        
    except Exception as e:
        print(f"❌ Error mostrando citas para cancelar web: {e}")
        clave_conversacion = f"{numero}_{negocio_id}"
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return generar_respuesta_web(
            mensaje=renderizar_plantilla_web('error_generico', negocio_id),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='error'
        )

def mostrar_confirmacion_cancelacion_web(numero, cita_id, negocio_id):
    """Mostrar confirmación de cancelación con botones"""
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.fecha, c.hora, p.nombre as profesional_nombre, s.nombre as servicio_nombre
            FROM citas c
            JOIN profesionales p ON c.profesional_id = p.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.id = %s AND c.negocio_id = %s
        ''', (cita_id, negocio_id))
        
        cita_info = cursor.fetchone()
        conn.close()
        
        if not cita_info:
            return generar_respuesta_web(
                mensaje=format_message_for_web("❌ Cita no encontrada."),
                buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
                step='error'
            )
        
        fecha, hora, profesional_nombre, servicio_nombre = cita_info
        fecha_str = datetime.strptime(str(fecha), '%Y-%m-%d').strftime('%d/%m/%Y')
        
        mensaje = format_message_for_web(
            f"❌ <strong>¿Confirmas cancelar esta cita?</strong><br><br>"
            f"📅 <strong>Fecha:</strong> {fecha_str}<br>"
            f"⏰ <strong>Hora:</strong> {hora}<br>"
            f"👨‍💼 <strong>Profesional:</strong> {profesional_nombre}<br>"
            f"💼 <strong>Servicio:</strong> {servicio_nombre}<br>"
            f"🎫 <strong>ID:</strong> #{cita_id}"
        )
        
        buttons = [
            {'text': '✅ Sí, cancelar', 'value': f'confirmar_cancelar_{cita_id}'},
            {'text': '❌ No, conservar', 'value': '0'}
        ]
        
        return generar_respuesta_web(
            mensaje=mensaje,
            buttons=buttons,
            step='confirmando_cancelacion'
        )
        
    except Exception as e:
        print(f"❌ Error en mostrar_confirmacion_cancelacion_web: {e}")
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Error al cargar información de la cita."),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='error'
        )

def mostrar_ayuda_web(negocio_id):
    """Mostrar mensaje de ayuda con botones"""
    mensaje = renderizar_plantilla_web('ayuda_general', negocio_id)
    
    buttons = [
        {'text': '👨‍💼 Agendar Cita', 'value': '1'},
        {'text': '📋 Ver Mis Citas', 'value': '2'},
        {'text': '🏠 Menú Principal', 'value': '0'}
    ]
    
    return generar_respuesta_web(
        mensaje=mensaje,
        buttons=buttons,
        step='ayuda'
    )

def mostrar_confirmacion_cita_web(numero, negocio_id):
    """Mostrar confirmación de cita con botones"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if clave_conversacion not in conversaciones_activas:
        return saludo_inicial_web(numero, negocio_id)
    
    conversacion = conversaciones_activas[clave_conversacion]
    
    # Obtener nombre del cliente
    nombre_cliente = conversacion.get('cliente_nombre')
    if not nombre_cliente:
        nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id)
    if not nombre_cliente or len(str(nombre_cliente).strip()) < 2:
        nombre_cliente = 'Cliente'
    
    profesional_nombre = conversacion['profesional_nombre']
    servicio_nombre = conversacion['servicio_nombre']
    servicio_precio = conversacion['servicio_precio']
    precio_formateado = f"${servicio_precio:,.0f}".replace(',', '.')
    fecha_seleccionada = conversacion['fecha_seleccionada']
    fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
    hora = conversacion['hora_seleccionada']
    
    mensaje = format_message_for_web(
        f"✅ <strong>Confirmar cita</strong><br><br>"
        f"Hola <strong>{nombre_cliente}</strong>, ¿confirmas tu cita?<br><br>"
        f"👨‍💼 <strong>Profesional:</strong> {profesional_nombre}<br>"
        f"💼 <strong>Servicio:</strong> {servicio_nombre}<br>"
        f"💰 <strong>Precio:</strong> {precio_formateado}<br>"
        f"📅 <strong>Fecha:</strong> {fecha_formateada}<br>"
        f"⏰ <strong>Hora:</strong> {hora}"
    )
    
    buttons = [
        {'text': '✅ Confirmar Cita', 'value': '1'},
        {'text': '❌ Cancelar', 'value': '2'},
        {'text': '🏠 Menú Principal', 'value': '0'}
    ]
    
    return generar_respuesta_web(
        mensaje=mensaje,
        buttons=buttons,
        step='confirmando_cita'
    )

# =============================================================================
# FUNCIONES AUXILIARES WEB
# =============================================================================

def continuar_conversacion_web(numero, mensaje, negocio_id):
    """Continuar conversación web basada en el estado actual"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if clave_conversacion not in conversaciones_activas:
        return saludo_inicial_web(numero, negocio_id)
    
    estado = conversaciones_activas[clave_conversacion]['estado']
    
    print(f"🔧 [WEB] CONTINUANDO CONVERSACIÓN - Estado: {estado}, Mensaje: '{mensaje}'")
    
    try:
        # Manejar confirmación de cancelación especial
        if mensaje.startswith('confirmar_cancelar_'):
            cita_id = mensaje.replace('confirmar_cancelar_', '')
            return procesar_cancelacion_directa_web(numero, cita_id, negocio_id)
        
        if estado == 'solicitando_nombre':
            return procesar_nombre_cliente_web(numero, mensaje, negocio_id)
        elif estado == 'seleccionando_profesional':
            return procesar_seleccion_profesional_web(numero, mensaje, negocio_id)
        elif estado == 'seleccionando_servicio':
            return procesar_seleccion_servicio_web(numero, mensaje, negocio_id)
        elif estado == 'seleccionando_fecha':
            return procesar_seleccion_fecha_web(numero, mensaje, negocio_id)
        elif estado == 'agendando_hora':
            return procesar_seleccion_hora_web(numero, mensaje, negocio_id)
        elif estado == 'confirmando_cita':
            return procesar_confirmacion_cita_web(numero, mensaje, negocio_id)
        elif estado == 'cancelando':
            return procesar_cancelacion_cita_web(numero, mensaje, negocio_id)
        else:
            # Estado no reconocido - reiniciar
            if clave_conversacion in conversaciones_activas:
                del conversaciones_activas[clave_conversacion]
            return saludo_inicial_web(numero, negocio_id)
        
    except Exception as e:
        print(f"❌ Error en continuar_conversacion_web: {e}")
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return generar_respuesta_web(
            mensaje=renderizar_plantilla_web('error_generico', negocio_id),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='error'
        )

def procesar_nombre_cliente_web(numero, mensaje, negocio_id):
    """Procesar nombre del cliente nuevo para web"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial_web(numero, negocio_id)
    
    nombre = mensaje.strip()
    if len(nombre) < 2:
        return generar_respuesta_web(
            mensaje=format_message_for_web("Por favor, ingresa un nombre válido:"),
            buttons=[{'text': '↩️ Cancelar', 'value': '0'}],
            step='solicitando_nombre'
        )
    
    print(f"🔧 [WEB] Procesando nombre '{nombre}' para {numero}")
    
    try:
        # Guardar el cliente
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar si ya existe
        cursor.execute('''
            SELECT id FROM clientes WHERE telefono = %s AND negocio_id = %s
        ''', (numero, negocio_id))
        
        cliente_existente = cursor.fetchone()
        
        if cliente_existente:
            # Actualizar nombre si ya existe
            cursor.execute('''
                UPDATE clientes 
                SET nombre = %s, updated_at = NOW()
                WHERE telefono = %s AND negocio_id = %s
            ''', (nombre, numero, negocio_id))
        else:
            # Insertar nuevo cliente
            cursor.execute('''
                INSERT INTO clientes (negocio_id, telefono, nombre, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
            ''', (negocio_id, numero, nombre))
        
        conn.commit()
        conn.close()
        
        print(f"✅ [WEB] Cliente guardado: {nombre}")
        
    except Exception as e:
        print(f"⚠️ [WEB] Error guardando cliente: {e}")
        # No es crítico, continuamos
    
    # Limpiar conversación activa
    if clave_conversacion in conversaciones_activas:
        del conversaciones_activas[clave_conversacion]
    
    # Mostrar menú principal personalizado
    return saludo_inicial_web(numero, negocio_id)

def procesar_seleccion_profesional_web(numero, mensaje, negocio_id):
    """Procesar selección de profesional para web"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial_web(numero, negocio_id)
    
    if 'profesionales' not in conversaciones_activas[clave_conversacion]:
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Sesión expirada."),
            buttons=[{'text': '👨‍💼 Agendar Cita', 'value': '1'}, {'text': '🏠 Menú Principal', 'value': '0'}],
            step='menu_principal'
        )
    
    profesionales = conversaciones_activas[clave_conversacion]['profesionales']
    
    if not mensaje.isdigit() or int(mensaje) < 1 or int(mensaje) > len(profesionales):
        return generar_respuesta_web(
            mensaje=format_message_for_web(f"❌ Selección inválida. Por favor, selecciona un profesional:"),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='seleccionando_profesional'
        )
    
    # Guardar profesional seleccionado
    profesional_index = int(mensaje) - 1
    profesional_seleccionado = profesionales[profesional_index]
    
    conversaciones_activas[clave_conversacion]['profesional_id'] = profesional_seleccionado['id']
    conversaciones_activas[clave_conversacion]['profesional_nombre'] = profesional_seleccionado['nombre']
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    return mostrar_servicios_web(numero, profesional_seleccionado['nombre'], negocio_id)

def procesar_seleccion_servicio_web(numero, mensaje, negocio_id):
    """Procesar selección de servicio para web"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial_web(numero, negocio_id)
    
    if 'servicios' not in conversaciones_activas[clave_conversacion]:
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Sesión expirada."),
            buttons=[{'text': '👨‍💼 Agendar Cita', 'value': '1'}, {'text': '🏠 Menú Principal', 'value': '0'}],
            step='menu_principal'
        )
    
    servicios = conversaciones_activas[clave_conversacion]['servicios']
    
    if not mensaje.isdigit() or int(mensaje) < 1 or int(mensaje) > len(servicios):
        return generar_respuesta_web(
            mensaje=format_message_for_web(f"❌ Selección inválida. Por favor, selecciona un servicio:"),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='seleccionando_servicio'
        )
    
    # Guardar servicio seleccionado
    servicio_index = int(mensaje) - 1
    servicio_seleccionado = servicios[servicio_index]
    
    conversaciones_activas[clave_conversacion]['servicio_id'] = servicio_seleccionado['id']
    conversaciones_activas[clave_conversacion]['servicio_nombre'] = servicio_seleccionado['nombre']
    conversaciones_activas[clave_conversacion]['servicio_precio'] = servicio_seleccionado['precio']
    conversaciones_activas[clave_conversacion]['servicio_duracion'] = servicio_seleccionado['duracion']
    conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    return mostrar_fechas_disponibles_web(numero, negocio_id)

def procesar_seleccion_fecha_web(numero, mensaje, negocio_id):
    """Procesar selección de fecha para web"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial_web(numero, negocio_id)
    
    if 'fechas_disponibles' not in conversaciones_activas[clave_conversacion]:
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Sesión expirada."),
            buttons=[{'text': '👨‍💼 Agendar Cita', 'value': '1'}, {'text': '🏠 Menú Principal', 'value': '0'}],
            step='menu_principal'
        )
    
    fechas_disponibles = conversaciones_activas[clave_conversacion]['fechas_disponibles']
    
    if not mensaje.isdigit() or int(mensaje) < 1 or int(mensaje) > len(fechas_disponibles):
        return generar_respuesta_web(
            mensaje=format_message_for_web(f"❌ Selección inválida. Por favor, selecciona una fecha:"),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='seleccionando_fecha'
        )
    
    # Guardar fecha seleccionada
    fecha_index = int(mensaje) - 1
    fecha_seleccionada = fechas_disponibles[fecha_index]['fecha']
    
    conversaciones_activas[clave_conversacion]['fecha_seleccionada'] = fecha_seleccionada
    conversaciones_activas[clave_conversacion]['estado'] = 'agendando_hora'
    conversaciones_activas[clave_conversacion]['pagina_horarios'] = 0
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    return mostrar_disponibilidad_web(numero, negocio_id, fecha_seleccionada)

def procesar_seleccion_hora_web(numero, mensaje, negocio_id):
    """Procesar selección de horario para web"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial_web(numero, negocio_id)
    
    # Navegación de horarios y cambio de fecha
    if mensaje == '7':  # Cambiar fecha
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
        return mostrar_fechas_disponibles_web(numero, negocio_id)
        
    elif mensaje == '8':  # Página anterior
        pagina_actual = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
        if pagina_actual > 0:
            conversaciones_activas[clave_conversacion]['pagina_horarios'] = pagina_actual - 1
        return mostrar_disponibilidad_web(numero, negocio_id)
        
    elif mensaje == '9':  # Página siguiente
        pagina_actual = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
        horarios_disponibles = conversaciones_activas[clave_conversacion]['todos_horarios']
        horarios_por_pagina = 6
        
        max_pagina = (len(horarios_disponibles) - 1) // horarios_por_pagina
        if pagina_actual < max_pagina:
            conversaciones_activas[clave_conversacion]['pagina_horarios'] = pagina_actual + 1
        else:
            # Ya estamos en la última página
            return generar_respuesta_web(
                mensaje=format_message_for_web("ℹ️ Ya estás en la última página de horarios."),
                buttons=[{'text': '⬅️ Anterior', 'value': '8'}, {'text': '📅 Cambiar Fecha', 'value': '7'}, {'text': '🏠 Menú Principal', 'value': '0'}],
                step='agendando_hora'
            )
        
        return mostrar_disponibilidad_web(numero, negocio_id)
    
    # Obtener horarios de la página actual
    pagina_actual = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
    horarios_disponibles = conversaciones_activas[clave_conversacion]['todos_horarios']
    horarios_por_pagina = 6
    inicio = pagina_actual * horarios_por_pagina
    fin = inicio + horarios_por_pagina
    horarios_pagina = horarios_disponibles[inicio:fin]
    
    # Verificar que el mensaje es un número válido para horarios
    if not mensaje.isdigit():
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Por favor, selecciona un horario válido."),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='agendando_hora'
        )
    
    mensaje_num = int(mensaje)
    
    # Solo procesar números 1-6 como horarios
    if mensaje_num < 1 or mensaje_num > len(horarios_pagina):
        return generar_respuesta_web(
            mensaje=format_message_for_web(f"❌ Selección inválida. Por favor, selecciona un horario entre 1 y {len(horarios_pagina)}:"),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='agendando_hora'
        )
    
    # Guardar horario seleccionado
    hora_index = mensaje_num - 1
    hora_seleccionada = horarios_pagina[hora_index]
    
    conversaciones_activas[clave_conversacion]['hora_seleccionada'] = hora_seleccionada
    conversaciones_activas[clave_conversacion]['estado'] = 'confirmando_cita'
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    # Mostrar confirmación
    return mostrar_confirmacion_cita_web(numero, negocio_id)

def procesar_confirmacion_cita_web(numero, mensaje, negocio_id):
    """Procesar confirmación de la cita para web"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial_web(numero, negocio_id)
    
    if mensaje == '2':  # Cancelar agendamiento
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Agendamiento cancelado."),
            buttons=[{'text': '👨‍💼 Nueva Cita', 'value': '1'}, {'text': '🏠 Menú Principal', 'value': '0'}],
            step='menu_principal'
        )
    
    if mensaje == '1':  # Confirmar cita
        try:
            conversacion = conversaciones_activas[clave_conversacion]
            
            if 'hora_seleccionada' not in conversacion:
                del conversaciones_activas[clave_conversacion]
                return generar_respuesta_web(
                    mensaje=format_message_for_web("❌ Error: No se seleccionó hora."),
                    buttons=[{'text': '👨‍💼 Nueva Cita', 'value': '1'}, {'text': '🏠 Menú Principal', 'value': '0'}],
                    step='menu_principal'
                )
            
            # Obtener datos
            hora = conversacion['hora_seleccionada']
            fecha = conversacion['fecha_seleccionada']
            profesional_id = conversacion['profesional_id']
            servicio_id = conversacion['servicio_id']
            profesional_nombre = conversacion['profesional_nombre']
            servicio_nombre = conversacion['servicio_nombre']
            servicio_precio = conversacion['servicio_precio']
            
            # Obtener nombre del cliente
            nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id)
            if not nombre_cliente or len(str(nombre_cliente).strip()) < 2:
                nombre_cliente = 'Cliente'
            else:
                nombre_cliente = str(nombre_cliente).strip()
            
            print(f"✅ [WEB] Agendando cita para: {nombre_cliente}")
            
            # Agendar cita
            cita_id = db.agendar_cita(
                negocio_id=negocio_id,
                profesional_id=profesional_id,
                cliente_telefono=numero,
                fecha=fecha,
                hora=hora,
                servicio_id=servicio_id,
                cliente_nombre=nombre_cliente
            )
            
            if cita_id:
                del conversaciones_activas[clave_conversacion]
                
                precio_formateado = f"${servicio_precio:,.0f}".replace(',', '.')
                fecha_formateada = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m/%Y')
                
                mensaje_exito = format_message_for_web(
                    f"✅ <strong>Cita confirmada</strong><br><br>"
                    f"Hola <strong>{nombre_cliente}</strong>, tu cita ha sido agendada:<br><br>"
                    f"👨‍💼 <strong>Profesional:</strong> {profesional_nombre}<br>"
                    f"💼 <strong>Servicio:</strong> {servicio_nombre}<br>"
                    f"💰 <strong>Precio:</strong> {precio_formateado}<br>"
                    f"📅 <strong>Fecha:</strong> {fecha_formateada}<br>"
                    f"⏰ <strong>Hora:</strong> {hora}<br>"
                    f"🎫 <strong>ID:</strong> #{cita_id}<br><br>"
                    f"¡Te esperamos!"
                )
                
                return generar_respuesta_web(
                    mensaje=mensaje_exito,
                    buttons=[
                        {'text': '📋 Ver Mis Citas', 'value': '2'},
                        {'text': '👨‍💼 Nueva Cita', 'value': '1'},
                        {'text': '🏠 Menú Principal', 'value': '0'}
                    ],
                    step='cita_confirmada'
                )
            else:
                del conversaciones_activas[clave_conversacion]
                return generar_respuesta_web(
                    mensaje=format_message_for_web("❌ Error al crear la cita."),
                    buttons=[{'text': '👨‍💼 Intentar de nuevo', 'value': '1'}, {'text': '🏠 Menú Principal', 'value': '0'}],
                    step='error'
                )
                
        except Exception as e:
            print(f"❌ Error confirmando cita web: {e}")
            if clave_conversacion in conversaciones_activas:
                del conversaciones_activas[clave_conversacion]
            return generar_respuesta_web(
                mensaje=format_message_for_web("❌ Error al confirmar la cita."),
                buttons=[{'text': '👨‍💼 Intentar de nuevo', 'value': '1'}, {'text': '🏠 Menú Principal', 'value': '0'}],
                step='error'
            )
    
    # Opción no válida
    return generar_respuesta_web(
        mensaje=format_message_for_web("❌ Opción no válida."),
        buttons=[
            {'text': '✅ Confirmar Cita', 'value': '1'},
            {'text': '❌ Cancelar', 'value': '2'},
            {'text': '🏠 Menú Principal', 'value': '0'}
        ],
        step='confirmando_cita'
    )

def procesar_cancelacion_cita_web(numero, mensaje, negocio_id):
    """Procesar cancelación de cita para web"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial_web(numero, negocio_id)
    
    if 'citas_disponibles' not in conversaciones_activas[clave_conversacion]:
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Sesión de cancelación expirada."),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='menu_principal'
        )
    
    citas_disponibles = conversaciones_activas[clave_conversacion]['citas_disponibles']
    
    if mensaje not in citas_disponibles:
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ ID de cita inválido."),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='cancelando'
        )
    
    # Mostrar confirmación de cancelación
    return mostrar_confirmacion_cancelacion_web(numero, mensaje, negocio_id)

def procesar_cancelacion_directa_web(numero, cita_id, negocio_id):
    """Procesar cancelación directa para web"""
    if cita_id == '0':
        clave_conversacion = f"{numero}_{negocio_id}"
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial_web(numero, negocio_id)
    
    # Cancelar cita directamente
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Primero obtener información de la cita para el mensaje
        cursor.execute('''
            SELECT c.fecha, c.hora, p.nombre as profesional_nombre, s.nombre as servicio_nombre
            FROM citas c
            JOIN profesionales p ON c.profesional_id = p.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.id = %s AND c.negocio_id = %s
        ''', (cita_id, negocio_id))
        
        cita_info = cursor.fetchone()
        
        if cita_info:
            # Actualizar estado en base de datos
            cursor.execute('UPDATE citas SET estado = %s WHERE id = %s AND negocio_id = %s', 
                          ('cancelado', cita_id, negocio_id))
            
            conn.commit()
            
            fecha, hora, profesional_nombre, servicio_nombre = cita_info
            fecha_str = datetime.strptime(str(fecha), '%Y-%m-%d').strftime('%d/%m/%Y')
            nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id) or 'Cliente'
            
            mensaje = format_message_for_web(
                f"❌ <strong>Cita cancelada</strong><br><br>"
                f"Hola {nombre_cliente}, has cancelado tu cita:<br><br>"
                f"📅 <strong>Fecha:</strong> {fecha_str}<br>"
                f"⏰ <strong>Hora:</strong> {hora}<br>"
                f"👨‍💼 <strong>Profesional:</strong> {profesional_nombre}<br>"
                f"💼 <strong>Servicio:</strong> {servicio_nombre}<br>"
                f"🎫 <strong>ID:</strong> #{cita_id}<br><br>"
                f"Esperamos verte pronto en otra ocasión."
            )
        else:
            mensaje = format_message_for_web("❌ Cita no encontrada.")
        
        conn.close()
        
        # Limpiar conversación
        clave_conversacion = f"{numero}_{negocio_id}"
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        
        return generar_respuesta_web(
            mensaje=mensaje,
            buttons=[
                {'text': '👨‍💼 Nueva Cita', 'value': '1'},
                {'text': '📋 Ver Mis Citas', 'value': '2'},
                {'text': '🏠 Menú Principal', 'value': '0'}
            ],
            step='cita_cancelada'
        )
        
    except Exception as e:
        print(f"❌ Error cancelando cita web: {e}")
        return generar_respuesta_web(
            mensaje=format_message_for_web("❌ Error al cancelar la cita."),
            buttons=[{'text': '🏠 Menú Principal', 'value': '0'}],
            step='error'
        )

# =============================================================================
# FUNCIÓN PARA GENERAR RESPUESTAS ESTANDARIZADAS
# =============================================================================

def generar_respuesta_web(mensaje, buttons=None, extra_buttons=None, step='unknown', metadata=None):
    """Generar respuesta estandarizada para el chat web"""
    response = {
        'message': mensaje,
        'step': step,
        'buttons': buttons or []
    }
    
    if extra_buttons:
        if 'buttons' not in response:
            response['buttons'] = []
        response['buttons'].extend(extra_buttons)
    
    if metadata:
        response['metadata'] = metadata
    
    return response

# =============================================================================
# FUNCIONES DE DISPONIBILIDAD Y FECHAS (REUTILIZADAS DEL ARCHIVO ORIGINAL)
# =============================================================================

def obtener_proximas_fechas_disponibles(negocio_id, dias_a_mostrar=7):
    """Obtener las próximas fechas donde el negocio está activo"""
    fechas_disponibles = []
    fecha_actual = datetime.now()
    
    print(f"🔧 [WEB] OBTENER_FECHAS_DISPONIBLES - Negocio: {negocio_id}")
    
    for i in range(dias_a_mostrar):
        fecha = fecha_actual + timedelta(days=i)
        fecha_str = fecha.strftime('%Y-%m-%d')
        
        # Verificar si el día está activo
        horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha_str)
        
        print(f"🔧 [WEB] Fecha {fecha_str}: activo={horarios_dia.get('activo')}")
        
        # Solo agregar si el día está activo
        if horarios_dia and horarios_dia['activo']:
            # Para HOY, verificar horarios futuros con margen
            if i == 0:  # Es hoy
                # Verificar si hay horarios disponibles para hoy con margen mínimo
                if verificar_disponibilidad_basica(negocio_id, fecha_str):
                    fechas_disponibles.append({
                        'fecha': fecha_str,
                        'mostrar': "Hoy"
                    })
                    print(f"🔧 [WEB] ✅ Hoy agregado - Hay horarios disponibles con margen")
                else:
                    print(f"🔧 [WEB] ❌ Hoy NO agregado - No hay horarios disponibles con margen mínimo")
            else:
                # Para días futuros, solo verificar que el día esté activo
                fecha_formateada = fecha.strftime('%A %d/%m').title()
                # Traducir días
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
                print(f"🔧 [WEB] ✅ Fecha {fecha_str} agregada como disponible")
        else:
            print(f"🔧 [WEB] ❌ Fecha {fecha_str} NO disponible (activo=False o no configurado)")
    
    print(f"🔧 [WEB] Total fechas disponibles: {len(fechas_disponibles)}")
    return fechas_disponibles

def generar_horarios_disponibles_actualizado(negocio_id, profesional_id, fecha, servicio_id):
    """Generar horarios disponibles considerando la configuración por días"""
    print(f"🔍 [WEB] Generando horarios para negocio {negocio_id}, profesional {profesional_id}, fecha {fecha}")
    
    # VERIFICAR SI EL DÍA ESTÁ ACTIVO
    horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha)
    
    if not horarios_dia or not horarios_dia['activo']:
        print(f"❌ [WEB] Día no activo para la fecha {fecha}")
        return []  # Día no activo, no hay horarios disponibles
    
    print(f"✅ [WEB] Día activo. Horario: {horarios_dia['hora_inicio']} - {horarios_dia['hora_fin']}")
    
    # Si es hoy, considerar margen mínimo de anticipación
    fecha_actual = datetime.now()
    fecha_cita = datetime.strptime(fecha, '%Y-%m-%d')
    es_hoy = fecha_cita.date() == fecha_actual.date()
    
    # Obtener citas ya agendadas
    citas_ocupadas = db.obtener_citas_dia(negocio_id, profesional_id, fecha)
    print(f"📅 [WEB] Citas ocupadas: {len(citas_ocupadas)}")
    
    # Obtener duración del servicio
    duracion_servicio = db.obtener_duracion_servicio(negocio_id, servicio_id)
    if not duracion_servicio:
        print(f"❌ [WEB] No se pudo obtener duración del servicio {servicio_id}")
        return []
    
    print(f"⏱️ [WEB] Duración servicio: {duracion_servicio} minutos")
    
    # Generar horarios disponibles
    horarios = []
    hora_actual = datetime.strptime(horarios_dia['hora_inicio'], '%H:%M')
    hora_fin = datetime.strptime(horarios_dia['hora_fin'], '%H:%M')
    
    while hora_actual < hora_fin:
        hora_str = hora_actual.strftime('%H:%M')
        
        # Si es hoy, aplicar margen mínimo de 1 hora
        if es_hoy:
            # Combinar fecha actual con hora del horario
            hora_actual_completa = datetime.combine(fecha_actual.date(), hora_actual.time())
            
            # Calcular tiempo hasta el horario
            tiempo_hasta_horario = hora_actual_completa - fecha_actual
            
            # MARGEN MÍNIMO: 60 minutos (1 hora) de anticipación
            margen_minimo_minutos = 60
            
            # Si el horario es muy pronto (menos de 1 hora), omitirlo
            if tiempo_hasta_horario.total_seconds() < (margen_minimo_minutos * 60):
                print(f"⏰ [WEB] Horario {hora_str} omitido (faltan {int(tiempo_hasta_horario.total_seconds()/60)} minutos, mínimo {margen_minimo_minutos} minutos requeridos)")
                hora_actual += timedelta(minutes=30)
                continue
        
        # Verificar si no es horario de almuerzo
        if not es_horario_almuerzo(hora_actual, horarios_dia):
            # Verificar disponibilidad
            if esta_disponible(hora_actual, duracion_servicio, citas_ocupadas, horarios_dia):
                horarios.append(hora_str)
                print(f"✅ [WEB] Horario disponible: {hora_str}")
        
        hora_actual += timedelta(minutes=30)
    
    print(f"🎯 [WEB] Total horarios disponibles: {len(horarios)}")
    return horarios

def verificar_disponibilidad_basica(negocio_id, fecha):
    """Verificación rápida de disponibilidad para una fecha (sin profesional específico)"""
    try:
        # Verificar si el día está activo
        horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha)
        if not horarios_dia or not horarios_dia['activo']:
            return False
        
        # Si es hoy, verificar que queden horarios futuros con margen mínimo
        fecha_actual = datetime.now()
        fecha_cita = datetime.strptime(fecha, '%Y-%m-%d')
        
        if fecha_cita.date() == fecha_actual.date():
            # Para hoy, verificar si hay al menos un horario futuro con margen de 1 hora
            hora_actual = datetime.strptime(horarios_dia['hora_inicio'], '%H:%M')
            hora_fin = datetime.strptime(horarios_dia['hora_fin'], '%H:%M')
            
            while hora_actual < hora_fin:
                hora_actual_completa = datetime.combine(fecha_actual.date(), hora_actual.time())
                
                # MARGEN MÍNIMO: 60 minutos (1 hora)
                if hora_actual_completa >= (fecha_actual + timedelta(minutes=60)):
                    return True  # Hay al menos un horario futuro con margen suficiente
                
                hora_actual += timedelta(minutes=30)
            return False  # No hay horarios futuros con margen suficiente para hoy
        
        return True  # Para días futuros, solo con que el día esté activo es suficiente
        
    except Exception as e:
        print(f"❌ [WEB] Error en verificación básica: {e}")
        return False

def es_horario_almuerzo(hora, config_dia):
    """Verificar si es horario de almuerzo"""
    if not config_dia.get('almuerzo_inicio') or not config_dia.get('almuerzo_fin'):
        return False  # No hay almuerzo configurado para este día
    
    try:
        almuerzo_ini = datetime.strptime(config_dia['almuerzo_inicio'], '%H:%M')
        almuerzo_fin = datetime.strptime(config_dia['almuerzo_fin'], '%H:%M')
        hora_time = hora.time()
        
        return almuerzo_ini.time() <= hora_time < almuerzo_fin.time()
    except Exception as e:
        print(f"❌ [WEB] Error verificando horario almuerzo: {e}")
        return False

def esta_disponible(hora_inicio, duracion_servicio, citas_ocupadas, config_dia):
    """Verificar si un horario está disponible"""
    hora_fin_servicio = hora_inicio + timedelta(minutes=duracion_servicio)
    
    # Verificar que no se pase del horario de cierre del día
    try:
        hora_fin_jornada = datetime.strptime(config_dia['hora_fin'], '%H:%M')
        if hora_fin_servicio.time() > hora_fin_jornada.time():
            return False
    except Exception as e:
        print(f"❌ [WEB] Error verificando horario cierre: {e}")
        return False
    
    # Verificar que no interfiera con horario de almuerzo
    if se_solapa_con_almuerzo(hora_inicio, hora_fin_servicio, config_dia):
        return False
    
    # Verificar que no se solape con otras citas
    for cita_ocupada in citas_ocupadas:
        try:
            hora_cita = datetime.strptime(cita_ocupada[0], '%H:%M')
            duracion_cita = cita_ocupada[1]
            hora_fin_cita = hora_cita + timedelta(minutes=duracion_cita)
            
            if se_solapan(hora_inicio, hora_fin_servicio, hora_cita, hora_fin_cita):
                return False
        except Exception as e:
            print(f"❌ [WEB] Error verificando cita ocupada: {e}")
            continue
    
    return True

def se_solapa_con_almuerzo(hora_inicio, hora_fin, config_dia):
    """Verificar si un horario se solapa con el almuerzo del día"""
    if not config_dia.get('almuerzo_inicio') or not config_dia.get('almuerzo_fin'):
        return False  # No hay almuerzo configurado
    
    try:
        almuerzo_ini = datetime.strptime(config_dia['almuerzo_inicio'], '%H:%M')
        almuerzo_fin = datetime.strptime(config_dia['almuerzo_fin'], '%H:%M')
        
        return (hora_inicio.time() < almuerzo_fin.time() and 
                hora_fin.time() > almuerzo_ini.time())
    except Exception as e:
        print(f"❌ [WEB] Error verificando solapamiento almuerzo: {e}")
        return False

def se_solapan(inicio1, fin1, inicio2, fin2):
    """Verificar si dos intervalos de tiempo se solapan"""
    return (inicio1.time() < fin2.time() and 
            fin1.time() > inicio2.time())

def reiniciar_conversacion_si_es_necesario(numero, negocio_id):
    """Reiniciar conversación si ha pasado mucho tiempo"""
    clave_conversacion = f"{numero}_{negocio_id}"
    if clave_conversacion in conversaciones_activas:
        if 'timestamp' in conversaciones_activas[clave_conversacion]:
            tiempo_transcurrido = datetime.now() - conversaciones_activas[clave_conversacion]['timestamp']
            if tiempo_transcurrido.total_seconds() > 600:  # 10 minutos
                del conversaciones_activas[clave_conversacion]

# =============================================================================
# FUNCIONES PARA ENVÍO DE CORREO/SMS Y RECORDATORIOS
# =============================================================================

def enviar_correo_confirmacion(cita, cliente_email):
    """Enviar confirmación de cita por correo electrónico"""
    # TODO: Implementar lógica de envío de correo
    # Usar smtplib o servicio como SendGrid
    print(f"📧 [WEB] Correo enviado a {cliente_email} para cita #{cita.get('id')}")
    return True

def enviar_sms_confirmacion(numero_telefono, mensaje):
    """Enviar SMS de confirmación"""
    # TODO: Implementar lógica de envío de SMS
    # Usar Twilio SMS (más barato que WhatsApp) u otro servicio
    print(f"📱 [WEB] SMS enviado a {numero_telefono}: {mensaje[:50]}...")
    return True

def notificar_cita_agendada(cita, cliente_info):
    """Notificar al cliente que su cita fue agendada"""
    try:
        # Obtener información del negocio
        negocio = db.obtener_negocio_por_id(cita['negocio_id'])
        
        # Preparar mensaje
        fecha_formateada = datetime.strptime(cita['fecha'], '%Y-%m-%d').strftime('%d/%m/%Y')
        precio_formateado = f"${cita.get('precio', 0):,.0f}".replace(',', '.')
        
        mensaje = f'''✅ Cita confirmada en {negocio['nombre']}

👤 Cliente: {cita['cliente_nombre']}
👨‍💼 Profesional: {cita['profesional_nombre']}
💼 Servicio: {cita['servicio_nombre']}
💰 Precio: {precio_formateado}
📅 Fecha: {fecha_formateada}
⏰ Hora: {cita['hora']}
🎫 ID: #{cita['id']}

📍 {negocio.get('direccion', 'Dirección no especificada')}

Recibirás recordatorios por correo electrónico.'''
        
        # Intentar enviar correo si hay email
        if cliente_info and cliente_info.get('email'):
            enviar_correo_confirmacion(cita, cliente_info['email'])
        
        # Enviar SMS si hay número de teléfono
        if cita.get('cliente_telefono'):
            enviar_sms_confirmacion(cita['cliente_telefono'], mensaje)
        
        return True
        
    except Exception as e:
        print(f"❌ [WEB] Error notificando cita: {e}")
        return False

def enviar_recordatorio_24h(cita):
    """Enviar recordatorio 24 horas antes de la cita - VERSIÓN PARA WEB CHAT"""
    try:
        print(f"🔔 [WEB] Recordatorio 24h para cita #{cita.get('id')}")
        print(f"   Cliente: {cita.get('cliente_nombre')}")
        print(f"   Fecha: {cita.get('fecha')} {cita.get('hora')}")
        
        # TODO: Implementar envío de correo/SMS aquí
        # Por ahora solo registramos en consola
        return True
        
    except Exception as e:
        print(f"❌ [WEB] Error enviando recordatorio 24h: {e}")
        return False

def enviar_recordatorio_1h(cita):
    """Enviar recordatorio 1 hora antes de la cita - VERSIÓN PARA WEB CHAT"""
    try:
        print(f"🔔 [WEB] Recordatorio 1h para cita #{cita.get('id')}")
        print(f"   Cliente: {cita.get('cliente_nombre')}")
        print(f"   Hora: {cita.get('hora')} (hoy)")
        
        # TODO: Implementar envío de correo/SMS aquí
        # Por ahora solo registramos en consola
        return True
        
    except Exception as e:
        print(f"❌ [WEB] Error enviando recordatorio 1h: {e}")
        return False
