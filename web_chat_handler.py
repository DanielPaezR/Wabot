"""
Manejador de chat web para agendamiento de citas
Versión convertida desde whatsapp_handler.py sin Twilio
"""

from flask import Blueprint
from datetime import datetime, timedelta
import database as db
import json
import os
import pytz
from dotenv import load_dotenv
from database import obtener_servicio_personalizado_cliente

load_dotenv()

tz_colombia = pytz.timezone('America/Bogota')

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
            'fecha_actual': datetime.now(tz_colombia).strftime('%d/%m/%Y'),
            'hora_actual': datetime.now(tz_colombia).strftime('%H:%M')
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
        elif paso_actual == 'solicitando_telefono_inicial':
            opciones_extra = None  # No hay opciones para este paso
        elif paso_actual == 'solicitando_nombre':
            opciones_extra = None  # No hay opciones para este paso
        elif paso_actual == 'seleccionando_servicio_personalizado':  # ✅ NUEVO CASO
            opciones_extra = [
                {'value': '1', 'text': 'Seleccionar mi servicio personalizado'},
                {'value': '2', 'text': 'Ver todos los servicios'}
            ]

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
# LÓGICA PRINCIPAL DE MENSAJES (MODIFICADA PARA NUEVO FLUJO)
# =============================================================================

def procesar_mensaje(mensaje, numero, negocio_id):
    """Procesar mensajes usando el sistema de plantillas - CON NUEVO FLUJO"""
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
        
        # Mostrar saludo inicial (pedirá teléfono)
        return saludo_inicial(numero, negocio_id)
    
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
    
    # Si el usuario envía un número directamente sin haber iniciado
    if mensaje in ['1', '2', '3', '4']:
        print(f"🔧 [DEBUG] Opción de menú seleccionada directamente: {mensaje}")
        # Primero pedir teléfono
        return saludo_inicial(numero, negocio_id)
    
    # Mensaje no reconocido - mostrar saludo inicial
    print(f"🔧 [DEBUG] Mensaje no reconocido - Mostrando saludo inicial")
    return saludo_inicial(numero, negocio_id)

def procesar_opcion_menu(numero, opcion, negocio_id):
    """Procesar opción del menú principal - SIN CAMBIOS"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if opcion == '1':
        print(f"🔧 [DEBUG] Comando '1' detectado - Mostrando profesionales")
        return mostrar_profesionales(numero, negocio_id)
    elif opcion == '2':
        print(f"🔧 [DEBUG] Comando '2' detectado - Mostrando citas")
        return mostrar_mis_citas(numero, negocio_id)
    elif opcion == '3':
        print(f"🔧 [DEBUG] Comando '3' detectado - Cancelando reserva")
        return mostrar_citas_para_cancelar(numero, negocio_id)
    elif opcion == '4':
        print(f"🔧 [DEBUG] Comando '4' detectado - Mostrando ayuda")
        return mostrar_ayuda(negocio_id)

# =============================================================================
# FUNCIONES PARA GENERAR OPCIONES EN EL CHAT WEB - SIN CAMBIOS
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
    """Generar opciones de profesionales para botones del chat web"""
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
    """Generar opciones de servicios para botones del chat web - ACTUALIZADA"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if clave_conversacion not in conversaciones_activas:
        return None
    
    estado_actual = conversaciones_activas[clave_conversacion].get('estado', '')
    print(f"🔍 [OPCIONES_SERVICIOS] Estado actual: {estado_actual}")
    
    # Si estamos mostrando la lista de servicios
    if estado_actual == 'mostrando_lista_servicios':
        print(f"📋 [OPCIONES_SERVICIOS] Generando opciones para lista completa")
        
        servicios = conversaciones_activas[clave_conversacion].get('servicios', [])
        opciones = []
        
        for i, servicio in enumerate(servicios, 3):  # Empieza en 3
            precio_formateado = f"${float(servicio['precio']):,.0f}"
            texto = f"{servicio['nombre']} - {precio_formateado} ({servicio['duracion']} min)"
            
            if len(texto) > 50:
                texto = texto[:47] + "..."
            
            opciones.append({
                'value': str(i),
                'text': texto
            })
        
        return opciones
    
    # Si estamos en selección normal con servicio personalizado
    tiene_personalizado = conversaciones_activas[clave_conversacion].get('tiene_personalizado', False)
    mostrar_todos = conversaciones_activas[clave_conversacion].get('mostrar_todos_servicios', False)
    
    if tiene_personalizado and not mostrar_todos:
        print(f"🎯 [OPCIONES_SERVICIOS] Generando 2 opciones para servicio personalizado")
        return [
            {'value': '1', 'text': 'Seleccionar mi servicio personalizado 🌟'},
            {'value': '2', 'text': 'Ver todos los servicios disponibles'}
        ]
    
    # Para flujo normal sin personalizado
    if 'servicios' not in conversaciones_activas[clave_conversacion]:
        return None
    
    servicios = conversaciones_activas[clave_conversacion]['servicios']
    opciones = []
    
    print(f"📋 [OPCIONES_SERVICIOS] Generando opciones para servicios normales")
    
    for i, servicio in enumerate(servicios, 1):
        precio_formateado = f"${float(servicio['precio']):,.0f}"
        texto = f"{servicio['nombre']} - {precio_formateado} ({servicio['duracion']} min)"
        
        if len(texto) > 50:
            texto = texto[:47] + "..."
        
        opciones.append({
            'value': str(i),
            'text': texto
        })
    
    return opciones

def generar_opciones_fechas(numero, negocio_id):
    """Generar opciones de fechas para botones del chat web"""
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
    """Generar opciones de horarios para botones del chat web"""
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
    
    return opciones

def generar_opciones_confirmacion():
    """Generar opciones de confirmación para botones del chat web"""
    opciones = [
        {'value': '1', 'text': '✅ Confirmar cita'},
        {'value': '2', 'text': '❌ Cancelar agendamiento'}
    ]
    return opciones

# =============================================================================
# FUNCIONES DE MENSAJES MODIFICADAS PARA NUEVO FLUJO
# =============================================================================

def saludo_inicial(numero, negocio_id):
    """Saludo inicial - NUEVO FLUJO: Primero pedir teléfono"""
    try:
        # Crear conversación activa en estado de solicitar teléfono inicial
        clave_conversacion = f"{numero}_{negocio_id}"
        
        # Limpiar conversación si existe
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        
        # Crear nueva conversación para pedir teléfono
        conversaciones_activas[clave_conversacion] = {
            'estado': 'solicitando_telefono_inicial',
            'timestamp': datetime.now(tz_colombia),
            'session_id': numero
        }
        
        # Obtener información del negocio para personalizar mensaje
        negocio = db.obtener_negocio_por_id(negocio_id)
        nombre_negocio = negocio['nombre'] if negocio else "nuestro negocio"
        
        return f"""¡Hola! 👋 Soy tu asistente virtual de {nombre_negocio}.

📱 **Para identificarte en nuestro sistema, necesitamos tu número de teléfono.**

Tu número de teléfono se usará como identificador durante toda la conversación para:
• Identificarte en futuras consultas
• Mantener el historial de tus citas
• Enviarte recordatorios importantes

**Por favor, ingresa tu número de 10 dígitos (debe empezar con 3, ejemplo: 3101234567):**"""
            
    except Exception as e:
        print(f"❌ Error en saludo_inicial: {e}")
        import traceback
        traceback.print_exc()
        
        # En caso de error, pedir teléfono de forma simple
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion] = {
            'estado': 'solicitando_telefono_inicial',
            'timestamp': datetime.now(tz_colombia)
        }
        return "¡Hola! 👋 Para comenzar, necesitamos tu número de teléfono como identificador.\n\nPor favor, ingresa tu número de 10 dígitos (debe empezar con 3, ej: 3101234567):"

def procesar_telefono_inicial(numero, mensaje, negocio_id):
    """Procesar teléfono ingresado al inicio - MEJORADO PARA RECONOCER CLIENTES"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    # Validar teléfono
    telefono = mensaje.strip()
    
    if not telefono.isdigit() or len(telefono) != 10 or not telefono.startswith('3'):
        return "❌ Número inválido. Por favor ingresa 10 dígitos (debe empezar con 3, ejemplo: 3101234567):"
    
    print(f"🔧 [DEBUG] Teléfono válido ingresado: {telefono}")
    
    # ✅ MEJORADO: Buscar cliente en múltiples fuentes
    nombre_cliente = buscar_cliente_existente(telefono, negocio_id)
    
    # Guardar teléfono en la conversación
    conversaciones_activas[clave_conversacion]['telefono_cliente'] = telefono
    
    if nombre_cliente:
        # Cliente existente reconocido
        nombre_cliente = str(nombre_cliente).strip().title()
        print(f"🔧 [DEBUG] Cliente existente encontrado: {nombre_cliente}")
        
        # Guardar nombre en conversación
        conversaciones_activas[clave_conversacion]['cliente_nombre'] = nombre_cliente
        
        # Ir directamente al menú principal
        conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
        
        return f"¡Hola {nombre_cliente}! 👋\n\nHe identificado tu número en nuestro sistema.\n\n¿En qué puedo ayudarte hoy?"
    else:
        # Cliente nuevo - pedir nombre
        print(f"🔧 [DEBUG] Cliente nuevo - pedir nombre")
        
        conversaciones_activas[clave_conversacion]['estado'] = 'solicitando_nombre'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
        
        return f"✅ Número registrado exitosamente.\n\n📝 **Ahora necesitamos tu nombre para completar tu registro.**\n\nPor favor, ingresa tu nombre completo:"

def buscar_cliente_existente(telefono, negocio_id):
    """Buscar cliente existente en múltiples fuentes"""
    nombre_cliente = None
    
    # Método 1: Buscar en tabla clientes
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if db.is_postgresql():
            cursor.execute('''
                SELECT nombre FROM clientes 
                WHERE telefono = %s AND negocio_id = %s
                ORDER BY updated_at DESC LIMIT 1
            ''', (telefono, negocio_id))
        else:
            cursor.execute('''
                SELECT nombre FROM clientes 
                WHERE telefono = ? AND negocio_id = ?
                ORDER BY updated_at DESC LIMIT 1
            ''', (telefono, negocio_id))
        
        resultado = cursor.fetchone()
        conn.close()
        
        if resultado:
            if isinstance(resultado, dict):
                nombre_cliente = resultado.get('nombre')
            else:
                nombre_cliente = resultado[0] if resultado else None
            
            if nombre_cliente and len(str(nombre_cliente).strip()) >= 2:
                print(f"✅ [DEBUG] Cliente encontrado en tabla clientes: {nombre_cliente}")
                return nombre_cliente
    
    except Exception as e:
        print(f"⚠️ [DEBUG] Error buscando en tabla clientes: {e}")
    
    # Método 2: Buscar en citas anteriores
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if db.is_postgresql():
            cursor.execute('''
                SELECT cliente_nombre FROM citas 
                WHERE cliente_telefono = %s AND negocio_id = %s
                ORDER BY fecha DESC, hora DESC LIMIT 1
            ''', (telefono, negocio_id))
        else:
            cursor.execute('''
                SELECT cliente_nombre FROM citas 
                WHERE cliente_telefono = ? AND negocio_id = ?
                ORDER BY fecha DESC, hora DESC LIMIT 1
            ''', (telefono, negocio_id))
        
        resultado = cursor.fetchone()
        conn.close()
        
        if resultado:
            if isinstance(resultado, dict):
                nombre_cliente = resultado.get('cliente_nombre')
            else:
                nombre_cliente = resultado[0] if resultado else None
            
            if nombre_cliente and len(str(nombre_cliente).strip()) >= 2:
                print(f"✅ [DEBUG] Cliente encontrado en historial de citas: {nombre_cliente}")
                return nombre_cliente
    
    except Exception as e:
        print(f"⚠️ [DEBUG] Error buscando en tabla citas: {e}")
    
    # Método 3: Usar la función original
    try:
        nombre_cliente = db.obtener_nombre_cliente(telefono, negocio_id)
        if nombre_cliente and len(str(nombre_cliente).strip()) >= 2:
            print(f"✅ [DEBUG] Cliente encontrado mediante db.obtener_nombre_cliente: {nombre_cliente}")
            return nombre_cliente
    except Exception as e:
        print(f"⚠️ [DEBUG] Error con db.obtener_nombre_cliente: {e}")
    
    print(f"🔍 [DEBUG] No se encontró cliente con teléfono {telefono}")
    return None


def procesar_nombre_cliente(numero, mensaje, negocio_id):
    """Procesar nombre del cliente nuevo - NUEVO FLUJO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    nombre = mensaje.strip()
    if len(nombre) < 2:
        return "Por favor, ingresa un nombre válido:"
    
    print(f"🔧 [DEBUG] Procesando nombre '{nombre}' para {numero}")
    
    # Validar que tenemos teléfono
    if 'telefono_cliente' not in conversaciones_activas[clave_conversacion]:
        # Si no hay teléfono, volver a pedirlo
        conversaciones_activas[clave_conversacion]['estado'] = 'solicitando_telefono_inicial'
        return "❌ Error: No se encontró tu número de teléfono. Por favor, ingrésalo nuevamente:"
    
    # Guardar nombre capitalizado
    nombre_cliente = nombre.strip().title()
    
    # Guardar nombre en conversación
    conversaciones_activas[clave_conversacion]['cliente_nombre'] = nombre_cliente
    
    # Intentar guardar cliente en BD
    try:
        telefono = conversaciones_activas[clave_conversacion]['telefono_cliente']
        fecha_actual = datetime.now(tz_colombia).strftime('%Y-%m-%d %H:%M:%S')
        
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar si ya existe
        cursor.execute('''
            SELECT id FROM clientes WHERE telefono = %s AND negocio_id = %s
        ''', (telefono, negocio_id))
        
        cliente_existente = cursor.fetchone()
        
        if not cliente_existente:
            # Insertar nuevo cliente
            cursor.execute('''
                INSERT INTO clientes (negocio_id, telefono, nombre, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
            ''', (negocio_id, telefono, nombre_cliente, fecha_actual, fecha_actual))
            print(f"✅ [DEBUG] Nuevo cliente creado en BD: Teléfono={telefono}, Nombre={nombre_cliente}")
        else:
            # Actualizar nombre si es necesario
            cursor.execute('''
                UPDATE clientes 
                SET nombre = %s, updated_at = %s
                WHERE telefono = %s AND negocio_id = %s
            ''', (nombre_cliente, fecha_actual, telefono, negocio_id))
            print(f"✅ [DEBUG] Nombre actualizado en BD: {nombre_cliente}")
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ [DEBUG] Error guardando cliente en BD: {e}")
        # Continuar aunque falle
    
    # Ir al menú principal
    conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
    
    print(f"✅ [DEBUG] Nombre '{nombre_cliente}' guardado y listo para menú principal")
    
    return f"¡Perfecto {nombre_cliente}! ✅\n\nTu registro se ha completado exitosamente.\n\n¿En qué puedo ayudarte hoy?"

# =============================================================================
# EL RESTO DE LAS FUNCIONES SE MANTIENEN IGUAL (PERO ACTUALIZADAS PARA NUEVO FLUJO)
# =============================================================================

def mostrar_profesionales(numero, negocio_id):
    """Mostrar lista de profesionales disponibles - SIN CAMBIOS"""
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
        
        clave_conversacion = f"{numero}_{negocio_id}"
        
        if clave_conversacion not in conversaciones_activas:
            conversaciones_activas[clave_conversacion] = {}
        
        conversaciones_activas[clave_conversacion].update({
            'estado': 'seleccionando_profesional',
            'profesionales': profesionales,
            'timestamp': datetime.now(tz_colombia)
        })
        
        print(f"✅ [DEBUG] Datos preservados en mostrar_profesionales:")
        for key, value in conversaciones_activas[clave_conversacion].items():
            if key not in ['estado', 'profesionales', 'timestamp']:
                print(f"   - {key}: {value}")
        
        return "👨‍💼 **Selecciona un profesional:**"
        
    except Exception as e:
        print(f"❌ Error en mostrar_profesionales: {e}")
        return "❌ Error al cargar profesionales."

def mostrar_servicios(numero, profesional_nombre, negocio_id):
    """Mostrar servicios disponibles - CON MANEJO DE ESTADOS"""
    try:
        print(f"🔍 [SERVICIOS] === INICIO mostrar_servicios ===")
        
        clave_conversacion = f"{numero}_{negocio_id}"
        
        # Verificar estado actual
        estado_actual = conversaciones_activas[clave_conversacion].get('estado', 'desconocido')
        print(f"🔍 [SERVICIOS] Estado actual: {estado_actual}")
        
        # Si ya estamos en "mostrando_lista_servicios", solo mostrar la lista
        if estado_actual == 'mostrando_lista_servicios':
            print(f"📋 [SERVICIOS] Estado 'mostrando_lista_servicios' - Generando lista completa")
            
            # Obtener servicios ya guardados
            servicios = conversaciones_activas[clave_conversacion].get('servicios', [])
            
            if not servicios:
                return "❌ No hay servicios disponibles en este momento."
            
            # Construir mensaje de lista completa
            mensaje = f"📋 **Todos los servicios con {profesional_nombre}:**\n\n"
            
            for i, servicio in enumerate(servicios, 3):  # Empieza en 3 porque 1 y 2 ya se usaron
                mensaje += f"*{i}* - *{servicio['nombre']}*\n"
                mensaje += f"   ⏱️ {servicio['duracion']} min | 💵 ${float(servicio['precio']):,.0f}\n"
                if servicio.get('descripcion'):
                    mensaje += f"   📝 {servicio['descripcion']}\n"
                mensaje += "\n"
            
            mensaje += "🔢 *Responde con el número del servicio que deseas (opciones 3 en adelante)*"
            
            return mensaje
        
        # Si no, continuar con el flujo normal...
        print(f"🔍 [SERVICIOS] Estado normal - Iniciando búsqueda de servicios")
        
        # ... (el resto de tu código actual para buscar servicios y cliente) ...
        # Solo necesitamos la parte de inicialización:
        
        # Obtener servicios normales del negocio
        servicios = db.obtener_servicios(negocio_id)
        
        # Filtrar servicios activos
        servicios_activos = []
        for servicio in servicios:
            if servicio.get('activo', True):
                servicios_activos.append(servicio)
        
        servicios = servicios_activos
        
        # Guardar en conversación activa
        if clave_conversacion not in conversaciones_activas:
            conversaciones_activas[clave_conversacion] = {}
            
        conversaciones_activas[clave_conversacion]['servicios'] = servicios
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_servicio'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
        
        # Verificar si el cliente tiene servicio personalizado
        telefono_cliente = conversaciones_activas[clave_conversacion].get('telefono_cliente')
        tiene_personalizado = False
        servicio_personalizado = None
        
        if telefono_cliente:
            try:
                from database import obtener_servicio_personalizado_cliente
                servicio_personalizado = obtener_servicio_personalizado_cliente(telefono_cliente, negocio_id)
                if servicio_personalizado:
                    tiene_personalizado = True
                    conversaciones_activas[clave_conversacion]['tiene_personalizado'] = True
                    conversaciones_activas[clave_conversacion]['servicio_personalizado'] = servicio_personalizado
                    conversaciones_activas[clave_conversacion]['mostrar_todos_servicios'] = False
                    print(f"✅ [SERVICIOS] Cliente tiene servicio personalizado")
            except Exception as e:
                print(f"⚠️ [SERVICIOS] Error buscando servicio personalizado: {e}")
        
        # Si tiene servicio personalizado, mostrar opciones
        if tiene_personalizado and servicio_personalizado:
            print(f"🎯 [SERVICIOS] Mostrando opciones para servicio personalizado")
            
            mensaje = f"🌟 *SERVICIO PERSONALIZADO PARA TI* 🌟\n\n"
            mensaje += f"*{servicio_personalizado['nombre_personalizado']}*\n"
            mensaje += f"⏱️ Duración: {servicio_personalizado['duracion_personalizada']} min\n"
            mensaje += f"💵 Precio: ${float(servicio_personalizado['precio_personalizado']):,.0f}\n"
            
            if servicio_personalizado.get('descripcion'):
                mensaje += f"📝 {servicio_personalizado['descripcion']}\n"
            
            mensaje += f"\n🔢 *Selecciona una opción:*\n"
            mensaje += f"*1* - Usar mi servicio personalizado 🌟\n"
            mensaje += f"*2* - Ver todos los servicios disponibles\n"
            
            return mensaje
        else:
            # Si no tiene personalizado, mostrar lista normal
            print(f"📋 [SERVICIOS] Mostrando lista normal (sin personalizado)")
            
            if not servicios:
                return "❌ No hay servicios disponibles en este momento."
            
            mensaje = f"📋 **Servicios con {profesional_nombre}:**\n\n"
            
            for i, servicio in enumerate(servicios, 1):
                mensaje += f"*{i}* - *{servicio['nombre']}*\n"
                mensaje += f"   ⏱️ {servicio['duracion']} min | 💵 ${float(servicio['precio']):,.0f}\n"
                if servicio.get('descripcion'):
                    mensaje += f"   📝 {servicio['descripcion']}\n"
                mensaje += "\n"
            
            mensaje += "🔢 *Responde con el número del servicio que deseas*"
            
            return mensaje
        
    except Exception as e:
        print(f"❌ Error en mostrar_servicios: {e}")
        import traceback
        traceback.print_exc()
        return "❌ Error al cargar servicios."
    
def procesar_seleccion_servicio(numero, mensaje, negocio_id):
    """Procesar selección de servicio - CON ESTADO INTERMEDIO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔍 [SELECCION_SERVICIO] === INICIO ===")
    print(f"🔍 [SELECCION_SERVICIO] Mensaje: '{mensaje}'")
    print(f"🔍 [SELECCION_SERVICIO] Estado actual: {conversaciones_activas[clave_conversacion].get('estado', 'desconocido')}")
    print(f"🔍 [SELECCION_SERVICIO] Tiene personalizado: {conversaciones_activas[clave_conversacion].get('tiene_personalizado', False)}")
    print(f"🔍 [SELECCION_SERVICIO] Mostrar todos: {conversaciones_activas[clave_conversacion].get('mostrar_todos_servicios', False)}")
    
    # Manejar el comando "0" para volver al menú principal
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
            conversaciones_activas[clave_conversacion]['mostrar_todos_servicios'] = False
        return "Volviendo al menú principal..."
    
    tiene_personalizado = conversaciones_activas[clave_conversacion].get('tiene_personalizado', False)
    mostrar_todos = conversaciones_activas[clave_conversacion].get('mostrar_todos_servicios', False)
    
    # PRIMERO: Verificar si estamos en el estado especial "mostrando_lista_servicios"
    if conversaciones_activas[clave_conversacion].get('estado') == 'mostrando_lista_servicios':
        print(f"📋 [SELECCION_SERVICIO] Estado: 'mostrando_lista_servicios' - Procesando selección de servicio normal")
        
        # Aquí el cliente está seleccionando un servicio de la lista completa
        servicios = conversaciones_activas[clave_conversacion]['servicios']
        
        try:
            idx_servicio = int(mensaje)
        except ValueError:
            return "❌ Por favor, ingresa un número válido."
        
        # Si tiene personalizado, los índices empiezan en 3
        if tiene_personalizado:
            if idx_servicio < 3:
                return "❌ Número inválido. Por favor, selecciona un servicio de la lista (opciones 3 en adelante)."
            idx_servicio_real = idx_servicio - 2
        else:
            idx_servicio_real = idx_servicio
        
        if idx_servicio_real < 1 or idx_servicio_real > len(servicios):
            return f"❌ Número inválido. Por favor, elige entre 1 y {len(servicios)}"
        
        # Guardar servicio seleccionado
        servicio_index = idx_servicio_real - 1
        servicio_seleccionado = servicios[servicio_index]
        
        print(f"✅ [SELECCION_SERVICIO] Servicio seleccionado: {servicio_seleccionado['nombre']}")
        
        conversaciones_activas[clave_conversacion]['servicio_id'] = servicio_seleccionado['id']
        conversaciones_activas[clave_conversacion]['servicio_nombre'] = servicio_seleccionado['nombre']
        conversaciones_activas[clave_conversacion]['servicio_precio'] = servicio_seleccionado['precio']
        conversaciones_activas[clave_conversacion]['servicio_duracion'] = servicio_seleccionado['duracion']
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
        
        return mostrar_fechas_disponibles(numero, negocio_id)
    
    # SEGUNDO: Si tiene servicio personalizado y NO ha mostrado la lista todavía
    if tiene_personalizado and not mostrar_todos:
        print(f"🎯 [SELECCION_SERVICIO] Estado: 'seleccionando_servicio' (con personalizado) - Procesando opción inicial")
        
        if mensaje == '1':
            # Cliente eligió su servicio personalizado
            print(f"✅ [SELECCION_SERVICIO] Opción 1 - Usar servicio personalizado")
            
            servicio_personalizado = conversaciones_activas[clave_conversacion]['servicio_personalizado']
            
            # Guardar el servicio personalizado como seleccionado
            conversaciones_activas[clave_conversacion]['servicio_id'] = servicio_personalizado['servicio_base_id']
            conversaciones_activas[clave_conversacion]['servicio_nombre'] = servicio_personalizado['nombre_personalizado']
            conversaciones_activas[clave_conversacion]['servicio_precio'] = servicio_personalizado['precio_personalizado']
            conversaciones_activas[clave_conversacion]['servicio_duracion'] = servicio_personalizado['duracion_personalizada']
            conversaciones_activas[clave_conversacion]['mostrar_todos_servicios'] = True
            conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
            conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
            
            return mostrar_fechas_disponibles(numero, negocio_id)
        
        elif mensaje == '2':
            # Cliente quiere ver todos los servicios
            print(f"📋 [SELECCION_SERVICIO] Opción 2 - Ver todos los servicios")
            
            # IMPORTANTE: Cambiamos a estado especial y marcamos que ya pasó por opciones
            conversaciones_activas[clave_conversacion]['mostrar_todos_servicios'] = True
            conversaciones_activas[clave_conversacion]['estado'] = 'mostrando_lista_servicios'
            conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
            
            # Llamar a mostrar_servicios para que genere la lista completa
            profesional_nombre = conversaciones_activas[clave_conversacion].get('profesional_nombre', 'Profesional')
            return mostrar_servicios(numero, profesional_nombre, negocio_id)
        
        else:
            return "❌ Opción no válida. Responde con *1* para tu servicio personalizado o *2* para ver todos los servicios."
    
    # TERCERO: Si no tiene personalizado (flujo normal)
    print(f"📋 [SELECCION_SERVICIO] Estado: 'seleccionando_servicio' (sin personalizado) - Procesando selección normal")
    
    if 'servicios' not in conversaciones_activas[clave_conversacion]:
        return "❌ Sesión expirada. Por favor, inicia nuevamente con *1*"
    
    servicios = conversaciones_activas[clave_conversacion]['servicios']
    
    try:
        idx_servicio = int(mensaje)
    except ValueError:
        return "❌ Por favor, ingresa un número válido."
    
    if idx_servicio < 1 or idx_servicio > len(servicios):
        return f"❌ Número inválido. Por favor, elige entre 1 y {len(servicios)}"
    
    # Guardar servicio seleccionado
    servicio_index = idx_servicio - 1
    servicio_seleccionado = servicios[servicio_index]
    
    print(f"✅ [SELECCION_SERVICIO] Servicio seleccionado: {servicio_seleccionado['nombre']}")
    
    conversaciones_activas[clave_conversacion]['servicio_id'] = servicio_seleccionado['id']
    conversaciones_activas[clave_conversacion]['servicio_nombre'] = servicio_seleccionado['nombre']
    conversaciones_activas[clave_conversacion]['servicio_precio'] = servicio_seleccionado['precio']
    conversaciones_activas[clave_conversacion]['servicio_duracion'] = servicio_seleccionado['duracion']
    conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
    
    return mostrar_fechas_disponibles(numero, negocio_id)
    
def mostrar_servicios_disponibles(numero_cliente, negocio_id):
    conn = db(negocio_id)
    cursor = conn.cursor()
    
    # PRIMERO: Verificar si tiene servicio personalizado
    cursor.execute('''
        SELECT sp.*, 
               json_agg(json_build_object(
                   'id', s.id,
                   'nombre', s.nombre,
                   'duracion', s.duracion,
                   'precio', s.precio,
                   'incluido_por_defecto', sac.incluido_por_defecto
               )) as servicios_adicionales
        FROM servicios_personalizados sp
        LEFT JOIN servicios_adicionales_cliente sac ON sp.id = sac.servicio_personalizado_id
        LEFT JOIN servicios s ON sac.servicio_id = s.id
        WHERE sp.cliente_id = (
            SELECT id FROM clientes WHERE telefono = %s AND negocio_id = %s
        ) AND sp.activo = true
        GROUP BY sp.id
    ''', (numero_cliente, negocio_id))
    
    servicio_personalizado = cursor.fetchone()
    
    if servicio_personalizado:
        # Construir mensaje con servicio personalizado primero
        mensaje = f"🌟 *SERVICIO PERSONALIZADO PARA TI* 🌟\n\n"
        mensaje += f"*{servicio_personalizado['nombre_personalizado']}*\n"
        mensaje += f"⏱️ Duración: {servicio_personalizado['duracion_personalizada']} min\n"
        mensaje += f"💵 Precio: ${servicio_personalizado['precio_personalizado']:,.0f}\n"
        
        if servicio_personalizado['servicios_adicionales']:
            mensaje += f"\n📋 *Servicios incluidos:*\n"
            for adicional in servicio_personalizado['servicios_adicionales']:
                if adicional['incluido_por_defecto']:
                    mensaje += f"✅ {adicional['nombre']}\n"
                else:
                    mensaje += f"⚪ {adicional['nombre']} (opcional)\n"
        
        mensaje += f"\n🔢 *Responde con el número:*\n"
        mensaje += f"1️⃣ - Seleccionar mi servicio personalizado\n"
        mensaje += f"2️⃣ - Ver todos los servicios disponibles\n"
        
        conn.close()
        return mensaje, 'servicio_personalizado'

def mostrar_fechas_disponibles(numero, negocio_id):
    """Mostrar fechas disponibles para agendar - SIN CAMBIOS"""
    try:
        # Obtener próximas fechas donde el negocio está activo
        fechas_disponibles = obtener_proximas_fechas_disponibles(negocio_id)
        
        if not fechas_disponibles:
            return "❌ No hay fechas disponibles en los próximos días."
        
        # Guardar en conversación activa
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion]['fechas_disponibles'] = fechas_disponibles
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
        
        return "📅 **Selecciona una fecha:**"
        
    except Exception as e:
        print(f"❌ Error en mostrar_fechas_disponibles: {e}")
        return "❌ Error al cargar fechas."

def mostrar_disponibilidad(numero, negocio_id, fecha_seleccionada=None):
    """Mostrar horarios disponibles - SIN CAMBIOS"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG] mostrar_disponibilidad - fecha_seleccionada: {fecha_seleccionada}")
    
    if not fecha_seleccionada:
        fecha_seleccionada = conversaciones_activas[clave_conversacion].get('fecha_seleccionada', datetime.now(tz_colombia).strftime('%Y-%m-%d'))
    
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
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
    
    return f"📅 **Horarios disponibles con {profesional_nombre} ({fecha_formateada}):**\n💼 Servicio: {servicio_nombre} - {precio_formateado}"

def mostrar_mis_citas(numero, negocio_id):
    """Mostrar citas del cliente - SIN CAMBIOS"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG] mostrar_mis_citas - Clave: {clave_conversacion}")
    
    # Verificar si ya tenemos teléfono
    telefono_real = None
    if clave_conversacion in conversaciones_activas:
        telefono_real = conversaciones_activas[clave_conversacion].get('telefono_cliente')
        print(f"🔧 [DEBUG] Teléfono en conversación: {telefono_real}")
    
    if not telefono_real:
        # En el nuevo flujo, siempre deberíamos tener teléfono
        return "❌ Error: No se encontró tu número de teléfono. Por favor, reinicia la conversación."
    
    print(f"🔧 [DEBUG] Buscando citas CONFIRMADAS con teléfono: {telefono_real}")
    
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ✅ Buscar citas confirmadas
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora, s.nombre as servicio, c.estado, p.nombre as profesional_nombre
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            JOIN profesionales p ON c.profesional_id = p.id
            WHERE c.cliente_telefono = %s 
            AND c.negocio_id = %s 
            AND (c.fecha)::date >= CURRENT_DATE
            AND c.estado = 'confirmado'
            ORDER BY (c.fecha)::date, c.hora
        ''', (telefono_real, negocio_id))
        
        citas_confirmadas = cursor.fetchall()
        conn.close()
        
        print(f"🔧 [DEBUG] Citas CONFIRMADAS encontradas: {len(citas_confirmadas) if citas_confirmadas else 0}")
        
        # Obtener nombre del cliente
        nombre_cliente = 'Cliente'
        if clave_conversacion in conversaciones_activas:
            nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre', 'Cliente')
        
        # Verificar si hay citas confirmadas
        if not citas_confirmadas or len(citas_confirmadas) == 0:
            return f"📋 **No tienes citas CONFIRMADAS programadas, {nombre_cliente}.**\n\nPara agendar una nueva cita, selecciona: *1*"
        
        # Construir respuesta
        respuesta = f"📋 **Tus citas CONFIRMADAS - {nombre_cliente}:**\n\n"
        
        for cita in citas_confirmadas:
            try:
                if isinstance(cita, dict):
                    id_cita = cita.get('id')
                    fecha = cita.get('fecha')
                    hora = cita.get('hora')
                    servicio = cita.get('servicio')
                    estado = cita.get('estado')
                    profesional_nombre = cita.get('profesional_nombre')
                else:
                    id_cita, fecha, hora, servicio, estado, profesional_nombre = cita
                
                # Formatear fecha
                try:
                    if isinstance(fecha, str):
                        fecha_str = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m')
                    else:
                        fecha_str = fecha.strftime('%d/%m')
                except:
                    fecha_str = str(fecha)
                
                respuesta += f"✅ *{fecha_str}* - **{hora}**\n"
                respuesta += f"   👨‍💼 **{profesional_nombre}** - {servicio}\n"
                respuesta += f"   🎫 **ID: #{id_cita}**\n\n"
                
            except Exception as e:
                print(f"⚠️ [DEBUG] Error procesando cita: {e}")
                continue
        
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
    """Mostrar citas que pueden ser canceladas - SIN CAMBIOS"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG] mostrar_citas_para_cancelar - Clave: {clave_conversacion}")
    
    # Verificar si ya tenemos teléfono
    telefono_real = None
    if clave_conversacion in conversaciones_activas:
        telefono_real = conversaciones_activas[clave_conversacion].get('telefono_cliente')
        print(f"🔧 [DEBUG] Teléfono en conversación: {telefono_real}")
    
    if not telefono_real:
        return "❌ Error: No se encontró tu número de teléfono. Por favor, reinicia la conversación."
    
    print(f"🔧 [DEBUG] Buscando citas para cancelar con teléfono: {telefono_real}")
    
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ✅ Buscar citas confirmadas
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora, p.nombre as profesional_nombre, 
                   s.nombre as servicio_nombre, c.cliente_nombre
            FROM citas c
            JOIN profesionales p ON c.profesional_id = p.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.cliente_telefono = %s 
            AND c.negocio_id = %s 
            AND (c.fecha)::date >= CURRENT_DATE 
            AND c.estado = 'confirmado'
            ORDER BY (c.fecha)::date, c.hora
        ''', (telefono_real, negocio_id))
        
        citas = cursor.fetchall()
        conn.close()
        
        print(f"🔧 [DEBUG] Citas encontradas para cancelar: {len(citas) if citas else 0}")
        
        # Verificar si no hay citas
        if not citas or len(citas) == 0:
            if clave_conversacion in conversaciones_activas:
                conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
            
            nombre_cliente = 'Cliente'
            if clave_conversacion in conversaciones_activas:
                nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre', 'Cliente')
            
            return f"❌ **No tienes citas confirmadas para cancelar, {nombre_cliente}.**\n\nPara ver tus citas, selecciona: *2*"
        
        if len(citas) == 1:
            # Solo una cita, cancelar directamente
            cita_id = citas[0][0] if isinstance(citas[0], tuple) else citas[0].get('id')
            return procesar_cancelacion_directa(numero, str(cita_id), negocio_id)
        
        # Construir lista de citas para cancelar
        nombre_cliente = 'Cliente'
        if clave_conversacion in conversaciones_activas:
            nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre', 'Cliente')
        
        respuesta = f"❌ **Citas para cancelar - {nombre_cliente}:**\n\n"
        
        citas_disponibles = {}
        
        for cita in citas:
            try:
                # Manejar diferentes tipos de datos
                if isinstance(cita, tuple):
                    id_cita, fecha, hora, profesional_nombre, servicio_nombre, nombre_cita = cita
                elif isinstance(cita, dict):
                    id_cita = cita.get('id')
                    fecha = cita.get('fecha')
                    hora = cita.get('hora')
                    profesional_nombre = cita.get('profesional_nombre')
                    servicio_nombre = cita.get('servicio_nombre')
                    nombre_cita = cita.get('cliente_nombre')
                else:
                    continue
                
                # Formatear fecha
                try:
                    if isinstance(fecha, str):
                        fecha_str = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m')
                    else:
                        fecha_str = fecha.strftime('%d/%m')
                except:
                    fecha_str = str(fecha)
                
                respuesta += f"📅 **{fecha_str}** - **{hora}**\n"
                respuesta += f"   👨‍💼 **{profesional_nombre}** - {servicio_nombre}\n"
                respuesta += f"   🎫 **ID: #{id_cita}**\n\n"
                
                # Guardar para referencia
                citas_disponibles[str(id_cita)] = (id_cita, fecha, hora, profesional_nombre, servicio_nombre)
                
            except Exception as e:
                print(f"⚠️ [DEBUG] Error procesando cita {cita}: {e}")
                continue
        
        respuesta += "**Selecciona el ID de la cita que quieres cancelar.**"
        
        # ✅ Guardar citas disponibles
        conversaciones_activas[clave_conversacion]['citas_disponibles'] = citas_disponibles
        conversaciones_activas[clave_conversacion]['estado'] = 'cancelando'
        conversaciones_activas[clave_conversacion]['telefono_cliente'] = telefono_real
        
        return respuesta
        
    except Exception as e:
        print(f"❌ Error mostrando citas para cancelar: {e}")
        import traceback
        traceback.print_exc()
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        return "❌ Error al cargar tus citas."

def mostrar_ayuda(negocio_id):
    """Mostrar mensaje de ayuda - SIN CAMBIOS"""
    return "ℹ️ **Ayuda:**\n\nPara agendar una cita, responde: *1*\nPara ver tus citas, responde: *2*\nPara cancelar una cita, responde: *3*\n\nEn cualquier momento puedes escribir *0* para volver al menú principal."

def procesar_confirmacion_cita(numero, mensaje, negocio_id):
    """Procesar confirmación de la cita - ACTUALIZADO PARA NUEVO FLUJO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG] procesar_confirmacion_cita - Clave: {clave_conversacion}, Mensaje: '{mensaje}'")
    
    # Verificar que existe la conversación
    if clave_conversacion not in conversaciones_activas:
        print(f"❌ [DEBUG] No hay conversación activa para {clave_conversacion}")
        return "❌ Sesión expirada. Por favor, inicia nuevamente."
    
    conversacion = conversaciones_activas[clave_conversacion]
    estado_actual = conversacion.get('estado', '')
    
    print(f"🔧 [DEBUG] Estado actual: {estado_actual}")
    
    # Si estamos solicitando teléfono (backup - ya no debería ocurrir en nuevo flujo)
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
        return procesar_confirmacion_directa(numero, negocio_id, conversacion)
    
    # Si no estamos solicitando teléfono, procesar opciones normales de confirmación
    if mensaje == '1':
        print(f"🔧 [DEBUG] Usuario confirmó cita con opción '1'")
        
        # ✅ EN NUEVO FLUJO: Ya tenemos el teléfono desde el inicio
        if 'telefono_cliente' not in conversacion:
            print(f"❌ [DEBUG] No hay teléfono en conversación, solicitando...")
            # Esto no debería ocurrir en el nuevo flujo, pero por seguridad
            conversacion['estado'] = 'solicitando_telefono'
            conversacion['timestamp'] = datetime.now(tz_colombia)
            
            return "📱 **Para enviarte recordatorios de tu cita, necesitamos tu número de teléfono.**\n\nPor favor, ingresa tu número de 10 dígitos (debe empezar con 3, ej: 3101234567):"
        
        # ✅ Ya tenemos teléfono, proceder a crear la cita
        return procesar_confirmacion_directa(numero, negocio_id, conversacion)
    
    elif mensaje == '2':
        print(f"🔧 [DEBUG] Usuario canceló agendamiento")
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return "❌ Agendamiento cancelado."
    
    else:
        print(f"❌ [DEBUG] Opción inválida recibida: {mensaje}")
        return "❌ Opción no válida. Responde con *1* para confirmar o *2* para cancelar."

def procesar_confirmacion_directa(numero, negocio_id, conversacion):
    """Procesar confirmación de cita - VERSIÓN SIMPLIFICADA SIN SERVICIOS ADICIONALES"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    try:
        print(f"🔧 [DEBUG] Creando cita con datos existentes...")
        
        # Verificar que tenemos todos los datos necesarios
        datos_requeridos = ['hora_seleccionada', 'fecha_seleccionada', 'profesional_id', 
                          'servicio_id', 'profesional_nombre', 'servicio_nombre', 'servicio_precio', 'telefono_cliente']
        
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
        telefono = conversacion['telefono_cliente']
        
        # Obtener duración del servicio
        duracion = db.obtener_duracion_servicio(negocio_id, servicio_id)
        print(f"Duración servicio: {duracion} minutos")
        
        # Verificar disponibilidad
        citas = db.obtener_citas_dia(negocio_id, profesional_id, fecha)
        
        # Verificar si ya existe una cita a esa hora
        cita_existente = None
        for cita in citas:
            if cita.get('hora') == hora and cita.get('estado') == 'confirmado':
                cita_existente = cita
                break
        
        if cita_existente:
            print(f"🚨 ¡YA EXISTE UNA CITA CONFIRMADA A ESA HORA!")
            return "❌ Error: Ya existe una cita confirmada a esta hora. Por favor, selecciona otro horario."
        
        # Obtener nombre del cliente
        if 'cliente_nombre' not in conversacion:
            nombre_cliente = 'Cliente'
        else:
            nombre_cliente = conversacion['cliente_nombre']
        
        if not nombre_cliente or len(str(nombre_cliente).strip()) < 2:
            nombre_cliente = 'Cliente'
        else:
            nombre_cliente = str(nombre_cliente).strip().title()
        
        print(f"🔧 [DEBUG] Datos para cita:")
        print(f"   - Cliente: {nombre_cliente}")
        print(f"   - Teléfono: {telefono}")
        print(f"   - Fecha: {fecha}")
        print(f"   - Hora: {hora}")
        print(f"   - Profesional: {profesional_nombre} (ID: {profesional_id})")
        print(f"   - Servicio: {servicio_nombre} (ID: {servicio_id})")
        print(f"   - Precio: ${servicio_precio:,.0f}")
        print(f"   - Duración: {duracion} min")
        
        # Crear la cita en la base de datos
        print(f"🔧 [DEBUG] Creando cita en BD...")
        cita_id = db.agregar_cita(
            negocio_id=negocio_id,
            profesional_id=profesional_id,
            cliente_telefono=telefono,
            fecha=fecha,
            hora=hora,
            servicio_id=servicio_id,
            cliente_nombre=nombre_cliente
        )
        
        if cita_id and cita_id > 0:
            print(f"✅ [DEBUG] Cita creada exitosamente. ID: {cita_id}")
            
            # ✅ LIMPIAR CONVERSACIÓN Y MOSTRAR CONFIRMACIÓN
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
• **Duración:** {duracion} minutos

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

def diagnostico_citas_duplicadas(negocio_id, profesional_id, fecha, hora, servicio_id):
    """Función para diagnosticar por qué se permiten citas duplicadas"""
    print(f"\n🚨 DIAGNÓSTICO DE DUPLICADOS 🚨")
    print(f"Fecha: {fecha}")
    print(f"Hora: {hora}")
    print(f"Profesional ID: {profesional_id}")
    print(f"Servicio ID: {servicio_id}")
    
    # Obtener duración del servicio
    duracion = db.obtener_duracion_servicio(negocio_id, servicio_id)
    print(f"Duración servicio: {duracion} minutos")
    
    # Obtener todas las citas del día
    citas = db.obtener_citas_dia(negocio_id, profesional_id, fecha)
    print(f"\n📋 TODAS las citas en BD para este día:")
    
    for i, cita in enumerate(citas):
        print(f"  Cita #{i+1}:")
        print(f"    Hora: {cita.get('hora')}")
        print(f"    Duración: {cita.get('duracion')}")
        print(f"    Estado: {cita.get('estado')}")
    
    # Verificar si ya existe una cita a esa hora
    cita_existente = None
    for cita in citas:
        if cita.get('hora') == hora and cita.get('estado') == 'confirmado':
            cita_existente = cita
            break
    
    if cita_existente:
        print(f"\n🚨 ¡YA EXISTE UNA CITA CONFIRMADA A ESA HORA!")
        print(f"   Hora: {cita_existente.get('hora')}")
        print(f"   Duración: {cita_existente.get('duracion')}")
        print(f"   Estado: {cita_existente.get('estado')}")
    else:
        print(f"\n✅ No hay citas confirmadas a las {hora}")
    
    # Calcular horario propuesto
    hora_inicio = datetime.strptime(hora, '%H:%M')
    hora_fin = hora_inicio + timedelta(minutes=duracion)
    
    print(f"\n⏰ Horario propuesto: {hora} - {hora_fin.strftime('%H:%M')}")
    
    # Verificar solapamientos
    for cita in citas:
        if cita.get('estado') == 'confirmado':
            cita_hora = datetime.strptime(cita.get('hora'), '%H:%M')
            cita_duracion = cita.get('duracion', 0)
            cita_fin = cita_hora + timedelta(minutes=int(cita_duracion))
            
            if se_solapan(hora_inicio, hora_fin, cita_hora, cita_fin):
                print(f"\n🚨 SOLAPAMIENTO CON CITA EXISTENTE:")
                print(f"   Cita existente: {cita.get('hora')} - {cita_fin.strftime('%H:%M')}")
                print(f"   Nueva cita: {hora} - {hora_fin.strftime('%H:%M')}")

def continuar_conversacion(numero, mensaje, negocio_id):
    """Continuar conversación basada en el estado actual - ACTUALIZADO PARA SERVICIO PERSONALIZADO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if clave_conversacion not in conversaciones_activas:
        print(f"❌ [DEBUG] No hay conversación activa en continuar_conversacion")
        return saludo_inicial(numero, negocio_id)
    
    estado = conversaciones_activas[clave_conversacion]['estado']
    
    print(f"🔧 CONTINUANDO CONVERSACIÓN - Estado: {estado}, Mensaje: '{mensaje}'")
    
    try:
        if estado == 'solicitando_telefono_inicial':
            return procesar_telefono_inicial(numero, mensaje, negocio_id)
        elif estado == 'solicitando_nombre':
            return procesar_nombre_cliente(numero, mensaje, negocio_id)
        elif estado == 'menu_principal':
            # Si estamos en menu_principal y el usuario envía opción
            if mensaje in ['1', '2', '3', '4']:
                return procesar_opcion_menu(numero, mensaje, negocio_id)
            else:
                return "Por favor, selecciona una opción válida del menú (1, 2, 3 o 4)."
        elif estado == 'seleccionando_profesional':
            return procesar_seleccion_profesional(numero, mensaje, negocio_id)
        elif estado == 'seleccionando_servicio':
            return procesar_seleccion_servicio(numero, mensaje, negocio_id)
        elif estado == 'seleccionando_servicio_personalizado':  # ✅ NUEVO ESTADO
            return procesar_seleccion_servicio_personalizado(numero, mensaje, negocio_id)
        elif estado == 'seleccionando_fecha':
            return procesar_seleccion_fecha(numero, mensaje, negocio_id)
        elif estado == 'agendando_hora':
            return procesar_seleccion_hora(numero, mensaje, negocio_id)
        elif estado == 'confirmando_cita':
            return procesar_confirmacion_cita(numero, mensaje, negocio_id)
        elif estado == 'cancelando':
            return procesar_cancelacion_cita(numero, mensaje, negocio_id)
        elif estado == 'solicitando_telefono':
            # Para confirmar cita (backup)
            return procesar_confirmacion_cita(numero, mensaje, negocio_id)
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

# =============================================================================
# EL RESTO DE LAS FUNCIONES SE MANTIENEN IGUAL (SIN MODIFICACIONES)
# =============================================================================

def procesar_seleccion_profesional(numero, mensaje, negocio_id):
    """Procesar selección de profesional - SIN CAMBIOS"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        return "Volviendo al menú principal..."
    
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
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
    
    return mostrar_servicios(numero, profesional_seleccionado['nombre'], negocio_id)

def procesar_seleccion_servicio(numero, mensaje, negocio_id):
    """Procesar selección de servicio - ACTUALIZADO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    # Manejar el comando "0" para volver al menú principal
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        return "Volviendo al menú principal..."
    
    # Verificar si hay servicios normales
    if 'servicios' not in conversaciones_activas[clave_conversacion]:
        # Verificar si estamos en modo servicio personalizado
        if 'tiene_personalizado' in conversaciones_activas[clave_conversacion]:
            return procesar_seleccion_servicio_personalizado(numero, mensaje, negocio_id)
        
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
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
    
    # Limpiar servicio personalizado si existe
    if 'servicio_personalizado' in conversaciones_activas[clave_conversacion]:
        del conversaciones_activas[clave_conversacion]['servicio_personalizado']
    if 'tiene_personalizado' in conversaciones_activas[clave_conversacion]:
        del conversaciones_activas[clave_conversacion]['tiene_personalizado']
    
    return mostrar_fechas_disponibles(numero, negocio_id)

def procesar_seleccion_fecha(numero, mensaje, negocio_id):
    """Procesar selección de fecha - SIN CAMBIOS"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        return "Volviendo al menú principal..."
    
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
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
    
    return mostrar_disponibilidad(numero, negocio_id, fecha_seleccionada)

def procesar_seleccion_hora(numero, mensaje, negocio_id):
    """Procesar selección de horario - ACTUALIZADO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    # ✅ Navegación de horarios y cambio de fecha
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
        
        max_pagina = (len(horarios_disponibles) - 1) // horarios_por_pagina
        if pagina_actual < max_pagina:
            conversaciones_activas[clave_conversacion]['pagina_horarios'] = pagina_actual + 1
        else:
            return "ℹ️ Ya estás en la última página de horarios.\n\nSelecciona un horario o usa otra opción"
        
        return mostrar_disponibilidad(numero, negocio_id)
    
    # ✅ Solo procesar números 1-6 como horarios
    if not mensaje.isdigit():
        return f"❌ Por favor, ingresa un número válido."
    
    mensaje_num = int(mensaje)
    
    # Obtener horarios de la página actual
    pagina_actual = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
    horarios_disponibles = conversaciones_activas[clave_conversacion]['todos_horarios']
    horarios_por_pagina = 6
    inicio = pagina_actual * horarios_por_pagina
    fin = inicio + horarios_por_pagina
    horarios_pagina = horarios_disponibles[inicio:fin]
    
    if mensaje_num < 1 or mensaje_num > len(horarios_pagina):
        return f"❌ Número inválido. Por favor, elige entre 1 y {len(horarios_pagina)}"
    
    # Guardar horario seleccionado
    hora_index = mensaje_num - 1
    hora_seleccionada = horarios_pagina[hora_index]
    
    conversaciones_activas[clave_conversacion]['hora_seleccionada'] = hora_seleccionada
    conversaciones_activas[clave_conversacion]['estado'] = 'confirmando_cita'
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now(tz_colombia)
    
    # Obtener nombre del cliente
    nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre', 'Cliente')
    
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
    """Procesar cancelación de cita - SIN CAMBIOS"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG-CANCELAR] procesar_cancelacion_cita - Clave: {clave_conversacion}, Mensaje: '{mensaje}'")
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        return "Volviendo al menú principal..."
    
    if 'citas_disponibles' not in conversaciones_activas[clave_conversacion]:
        print(f"❌ [DEBUG-CANCELAR] No hay citas disponibles en la conversación")
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        return "❌ Sesión de cancelación expirada. Por favor, selecciona *3* nuevamente."
    
    citas_disponibles = conversaciones_activas[clave_conversacion]['citas_disponibles']
    
    print(f"🔧 [DEBUG-CANCELAR] Citas disponibles: {list(citas_disponibles.keys())}")
    print(f"🔧 [DEBUG-CANCELAR] Mensaje recibido: '{mensaje}'")
    
    if mensaje not in citas_disponibles:
        return "❌ ID de cita inválido. Por favor, ingresa un ID de la lista anterior."
    
    # Cancelar cita
    try:
        cita_id = mensaje
        cita_info = citas_disponibles[cita_id]
        
        print(f"🔧 [DEBUG-CANCELAR] Cancelando cita ID: {cita_id}")
        print(f"🔧 [DEBUG-CANCELAR] Info cita: {cita_info}")
        
        # Obtener teléfono REAL para la cancelación
        telefono_real = conversaciones_activas[clave_conversacion].get('telefono_cliente')
        if not telefono_real:
            telefono_real = '3174694941'  # Fallback
        
        # Actualizar estado en base de datos
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ✅ CORRECCIÓN: Usar cita_id convertido a entero
        cursor.execute('''
            UPDATE citas 
            SET estado = %s 
            WHERE id = %s AND negocio_id = %s AND cliente_telefono = %s
        ''', ('cancelado', int(cita_id), negocio_id, telefono_real))
        
        filas_afectadas = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"✅ [DEBUG-CANCELAR] Cita cancelada. Filas afectadas: {filas_afectadas}")
        
        if filas_afectadas == 0:
            print(f"❌ [DEBUG-CANCELAR] No se pudo cancelar la cita. Verificar datos.")
            if clave_conversacion in conversaciones_activas:
                conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
            return "❌ No se pudo cancelar la cita. Por favor, verifica el ID e intenta nuevamente."
        
        # Limpiar datos de cancelación pero mantener la conversación
        if clave_conversacion in conversaciones_activas:
            # Eliminar solo los datos de cancelación
            if 'citas_disponibles' in conversaciones_activas[clave_conversacion]:
                del conversaciones_activas[clave_conversacion]['citas_disponibles']
            
            # Volver al menú principal
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
            
            # Obtener nombre del cliente
            nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre', 'Cliente')
        
        # Formatear fecha para el mensaje
        try:
            fecha = cita_info[1]  # Índice 1 es fecha
            if isinstance(fecha, str):
                fecha_str = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m')
            else:
                fecha_str = fecha.strftime('%d/%m')
        except:
            fecha_str = str(fecha)
        
        hora = cita_info[2]  # Índice 2 es hora
        
        return f'''❌ **Cita cancelada exitosamente**

Hola {nombre_cliente}, has cancelado tu cita:

📅 **Fecha:** {fecha_str}
⏰ **Hora:** {hora}
🎫 **ID de cita:** #{cita_id}

Esperamos verte pronto en otra ocasión.'''
        
    except Exception as e:
        print(f"❌ [DEBUG-CANCELAR] Error cancelando cita: {e}")
        import traceback
        traceback.print_exc()
        
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        
        return "❌ Error al cancelar la cita. Por favor, intenta nuevamente."

def procesar_cancelacion_directa(numero, cita_id, negocio_id):
    """Procesar cancelación cuando solo hay una cita - SIN CAMBIOS"""
    print(f"🔧 [DEBUG-CANCELAR-DIRECTO] Cancelando cita ID: {cita_id}")
    
    if cita_id == '0':
        clave_conversacion = f"{numero}_{negocio_id}"
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        return "Volviendo al menú principal..."
    
    # Cancelar cita directamente
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener teléfono REAL de la conversación
        clave_conversacion = f"{numero}_{negocio_id}"
        telefono_real = None
        if clave_conversacion in conversaciones_activas:
            telefono_real = conversaciones_activas[clave_conversacion].get('telefono_cliente')
        
        if not telefono_real:
            print(f"⚠️ [DEBUG-CANCELAR-DIRECTO] No hay teléfono, buscando en BD...")
            # Buscar teléfono de la cita
            cursor.execute('''
                SELECT cliente_telefono FROM citas WHERE id = %s AND negocio_id = %s
            ''', (cita_id, negocio_id))
            
            resultado = cursor.fetchone()
            if resultado:
                telefono_real = resultado[0] if isinstance(resultado, tuple) else resultado.get('cliente_telefono')
                print(f"✅ [DEBUG-CANCELAR-DIRECTO] Teléfono obtenido de BD: {telefono_real}")
        
        # Cancelar la cita
        if telefono_real:
            cursor.execute('''
                UPDATE citas SET estado = %s 
                WHERE id = %s AND negocio_id = %s AND cliente_telefono = %s
            ''', ('cancelado', int(cita_id), negocio_id, telefono_real))
        else:
            cursor.execute('''
                UPDATE citas SET estado = %s 
                WHERE id = %s AND negocio_id = %s
            ''', ('cancelado', int(cita_id), negocio_id))
        
        filas_afectadas = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"✅ [DEBUG-CANCELAR-DIRECTO] Cita cancelada. Filas afectadas: {filas_afectadas}")
        
        # Obtener nombre del cliente
        nombre_cliente = 'Cliente'
        if clave_conversacion in conversaciones_activas:
            nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre', 'Cliente')
        
        if clave_conversacion in conversaciones_activas:
            conversaciones_activas[clave_conversacion]['estado'] = 'menu_principal'
        
        return f'''❌ **Cita cancelada exitosamente**

Hola {nombre_cliente}, has cancelado tu cita (ID: #{cita_id}).

Esperamos verte pronto en otra ocasión.'''
        
    except Exception as e:
        print(f"❌ [DEBUG-CANCELAR-DIRECTO] Error cancelando cita: {e}")
        import traceback
        traceback.print_exc()
        
        return "❌ Error al cancelar la cita."

def obtener_proximas_fechas_disponibles(negocio_id, dias_a_mostrar=7):
    """Obtener las próximas fechas donde el negocio está activo - SIN CAMBIOS"""
    fechas_disponibles = []
    fecha_actual = datetime.now(tz_colombia)
    
    print(f"🔧 [DEBUG] OBTENER_FECHAS_DISPONIBLES - Negocio: {negocio_id}")
    
    for i in range(dias_a_mostrar):
        fecha = fecha_actual + timedelta(days=i)
        fecha_str = fecha.strftime('%Y-%m-%d')
        
        # ✅ VERIFICAR SI EL DÍA ESTÁ ACTIVO
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
    """Generar horarios disponibles considerando la configuración por días - CON LOGS DIAGNÓSTICOS"""
    print(f"\n🔍 [DIAGNÓSTICO] Iniciando verificación para {fecha}")
    print(f"   Negocio: {negocio_id}, Profesional: {profesional_id}, Servicio: {servicio_id}")
    
    # ✅ VERIFICAR SI EL DÍA ESTÁ ACTIVO
    horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha)
    
    if not horarios_dia or not horarios_dia['activo']:
        print(f"❌ Día no activo para la fecha {fecha}")
        return []  # Día no activo, no hay horarios disponibles
    
    print(f"✅ Día activo. Horario: {horarios_dia['hora_inicio']} - {horarios_dia['hora_fin']}")
    
    # ✅ Obtener citas ya agendadas - CON DIAGNÓSTICO
    print(f"📋 Llamando a obtener_citas_dia...")
    citas_ocupadas = db.obtener_citas_dia(negocio_id, profesional_id, fecha)
    print(f"📊 TOTAL citas devueltas por BD: {len(citas_ocupadas)}")
    
    # DIAGNÓSTICO DETALLADO de cada cita
    if citas_ocupadas:
        print("📋 DETALLE DE CADA CITA OBTENIDA DE BD:")
        for i, cita in enumerate(citas_ocupadas):
            print(f"   Cita #{i+1}:")
            print(f"     Tipo de dato: {type(cita)}")
            
            if isinstance(cita, dict):
                print(f"     Dict - Hora: {cita.get('hora')}, Duración: {cita.get('duracion')}, Estado: {cita.get('estado')}")
            elif isinstance(cita, (list, tuple)):
                print(f"     List/Tuple - Contenido: {cita}")
                if len(cita) > 0:
                    print(f"       Hora: {cita[0]}")
                if len(cita) > 1:
                    print(f"       Duración: {cita[1]}")
                if len(cita) > 2:
                    print(f"       Estado: {cita[2]}")
            else:
                print(f"     Otro tipo: {cita}")
    else:
        print("📭 No hay citas registradas en BD para este día/profesional")
    
    # Obtener duración del servicio
    duracion_servicio = db.obtener_duracion_servicio(negocio_id, servicio_id)
    if not duracion_servicio:
        print(f"❌ No se pudo obtener duración del servicio {servicio_id}")
        return []
    
    print(f"⏱️ Duración del servicio a agendar: {duracion_servicio} minutos")
    
    # ✅ CORRECCIÓN: Si es hoy, considerar margen mínimo de anticipación
    fecha_actual = datetime.now(tz_colombia)
    fecha_cita = datetime.strptime(fecha, '%Y-%m-%d')
    es_hoy = fecha_cita.date() == fecha_actual.date()
    
    # Generar horarios disponibles
    horarios = []
    hora_actual = datetime.strptime(horarios_dia['hora_inicio'], '%H:%M')
    hora_fin = datetime.strptime(horarios_dia['hora_fin'], '%H:%M')
    
    while hora_actual < hora_fin:
        hora_str = hora_actual.strftime('%H:%M')
        
        # ✅ CORRECCIÓN CRÍTICA: Si es hoy, verificar horarios futuros con margen
        if es_hoy:
            # Combinar fecha actual con hora del horario
            hora_actual_completa = datetime.combine(fecha_actual.date(), hora_actual.time())
            
            # ✅ FIX: Asegurar que ambas fechas tengan timezone
            hora_actual_completa = hora_actual_completa.replace(tzinfo=tz_colombia)
            
            # Calcular tiempo hasta el horario
            tiempo_hasta_horario = hora_actual_completa - fecha_actual
            
            # ✅ MARGEN MÍNIMO: 30 minutos de anticipación
            margen_minimo_minutos = 30
            
            if tiempo_hasta_horario.total_seconds() <= 0:
                # Horario YA PASÓ
                print(f"⏰ Horario {hora_str} omitido (ya pasó)")
                hora_actual += timedelta(minutes=30)
                continue
            elif tiempo_hasta_horario.total_seconds() < (margen_minimo_minutos * 60):
                # Horario es muy pronto
                print(f"⏰ Horario {hora_str} omitido (faltan {int(tiempo_hasta_horario.total_seconds()/60)} minutos)")
                hora_actual += timedelta(minutes=30)
                continue
        
        # Verificar si no es horario de almuerzo
        if not es_horario_almuerzo(hora_actual, horarios_dia):
            # ✅ MEJORADO: Verificar disponibilidad
            if esta_disponible(hora_actual, duracion_servicio, citas_ocupadas, horarios_dia):
                horarios.append(hora_str)
                print(f"✅ Horario disponible: {hora_str}")
            else:
                print(f"❌ Horario NO disponible: {hora_str} (ocupado o conflicto)")
        else:
            print(f"🍽️ Horario {hora_str} omitido (horario de almuerzo)")
        
        hora_actual += timedelta(minutes=30)
    
    print(f"🎯 Total horarios disponibles: {len(horarios)}")
    return horarios


def verificar_disponibilidad_basica(negocio_id, fecha):
    """Verificación rápida de disponibilidad para una fecha - FIX TIMEZONE"""
    try:
        # Verificar si el día está activo
        horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha)
        if not horarios_dia or not horarios_dia['activo']:
            return False
        
        # Si es hoy, verificar que queden horarios futuros con margen mínimo
        fecha_actual = datetime.now(tz_colombia)
        fecha_cita = datetime.strptime(fecha, '%Y-%m-%d')
        
        if fecha_cita.date() == fecha_actual.date():
            # Para hoy, verificar si hay al menos un horario futuro con margen
            hora_actual = datetime.strptime(horarios_dia['hora_inicio'], '%H:%M')
            hora_fin = datetime.strptime(horarios_dia['hora_fin'], '%H:%M')
            
            while hora_actual < hora_fin:
                # ✅ FIX: Asegurar timezone
                hora_actual_completa = datetime.combine(fecha_actual.date(), hora_actual.time())
                hora_actual_completa = hora_actual_completa.replace(tzinfo=tz_colombia)
                
                # ✅ CORRECCIÓN: Solo considerar horarios FUTUROS con margen
                tiempo_hasta_horario = hora_actual_completa - fecha_actual
                
                # Horario debe ser futuro y con al menos 30 minutos de margen
                if tiempo_hasta_horario.total_seconds() > 0 and tiempo_hasta_horario.total_seconds() >= (30 * 60):
                    return True  # Hay al menos un horario futuro con margen suficiente
                
                hora_actual += timedelta(minutes=30)
            return False  # No hay horarios futuros con margen suficiente para hoy
        
        return True  # Para días futuros, solo con que el día esté activo es suficiente
        
    except Exception as e:
        print(f"❌ Error en verificación básica: {e}")
        import traceback
        traceback.print_exc()
        return False

def es_horario_almuerzo(hora, config_dia):
    """Verificar si es horario de almuerzo - SIN CAMBIOS"""
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
    """Verificar si un horario está disponible - CON LUGS DETALLADOS"""
    hora_str = hora_inicio.strftime('%H:%M')
    hora_fin_servicio = hora_inicio + timedelta(minutes=duracion_servicio)
    
    print(f"\n   🔍 Verificando disponibilidad para {hora_str} (duración: {duracion_servicio} min)")
    
    # Verificar límites del día
    try:
        hora_fin_jornada = datetime.strptime(config_dia['hora_fin'], '%H:%M')
        if hora_fin_servicio.time() > hora_fin_jornada.time():
            print(f"     ❌ NO DISPONIBLE - Se pasa del horario de cierre ({config_dia['hora_fin']})")
            return False
    except Exception as e:
        print(f"❌ Error verificando horario cierre: {e}")
        return False
    
    # Verificar almuerzo
    if se_solapa_con_almuerzo(hora_inicio, hora_fin_servicio, config_dia):
        print(f"     ❌ NO DISPONIBLE - Se solapa con horario de almuerzo")
        return False
    
    # Verificar citas existentes
    if citas_ocupadas:
        print(f"     📋 Verificando contra {len(citas_ocupadas)} citas existentes...")
        
        for i, cita_ocupada in enumerate(citas_ocupadas):
            try:
                # Extraer datos de la cita
                hora_cita_str = None
                duracion_cita = 0
                estado_cita = 'confirmado'
                
                if isinstance(cita_ocupada, dict):
                    hora_cita_str = cita_ocupada.get('hora')
                    duracion_cita = cita_ocupada.get('duracion', 0)
                    estado_cita = cita_ocupada.get('estado', 'confirmado')
                elif isinstance(cita_ocupada, (list, tuple)) and len(cita_ocupada) >= 2:
                    hora_cita_str = cita_ocupada[0]
                    duracion_cita = cita_ocupada[1]
                    estado_cita = cita_ocupada[2] if len(cita_ocupada) > 2 else 'confirmado'
                
                if not hora_cita_str:
                    print(f"       ⚠️ Hora de cita vacía, saltando...")
                    continue
                
                print(f"     🔍 Comparando con cita #{i+1}: {hora_cita_str} ({duracion_cita} min, Estado: {estado_cita})")
                
                # VERIFICACIÓN CRÍTICA DEL ESTADO
                if estado_cita and estado_cita.lower() != 'confirmado':
                    print(f"       ⏭️ IGNORADA - Estado no confirmado: {estado_cita}")
                    continue
                
                # Verificar solapamiento
                hora_cita = datetime.strptime(str(hora_cita_str).strip(), '%H:%M')
                hora_fin_cita = hora_cita + timedelta(minutes=int(duracion_cita))
                
                if se_solapan(hora_inicio, hora_fin_servicio, hora_cita, hora_fin_cita):
                    print(f"       ❌ SOLAPAMIENTO DETECTADO")
                    print(f"         Nuevo: {hora_str}-{hora_fin_servicio.strftime('%H:%M')}")
                    print(f"         Existente: {hora_cita_str}-{hora_fin_cita.strftime('%H:%M')}")
                    return False
                else:
                    print(f"       ✅ No hay solapamiento")
                    
            except Exception as e:
                print(f"⚠️ Error procesando cita ocupada {cita_ocupada}: {e}")
                continue
    else:
        print(f"     📭 No hay citas para comparar")
    
    print(f"     ✅ DISPONIBLE - {hora_str}")
    return True

def se_solapa_con_almuerzo(hora_inicio, hora_fin, config_dia):
    """Verificar si un horario se solapa con el almuerzo del día - SIN CAMBIOS"""
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
    """Verificar si dos intervalos de tiempo se solapan - CON LOGS"""
    solapan = (inicio1.time() < fin2.time() and fin1.time() > inicio2.time())
    
    if solapan:
        print(f"       🚨 SOLAPAMIENTO DETECTADO:")
        print(f"         Intervalo 1: {inicio1.time()} - {fin1.time()}")
        print(f"         Intervalo 2: {inicio2.time()} - {fin2.time()}")
    
    return solapan

def reiniciar_conversacion_si_es_necesario(numero, negocio_id):
    """Reiniciar conversación si ha pasado mucho tiempo - SIN CAMBIOS"""
    clave_conversacion = f"{numero}_{negocio_id}"
    if clave_conversacion in conversaciones_activas:
        if 'timestamp' in conversaciones_activas[clave_conversacion]:
            tiempo_transcurrido = datetime.now(tz_colombia) - conversaciones_activas[clave_conversacion]['timestamp']
            if tiempo_transcurrido.total_seconds() > 600:  # 10 minutos
                del conversaciones_activas[clave_conversacion]

# =============================================================================
# FUNCIONES PARA ENVÍO DE CORREO/SMS (REEMPLAZAN TWILIO) - SIN CAMBIOS
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
    
def limpiar_formato_whatsapp(texto):
    """
    Limpiar formato WhatsApp (*negrita*, _cursiva_) para el chat web
    """
    if not texto:
        return texto
    
    # Reemplazar formato WhatsApp por HTML para mejor visualización
    texto = texto.replace('*', '')  # Quitar asteriscos de negrita
    texto = texto.replace('_', '')  # Quitar guiones bajos de cursiva
    
    return texto