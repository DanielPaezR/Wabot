from flask import Blueprint, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import sqlite3
from datetime import datetime, timedelta
import database as db
import json
import os
from dotenv import load_dotenv
import database

load_dotenv()

whatsapp_bp = Blueprint('whatsapp', __name__)

# Estados de conversación
conversaciones_activas = {}

# =============================================================================
# MOTOR DE PLANTILLAS (CORREGIDO)
# =============================================================================

def renderizar_plantilla(nombre_plantilla, negocio_id, variables_extra=None):
    """Motor principal de plantillas - CORREGIDO"""
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
        config_json = negocio['configuracion'] if 'configuracion' in negocio.keys() else '{}'
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
# WEBHOOK PRINCIPAL (CORREGIDO)
# =============================================================================

@whatsapp_bp.route('/webhook', methods=['POST'])
def webhook_whatsapp():
    """Webhook principal para WhatsApp - CON DEBUGGING"""
    try:
        # Obtener datos del mensaje
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '').replace('whatsapp:', '')
        to_number = request.values.get('To', '')  # Número del negocio
        
        print(f"🔧 [DEBUG] WEBHOOK - Mensaje de {from_number} a {to_number}: '{incoming_msg}'")
        
        # Identificar negocio por el número que recibió el mensaje
        print(f"🔧 [DEBUG] Buscando negocio para número: {to_number}")
        negocio = db.obtener_negocio_por_telefono(to_number)
        if not negocio:
            print(f"❌ [DEBUG] Negocio NO encontrado para: {to_number}")
            resp = MessagingResponse()
            resp.message("❌ Este número no está configurado en el sistema.")
            return str(resp)
        
        print(f"✅ [DEBUG] Negocio identificado: {negocio['nombre']} (ID: {negocio['id']})")
        
        if not negocio['activo']:
            print(f"❌ [DEBUG] Negocio INACTIVO: {negocio['nombre']}")
            resp = MessagingResponse()
            resp.message("❌ Este negocio no está activo actualmente.")
            return str(resp)
        
        # ✅ CORRECCIÓN: Verificar si es un mensaje duplicado o automático
        if not incoming_msg or incoming_msg.isspace():
            print(f"⚠️ [DEBUG] Mensaje vacío o automático, ignorando...")
            resp = MessagingResponse()
            return str(resp)
        
        # Procesar mensaje
        print(f"🔧 [DEBUG] Llamando a procesar_mensaje...")
        respuesta = procesar_mensaje(incoming_msg, from_number, negocio['id'])
        
        # Enviar respuesta solo si hay contenido
        if respuesta:
            print(f"🔧 [DEBUG] Enviando respuesta: {respuesta}")
            resp = MessagingResponse()
            resp.message(respuesta)
            return str(resp)
        else:
            print(f"⚠️ [DEBUG] No hay respuesta para enviar")
            resp = MessagingResponse()
            return str(resp)
        
    except Exception as e:
        print(f"❌ [DEBUG] Error CRÍTICO en webhook: {e}")
        import traceback
        traceback.print_exc()
        
        resp = MessagingResponse()
        resp.message("❌ Ocurrió un error. Por favor, intenta nuevamente.")
        return str(resp)

# =============================================================================
# LÓGICA PRINCIPAL DE MENSAJES (MEJORADA)
# =============================================================================

def procesar_mensaje(mensaje, numero, negocio_id):
    """Procesar mensajes usando el sistema de plantillas - CON DEBUGGING"""
    mensaje = mensaje.lower().strip()
    clave_conversacion = f"{numero}_{negocio_id}"
    
    print(f"🔧 [DEBUG] PROCESANDO MENSAJE: '{mensaje}' de {numero}")
    print(f"🔧 [DEBUG] Clave conversación: {clave_conversacion}")
    
    # Comando especial para volver al menú principal
    if mensaje == '0':
        print(f"🔧 [DEBUG] Comando '0' detectado - Volviendo al menú principal")
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    # Reiniciar conversación si ha pasado mucho tiempo
    reiniciar_conversacion_si_es_necesario(numero, negocio_id)
    
    # Si hay conversación activa, continuarla
    if clave_conversacion in conversaciones_activas:
        estado_actual = conversaciones_activas[clave_conversacion]['estado']
        print(f"🔧 [DEBUG] Conversación activa encontrada - Estado: {estado_actual}")
        return continuar_conversacion(numero, mensaje, negocio_id)
    
    print(f"🔧 [DEBUG] No hay conversación activa - Procesando comando del menú")
    
    # Procesar comandos del menú principal SOLO si no hay conversación activa
    if mensaje == '1':
        print(f"🔧 [DEBUG] Comando '1' detectado - Mostrando profesionales")
        return mostrar_profesionales(numero, negocio_id)
    elif mensaje == '2':
        print(f"🔧 [DEBUG] Comando '2' detectado - Mostrando citas")
        return mostrar_mis_citas(numero, negocio_id)
    elif mensaje == '3':
        print(f"🔧 [DEBUG] Comando '3' detectado - Cancelando reserva")
        conversaciones_activas[clave_conversacion] = {'estado': 'cancelando', 'timestamp': datetime.now()}
        return mostrar_citas_para_cancelar(numero, negocio_id)
    elif mensaje == '4':
        print(f"🔧 [DEBUG] Comando '4' detectado - Mostrando ayuda")
        return mostrar_ayuda(negocio_id)
    elif mensaje in ['hola', 'hi', 'hello', 'buenas']:
        print(f"🔧 [DEBUG] Saludo detectado - Mostrando menú inicial")
        return saludo_inicial(numero, negocio_id)
    else:
        # Mensaje no reconocido - mostrar menú principal
        print(f"🔧 [DEBUG] Mensaje no reconocido - Mostrando menú principal")
        return renderizar_plantilla('menu_principal', negocio_id)

def saludo_inicial(numero, negocio_id):
    """Saludo inicial - Cliente nuevo o existente - MEJORADO"""
    try:
        # DEBUG: Verificar estado real del cliente
        es_nuevo = db.es_cliente_nuevo(numero, negocio_id)
        nombre_existente = db.obtener_nombre_cliente(numero, negocio_id)
        
        print(f"🔧 DEBUG saludo_inicial: numero={numero}, es_nuevo={es_nuevo}, nombre_existente='{nombre_existente}'")
        
        # ✅ CORRECCIÓN MEJORADA: Si es cliente nuevo O no tenemos su nombre registrado
        if es_nuevo or not nombre_existente:
            print("🔧 DEBUG: Tratando como cliente NUEVO o sin nombre")
            # Cliente nuevo - pedir nombre
            clave_conversacion = f"{numero}_{negocio_id}"
            conversaciones_activas[clave_conversacion] = {
                'estado': 'solicitando_nombre',
                'timestamp': datetime.now()
            }
            return renderizar_plantilla('saludo_inicial_nuevo', negocio_id)
        else:
            print("🔧 DEBUG: Tratando como cliente EXISTENTE con nombre")
            # Cliente existente - mostrar menú personalizado
            return renderizar_plantilla('saludo_inicial_existente', negocio_id, {
                'cliente_nombre': nombre_existente
            })
    except Exception as e:
        print(f"❌ Error en saludo_inicial: {e}")
        return renderizar_plantilla('error_generico', negocio_id)


def mostrar_profesionales(numero, negocio_id):
    """Mostrar lista de profesionales disponibles - CORREGIDO"""
    try:
        print(f"🔧 [DEBUG] MOSTRAR_PROFESIONALES - Iniciando")
        print(f"🔧 [DEBUG] Parámetros - Negocio: {negocio_id}, Cliente: {numero}")
        
        # ✅ CORRECCIÓN: Usar la función que SÍ existe de database
        print(f"🔧 [DEBUG] Llamando a db.obtener_profesionales...")
        profesionales = db.obtener_profesionales(negocio_id)
        
        print(f"🔧 [DEBUG] Profesionales obtenidos: {len(profesionales)}")
        
        # ✅ FILTRAR solo profesionales activos manualmente
        profesionales_activos = []
        for prof in profesionales:
            print(f"🔧 [DEBUG] Profesional: ID={prof['id']}, Nombre='{prof['nombre']}', Activo={prof.get('activo', 'No especificado')}")
            # Asumir que está activo si no hay campo 'activo' o si activo=True
            if prof.get('activo', True):
                profesionales_activos.append(prof)
        
        profesionales = profesionales_activos
        print(f"🔧 [DEBUG] Profesionales activos después de filtrar: {len(profesionales)}")
        
        if not profesionales:
            print(f"🔧 [DEBUG] No hay profesionales disponibles")
            return "❌ No hay profesionales disponibles en este momento."
        
        # Obtener información del negocio para textos dinámicos
        print(f"🔧 [DEBUG] Obteniendo información del negocio...")
        negocio = db.obtener_negocio_por_id(negocio_id)
        print(f"🔧 [DEBUG] Negocio obtenido: {negocio}")
        
        if not negocio:
            print(f"❌ [DEBUG] No se pudo obtener información del negocio")
            return "❌ Error: Información del negocio no disponible."
        
        # Construir lista de profesionales
        lista_profesionales = ""
        for i, prof in enumerate(profesionales, 1):
            lista_profesionales += f"*{i}.* {prof['nombre']} - {prof['especialidad']}\n"
        
        # Guardar en conversación activa
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion] = {
            'estado': 'seleccionando_profesional',
            'profesionales': profesionales,
            'timestamp': datetime.now()
        }
        
        print(f"🔧 [DEBUG] Conversación activa guardada: {clave_conversacion}")
        
        texto_profesional = 'estilista' if negocio['tipo_negocio'] == 'spa_unas' else 'profesional'
        emoji_profesional = '👩‍💼' if negocio['tipo_negocio'] == 'spa_unas' else '👨‍💼'
        
        respuesta = f'''{emoji_profesional} *Nuestros {texto_profesional.title()}es* 

{lista_profesionales}
Responde con el *número* del {texto_profesional} que prefieres:

💡 *O vuelve al menú principal con* *0*'''
        
        print(f"🔧 [DEBUG] Respuesta preparada exitosamente")
        return respuesta
        
    except Exception as e:
        print(f"❌ [DEBUG] Error CRÍTICO en mostrar_profesionales: {e}")
        import traceback
        traceback.print_exc()
        return renderizar_plantilla('error_generico', negocio_id)
    
def mostrar_servicios(numero, profesional_nombre, negocio_id):
    """Mostrar servicios disponibles - CORREGIDO"""
    try:
        # ✅ CORRECCIÓN: Usar la función que existe y filtrar activos
        print(f"🔧 [DEBUG] Llamando a db.obtener_servicios...")
        servicios = db.obtener_servicios(negocio_id)
        
        # Filtrar servicios activos manualmente
        servicios_activos = []
        for servicio in servicios:
            if servicio.get('activo', True):
                servicios_activos.append(servicio)
        
        servicios = servicios_activos
        print(f"🔧 [DEBUG] Servicios activos: {len(servicios)}")
        
        if not servicios:
            return "❌ No hay servicios disponibles en este momento."
        
        # El resto del código permanece igual...
        # Construir lista de servicios
        lista_servicios = ""
        for i, servicio in enumerate(servicios, 1):
            precio_formateado = f"${servicio['precio']:,.0f}".replace(',', '.')
            lista_servicios += f"*{i}.* {servicio['nombre']} - {precio_formateado}\n"
            if servicio.get('descripcion'):
                lista_servicios += f"   📝 {servicio['descripcion']}\n"
            lista_servicios += f"   ⏰ {servicio['duracion']} minutos\n\n"
        
        # Guardar en conversación activa
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion]['servicios'] = servicios
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_servicio'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
        
        return f'''📋 *Servicios con {profesional_nombre}*

{lista_servicios}
Responde con el *número* del servicio que deseas:

💡 *O vuelve al menú principal con* *0*'''
        
    except Exception as e:
        print(f"❌ [DEBUG] Error en mostrar_servicios: {e}")
        return renderizar_plantilla('error_generico', negocio_id)
    
def verificar_configuracion_horarios_completa(negocio_id):
    """Diagnóstico completo de la configuración de horarios"""
    try:
        print(f"🔍 [DIAGNÓSTICO HORARIOS] Verificando configuración para negocio {negocio_id}")
        
        # 1. Verificar tabla configuracion_horarios
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='configuracion_horarios'")
        tabla_existe = cursor.fetchone()
        print(f"🔍 [DIAGNÓSTICO] Tabla 'configuracion_horarios' existe: {bool(tabla_existe)}")
        
        if not tabla_existe:
            print(f"🔍 [DIAGNÓSTICO] ❌ La tabla configuracion_horarios NO existe")
            conn.close()
            return False
        
        # 2. Verificar registros existentes
        cursor.execute('SELECT COUNT(*) FROM configuracion_horarios WHERE negocio_id = ?', (negocio_id,))
        count = cursor.fetchone()[0]
        print(f"🔍 [DIAGNÓSTICO] Registros existentes: {count}")
        
        # 3. Mostrar configuración actual
        cursor.execute('''
            SELECT dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin 
            FROM configuracion_horarios WHERE negocio_id = ? ORDER BY dia_semana
        ''', (negocio_id,))
        
        horarios = cursor.fetchall()
        print(f"🔍 [DIAGNÓSTICO] Configuración actual:")
        for dia, activo, inicio, fin, alm_ini, alm_fin in horarios:
            estado = "✅ ACTIVO" if activo else "❌ INACTIVO"
            almuerzo = f" | Almuerzo: {alm_ini}-{alm_fin}" if alm_ini and alm_fin else ""
            print(f"🔍 [DIAGNÓSTICO] - Día {dia}: {estado} ({inicio} - {fin}){almuerzo}")
        
        conn.close()
        
        # 4. Verificar funcionamiento para próximos días
        print(f"🔍 [DIAGNÓSTICO] Verificando disponibilidad próximos 7 días:")
        for i in range(7):
            fecha = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
            horario_dia = db.obtener_horarios_por_dia(negocio_id, fecha)
            estado = "✅ DISPONIBLE" if horario_dia.get('activo') else "❌ NO DISPONIBLE"
            print(f"🔍 [DIAGNÓSTICO] - {fecha}: {estado}")
            
        return True
        
    except Exception as e:
        print(f"❌ [DIAGNÓSTICO] Error en verificación de horarios: {e}")
        return False

def mostrar_fechas_disponibles(numero, negocio_id):
    """Mostrar fechas disponibles para agendar"""
    try:
        # Obtener próximas fechas donde el negocio está activo
        fechas_disponibles = obtener_proximas_fechas_disponibles(negocio_id)
        
        if not fechas_disponibles:
            return "❌ No hay fechas disponibles en los próximos días. Por favor, intenta más tarde."
        
        # Construir lista de fechas
        lista_fechas = ""
        for i, fecha_info in enumerate(fechas_disponibles, 1):
            lista_fechas += f"*{i}.* {fecha_info['mostrar']}\n"
        
        # Guardar en conversación activa
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion]['fechas_disponibles'] = fechas_disponibles
        conversaciones_activas[clave_conversacion]['estado'] = 'seleccionando_fecha'
        conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
        
        return f'''📅 *Selecciona una fecha*

{lista_fechas}
Responde con el *número* de la fecha que prefieres:

💡 *O vuelve al menú principal con* *0*'''
        
    except Exception as e:
        print(f"❌ Error en mostrar_fechas_disponibles: {e}")
        return renderizar_plantilla('error_generico', negocio_id)

def mostrar_disponibilidad(numero, negocio_id, fecha_seleccionada=None):
    """Mostrar horarios disponibles para una fecha específica - CORREGIDA"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if not fecha_seleccionada:
        fecha_seleccionada = conversaciones_activas[clave_conversacion].get('fecha_seleccionada', datetime.now().strftime('%Y-%m-%d'))
    
    # ✅ VERIFICAR SI EL DÍA ESTÁ ACTIVO
    horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha_seleccionada)
    
    if not horarios_dia or not horarios_dia['activo']:
        # Obtener información del negocio para el mensaje
        negocio = db.obtener_negocio_por_id(negocio_id)
        config_negocio = json.loads(negocio['configuracion']) if negocio['configuracion'] else {}
        
        fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
        mensaje = f"❌ *{negocio['nombre']}* no atiende el {fecha_formateada}.\n\n"
        mensaje += f"📅 *Horarios de atención:*\n"
        mensaje += f"{config_negocio.get('horario_atencion', 'Lunes a Sábado 9:00 AM - 7:00 PM')}\n\n"
        mensaje += "Por favor, selecciona otra fecha.\n\n"
        mensaje += "💡 *Vuelve al menú principal con* *0*"
        
        # Volver a mostrar fechas disponibles
        return mostrar_fechas_disponibles(numero, negocio_id)
    
    # Obtener datos de la conversación
    profesional_id = conversaciones_activas[clave_conversacion]['profesional_id']
    servicio_id = conversaciones_activas[clave_conversacion]['servicio_id']
    pagina = conversaciones_activas[clave_conversacion].get('pagina_horarios', 0)
    
    # ✅ CORRECCIÓN 3: Generar horarios disponibles con datos ACTUALIZADOS
    horarios_disponibles = generar_horarios_disponibles_actualizado(negocio_id, profesional_id, fecha_seleccionada, servicio_id)
    
    if not horarios_disponibles:
        fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
        return f"❌ No hay horarios disponibles para el {fecha_formateada}. Por favor, selecciona otra fecha.\n\n💡 *Vuelve al menú principal con* *0*"
    
    # Datos para el mensaje
    profesional_nombre = conversaciones_activas[clave_conversacion]['profesional_nombre']
    servicio_nombre = conversaciones_activas[clave_conversacion]['servicio_nombre']
    servicio_precio = conversaciones_activas[clave_conversacion]['servicio_precio']
    precio_formateado = f"${servicio_precio:,.0f}".replace(',', '.')
    fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
    
    # ✅ CORRECCIÓN: Paginación reducida a 6 horarios por página
    horarios_por_pagina = 6  # Cambiado de 8 a 6 para evitar conflicto con opciones 7,8,9
    inicio = pagina * horarios_por_pagina
    fin = inicio + horarios_por_pagina
    horarios_pagina = horarios_disponibles[inicio:fin]
    
    # Construir lista de horarios
    lista_horarios = ""
    for i, hora in enumerate(horarios_pagina, 1):
        lista_horarios += f"*{i}.* {hora}\n"
    
    # ✅ CORRECCIÓN: Opciones de navegación mejoradas
    opciones_navegacion = "\n💡 *Opciones de navegación:*\n"
    opciones_navegacion += f"*1-{len(horarios_pagina)}* - Seleccionar horario\n"
    
    total_paginas = (len(horarios_disponibles) + horarios_por_pagina - 1) // horarios_por_pagina
    pagina_actual = pagina + 1
    
    if pagina_actual < total_paginas:
        horarios_restantes = len(horarios_disponibles) - fin
        opciones_navegacion += f"*9* - ➡️ Siguiente página ({horarios_restantes} horarios más)\n"
    
    if pagina > 0:
        opciones_navegacion += f"*8* - ⬅️ Página anterior\n"
        
    opciones_navegacion += "*7* - 📅 Cambiar fecha\n"
    opciones_navegacion += f"*0* - ↩️ Volver al menú principal\n"
    opciones_navegacion += f"\n📄 Página {pagina_actual} de {total_paginas}"
    
    # Guardar datos para paginación
    conversaciones_activas[clave_conversacion]['todos_horarios'] = horarios_disponibles
    conversaciones_activas[clave_conversacion]['fecha_seleccionada'] = fecha_seleccionada
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    return f'''📅 *Horarios disponibles con {profesional_nombre}* ({fecha_formateada})
💼 *Servicio:* {servicio_nombre} - {precio_formateado}

{lista_horarios}
{opciones_navegacion}'''

def mostrar_mis_citas(numero, negocio_id):
    """Mostrar citas del cliente - USANDO PLANTILLAS"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora, s.nombre as servicio, c.estado, p.nombre as profesional_nombre
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            JOIN profesionales p ON c.profesional_id = p.id
            WHERE c.cliente_telefono = ? AND c.negocio_id = ? AND c.fecha >= date('now')
            ORDER BY c.fecha, c.hora
        ''', (numero, negocio_id))
        
        citas = cursor.fetchall()
        conn.close()
        
        if not citas:
            return renderizar_plantilla('sin_citas', negocio_id)
        
        # Construir lista de citas
        nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id) or 'Cliente'
        respuesta = f"📋 *Tus citas programadas* - {nombre_cliente}:\n\n"
        
        for id_cita, fecha, hora, servicio, estado, profesional_nombre in citas:
            fecha_str = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m')
            emoji = "✅" if estado == 'confirmado' else "❌"
            respuesta += f"{emoji} *{fecha_str}* - {hora}\n"
            respuesta += f"   👨‍💼 {profesional_nombre} - {servicio}\n"
            respuesta += f"   🎫 ID: #{id_cita}\n\n"
        
        respuesta += "Para cancelar responde: *3*"
        respuesta += "\n\n💡 *O vuelve al menú principal con* *0*"
        
        return respuesta
        
    except Exception as e:
        print(f"❌ Error mostrando citas: {e}")
        return renderizar_plantilla('error_generico', negocio_id)

def mostrar_citas_para_cancelar(numero, negocio_id):
    """Mostrar citas que pueden ser canceladas - MEJORADO"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora, p.nombre as profesional_nombre, s.nombre as servicio_nombre
            FROM citas c
            JOIN profesionales p ON c.profesional_id = p.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.cliente_telefono = ? AND c.negocio_id = ? AND c.fecha >= date('now') AND c.estado = 'confirmado'
            ORDER BY c.fecha, c.hora
        ''', (numero, negocio_id))
        
        citas = cursor.fetchall()
        conn.close()
        
        if not citas:
            clave_conversacion = f"{numero}_{negocio_id}"
            if clave_conversacion in conversaciones_activas:
                del conversaciones_activas[clave_conversacion]
            return "❌ No tienes citas para cancelar.\n\n💡 *Vuelve al menú principal con* *0*"
        
        if len(citas) == 1:
            # Solo una cita, cancelar directamente
            cita_id = citas[0][0]
            return procesar_cancelacion_directa(numero, str(cita_id), negocio_id)
        
        # Construir lista de citas para cancelar
        nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id) or 'Cliente'
        respuesta = f"❌ *Citas para cancelar* - {nombre_cliente}:\n\n"
        
        for id_cita, fecha, hora, profesional_nombre, servicio_nombre in citas:
            fecha_str = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m')
            respuesta += f"📅 {fecha_str} - {hora}\n"
            respuesta += f"   👨‍💼 {profesional_nombre} - {servicio_nombre}\n"
            respuesta += f"   🎫 ID: #{id_cita}\n\n"
        
        respuesta += "\nResponde con el *ID* de la cita que quieres cancelar.\nEjemplo: *123*"
        respuesta += "\n\n💡 *O vuelve al menú principal con* *0*"
        
        # Guardar citas disponibles para cancelación
        clave_conversacion = f"{numero}_{negocio_id}"
        conversaciones_activas[clave_conversacion]['citas_disponibles'] = {str(t[0]): t for t in citas}
        
        return respuesta
        
    except Exception as e:
        print(f"❌ Error mostrando citas para cancelar: {e}")
        clave_conversacion = f"{numero}_{negocio_id}"
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return renderizar_plantilla('error_generico', negocio_id)

def mostrar_ayuda(negocio_id):
    """Mostrar mensaje de ayuda"""
    return renderizar_plantilla('ayuda_general', negocio_id)

# =============================================================================
# LÓGICA DE CONVERSACIÓN CONTINUA (MEJORADA)
# =============================================================================

def continuar_conversacion(numero, mensaje, negocio_id):
    """Continuar conversación basada en el estado actual - MEJORADO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if clave_conversacion not in conversaciones_activas:
        # ✅ CORRECCIÓN 4: Si la sesión expiró, mostrar menú principal
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
        else:
            # Estado no reconocido - reiniciar
            if clave_conversacion in conversaciones_activas:
                del conversaciones_activas[clave_conversacion]
            return saludo_inicial(numero, negocio_id)
        
    except Exception as e:
        print(f"❌ Error en continuar_conversacion: {e}")
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return renderizar_plantilla('error_generico', negocio_id)

def procesar_nombre_cliente(numero, mensaje, negocio_id):
    """Procesar nombre del cliente nuevo - MEJORADO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    nombre = mensaje.strip()
    if len(nombre) < 2:
        return "Por favor, ingresa un nombre válido:\n\n💡 *O vuelve al menú principal con* *0*"
    
    print(f"🔧 DEBUG: Procesando nombre '{nombre}' para {numero}")
    
    # ✅ CORRECCIÓN: Guardar el nombre creando una cita de prueba
    try:
        # Crear una cita de prueba en el pasado para que el sistema recuerde al cliente
        fecha_pasado = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Obtener un profesional y servicio por defecto
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM profesionales WHERE negocio_id = ? AND activo = 1 LIMIT 1', (negocio_id,))
        profesional = cursor.fetchone()
        profesional_id = profesional[0] if profesional else 1
        
        cursor.execute('SELECT id FROM servicios WHERE negocio_id = ? AND activo = 1 LIMIT 1', (negocio_id,))
        servicio = cursor.fetchone()
        servicio_id = servicio[0] if servicio else 1
        
        conn.close()
        
        # Crear cita en el PASADO (para que no aparezca en citas futuras)
        cita_id = db.agregar_cita(negocio_id, profesional_id, numero, fecha_pasado, '10:00', servicio_id, nombre)
        
        if cita_id:
            print(f"✅ DEBUG: Cita de prueba creada exitosamente. ID: {cita_id}")
            
            # ✅ CORRECCIÓN IMPORTANTE: Actualizar el estado a 'completado' para que no aparezca en listados
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE citas SET estado = "completado" WHERE id = ?', (cita_id,))
            conn.commit()
            conn.close()
            print(f"✅ DEBUG: Cita marcada como completada")
        else:
            print(f"❌ DEBUG: No se pudo crear cita de prueba")
            
    except Exception as e:
        print(f"⚠️ DEBUG: Error creando cita de prueba: {e}")
    
    # ✅ CORRECCIÓN: Limpiar conversación activa inmediatamente después de procesar el nombre
    if clave_conversacion in conversaciones_activas:
        del conversaciones_activas[clave_conversacion]
    
    # ✅ CORRECCIÓN: Enviar el menú principal personalizado
    return renderizar_plantilla('menu_principal', negocio_id, {
        'cliente_nombre': nombre
    })

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
        return f"❌ Número inválido. Por favor, elige entre 1 y {len(profesionales)}\n\n💡 *O vuelve al menú principal con* *0*"
    
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
        return f"❌ Número inválido. Por favor, elige entre 1 y {len(servicios)}\n\n💡 *O vuelve al menú principal con* *0*"
    
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
    """Procesar selección de fecha"""
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
        return f"❌ Número inválido. Por favor, elige entre 1 y {len(fechas_disponibles)}\n\n💡 *O vuelve al menú principal con* *0*"
    
    # Guardar fecha seleccionada
    fecha_index = int(mensaje) - 1
    fecha_seleccionada = fechas_disponibles[fecha_index]['fecha']
    
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
            return "ℹ️ Ya estás en la última página de horarios.\n\n💡 *Selecciona un horario o usa otra opción*"
        
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
        return f"❌ Por favor, ingresa un número válido.\n\n💡 *O vuelve al menú principal con* *0*"
    
    mensaje_num = int(mensaje)
    
    # ✅ CORRECCIÓN: Solo procesar números 1-6 como horarios (evitar conflicto con 7,8,9)
    if mensaje_num < 1 or mensaje_num > len(horarios_pagina):
        return f"❌ Número inválido. Por favor, elige entre 1 y {len(horarios_pagina)}\n\n💡 *O vuelve al menú principal con* *0*"
    
    # Guardar horario seleccionado y pedir confirmación
    hora_index = mensaje_num - 1
    hora_seleccionada = horarios_pagina[hora_index]
    
    conversaciones_activas[clave_conversacion]['hora_seleccionada'] = hora_seleccionada
    conversaciones_activas[clave_conversacion]['estado'] = 'confirmando_cita'
    conversaciones_activas[clave_conversacion]['timestamp'] = datetime.now()
    
    # Obtener datos para la confirmación
    nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre', 
                                                                   db.obtener_nombre_cliente(numero, negocio_id) or 'Cliente')
    profesional_nombre = conversaciones_activas[clave_conversacion]['profesional_nombre']
    servicio_nombre = conversaciones_activas[clave_conversacion]['servicio_nombre']
    servicio_precio = conversaciones_activas[clave_conversacion]['servicio_precio']
    precio_formateado = f"${servicio_precio:,.0f}".replace(',', '.')
    fecha_seleccionada = conversaciones_activas[clave_conversacion]['fecha_seleccionada']
    fecha_formateada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').strftime('%d/%m/%Y')
    
    return f'''✅ *Confirmar cita*

Hola {nombre_cliente}, ¿confirmas tu cita?

👨‍💼 *Profesional:* {profesional_nombre}
💼 *Servicio:* {servicio_nombre}
💰 *Precio:* {precio_formateado}
📅 *Fecha:* {fecha_formateada}
⏰ *Hora:* {hora_seleccionada}

Responde:
*1* - ✅ Confirmar cita
*2* - ❌ Cancelar agendamiento
*0* - ↩️ Volver al menú principal'''

def procesar_confirmacion_cita(numero, mensaje, negocio_id):
    """Procesar confirmación de la cita - MEJORADO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    if mensaje == '1':
        # Confirmar cita
        try:
            hora = conversaciones_activas[clave_conversacion]['hora_seleccionada']
            fecha = conversaciones_activas[clave_conversacion]['fecha_seleccionada']
            profesional_id = conversaciones_activas[clave_conversacion]['profesional_id']
            servicio_id = conversaciones_activas[clave_conversacion]['servicio_id']
            
            # Obtener nombre del cliente
            nombre_cliente = conversaciones_activas[clave_conversacion].get('cliente_nombre')
            if not nombre_cliente:
                nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id)
            if not nombre_cliente:
                nombre_cliente = 'Cliente'
            
            # Agendar cita
            cita_id = db.agregar_cita(negocio_id, profesional_id, numero, fecha, hora, servicio_id, nombre_cliente)
            
            if cita_id:
                # Datos para la plantilla de confirmación
                profesional_nombre = conversaciones_activas[clave_conversacion]['profesional_nombre']
                servicio_nombre = conversaciones_activas[clave_conversacion]['servicio_nombre']
                servicio_precio = conversaciones_activas[clave_conversacion]['servicio_precio']
                precio_formateado = f"${servicio_precio:,.0f}".replace(',', '.')
                fecha_formateada = datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m/%Y')
                
                # Limpiar conversación
                if clave_conversacion in conversaciones_activas:
                    del conversaciones_activas[clave_conversacion]
                
                # Usar plantilla para el mensaje de confirmación
                return renderizar_plantilla('cita_confirmada', negocio_id, {
                    'cliente_nombre': nombre_cliente,
                    'profesional_nombre': profesional_nombre,
                    'servicio_nombre': servicio_nombre,
                    'precio_formateado': precio_formateado,
                    'fecha': fecha_formateada,
                    'hora': hora,
                    'cita_id': cita_id
                })
            else:
                if clave_conversacion in conversaciones_activas:
                    del conversaciones_activas[clave_conversacion]
                return renderizar_plantilla('error_generico', negocio_id)
                
        except Exception as e:
            print(f"❌ Error confirmando cita: {e}")
            if clave_conversacion in conversaciones_activas:
                del conversaciones_activas[clave_conversacion]
            return renderizar_plantilla('error_generico', negocio_id)
    else:
        # Cancelar agendamiento
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return "❌ Agendamiento cancelado. Si necesitas algo más, ¡estaré aquí!"

def procesar_cancelacion_cita(numero, mensaje, negocio_id):
    """Procesar cancelación de cita - MEJORADO"""
    clave_conversacion = f"{numero}_{negocio_id}"
    
    if mensaje == '0':
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    if 'citas_disponibles' not in conversaciones_activas[clave_conversacion]:
        # ✅ CORRECCIÓN 4: Si la sesión expiró durante cancelación, mostrar menú principal
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return "❌ Sesión de cancelación expirada.\n\n" + saludo_inicial(numero, negocio_id)
    
    citas_disponibles = conversaciones_activas[clave_conversacion]['citas_disponibles']
    
    if mensaje not in citas_disponibles:
        return "❌ ID de cita inválido. Por favor, ingresa un ID de la lista anterior.\n\n💡 *O vuelve al menú principal con* *0*"
    
    # Cancelar cita
    try:
        cita_id = mensaje
        cita_info = citas_disponibles[cita_id]
        
        # Actualizar estado en base de datos
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE citas SET estado = "cancelado" WHERE id = ? AND negocio_id = ?', 
                      (cita_id, negocio_id))
        
        conn.commit()
        conn.close()
        
        # Limpiar conversación
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        
        # Usar plantilla para mensaje de cancelación
        nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id) or 'Cliente'
        fecha_str = datetime.strptime(cita_info[1], '%Y-%m-%d').strftime('%d/%m')
        
        return renderizar_plantilla('cita_cancelada', negocio_id, {
            'cliente_nombre': nombre_cliente,
            'fecha': fecha_str,
            'hora': cita_info[2]
        })
        
    except Exception as e:
        print(f"❌ Error cancelando cita: {e}")
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return renderizar_plantilla('error_generico', negocio_id)

def procesar_cancelacion_directa(numero, cita_id, negocio_id):
    """Procesar cancelación cuando solo hay una cita - GENÉRICO"""
    if cita_id == '0':
        clave_conversacion = f"{numero}_{negocio_id}"
        if clave_conversacion in conversaciones_activas:
            del conversaciones_activas[clave_conversacion]
        return saludo_inicial(numero, negocio_id)
    
    # Cancelar cita directamente
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE citas SET estado = "cancelado" WHERE id = ? AND negocio_id = ?', 
                  (cita_id, negocio_id))
    
    conn.commit()
    conn.close()
    
    nombre_cliente = db.obtener_nombre_cliente(numero, negocio_id) or 'Cliente'
    
    return f'''❌ *Cita cancelada*

Hola {nombre_cliente}, has cancelado tu cita (ID: #{cita_id}).

Esperamos verte pronto en otra ocasión.'''

# =============================================================================
# FUNCIONES AUXILIARES (MANTENIDAS)
# =============================================================================

def obtener_proximas_fechas_disponibles(negocio_id, dias_a_mostrar=7):
    """Obtener las próximas fechas donde el negocio está activo - CORREGIDA"""
    fechas_disponibles = []
    fecha_actual = datetime.now()
    
    print(f"🔧 [DEBUG] OBTENER_FECHAS_DISPONIBLES - Negocio: {negocio_id}")
    
    # ✅ CORRECCIÓN: Mostrar siempre los próximos X días, NO solo desde hoy
    for i in range(dias_a_mostrar):
        fecha = fecha_actual + timedelta(days=i)
        fecha_str = fecha.strftime('%Y-%m-%d')
        
        # ✅ VERIFICAR SI EL DÍA ESTÁ ACTIVO (con la nueva conversión)
        horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha_str)
        
        print(f"🔧 [DEBUG] Fecha {fecha_str}: activo={horarios_dia.get('activo')}")
        
        if horarios_dia and horarios_dia['activo']:
            # Formatear fecha para mostrar
            if i == 0:
                fecha_formateada = "Hoy"
            elif i == 1:
                fecha_formateada = "Mañana"
            else:
                fecha_formateada = fecha.strftime('%A %d/%m').title()
                # Traducir días
                fecha_formateada = fecha_formateada.replace('Monday', 'Lunes')\
                                                  .replace('Tuesday', 'Martes')\
                                                  .replace('Wednesday', 'Miércoles')\
                                                  .replace('Thursday', 'Jueves')\
                                                  .replace('Friday', 'Viernes')\
                                                  .replace('Saturday', 'Sábado')\
                                                  .replace('Sunday', 'Domingo')
            
            fechas_disponibles.append({
                'fecha': fecha_str,
                'mostrar': fecha_formateada
            })
            print(f"🔧 [DEBUG] ✅ Fecha {fecha_str} agregada como disponible")
        else:
            print(f"🔧 [DEBUG] ❌ Fecha {fecha_str} NO disponible (activo=False)")
    
    print(f"🔧 [DEBUG] Total fechas disponibles: {len(fechas_disponibles)}")
    return fechas_disponibles

def generar_horarios_disponibles_actualizado(negocio_id, profesional_id, fecha, servicio_id):
    """Generar horarios disponibles considerando la configuración por días"""
    print(f"🔍 Generando horarios para negocio {negocio_id}, profesional {profesional_id}, fecha {fecha}")
    
    # ✅ VERIFICAR SI EL DÍA ESTÁ ACTIVO
    horarios_dia = db.obtener_horarios_por_dia(negocio_id, fecha)
    
    if not horarios_dia or not horarios_dia['activo']:
        print(f"❌ Día no activo para la fecha {fecha}")
        return []  # Día no activo, no hay horarios disponibles
    
    print(f"✅ Día activo. Horario: {horarios_dia['hora_inicio']} - {horarios_dia['hora_fin']}")
    
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
        
        # Verificar si no es horario de almuerzo
        if not es_horario_almuerzo(hora_actual, horarios_dia):
            # Verificar disponibilidad
            if esta_disponible(hora_actual, duracion_servicio, citas_ocupadas, horarios_dia):
                horarios.append(hora_str)
                print(f"✅ Horario disponible: {hora_str}")
        
        hora_actual += timedelta(minutes=30)
    
    print(f"🎯 Total horarios disponibles: {len(horarios)}")
    return horarios

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

def enviar_mensaje_whatsapp(destino, mensaje):
    """Enviar mensaje de WhatsApp usando Twilio"""
    # Configuración Twilio (la misma que ya está arriba)
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER')
    
    client = None
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    
    if not client:
        print(f"⚠️ Twilio no configurado. Mensaje simulado para {destino}: {mensaje}")
        return True
    
    try:
        message = client.messages.create(
            body=mensaje,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f'whatsapp:{destino}'
        )
        print(f"✅ Mensaje enviado a {destino}: {message.sid}")
        return True
    
    except Exception as e:
        print(f"❌ Error enviando mensaje a {destino}: {e}")
        return False

# =============================================================================
# FUNCIONES PARA RECORDATORIOS AUTOMÁTICOS
# =============================================================================

def enviar_recordatorio_24h(cita):
    """Enviar recordatorio 24 horas antes de la cita"""
    try:
        negocio_id = cita['negocio_id']
        cliente_telefono = cita['cliente_telefono']
        
        # Obtener plantilla de recordatorio
        plantilla = database.obtener_plantilla(negocio_id, 'recordatorio_24h')
        if not plantilla:
            # Plantilla por defecto si no existe
            plantilla = '''
⏰ *RECORDATORIO - {nombre_negocio}*

¡Hola {cliente_nombre}! 

Te recordamos que tienes una cita programada para mañana:

📅 *Fecha:* {fecha}
⏰ *Hora:* {hora}
💼 *Servicio:* {servicio_nombre}
👨‍💼 *Profesional:* {profesional_nombre}

📍 *Dirección:* {direccion}
📞 *Contacto:* {telefono_contacto}

*Importante:* 
- Puedes cancelar hasta 2 horas antes
- Llega 5 minutos antes de tu horario

¡Te esperamos!
            '''
        
        # Obtener configuración del negocio
        negocio = database.obtener_negocio_por_id(negocio_id)
        config = json.loads(negocio['configuracion']) if negocio['configuracion'] else {}
        
        # Preparar variables para la plantilla
        variables = {
            'nombre_negocio': negocio['nombre'],
            'cliente_nombre': cita['cliente_nombre'] or 'Cliente',
            'fecha': cita['fecha'],
            'hora': cita['hora'],
            'servicio_nombre': cita['servicio_nombre'],
            'profesional_nombre': cita['profesional_nombre'],
            'direccion': config.get('direccion', 'Calle Principal #123'),
            'telefono_contacto': config.get('telefono_contacto', 'No especificado')
        }
        
        # Formatear mensaje
        mensaje = plantilla.format(**variables)
        
        # Enviar mensaje
        enviar_mensaje_whatsapp(cliente_telefono, mensaje)
        
        print(f"✅ Recordatorio 24h enviado a {cliente_telefono}")
        return True
        
    except Exception as e:
        print(f"❌ Error enviando recordatorio 24h: {e}")
        return False

def enviar_recordatorio_1h(cita):
    """Enviar recordatorio 1 hora antes de la cita"""
    try:
        negocio_id = cita['negocio_id']
        cliente_telefono = cita['cliente_telefono']
        
        # Obtener plantilla de recordatorio
        plantilla = database.obtener_plantilla(negocio_id, 'recordatorio_1h')
        if not plantilla:
            # Plantilla por defecto si no existe
            plantilla = '''
🔔 *RECORDATORIO INMEDIATO - {nombre_negocio}*

¡Hola {cliente_nombre}! 

Tu cita es en aproximadamente 1 hora:

⏰ *Hora:* {hora} (hoy)
💼 *Servicio:* {servicio_nombre}
👨‍💼 *Profesional:* {profesional_nombre}

📍 *Dirección:* {direccion}

*Recuerda:* 
- Llega 5 minutos antes
- Trae todo lo necesario para tu servicio

¡Nos vemos pronto!
            '''
        
        # Obtener configuración del negocio
        negocio = database.obtener_negocio_por_id(negocio_id)
        config = json.loads(negocio['configuracion']) if negocio['configuracion'] else {}
        
        # Preparar variables para la plantilla
        variables = {
            'nombre_negocio': negocio['nombre'],
            'cliente_nombre': cita['cliente_nombre'] or 'Cliente',
            'hora': cita['hora'],
            'servicio_nombre': cita['servicio_nombre'],
            'profesional_nombre': cita['profesional_nombre'],
            'direccion': config.get('direccion', 'Calle Principal #123')
        }
        
        # Formatear mensaje
        mensaje = plantilla.format(**variables)
        
        # Enviar mensaje
        enviar_mensaje_whatsapp(cliente_telefono, mensaje)
        
        print(f"✅ Recordatorio 1h enviado a {cliente_telefono}")
        return True
        
    except Exception as e:
        print(f"❌ Error enviando recordatorio 1h: {e}")
        return False

def notificar_profesional_nueva_cita(cita):
    """Notificar al profesional sobre una nueva cita"""
    try:
        negocio_id = cita['negocio_id']
        profesional_id = cita['profesional_id']
        
        # Obtener información del profesional
        profesional = database.obtener_profesional_por_id(profesional_id, negocio_id)
        if not profesional or not profesional.get('telefono'):
            return False
        
        telefono_profesional = profesional['telefono']
        
        # Plantilla de notificación para profesionales
        plantilla = '''
📋 *NUEVA CITA AGENDADA*

Tienes una nueva cita programada:

👤 *Cliente:* {cliente_nombre}
📞 *Teléfono:* {cliente_telefono}
💼 *Servicio:* {servicio_nombre}
💰 *Precio:* {precio}
📅 *Fecha:* {fecha}
⏰ *Hora:* {hora}

¡Prepárate para atender a tu cliente!
        '''
        
        # Preparar variables
        variables = {
            'cliente_nombre': cita['cliente_nombre'] or 'Cliente',
            'cliente_telefono': cita['cliente_telefono'],
            'servicio_nombre': cita['servicio_nombre'],
            'precio': f"${cita['precio']:,.0f}" if cita.get('precio') else 'No especificado',
            'fecha': cita['fecha'],
            'hora': cita['hora']
        }
        
        # Formatear mensaje
        mensaje = plantilla.format(**variables)
        
        # Enviar mensaje al profesional
        enviar_mensaje_whatsapp(telefono_profesional, mensaje)
        
        print(f"✅ Notificación enviada al profesional {profesional['nombre']}")
        return True
        
    except Exception as e:
        print(f"❌ Error notificando al profesional: {e}")
        return False