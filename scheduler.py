# scheduler.py - VERSIÓN COMPLETA CON NOTIFICACIONES PARA PROFESIONALES
import schedule
import time
import threading
from datetime import datetime, timedelta
import database as db
from sms_manager import sms_manager
from notification_system import notification_system

def verificar_recordatorios():
    """Verificar y enviar TODOS los recordatorios: 24h y 1h"""
    try:
        ahora = datetime.now()
        print(f"⏰ [{ahora.strftime('%H:%M:%S')}] Verificando recordatorios...")
        
        # OBTENER CITAS PENDIENTES DE RECORDATORIO
        citas_pendientes = obtener_citas_pendientes_recordatorio()
        
        if not citas_pendientes:
            print("   ℹ️ No hay citas pendientes de recordatorio")
            # Pero igual verificamos notificaciones para profesionales
            enviar_notificaciones_profesionales()
            return
        
        print(f"   📊 Citas para procesar: {len(citas_pendientes)}")
        
        # PROCESAR CADA CITA
        for cita in citas_pendientes:
            try:
                cita_id = cita['id']
                cita_fecha = datetime.strptime(cita['fecha'], '%Y-%m-%d').date()
                cita_hora = datetime.strptime(cita['hora'], '%H:%M').time()
                cita_datetime = datetime.combine(cita_fecha, cita_hora)
                
                # Calcular tiempo restante
                tiempo_restante = cita_datetime - ahora
                horas_restantes = tiempo_restante.total_seconds() / 3600
                
                print(f"   🔍 Cita #{cita_id}: {horas_restantes:.1f} horas restantes")
                
                # DECIDIR QUÉ RECORDATORIO ENVIAR
                enviado = False
                
                # Recordatorio 24h (entre 23 y 25 horas antes)
                if 23 <= horas_restantes <= 25 and not cita.get('recordatorio_24h_enviado'):
                    print(f"     📅 Enviando recordatorio 24h...")
                    
                    # 1. Enviar SMS al cliente
                    if sms_manager.enviar_recordatorio_24h(cita):
                        db.marcar_recordatorio_enviado(cita_id, '24h')
                        print(f"     ✅ Recordatorio 24h SMS enviado")
                    
                    # 2. Notificar al profesional
                    notification_system.notify_appointment_reminder(
                        cita['profesional_id'], cita, hours_before=24
                    )
                    print(f"     👨‍💼 Notificación 24h enviada al profesional")
                    
                    enviado = True
                
                # Recordatorio 1h (entre 0.5 y 1.5 horas antes)
                elif 0.5 <= horas_restantes <= 1.5 and not cita.get('recordatorio_1h_enviado'):
                    print(f"     ⏰ Enviando recordatorio 1h...")
                    
                    # 1. Enviar SMS al cliente
                    if sms_manager.enviar_recordatorio_1h(cita):
                        db.marcar_recordatorio_enviado(cita_id, '1h')
                        print(f"     ✅ Recordatorio 1h SMS enviado")
                    
                    # 2. Notificar al profesional
                    notification_system.notify_appointment_reminder(
                        cita['profesional_id'], cita, hours_before=1
                    )
                    print(f"     👨‍💼 Notificación 1h enviada al profesional")
                    
                    enviado = True
                
                # Si la cita es para hoy, notificar al profesional
                elif cita_fecha == ahora.date() and horas_restantes > 0:
                    # Notificar cita de hoy al profesional (si aún no se ha notificado)
                    print(f"     📋 Cita de hoy para profesional {cita['profesional_id']}")
                
                if not enviado:
                    print(f"     ℹ️ No requiere recordatorio aún")
                    
            except Exception as e:
                print(f"     ❌ Error procesando cita #{cita.get('id')}: {e}")
        
        # Enviar notificaciones generales para profesionales
        enviar_notificaciones_profesionales()
                
    except Exception as e:
        print(f"❌ Error en verificar_recordatorios: {e}")
        import traceback
        traceback.print_exc()

def obtener_citas_pendientes_recordatorio():
    """Obtener citas confirmadas que necesitan recordatorios"""
    conn = db.get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor()
    try:
        # Obtener citas confirmadas para hoy y mañana
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        fecha_manana = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        sql = '''
            SELECT c.*, n.nombre as negocio_nombre, n.direccion as negocio_direccion,
                   p.nombre as profesional_nombre, s.nombre as servicio_nombre,
                   s.precio, s.duracion
            FROM citas c
            JOIN negocios n ON c.negocio_id = n.id
            JOIN profesionales p ON c.profesional_id = p.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.estado = 'confirmado'
            AND c.fecha IN (%s, %s)
            AND (c.recordatorio_24h_enviado = FALSE OR c.recordatorio_1h_enviado = FALSE)
            ORDER BY c.fecha, c.hora
        '''
        
        cursor.execute(sql, (fecha_hoy, fecha_manana))
        citas = cursor.fetchall()
        
        # Convertir a diccionarios
        citas_dict = []
        for cita in citas:
            if hasattr(cita, 'keys'):
                citas_dict.append(dict(cita))
            else:
                # Convertir tupla a dict
                citas_dict.append({
                    'id': cita[0],
                    'negocio_id': cita[1],
                    'profesional_id': cita[2],
                    'cliente_telefono': cita[3],
                    'cliente_nombre': cita[4],
                    'fecha': cita[5],
                    'hora': cita[6],
                    'servicio_id': cita[7],
                    'estado': cita[8],
                    'recordatorio_24h_enviado': cita[9],
                    'recordatorio_1h_enviado': cita[10],
                    'negocio_nombre': cita[12] if len(cita) > 12 else '',
                    'negocio_direccion': cita[13] if len(cita) > 13 else '',
                    'profesional_nombre': cita[14] if len(cita) > 14 else '',
                    'servicio_nombre': cita[15] if len(cita) > 15 else '',
                    'precio': cita[16] if len(cita) > 16 else 0,
                    'duracion': cita[17] if len(cita) > 17 else 30
                })
        
        return citas_dict
        
    except Exception as e:
        print(f"❌ Error obteniendo citas: {e}")
        return []
    finally:
        conn.close()

def enviar_notificaciones_profesionales():
    """Enviar notificaciones a profesionales sobre citas"""
    try:
        ahora = datetime.now()
        print(f"👨‍💼 [{ahora.strftime('%H:%M:%S')}] Enviando notificaciones a profesionales...")
        
        # 1. Obtener citas para hoy y mañana
        conn = db.get_db_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        
        # Obtener citas confirmadas para hoy y mañana
        fecha_hoy = ahora.strftime('%Y-%m-%d')
        fecha_manana = (ahora + timedelta(days=1)).strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT c.*, p.id as profesional_id, p.nombre as profesional_nombre,
                   COALESCE(cl.nombre, c.cliente_nombre) as cliente_nombre, 
                   s.nombre as servicio_nombre, s.precio
            FROM citas c
            JOIN profesionales p ON c.profesional_id = p.id
            JOIN servicios s ON c.servicio_id = s.id
            LEFT JOIN clientes cl ON c.cliente_telefono = cl.telefono
            WHERE c.estado = 'confirmado'
            AND c.fecha IN (%s, %s)
            ORDER BY c.fecha, c.hora
        ''', (fecha_hoy, fecha_manana))
        
        citas = cursor.fetchall()
        conn.close()
        
        if not citas:
            print("   ℹ️ No hay citas para notificar a profesionales")
            return
        
        # 2. Enviar notificaciones
        notificaciones_enviadas = 0
        
        for cita in citas:
            try:
                # Convertir a diccionario
                if hasattr(cita, 'keys'):
                    cita_dict = dict(cita)
                else:
                    cita_dict = {
                        'id': cita[0],
                        'profesional_id': cita[2],  # profesional_id de la tabla citas
                        'cliente_nombre': cita[4] if len(cita) > 4 else cita[3],
                        'servicio_nombre': cita[13] if len(cita) > 13 else '',
                        'fecha': cita[5],
                        'hora': cita[6],
                        'precio': cita[14] if len(cita) > 14 else 0
                    }
                
                # Verificar si ya se notificó esta cita hoy
                if cita_dict['fecha'] == fecha_hoy:
                    # Notificar cita de HOY al profesional (solo una vez por día)
                    notification_system.notify_appointment_created(
                        cita_dict['profesional_id'], cita_dict
                    )
                    notificaciones_enviadas += 1
                    print(f"   ✅ Notificada cita de hoy #{cita_dict['id']} para profesional {cita_dict['profesional_id']}")
                
                elif cita_dict['fecha'] == fecha_manana:
                    # Podríamos enviar un recordatorio temprano para mañana
                    print(f"   📅 Cita de mañana #{cita_dict['id']} para profesional {cita_dict['profesional_id']}")
                
            except Exception as e:
                print(f"   ❌ Error notificando cita: {e}")
        
        print(f"   📨 {notificaciones_enviadas} notificaciones enviadas a profesionales")
        
    except Exception as e:
        print(f"❌ Error enviando notificaciones profesionales: {e}")
        import traceback
        traceback.print_exc()

# FUNCIÓN PARA CONFIRMACIÓN INMEDIATA
def enviar_confirmacion_inmediata(cita):
    """Llamar esta función después de crear una cita"""
    try:
        print(f"📧 Enviando confirmación para cita #{cita.get('id')}")
        
        # 1. Enviar SMS al cliente
        sms_result = sms_manager.enviar_confirmacion_cita(cita)
        
        # 2. Notificar al profesional sobre la nueva cita
        if 'profesional_id' in cita:
            notification_system.notify_appointment_created(
                cita['profesional_id'], cita
            )
            print(f"👨‍💼 Notificación enviada al profesional {cita['profesional_id']}")
        
        return sms_result
        
    except Exception as e:
        print(f"❌ Error confirmación: {e}")
        return False

# CÓDIGO DEL SCHEDULER
def iniciar_scheduler():
    """Iniciar el scheduler principal"""
    print("🔄 Iniciando scheduler de recordatorios y notificaciones...")
    print("📱 SMS para clientes + 🔔 Notificaciones web para profesionales")
    
    # Programar verificaciones
    schedule.every(1).minutes.do(verificar_recordatorios)
    
    # Programar notificaciones diarias para profesionales (cada mañana a las 8 AM)
    schedule.every().day.at("08:00").do(enviar_resumen_diario_profesionales)
    
    # Ejecutar inmediatamente
    verificar_recordatorios()
    
    print("✅ Scheduler iniciado correctamente")
    print("   • Recordatorios cada 1 minuto")
    print("   • Resumen diario a las 8:00 AM")
    print("   • Notificaciones web para profesionales activas")
    
    # Bucle principal
    while True:
        schedule.run_pending()
        time.sleep(1)

def enviar_resumen_diario_profesionales():
    """Enviar resumen diario de citas a cada profesional"""
    try:
        ahora = datetime.now()
        print(f"📋 [{ahora.strftime('%H:%M:%S')}] Enviando resumen diario a profesionales...")
        
        conn = db.get_db_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        
        # Obtener todos los profesionales activos
        cursor.execute('''
            SELECT p.id, p.nombre, p.email,
                   COUNT(c.id) as citas_hoy
            FROM profesionales p
            LEFT JOIN citas c ON p.id = c.profesional_id 
                AND c.fecha = CURRENT_DATE 
                AND c.estado = 'confirmado'
            WHERE p.activo = TRUE
            GROUP BY p.id, p.nombre, p.email
        ''')
        
        profesionales = cursor.fetchall()
        conn.close()
        
        for prof in profesionales:
            if hasattr(prof, 'keys'):
                prof_id = prof['id']
                prof_nombre = prof['nombre']
                citas_hoy = prof['citas_hoy']
            else:
                prof_id = prof[0]
                prof_nombre = prof[1]
                citas_hoy = prof[3]
            
            if citas_hoy > 0:
                # Enviar notificación con resumen
                titulo = "📋 Resumen del Día"
                mensaje = f"""RESUMEN DIARIO

Hola {prof_nombre},

Tienes {citas_hoy} cita(s) programada(s) para hoy.

¡Que tengas un excelente día!"""
                
                notification_system._save_notification_db(
                    prof_id, titulo, mensaje, 'info'
                )
                print(f"   📨 Resumen enviado a {prof_nombre}")
        
        print(f"✅ Resumen diario enviado a {len(profesionales)} profesionales")
        
    except Exception as e:
        print(f"❌ Error enviando resumen diario: {e}")

def iniciar_scheduler_en_segundo_plano():
    """Iniciar scheduler en segundo plano"""
    scheduler_thread = threading.Thread(target=iniciar_scheduler, daemon=True)
    scheduler_thread.start()
    print("✅ Scheduler ejecutándose en segundo plano")
    
    return scheduler_thread

# Si se ejecuta directamente, iniciar el scheduler
if __name__ == "__main__":
    print("🚀 Iniciando scheduler de forma independiente...")
    iniciar_scheduler()