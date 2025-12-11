"""
Manejador de chat web para agendamiento de citas
Versión convertida desde whatsapp_handler.py sin Twilio
"""

from flask import Blueprint
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
# MOTOR DE PLANTILLAS (CORREGIDO PARA POSTGRESQL) - SIN CAMBIOS
# =============================================================================

def limpiar_formato_whatsapp(texto):
    """
    Limpiar formato WhatsApp (*negrita*, _cursiva_) para el chat web
    """
    if not texto:
        return texto
    
    # Reemplazar formato WhatsApp por HTML
    texto = texto.replace('*', '')  # Quitar asteriscos de negrita
    texto = texto.replace('_', '')  # Quitar guiones bajos de cursiva
    
    # Reemplazar emojis por iconos si lo prefieres (opcional)
    emoji_map = {
        '👨‍💼': '<i class="fas fa-user-tie"></i>',
        '💼': '<i class="fas fa-briefcase"></i>',
        '💰': '<i class="fas fa-money-bill-wave"></i>',
        '📅': '<i class="fas fa-calendar-alt"></i>',
        '⏰': '<i class="fas fa-clock"></i>',
        '🎫': '<i class="fas fa-ticket-alt"></i>',
        '✅': '<i class="fas fa-check-circle"></i>',
        '❌': '<i class="fas fa-times-circle"></i>',
        '💡': '<i class="fas fa-lightbulb"></i>',
        '📋': '<i class="fas fa-clipboard-list"></i>',
    }
    
    for emoji, icon in emoji_map.items():
        texto = texto.replace(emoji, f'{icon} ')
    
    return texto

def renderizar_plantilla(nombre_plantilla, negocio_id, variables_extra=None):
    """Motor principal de plantillas - CORREGIDO PARA POSTGRESQL"""
    try:
        # Obtener plantilla de la base de datos
        plantilla_data = db.obtener_plantilla(negocio_id, nombre_plantilla)
        
        if not plantilla_data:
            print(f"❌ Plantilla '{nombre_plantilla}' no encontrada para negocio {negocio_id}")
            return f"❌ Error: Plantilla '{nombre_plantilla}' no encontrada"
        
        if isinstance(plantilla_data, dict) and 'plantilla' in plantilla_data:
            plantilla_texto = plantilla_data['plantilla']
        else:
            print(f"❌ Estructura de plantilla inválida: {type(plantilla_data)}")
            return f"❌ Error: Estructura de plantilla inválida"
        
        if not plantilla_texto:
            return f"❌ Error: Plantilla '{nombre_plantilla}' está vacía"
        
        # Obtener información del negocio
        negocio = db.obtener_negocio_por_id(negocio_id)
        if not negocio:
            return "❌ Error: Negocio no encontrado"
        
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
        
        return mensaje_final
        
    except Exception as e:
        print(f"❌ Error en renderizar_plantilla: {e}")
        return f"❌ Error al procesar plantilla '{nombre_plantilla}'"

# =============================================================================
# FUNCIÓN PRINCIPAL PARA PROCESAR MENSAJES DEL CHAT WEB - MODIFICADA
# =============================================================================

def procesar_mensaje_chat(user_message, session_id, negocio_id, session):
    """
    Función principal que procesa mensajes del chat web
    Reemplaza la función webhook_whatsapp
    """
    try:
        user_message = user_message.strip()
        
        print(f"🔧 [CHAT WEB] Mensaje recibido: '{user_message}'")
        
        # Verificar que el negocio existe y está activo
        negocio = db.obtener_negocio_por_id(negocio_id)
        if not negocio:
            return {
                'message': '❌ Este negocio no está configurado en el sistema.',
                'step': 'error'
            }
        
        if not negocio['activo']:
            return {
                'message': '❌ Este negocio no está activo actualmente.',
                'step': 'error'
            }
        
        # Usar session_id como identificador único (similar al número de teléfono)
        numero = session_id  # Para mantener compatibilidad con funciones existentes
        
        # Procesar mensaje usando la lógica existente
        respuesta_texto = procesar_mensaje(user_message, numero, negocio_id)
        
        # Obtener el paso actual para la respuesta
        clave_conversacion = f"{numero}_{negocio_id}"
        paso_actual = 'inicio'
        if clave_conversacion in conversaciones_activas:
            paso_actual = conversaciones_activas[clave_conversacion].get('estado', 'inicio')
        
        # Inicializar respuesta
        respuesta = {
            'message': limpiar_formato_whatsapp(respuesta_texto),
            'step': paso_actual
        }
        
        # Si estamos en un paso de selección, devolver opciones adicionales
        opciones_extra = None
        if paso_actual == 'seleccionando_profesional':
            opciones_extra = generar_opciones_profesionales(numero, negocio_id)
        elif paso_actual == 'seleccionando_servicio':
            opciones_extra = generar_opciones_servicios(numero, negocio_id)
        elif paso_actual == 'seleccionando_fecha':
            opciones_extra = generar_opciones_fechas(numero, negocio_id)
        elif paso_actual == 'agendando_hora':
            opciones_extra = generar_opciones_horarios(numero, negocio_id)
            # Agregar información de paginación al mensaje si existe
            if clave_conversacion in conversaciones_activas and 'info_paginacion' in conversaciones_activas[clave_conversacion]:
                respuesta['pagination'] = conversaciones_activas[clave_conversacion]['info_paginacion']
        elif paso_actual == 'confirmando_cita':
            opciones_extra = generar_opciones_confirmacion()
        elif paso_actual == 'menu_principal':
            opciones_extra = generar_opciones_menu_principal()
        
        if opciones_extra:
            respuesta['options'] = opciones_extra
        
        print(f"🔧 [CHAT WEB] Respuesta generada - Paso: {paso_actual}, Opciones: {opciones_extra}")
        
        return respuesta
        
    except Exception as e:
        print(f"❌ [CHAT WEB] Error procesando mensaje: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'message': '❌ Ocurrió un error al procesar tu mensaje. Por favor, intenta nuevamente.',
            'step': 'error'
        }

# =============================================================================
# LÓGICA PRINCIPAL DE MENSAJES (MODIFICADA PARA SEPARAR TEXTO Y OPCIONES)
# =============================================================================

def procesar_mensaje(mensaje, numero, negocio_id):
    """Procesar mensajes usando el sistema de plantillas - CORREGIDA"""
    mensaje = mensaje.lower().strip()
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG] PROCESANDO MENSAJE: '{mensaje}' de {numero}")
    print(f"🔧 [DEBUG] Clave conversación: {clave_conversacion}")
    print(f"🔧 [DEBUG] Conversación activa: {clave_conversacion in conversaciones_activas}")
    
    # Comando especial para volver al menú principal
    if mensaje == '0':
        print(f"🔧 [DEBUG] Comando '0' detectado - Volviendo al menú principal")
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        
        # Establecer estado como menu_principal
        conversaciones_activas[clave_conversacion] = {
            'estado': 'menu_principal',
            'timestamp': datetime.now()
        }
        return "¿En qué puedo ayudarte?"
    
    # Reiniciar conversación si ha pasado mucho tiempo
    reiniciar_conversacion_si_es_necesario(numero, negocio_id)
    
    # Si hay conversación activa, continuarla
    if clave_conversacion in conversaciones_activas:
        estado = conversaciones_activas[clave_conversacion]['estado']
        print(f"🔧 [DEBUG] Conversación activa encontrada - Estado: {estado}")
        
        # Si estamos en menu_principal y el usuario envía un número, procesarlo
        if estado == 'menu_principal' and mensaje in ['1', '2', '3', '4']:
            print(f"🔧 [DEBUG] Opción de menú seleccionada: {mensaje}")
            return procesar_opcion_menu(numero, mensaje, negocio_id)
        
        return continuar_conversacion(numero, mensaje, negocio_id)
    
    print(f"🔧 [DEBUG] No hay conversación activa - Procesando mensaje inicial")
    
    # Si el usuario envía 'hola' y no hay conversación activa
    if mensaje in ['hola', 'hi', 'hello', 'buenas']:
        print(f"🔧 [DEBUG] Saludo detectado - Mostrando saludo inicial")
        return saludo_inicial(numero, negocio_id)
    
    # Si el usuario envía un número directamente
    if mensaje in ['1', '2', '3', '4']:
        print(f"🔧 [DEBUG] Opción de menú seleccionada directamente: {mensaje}")
        return procesar_opcion_menu(numero, mensaje, negocio_id)
    
    # Mensaje no reconocido - mostrar saludo inicial
    print(f"🔧 [DEBUG] Mensaje no reconocido - Mostrando saludo inicial")
    return saludo_inicial(numero, negocio_id)

def procesar_opcion_menu(numero, opcion, negocio_id):
    """Procesar opción del menú principal"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if opcion == '1':
        print(f"🔧 [DEBUG] Comando '1' detectado - Mostrando profesionales")
        return mostrar_profesionales(numero, negocio_id)
    elif opcion == '2':
        print(f"🔧 [DEBUG] Comando '2' detectado - Mostrando citas")
        return mostrar_mis_citas(numero, negocio_id)
    elif opcion == '3':
        print(f"🔧 [DEBUG] Comando '3' detectado - Cancelando reserva")
        conversaciones_activas[clave_conversacion] = {'estado': 'cancelando', 'timestamp': datetime.now()}
        return mostrar_citas_para_cancelar(numero, negocio_id)
    elif opcion == '4':
        print(f"🔧 [DEBUG] Comando '4' detectado - Mostrando ayuda")
        return mostrar_ayuda(negocio_id)

# =============================================================================
# FUNCIONES PARA GENERAR OPCIONES EN EL CHAT WEB - MODIFICADAS
# =============================================================================

def generar_opciones_menu_principal():
    """Generar opciones del menú principal para botones del chat web"""
    opciones = [
        {'value': '1', 'text': 'Agendar cita'},
        {'value': '2', 'text': 'Ver mis citas'},
        {'value': '3', 'text': 'Cancelar cita'},
        {'value': '4', 'text': 'Ayuda'}
    ]
    return opciones

def generar_opciones_profesionales(numero, negocio_id):
    """Generar opciones de profesionales para botones del chat web - SIN texto de opciones"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if clave_conversacion not in conversaciones_activas or 'profesionales' not in conversaciones_activas[clave_conversacion]:
        return None
    
    profesionales = conversaciones_activas[clave_conversacion]['profesionales']
    opciones = []
    
    for i, prof in enumerate(profesionales, 1):
        opciones.append({
            'value': str(i),
            'text': f"{prof['nombre']} - {prof['especialidad']}"
        })
    
    return opciones

def generar_opciones_servicios(numero, negocio_id):
    """Generar opciones de servicios para botones del chat web - SIN texto de opciones"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if clave_conversacion not in conversaciones_activas or 'servicios' not in conversaciones_activas[clave_conversacion]:
        return None
    
    servicios = conversaciones_activas[clave_conversacion]['servicios']
    opciones = []
    
    for i, servicio in enumerate(servicios, 1):
        precio_formateado = f"${servicio['precio']:,.0f}".replace(',', '.')
        opciones.append({
            'value': str(i),
            'text': f"{servicio['nombre']} - {precio_formateado} ({servicio['duracion']} min)"
        })
    
    return opciones

def generar_opciones_fechas(numero, negocio_id):
    """Generar opciones de fechas para botones del chat web - SIN texto de opciones"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if clave_conversacion not in conversaciones_activas or 'fechas_disponibles' not in conversaciones_activas[clave_conversacion]:
        return None
    
    fechas = conversaciones_activas[clave_conversacion]['fechas_disponibles']
    opciones = []
    
    for i, fecha_info in enumerate(fechas, 1):
        opciones.append({
            'value': str(i),
            'text': fecha_info['mostrar']
        })
    
    return opciones

def generar_opciones_horarios(numero, negocio_id):
    """Generar opciones de horarios para botones del chat web - CORREGIDA"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if clave_conversacion not in conversaciones_activas or 'todos_horarios' not in conversaciones_activas[clave_conversacion]:
        return None
    
    horarios_disponibles = conversaciones_activas[clave_conversacion]['todos_horarios']
    pagina = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
    
    # Paginación
    horarios_por_pagina = 6
    inicio = pagina * horarios_por_pagina
    fin = inicio + horarios_por_pagina
    horarios_pagina = horarios_disponibles[inicio:fin]
    
    opciones = []
    
    # Agregar opciones de horarios
    for i, hora in enumerate(horarios_pagina, 1):
        opciones.append({
            'value': str(i),
            'text': f"{hora}"
        })
    
    # Agregar opciones de navegación como elementos adicionales del array
    total_paginas = (len(horarios_disponibles) + horarios_por_pagina - 1) // horarios_por_pagina
    pagina_actual = pagina + 1
    
    # Solo agregar navegación si hay múltiples páginas
    if total_paginas > 1:
        if pagina_actual < total_paginas:
            opciones.append({
                'value': '9',
                'text': '➡️ Siguiente página'
            })
        
        if pagina > 0:
            opciones.append({
                'value': '8',
                'text': '⬅️ Página anterior'
            })
    
    # Siempre agregar opción para cambiar fecha
    opciones.append({
        'value': '7',
        'text': '📅 Cambiar fecha'
    })
    
    # Guardar información de paginación en la conversación para referencia
    conversaciones_activas[clave_conversacion]['info_paginacion'] = f'Página {pagina_actual} de {total_paginas}'
    
    return opciones  # Devuelve un array simple, no un objeto

def generar_opciones_confirmacion():
    """Generar opciones de confirmación para botones del chat web"""
    opciones = [
        {'value': '1', 'text': '✅ Confirmar cita'},
        {'value': '2', 'text': '❌ Cancelar agendamiento'}
    ]
    return opciones

# =============================================================================
# FUNCIONES DE MENSAJES MODIFICADAS (SOLO TEXTO, SIN OPCIONES)
# =============================================================================

def saludo_inicial(numero, negocio_id):
    """Saludo inicial - MANEJO MEJORADO DE ERRORES"""
    try:
        # Intentar obtener nombre del cliente
        nombre_cliente = None
        try:
            nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id)
        except Exception as e:
            print(f"⚠️ [DEBUG] Error al obtener nombre del cliente: {e}")
            # No es crítico, continuamos sin nombre
        
        print(f"🔧 DEBUG saludo_inicial: numero={numero}, nombre_cliente='{nombre_cliente}'")
        
        if nombre_cliente and len(str(nombre_cliente).strip()) >= 2:
            print(f"🔧 DEBUG: Cliente existente: {nombre_cliente}")
            # Cliente existente - mostrar menú directamente
            clave_conversacion = f"{numero}_{negocio_id}"
            conversaciones_activas[clave_conversacion] = {
                'estado': 'menu_principal',
                'timestamp': datetime.now(),
                'cliente_nombre': nombre_cliente
            }
            return f"¡Hola {nombre_cliente}! 👋\n\n¿En qué puedo ayudarte hoy?"
        else:
            print(f"🔧 DEBUG: Cliente nuevo - pedir nombre")
            # Cliente nuevo - pedir nombre
            clave_conversacion = f"{numero}_{negocio_id}"
            conversaciones_activas[clave_conversacion] = {
                'estado': 'solicitando_nombre',
                'timestamp': datetime.now()
            }
            return "¡Hola! 👋 Soy tu asistente virtual para agendar citas.\n\n¿Cuál es tu nombre?"
            
    except Exception as e:
        print(f"❌ Error en saludo_inicial: {e}")
        import traceback
        traceback.print_exc()
        
        # En caso de error, pedir nombre
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion] = {
            'estado': 'solicitando_nombre',
            'timestamp': datetime.now()
        }
        return "¡Hola! 👋 Para comenzar, ¿cuál es tu nombre?"

def mostrar_profesionales(numero, negocio_id):
    """Mostrar lista de profesionales disponibles - SOLO TEXTO"""
    try:
        profesionales = db.obtener_profesionales(negocio_id)
        
        # Filtrar solo profesionales activos
        profesionales_activos = []
        for prof in profesionales:
            if prof.get('activo', True):
                profesionales_activos.append(prof)
        
        profesionales = profesionales_activos
        
        if not profesionales:
            return "❌ No hay profesionales disponibles en este momento."
        
        # Guardar en conversación activa
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion] = {
            'estado': 'seleccionando_profesional',
            'profesionales': profesionales,
            'timestamp': datetime.now()
        }
        
        return "👨‍💼 **Selecciona un profesional:**"
        
    except Exception as e:
        print(f"❌ Error en mostrar_profesionales: {e}")
        return "❌ Error al cargar profesionales."

def mostrar_servicios(numero, profesional_nombre, negocio_id):
    """Mostrar servicios disponibles - SOLO TEXTO"""
    try:
        servicios = db.obtener_servicios(negocio_id)
        
        # Filtrar servicios activos
        servicios_activos = []
        for servicio in servicios:
            if servicio.get('activo', True):
                servicios_activos.append(servicio)
        
        servicios = servicios_activos
        
        if not servicios:
            return "❌ No hay servicios disponibles en este momento."
        
        # Guardar en conversación activa
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion]['servicios'] = servicios
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_servicio'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
        
        return f"📋 **Servicios con {profesional_nombre}:**"
        
    except Exception as e:
        print(f"❌ Error en mostrar_servicios: {e}")
        return "❌ Error al cargar servicios."

def mostrar_fechas_disponibles(numero, negocio_id):
    """Mostrar fechas disponibles para agendar - SOLO TEXTO"""
    try:
        # Obtener próximas fechas donde el negocio está activo
        fechas_disponibles = obtener_proximas_fechas_disponibles(negocio_id)
        
        if not fechas_disponibles:
            return "❌ No hay fechas disponibles en los próximos días."
        
        # Guardar en conversación activa
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion]['fechas_disponibles'] = fechas_disponibles
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
        
        return "📅 **Selecciona una fecha:**"
        
    except Exception as e:
        print(f"❌ Error en mostrar_fechas_disponibles: {e}")
        return "❌ Error al cargar fechas."

def mostrar_disponibilidad(numero, negocio_id, fecha_seleccionada=None):
    """Mostrar horarios disponibles - SOLO TEXTO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG] mostrar_disponibilidad - fecha_seleccionada: {fecha_seleccionada}")
    
    if not fecha_seleccionada:
        fecha_seleccionada = conversaciones_activas[clave_conversacion].get('fecha_seleccionada', datetime.now().strftime('%Y-%m-%d'))
    
    print(f"🔧 [DEBUG] Fecha a usar: {fecha_seleccionada}")
    
    # Verificar disponibilidad básica
    if not verificar_disponibilidad_basica(negocio_id, fecha_seleccionada):
        fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
        return f"❌ No hay horarios disponibles para el {fecha_formateada}.\n\nPor favor, selecciona otra fecha."
    
    # Obtener datos de la conversación
    if 'profesional_id' not in conversaciones_activas[clave_conversacion]:
        return "❌ Error: No se encontró información del profesional."
    
    profesional_id = conversaciones_activas[clave_conversacion]['profesional_id']
    servicio_id = conversaciones_activas[clave_conversacion]['servicio_id']
    pagina = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
    
    print(f"🔧 [DEBUG] Generando horarios para: profesional_id={profesional_id}, servicio_id={servicio_id}")
    
    # Generar horarios disponibles
    horarios_disponibles = generar_horarios_disponibles_actualizado(negocio_id, profesional_id, fecha_seleccionada, servicio_id)
    
    print(f"🔧 [DEBUG] Horarios generados: {len(horarios_disponibles)}")
    
    if not horarios_disponibles:
        fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
        return f"❌ No hay horarios disponibles para el {fecha_formateada}."
    
    # Datos para el mensaje
    profesional_nombre = conversaciones_activas[clave_conversacion]['profesional_nombre']
    servicio_nombre = conversaciones_activas[clave_conversacion]['servicio_nombre']
    servicio_precio = conversaciones_activas[clave_conversacion]['servicio_precio']
    precio_formateado = f"${servicio_precio:,.0f}".replace(',', '.')
    fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
    
    # Guardar datos para paginación
    conversaciones_activas[clave_conversacion]['todos_horarios'] = horarios_disponibles
    conversaciones_activas[clave_conversacion]['fecha_seleccionada'] = fecha_seleccionada
    conversaciones_activas[clave_conversacion]['estado'] = 'agendando_hora'
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    return f"📅 **Horarios disponibles con {profesional_nombre} ({fecha_formateada}):**\n💼 Servicio: {servicio_nombre} - {precio_formateado}"

def mostrar_mis_citas(numero, negocio_id):
    """Mostrar citas del cliente - CORREGIDA para PostgreSQL"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG] mostrar_mis_citas - Clave: {clave_conversacion}")
    
    # Verificar si ya tenemos teléfono en esta conversación
    telefono_real = None
    if clave_conversacion in conversaciones_activas:
        telefono_real = conversaciones_activas[clave_conversacion].get('telefono_cliente')
        print(f"🔧 [DEBUG] Teléfono en conversación: {telefono_real}")
    
    # Si NO tenemos teléfono, pedirlo
    if not telefono_real:
        print(f"🔧 [DEBUG] No hay teléfono en conversación, solicitando...")
        # Pasar a estado de solicitar teléfono para ver citas
        conversaciones_activas[clave_conversacion] = {
            'estado': 'solicitando_telefono_para_ver',
            'timestamp': datetime.now(),
            'session_id': numero
        }
        return "📱 **Para ver tus citas, necesitamos tu número de teléfono.**\n\nPor favor, ingresa tu número de 10 dígitos (debe empezar con 3, ej: 3101234567):"
    
    # Si SÍ tenemos teléfono, buscar citas
    print(f"🔧 [DEBUG] Buscando citas con teléfono: {telefono_real}")
    
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ✅ CORRECCIÓN: Usar CAST para convertir fecha de texto a date
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora, s.nombre as servicio, c.estado, p.nombre as profesional_nombre
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            JOIN profesionales p ON c.profesional_id = p.id
            WHERE c.cliente_telefono = %s AND c.negocio_id = %s 
            AND (c.fecha)::date >= CURRENT_DATE  -- ✅ CONVERTIR texto a date
            ORDER BY (c.fecha)::date, c.hora
        ''', (telefono_real, negocio_id))
        
        citas = cursor.fetchall()
        conn.close()
        
        print(f"🔧 [DEBUG] Citas encontradas: {len(citas)}")
        
        # Obtener nombre del cliente
        nombre_cliente = None
        
        # 1. Primero de la conversación
        if clave_conversacion in conversaciones_activas:
            nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre')
            print(f"🔧 [DEBUG] Nombre de conversación: {nombre_cliente}")
        
        # 2. Si no hay, intentar de BD
        if not nombre_cliente or len(str(nombre_cliente).strip()) < 2:
            try:
                nombre_cliente = db.obtener_nombre_cliente(telefono_real, negocio_id)
                print(f"🔧 [DEBUG] Nombre de BD: {nombre_cliente}")
            except Exception as e:
                print(f"⚠️ [DEBUG] Error obteniendo nombre de BD: {e}")
                nombre_cliente = 'Cliente'
        
        # Formatear nombre
        if nombre_cliente and len(str(nombre_cliente).strip()) >= 2:
            nombre_cliente = str(nombre_cliente).strip()
        else:
            nombre_cliente = 'Cliente'
        
        if not citas:
            return f"📋 **No tienes citas programadas, {nombre_cliente}.**\n\nPara agendar una nueva cita, selecciona: *1*"
        
        # Construir lista de citas
        respuesta = f"📋 **Tus citas programadas - {nombre_cliente}:**\n\n"
        
        for cita in citas:
            id_cita, fecha, hora, servicio, estado, profesional_nombre = cita
            
            # Formatear fecha (manejar tanto string como date)
            try:
                if isinstance(fecha, str):
                    fecha_str = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m')
                else:
                    fecha_str = fecha.strftime('%d/%m')
            except Exception as e:
                fecha_str = str(fecha)
                print(f"⚠️ [DEBUG] Error formateando fecha {fecha}: {e}")
            
            emoji = "✅" if estado == 'confirmado' else "❌"
            respuesta += f"{emoji} *{fecha_str}* - {hora}\n"
            respuesta += f"   👨‍💼 {profesional_nombre} - {servicio}\n"
            respuesta += f"   🎫 ID: #{id_cita}\n\n"
        
        respuesta += "Para cancelar una cita, selecciona: *3*"
        
        # Volver al menú principal
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        
        return respuesta
        
    except Exception as e:
        print(f"❌ Error mostrando citas: {e}")
        import traceback
        traceback.print_exc()
        
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        
        return "❌ Error al cargar tus citas. Por favor, intenta más tarde."

def mostrar_citas_para_cancelar(numero, negocio_id):
    """Mostrar citas que pueden ser canceladas - MODIFICADA para pedir teléfono"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG] mostrar_citas_para_cancelar - Clave: {clave_conversacion}")
    
    # Verificar si ya tenemos teléfono en esta conversación
    telefono_real = None
    if clave_conversacion in conversaciones_activas:
        telefono_real = conversaciones_activas[clave_conversacion].get('telefono_cliente')
        print(f"🔧 [DEBUG] Teléfono en conversación: {telefono_real}")
    
    # Si NO tenemos teléfono, pedirlo
    if not telefono_real:
        print(f"🔧 [DEBUG] No hay teléfono en conversación, solicitando...")
        return solicitar_telefono_para_consulta(numero, negocio_id, "cancelar")
    
    # Si SÍ tenemos teléfono, buscar citas para cancelar
    print(f"🔧 [DEBUG] Buscando citas para cancelar con teléfono: {telefono_real}")
    
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ✅ CORRECCIÓN: Usar ::date para convertir texto a fecha
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora, p.nombre as profesional_nombre, s.nombre as servicio_nombre
            FROM citas c
            JOIN profesionales p ON c.profesional_id = p.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.cliente_telefono = %s AND c.negocio_id = %s 
            AND c.fecha::date >= CURRENT_DATE AND c.estado = 'confirmado'
            ORDER BY c.fecha::date, c.hora
        ''', (telefono_real, negocio_id))
        
        citas = cursor.fetchall()
        conn.close()
        
        print(f"🔧 [DEBUG] Citas encontradas para cancelar: {len(citas)}")
        
        if not citas:
            # Limpiar conversación de cancelación
            if clave_conversacion in conversaciones_activas:
                conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
            
            nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre', 'Cliente')
            return f"❌ **No tienes citas para cancelar, {nombre_cliente}.**"
        
        if len(citas) == 1:
            # Solo una cita, cancelar directamente
            cita_id = citas[0][0]
            return procesar_cancelacion_directa(numero, str(cita_id), negocio_id)
        
        # Construir lista de citas para cancelar
        nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre', 'Cliente')
        respuesta = f"❌ **Citas para cancelar - {nombre_cliente}:**\n\n"
        
        for cita in citas:
            id_cita, fecha, hora, profesional_nombre, servicio_nombre = cita
            try:
                if isinstance(fecha, str):
                    fecha_str = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m')
                else:
                    fecha_str = fecha.strftime('%d/%m')
            except:
                fecha_str = str(fecha)
            
            respuesta += f"📅 {fecha_str} - {hora}\n"
            respuesta += f"   👨‍💼 {profesional_nombre} - {servicio_nombre}\n"
            respuesta += f"   🎫 ID: #{id_cita}\n\n"
        
        respuesta += "\n**Selecciona el ID de la cita que quieres cancelar.**"
        
        # Guardar citas disponibles para cancelación
        conversaciones_activas[clave_conversacion]['citas_disponibles'] = {str(t[0]): t for t in citas}
        conversaciones_activas[clave_conversacion]['estado'] = 'cancelando'
        
        return respuesta
        
    except Exception as e:
        print(f"❌ Error mostrando citas para cancelar: {e}")
        import traceback
        traceback.print_exc()
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        return "❌ Error al cargar tus citas."

def mostrar_ayuda(negocio_id):
    """Mostrar mensaje de ayuda"""
    return "ℹ️ **Ayuda:**\n\nPara agendar una cita, responde: *1*\nPara ver tus citas, responde: *2*\nPara cancelar una cita, responde: *3*\n\nEn cualquier momento puedes escribir *0* para volver al menú principal."

def procesar_confirmacion_cita(numero, mensaje, negocio_id):
    """Procesar confirmación de la cita - COMPLETAMENTE CORREGIDA"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG] procesar_confirmacion_cita - Clave: {clave_conversacion}, Mensaje: '{mensaje}'")
    
    # Verificar que existe la conversación
    if clave_conversacion not in conversaciones_activas:
        print(f"❌ [DEBUG] No hay conversación activa para {clave_conversacion}")
        return "❌ Sesión expirada. Por favor, inicia nuevamente."
    
    conversacion = conversaciones_activas[clave_conversacion]
    estado_actual = conversacion.get('estado', '')
    
    print(f"🔧 [DEBUG] Estado actual: {estado_actual}")
    
    # Si estamos solicitando teléfono
    if estado_actual == 'solicitando_telefono':
        print(f"🔧 [DEBUG] Procesando número de teléfono: {mensaje}")
        
        # Validar teléfono
        telefono = mensaje.strip()
        
        # Validar formato: 10 dígitos, debe empezar con 3
        if not telefono.isdigit() or len(telefono) != 10:
            print(f"❌ [DEBUG] Teléfono inválido: {telefono}")
            return "❌ Número inválido. Por favor ingresa 10 dígitos (debe empezar con 3, ej: 3101234567):"
        
        if not telefono.startswith('3'):
            print(f"❌ [DEBUG] Teléfono no empieza con 3: {telefono}")
            return "❌ Número inválido. El número debe empezar con 3 (ej: 3101234567):"
        
        # Guardar teléfono en la conversación
        conversacion['telefono_cliente'] = telefono
        
        # Obtener todos los datos necesarios para crear la cita
        try:
            print(f"🔧 [DEBUG] Obteniendo datos de la cita...")
            
            # Verificar que tenemos todos los datos necesarios
            datos_requeridos = ['hora_seleccionada', 'fecha_seleccionada', 'profesional_id', 
                              'servicio_id', 'profesional_nombre', 'servicio_nombre', 'servicio_precio']
            
            for dato in datos_requeridos:
                if dato not in conversacion:
                    print(f"❌ [DEBUG] Falta dato: {dato}")
                    del conversaciones_activas[clave_conversacion]
                    return "❌ Error: Datos incompletos. Comienza de nuevo."
            
            hora = conversacion['hora_seleccionada']
            fecha = conversacion['fecha_seleccionada']
            profesional_id = conversacion['profesional_id']
            servicio_id = conversacion['servicio_id']
            profesional_nombre = conversacion['profesional_nombre']
            servicio_nombre = conversacion['servicio_nombre']
            servicio_precio = conversacion['servicio_precio']
            
            # ⚠️ CORRECCIÓN CRÍTICA: Obtener nombre del cliente SIN valor por defecto 'Cliente'
            if 'cliente_nombre' not in conversacion:
                print(f"❌ [DEBUG-CRÍTICO] ERROR: No hay 'cliente_nombre' en conversación")
                print(f"❌ [DEBUG] Claves disponibles: {list(conversacion.keys())}")
                
                # Pedir nombre nuevamente
                conversacion['estado'] = 'solicitando_nombre'
                return "📝 **Antes de confirmar, necesitamos tu nombre.**\n\nPor favor, ingresa tu nombre:"
            
            nombre_cliente = conversacion['cliente_nombre']  # ✅ SIN 'Cliente' por defecto
            
            # Validar que el nombre sea válido
            if not nombre_cliente or len(str(nombre_cliente).strip()) < 2:
                print(f"❌ [DEBUG] Nombre inválido: '{nombre_cliente}'")
                conversacion['estado'] = 'solicitando_nombre'
                return "❌ El nombre ingresado no es válido. Por favor, ingresa tu nombre:"
            
            nombre_cliente = str(nombre_cliente).strip().title()
            print(f"✅ [DEBUG] Nombre validado para cita: '{nombre_cliente}'")
            
            print(f"🔧 [DEBUG] Datos para cita:")
            print(f"   - Cliente: {nombre_cliente}")
            print(f"   - Teléfono REAL: {telefono}")
            print(f"   - Session ID: {numero}")
            print(f"   - Fecha: {fecha}")
            print(f"   - Hora: {hora}")
            print(f"   - Profesional: {profesional_nombre} (ID: {profesional_id})")
            print(f"   - Servicio: {servicio_nombre} (ID: {servicio_id})")
            
            # ✅ 1. PRIMERO: GUARDAR O ACTUALIZAR CLIENTE EN BD CON TELÉFONO REAL
            print(f"🔧 [DEBUG] Guardando cliente en BD con teléfono real...")
            try:
                from database import get_db_connection
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Verificar si ya existe (usando teléfono REAL)
                cursor.execute('''
                    SELECT id, nombre FROM clientes WHERE telefono = %s AND negocio_id = %s
                ''', (telefono, negocio_id))
                
                cliente_existente = cursor.fetchone()
                
                fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                if cliente_existente:
                    cliente_id, nombre_actual = cliente_existente
                    # Si el nombre actual es genérico o diferente, actualizarlo
                    if nombre_actual in ['Cliente', 'cliente', ''] or len(nombre_actual.strip()) < 2:
                        cursor.execute('''
                            UPDATE clientes 
                            SET nombre = %s, updated_at = %s
                            WHERE id = %s
                        ''', (nombre_cliente, fecha_actual, cliente_id))
                        print(f"✅ [DEBUG] Nombre actualizado en BD: '{nombre_actual}' -> '{nombre_cliente}'")
                    else:
                        print(f"✅ [DEBUG] Manteniendo nombre existente en BD: '{nombre_actual}'")
                else:
                    # Insertar nuevo cliente
                    cursor.execute('''
                        INSERT INTO clientes (negocio_id, telefono, nombre, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                    ''', (negocio_id, telefono, nombre_cliente, fecha_actual, fecha_actual))
                    
                    cliente_id = cursor.fetchone()[0]
                    print(f"✅ [DEBUG] Nuevo cliente creado en BD: ID={cliente_id}, Teléfono={telefono}")
                
                conn.commit()
                conn.close()
                print(f"✅ [DEBUG] Cliente guardado/actualizado exitosamente en BD")
                
            except Exception as e:
                print(f"⚠️ [DEBUG] Error guardando cliente en BD: {e}")
                import traceback
                traceback.print_exc()
                # Continuamos aunque falle, la cita se puede crear igual
            
            # ✅ 2. CREAR LA CITA con el TELÉFONO REAL
            print(f"🔧 [DEBUG] Creando cita en BD...")
            cita_id = db.agregar_cita(
                negocio_id=negocio_id,
                profesional_id=profesional_id,
                cliente_telefono=telefono,  # ✅ TELÉFONO REAL
                fecha=fecha,
                hora=hora,
                servicio_id=servicio_id,
                cliente_nombre=nombre_cliente  # ✅ NOMBRE REAL, NO 'Cliente'
            )
            
            if cita_id and cita_id > 0:
                print(f"✅ [DEBUG] Cita creada exitosamente. ID: {cita_id}")
                
                # Limpiar conversación ANTES de devolver el mensaje
                del conversaciones_activas[clave_conversacion]
                
                precio_formateado = f"${servicio_precio:,.0f}".replace(',', '.')
                fecha_formateada = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m/%Y')
                
                mensaje_confirmacion = f'''✅ **Cita Confirmada**

Hola *{nombre_cliente}*, 

Tu cita ha sido agendada exitosamente:

• **Profesional:** {profesional_nombre}
• **Servicio:** {servicio_nombre}  
• **Precio:** {precio_formateado}
• **Fecha:** {fecha_formateada}
• **Hora:** {hora}
• **ID de cita:** #{cita_id}
• **Teléfono:** {telefono}

Recibirás recordatorios por mensaje antes de tu cita.

¡Te esperamos!'''
                
                return mensaje_confirmacion
            else:
                print(f"❌ [DEBUG] Error al crear la cita. ID retornado: {cita_id}")
                del conversaciones_activas[clave_conversacion]
                return "❌ Error al crear la cita en el sistema. Por favor, intenta nuevamente o contacta al negocio directamente."
                
        except Exception as e:
            print(f"❌ [DEBUG] Error general al crear cita: {e}")
            import traceback
            traceback.print_exc()
            
            if clave_conversacion in conversaciones_activas:
                del conversaciones_activas[clave_conversacion]
            return "❌ Error inesperado al procesar tu cita. Por favor, intenta nuevamente."
    
    # Si no estamos solicitando teléfono, procesar opciones normales de confirmación
    if mensaje == '1':
        # Primera confirmación: pedir teléfono
        print(f"🔧 [DEBUG] Usuario confirmó cita, solicitando teléfono...")
        conversacion['estado'] = 'solicitando_telefono'
        conversacion['timestamp'] = datetime.now()
        
        return "📱 **Para enviarte recordatorios de tu cita, necesitamos tu número de teléfono.**\n\nPor favor, ingresa tu número de 10 dígitos (debe empezar con 3, ej: 3101234567):"
    
    elif mensaje == '2':
        print(f"🔧 [DEBUG] Usuario canceló agendamiento")
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return "❌ Agendamiento cancelado."
    
    else:
        print(f"❌ [DEBUG] Opción inválida recibida: {mensaje}")
        return "❌ Opción no válida. Responde con *1* para confirmar o *2* para cancelar."
    
def solicitar_telefono_para_consulta(numero, negocio_id, accion="ver"):
    """
    Solicitar teléfono al cliente para consultar/cancelar citas
    accion: "ver" para ver citas, "cancelar" para cancelar citas
    """
    clave_conversacion = f"{numero}_{negocio_id}"
    
    # Crear o actualizar conversación
    conversaciones_activas[clave_conversacion] = {
        'estado': f'solicitando_telefono_para_{accion}',
        'timestamp': datetime.now(),
        'session_id': numero,
        'accion_pendiente': accion
    }
    
    if accion == "ver":
        return "📱 **Para ver tus citas, necesitamos verificar tu número de teléfono.**\n\nPor favor, ingresa tu número de 10 dígitos (debe empezar con 3, ej: 3101234567):"
    else:  # cancelar
        return "📱 **Para cancelar una cita, necesitamos verificar tu número de teléfono.**\n\nPor favor, ingresa tu número de 10 dígitos (debe empezar con 3, ej: 3101234567):"

# =============================================================================
# EL RESTO DE LAS FUNCIONES SE MANTIENEN IGUAL
# =============================================================================

def continuar_conversacion(numero, mensaje, negocio_id):
    """Continuar conversación basada en el estado actual - CORREGIDA"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if clave_conversacion not in conversaciones_activas:
        print(f"❌ [DEBUG] No hay conversación activa en continuar_conversacion")
        return saludo_inicial(numero, negocio_id)
    
    estado = conversaciones_activas[clave_conversacion]['estado']
    
    print(f"🔧 CONTINUANDO CONVERSACIÓN - Estado: {estado}, Mensaje: '{mensaje}'")
    
    try:
        if estado == 'solicitando_nombre':
            return procesar_nombre_cliente(numero, mensaje, negocio_id)
        elif estado == 'seleccionando_profesional':
            return procesar_seleccion_profesional(numero, mensaje, negocio_id)
        elif estado == 'seleccionando_servicio':
            return procesar_seleccion_servicio(numero, mensaje, negocio_id)
        elif estado == 'seleccionando_fecha':
            return procesar_seleccion_fecha(numero, mensaje, negocio_id)
        elif estado == 'agendando_hora':
            return procesar_seleccion_hora(numero, mensaje, negocio_id)
        elif estado == 'confirmando_cita':
            return procesar_confirmacion_cita(numero, mensaje, negocio_id)
        elif estado == 'cancelando':
            return procesar_cancelacion_cita(numero, mensaje, negocio_id)
        elif estado == 'solicitando_telefono':
            # Para confirmar cita
            return procesar_confirmacion_cita(numero, mensaje, negocio_id)
        elif estado == 'solicitando_telefono_para_ver':
            # Nuevo estado: procesar teléfono para ver citas
            return procesar_telefono_para_ver_citas(numero, mensaje, negocio_id)
        else:
            # Estado no reconocido - reiniciar
            print(f"❌ [DEBUG] Estado no reconocido: {estado}")
            if clave_conversacion in conversaciones_activas:
                del conversaciones_activas[clave_conversacion]
            return saludo_inicial(numero, negocio_id)
        
    except Exception as e:
        print(f"❌ Error en continuar_conversacion: {e}")
        import traceback
        traceback.print_exc()
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return "❌ Error al procesar tu solicitud."
    
def procesar_telefono_para_ver_citas(numero, mensaje, negocio_id):
    """Procesar teléfono ingresado para ver citas"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        return "Volviendo al menú principal..."
    
    # Validar teléfono
    telefono = mensaje.strip()
    
    if not telefono.isdigit() or len(telefono) != 10 or not telefono.startswith('3'):
        return "❌ Número inválido. Por favor ingresa 10 dígitos (debe empezar con 3, ej: 3101234567):"
    
    print(f"🔧 [DEBUG] Teléfono válido para ver citas: {telefono}")
    
    # Guardar teléfono en conversación
    if clave_conversacion not in conversaciones_activas:
        conversaciones_activas[clave_conversacion] = {}
    
    conversaciones_activas[clave_conversacion]['telefono_cliente'] = telefono
    
    # También intentar obtener nombre del cliente de BD
    try:
        nombre_cliente = db.obtener_nombre_cliente(telefono, negocio_id)
        if nombre_cliente and len(str(nombre_cliente).strip()) >= 2:
            conversaciones_activas[clave_conversacion]['cliente_nombre'] = str(nombre_cliente).strip()
            print(f"🔧 [DEBUG] Nombre obtenido de BD: {nombre_cliente}")
    except Exception as e:
        print(f"⚠️ [DEBUG] Error obteniendo nombre de BD: {e}")
    
    # Cambiar estado y mostrar citas
    conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
    
    return mostrar_mis_citas(numero, negocio_id)

def procesar_nombre_cliente(numero, mensaje, negocio_id):
    """Procesar nombre del cliente nuevo - GUARDAR EN CONVERSACIÓN"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    nombre = mensaje.strip()
    if len(nombre) < 2:
        return "Por favor, ingresa un nombre válido:"
    
    print(f"🔧 [DEBUG] Procesando nombre '{nombre}' para {numero}")
    
    # ⚠️ IMPORTANTE: NO guardar en BD con session_id como teléfono
    # Solo guardar en la conversación activa
    # El cliente se guardará en BD con su teléfono REAL cuando lo ingrese
    
    # ✅ Limpiar conversación activa si existe
    if clave_conversacion in conversaciones_activas:
        del conversaciones_activas[clave_conversacion]
    
    # ✅ Guardar nombre CORRECTAMENTE (capitalizado)
    nombre_cliente = nombre.strip().title()
    
    # ✅ Cambiar el estado a 'menu_principal' y GUARDAR EL NOMBRE CORRECTAMENTE
    conversaciones_activas[clave_conversacion] = {
        'estado': 'menu_principal',
        'timestamp': datetime.now(),
        'cliente_nombre': nombre_cliente,  # ¡IMPORTANTE! Guardar aquí para usarlo después
        'session_id': numero  # Guardar para referencia
    }
    
    print(f"✅ [DEBUG] Nombre '{nombre_cliente}' guardado en conversación activa")
    
    return f"¡Hola {nombre_cliente}! 👋\n\n¿En qué puedo ayudarte?"

def procesar_seleccion_profesional(numero, mensaje, negocio_id):
    """Procesar selección de profesional"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    if 'profesionales' not in conversaciones_activas[clave_conversacion]:
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return "❌ Sesión expirada. Por favor, inicia nuevamente con *1*"
    
    profesionales = conversaciones_activas[clave_conversacion]['profesionales']
    
    if not mensaje.isdigit() or int(mensaje) < 1 or int(mensaje) > len(profesionales):
        return f"❌ Número inválido. Por favor, elige entre 1 y {len(profesionales)}"
    
    # Guardar profesional seleccionado
    profesional_index = int(mensaje) - 1
    profesional_seleccionado = profesionales[profesional_index]
    
    conversaciones_activas[clave_conversacion]['profesional_id'] = profesional_seleccionado['id']
    conversaciones_activas[clave_conversacion]['profesional_nombre'] = profesional_seleccionado['nombre']
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    return mostrar_servicios(numero, profesional_seleccionado['nombre'], negocio_id)

def procesar_seleccion_servicio(numero, mensaje, negocio_id):
    """Procesar selección de servicio - CORREGIDO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    # ✅ CORRECCIÓN: Manejar el comando "0" para volver al menú principal
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    if 'servicios' not in conversaciones_activas[clave_conversacion]:
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return "❌ Sesión expirada. Por favor, inicia nuevamente con *1*"
    
    servicios = conversaciones_activas[clave_conversacion]['servicios']
    
    if not mensaje.isdigit() or int(mensaje) < 1 or int(mensaje) > len(servicios):
        return f"❌ Número inválido. Por favor, elige entre 1 y {len(servicios)}"
    
    # Guardar servicio seleccionado
    servicio_index = int(mensaje) - 1
    servicio_seleccionado = servicios[servicio_index]
    
    conversaciones_activas[clave_conversacion]['servicio_id'] = servicio_seleccionado['id']
    conversaciones_activas[clave_conversacion]['servicio_nombre'] = servicio_seleccionado['nombre']
    conversaciones_activas[clave_conversacion]['servicio_precio'] = servicio_seleccionado['precio']
    conversaciones_activas[clave_conversacion]['servicio_duracion'] = servicio_seleccionado['duracion']
    conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    return mostrar_fechas_disponibles(numero, negocio_id)

def procesar_seleccion_fecha(numero, mensaje, negocio_id):
    """Procesar selección de fecha - CORREGIDA"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    if 'fechas_disponibles' not in conversaciones_activas[clave_conversacion]:
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return "❌ Sesión expirada. Por favor, inicia nuevamente con *1*"
    
    fechas_disponibles = conversaciones_activas[clave_conversacion]['fechas_disponibles']
    
    if not mensaje.isdigit() or int(mensaje) < 1 or int(mensaje) > len(fechas_disponibles):
        return f"❌ Número inválido. Por favor, elige entre 1 y {len(fechas_disponibles)}"
    
    # Guardar fecha seleccionada
    fecha_index = int(mensaje) - 1
    fecha_seleccionada = fechas_disponibles[fecha_index]['fecha']  # YA está en formato YYYY-MM-DD
    
    print(f"🔧 [DEBUG] Fecha seleccionada: {fecha_seleccionada} (índice: {fecha_index})")
    print(f"🔧 [DEBUG] Datos completos: {fechas_disponibles[fecha_index]}")
    
    conversaciones_activas[clave_conversacion]['fecha_seleccionada'] = fecha_seleccionada
    conversaciones_activas[clave_conversacion]['estado'] = 'agendando_hora'
    conversaciones_activas[clave_conversacion]['pagina_horarios'] = 0
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    return mostrar_disponibilidad(numero, negocio_id, fecha_seleccionada)

def procesar_seleccion_hora(numero, mensaje, negocio_id):
    """Procesar selección de horario - CORREGIDA Y GENÉRICA"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    # ✅ CORRECCIÓN: Navegación de horarios y cambio de fecha
    if mensaje == '7':  # Cambiar fecha
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
        return mostrar_fechas_disponibles(numero, negocio_id)
        
    elif mensaje == '8':  # Página anterior
        pagina_actual = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
        if pagina_actual > 0:
            conversaciones_activas[clave_conversacion]['pagina_horarios'] = pagina_actual - 1
        return mostrar_disponibilidad(numero, negocio_id)
        
    elif mensaje == '9':  # Página siguiente
        pagina_actual = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
        horarios_disponibles = conversaciones_activas[clave_conversacion]['todos_horarios']
        horarios_por_pagina = 6
        
        # ✅ CORRECCIÓN: Verificar que hay más páginas
        max_pagina = (len(horarios_disponibles) - 1) // horarios_por_pagina
        if pagina_actual < max_pagina:
            conversaciones_activas[clave_conversacion]['pagina_horarios'] = pagina_actual + 1
        else:
            # Ya estamos en la última página, mostrar mensaje
            return "ℹ️ Ya estás en la última página de horarios.\n\nSelecciona un horario o usa otra opción"
        
        return mostrar_disponibilidad(numero, negocio_id)
    
    # Obtener horarios de la página actual
    pagina_actual = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
    horarios_disponibles = conversaciones_activas[clave_conversacion]['todos_horarios']
    horarios_por_pagina = 6
    inicio = pagina_actual * horarios_por_pagina
    fin = inicio + horarios_por_pagina
    horarios_pagina = horarios_disponibles[inicio:fin]
    
    # ✅ CORRECCIÓN: Verificar que el mensaje es un número válido para horarios
    if not mensaje.isdigit():
        return f"❌ Por favor, ingresa un número válido."
    
    mensaje_num = int(mensaje)
    
    # ✅ CORRECCIÓN: Solo procesar números 1-6 como horarios (evitar conflicto con 7,8,9)
    if mensaje_num < 1 or mensaje_num > len(horarios_pagina):
        return f"❌ Número inválido. Por favor, elige entre 1 y {len(horarios_pagina)}"
    
    # Guardar horario seleccionado y pedir confirmación
    hora_index = mensaje_num - 1
    hora_seleccionada = horarios_pagina[hora_index]
    
    conversaciones_activas[clave_conversacion]['hora_seleccionada'] = hora_seleccionada
    conversaciones_activas[clave_conversacion]['estado'] = 'confirmando_cita'
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    # ✅ CORRECCIÓN: Obtener nombre del cliente correctamente
    nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre')
    if not nombre_cliente:
        nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id)
    
    # Si aún no hay nombre, usar valor por defecto
    if not nombre_cliente or len(str(nombre_cliente).strip()) < 2:
        nombre_cliente = 'Cliente'
    else:
        nombre_cliente = str(nombre_cliente).strip()
    
    profesional_nombre = conversaciones_activas[clave_conversacion]['profesional_nombre']
    servicio_nombre = conversaciones_activas[clave_conversacion]['servicio_nombre']
    servicio_precio = conversaciones_activas[clave_conversacion]['servicio_precio']
    precio_formateado = f"${servicio_precio:,.0f}".replace(',', '.')
    fecha_seleccionada = conversaciones_activas[clave_conversacion]['fecha_seleccionada']
    fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
    
    return f'''✅ **Confirmar cita**

Hola *{nombre_cliente}*, ¿confirmas tu cita?

👨‍💼 **Profesional:** {profesional_nombre}
💼 **Servicio:** {servicio_nombre}
💰 **Precio:** {precio_formateado}
📅 **Fecha:** {fecha_formateada}
⏰ **Hora:** {hora_seleccionada}

**Selecciona una opción:**'''

def procesar_cancelacion_cita(numero, mensaje, negocio_id):
    """Procesar cancelación de cita - MEJORADO PARA POSTGRESQL"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    if 'citas_disponibles' not in conversaciones_activas[clave_conversacion]:
        # ✅ CORRECCIÓN 4: Si la sesión expiró durante cancelación, mostrar menú principal
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return "❌ Sesión de cancelación expirada."
    
    citas_disponibles = conversaciones_activas[clave_conversacion]['citas_disponibles']
    
    if mensaje not in citas_disponibles:
        return "❌ ID de cita inválido. Por favor, ingresa un ID de la lista anterior."
    
    # Cancelar cita
    try:
        cita_id = mensaje
        cita_info = citas_disponibles[cita_id]
        
        # Actualizar estado en base de datos
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE citas SET estado = %s WHERE id = %s AND negocio_id = %s', 
                      ('cancelado', cita_id, negocio_id))
        
        conn.commit()
        conn.close()
        
        # Limpiar conversación
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        
        # Usar plantilla para mensaje de cancelación
        nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id) or 'Cliente'
        fecha_str = datetime.strptime(str(cita_info[1]), '%Y-%m-%d').strftime('%d/%m')
        
        return f'''❌ **Cita cancelada**

Hola {nombre_cliente}, has cancelado tu cita del {fecha_str} a las {cita_info[2]}.

Esperamos verte pronto en otra ocasión.'''
        
    except Exception as e:
        print(f"❌ Error cancelando cita: {e}")
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return "❌ Error al cancelar la cita."

def procesar_cancelacion_directa(numero, cita_id, negocio_id):
    """Procesar cancelación cuando solo hay una cita - GENÉRICO PARA POSTGRESQL"""
    if cita_id == '0':
        clave_conversacion = f"{numero}_{negocio_id}"
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    # Cancelar cita directamente
    from database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE citas SET estado = %s WHERE id = %s AND negocio_id = %s', 
                  ('cancelado', cita_id, negocio_id))
    
    conn.commit()
    conn.close()
    
    nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id) or 'Cliente'
    
    return f'''❌ **Cita cancelada**

Hola {nombre_cliente}, has cancelado tu cita (ID: #{cita_id}).

Esperamos verte pronto en otra ocasión.'''

def obtener_proximas_fechas_disponibles(negocio_id, dias_a_mostrar=7):
    """Obtener las próximas fechas donde el negocio está activo - VERSIÓN MEJORADA PARA POSTGRESQL"""
    fechas_disponibles = []
    fecha_actual = datetime.now()
    
    print(f"🔧 [DEBUG] OBTENER_FECHAS_DISPONIBLES - Negocio: {negocio_id}")
    
    for i in range(dias_a_mostrar):
        fecha = fecha_actual + timedelta(days=i)
        fecha_str = fecha.strftime('%Y-%m-%d')
        
        # ✅ VERIFICAR SI EL DÍA ESTÁ ACTIVO (con la nueva conversión)
        horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha_str)
        
        print(f"🔧 [DEBUG] Fecha {fecha_str}: activo={horarios_dia.get('activo')}")
        
        # ✅ CORRECCIÓN: Solo agregar si el día está activo
        if horarios_dia and horarios_dia['activo']:
            # ✅ CORRECCIÓN MEJORADA: Para HOY, verificar horarios futuros con margen
            if i == 0:  # Es hoy
                # Verificar si hay horarios disponibles para hoy con margen mínimo
                if verificar_disponibilidad_basica(negocio_id, fecha_str):
                    fechas_disponibles.append({
                        'fecha': fecha_str,  # YA en formato YYYY-MM-DD
                        'mostrar': "Hoy",
                        'fecha_original': fecha_str  # Mantener referencia
                    })
                    print(f"🔧 [DEBUG] ✅ Hoy agregado - Hay horarios disponibles con margen")
                else:
                    print(f"🔧 [DEBUG] ❌ Hoy NO agregado - No hay horarios disponibles con margen mínimo")
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
                    'fecha': fecha_str,  # YA en formato YYYY-MM-DD
                    'mostrar': fecha_formateada,
                    'fecha_original': fecha_str  # Mantener referencia
                })
                print(f"🔧 [DEBUG] ✅ Fecha {fecha_str} agregada como disponible")
        else:
            print(f"🔧 [DEBUG] ❌ Fecha {fecha_str} NO disponible (activo=False o no configurado)")
    
    print(f"🔧 [DEBUG] Total fechas disponibles: {len(fechas_disponibles)}")
    return fechas_disponibles

def generar_horarios_disponibles_actualizado(negocio_id, profesional_id, fecha, servicio_id):
    """Generar horarios disponibles considerando la configuración por días - VERSIÓN MEJORADA PARA POSTGRESQL"""
    print(f"🔍 Generando horarios para negocio {negocio_id}, profesional {profesional_id}, fecha {fecha}")
    
    # ✅ VERIFICAR SI EL DÍA ESTÁ ACTIVO
    horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha)
    
    if not horarios_dia or not horarios_dia['activo']:
        print(f"❌ Día no activo para la fecha {fecha}")
        return []  # Día no activo, no hay horarios disponibles
    
    print(f"✅ Día activo. Horario: {horarios_dia['hora_inicio']} - {horarios_dia['hora_fin']}")
    
    # ✅ CORRECCIÓN: Si es hoy, considerar margen mínimo de anticipación
    fecha_actual = datetime.now()
    fecha_cita = datetime.strptime(fecha, '%Y-%m-%d')
    es_hoy = fecha_cita.date() == fecha_actual.date()
    
    # Obtener citas ya agendadas
    citas_ocupadas = db.obtener_citas_dia(negocio_id, profesional_id, fecha)
    print(f"📅 Citas ocupadas: {len(citas_ocupadas)}")
    
    # Obtener duración del servicio
    duracion_servicio = db.obtener_duracion_servicio(negocio_id, servicio_id)
    if not duracion_servicio:
        print(f"❌ No se pudo obtener duración del servicio {servicio_id}")
        return []
    
    print(f"⏱️ Duración servicio: {duracion_servicio} minutos")
    
    # Generar horarios disponibles
    horarios = []
    hora_actual = datetime.strptime(horarios_dia['hora_inicio'], '%H:%M')
    hora_fin = datetime.strptime(horarios_dia['hora_fin'], '%H:%M')
    
    while hora_actual < hora_fin:
        hora_str = hora_actual.strftime('%H:%M')
        
        # ✅ CORRECCIÓN MEJORADA: Si es hoy, aplicar margen mínimo de 1 hora
        if es_hoy:
            # Combinar fecha actual con hora del horario
            hora_actual_completa = datetime.combine(fecha_actual.date(), hora_actual.time())
            
            # Calcular tiempo hasta el horario
            tiempo_hasta_horario = hora_actual_completa - fecha_actual
            
            # ✅ MARGEN MÍNIMO: 60 minutos (1 hora) de anticipación
            margen_minimo_minutos = 60
            
            # Si el horario es muy pronto (menos de 1 hora), omitirlo
            if tiempo_hasta_horario.total_seconds() < (margen_minimo_minutos * 60):
                print(f"⏰ Horario {hora_str} omitido (faltan {int(tiempo_hasta_horario.total_seconds()/60)} minutos, mínimo {margen_minimo_minutos} minutos requeridos)")
                hora_actual += timedelta(minutes=30)
                continue
        
        # Verificar si no es horario de almuerzo
        if not es_horario_almuerzo(hora_actual, horarios_dia):
            # Verificar disponibilidad
            if esta_disponible(hora_actual, duracion_servicio, citas_ocupadas, horarios_dia):
                horarios.append(hora_str)
                print(f"✅ Horario disponible: {hora_str}")
        
        hora_actual += timedelta(minutes=30)
    
    print(f"🎯 Total horarios disponibles: {len(horarios)}")
    return horarios

def verificar_disponibilidad_basica(negocio_id, fecha):
    """Verificación rápida de disponibilidad para una fecha (sin profesional específico) - VERSIÓN MEJORADA"""
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
                
                # ✅ MARGEN MÍNIMO: 60 minutos (1 hora)
                if hora_actual_completa >= (fecha_actual + timedelta(minutes=60)):
                    return True  # Hay al menos un horario futuro con margen suficiente
                
                hora_actual += timedelta(minutes=30)
            return False  # No hay horarios futuros con margen suficiente para hoy
        
        return True  # Para días futuros, solo con que el día esté activo es suficiente
        
    except Exception as e:
        print(f"❌ Error en verificación básica: {e}")
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
        print(f"❌ Error verificando horario almuerzo: {e}")
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
        print(f"❌ Error verificando horario cierre: {e}")
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
            print(f"❌ Error verificando cita ocupada: {e}")
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
        print(f"❌ Error verificando solapamiento almuerzo: {e}")
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
# FUNCIONES PARA ENVÍO DE CORREO/SMS (REEMPLAZAN TWILIO)
# =============================================================================

def enviar_correo_confirmacion(cita, cliente_email):
    """Enviar confirmación de cita por correo electrónico"""
    # TODO: Implementar lógica de envío de correo
    # Usar smtplib o servicio como SendGrid
    print(f"📧 [SIMULADO] Correo enviado a {cliente_email} para cita #{cita.get('id')}")
    return True

def enviar_sms_confirmacion(numero_telefono, mensaje):
    """Enviar SMS de confirmación"""
    # TODO: Implementar lógica de envío de SMS
    # Usar Twilio SMS (más barato que WhatsApp) u otro servicio
    print(f"📱 [SIMULADO] SMS enviado a {numero_telefono}: {mensaje[:50]}...")
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
        print(f"❌ Error notificando cita: {e}")
        return False

# =============================================================================
# FUNCIONES PARA RECORDATORIOS (MIGRADAS DESDE WHATSAPP_HANDLER)
# =============================================================================

def enviar_recordatorio_24h(cita):
    """Enviar recordatorio 24 horas antes de la cita - VERSIÓN PARA WEB CHAT"""
    try:
        # Esta función ahora debe enviar correo o SMS, no WhatsApp
        print(f"🔔 [WEB CHAT] Recordatorio 24h para cita #{cita.get('id')}")
        print(f"   Cliente: {cita.get('cliente_nombre')}")
        print(f"   Fecha: {cita.get('fecha')} {cita.get('hora')}")
        
        # TODO: Implementar envío de correo/SMS aquí
        # Por ahora solo registramos en consola
        return True
        
    except Exception as e:
        print(f"❌ Error enviando recordatorio 24h: {e}")
        return False

def enviar_recordatorio_1h(cita):
    """Enviar recordatorio 1 hora antes de la cita - VERSIÓN PARA WEB CHAT"""
    try:
        print(f"🔔 [WEB CHAT] Recordatorio 1h para cita #{cita.get('id')}")
        print(f"   Cliente: {cita.get('cliente_nombre')}")
        print(f"   Hora: {cita.get('hora')} (hoy)")
        
        # TODO: Implementar envío de correo/SMS aquí
        # Por ahora solo registramos en consola
        return True
        
    except Exception as e:
        print(f"❌ Error enviando recordatorio 1h: {e}")
        return False