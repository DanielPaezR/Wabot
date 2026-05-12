# scheduler.py - VERSIÓN COMPLETA CON RECORDATORIOS PUSH PARA CLIENTES
import schedule
import time
import threading
from datetime import datetime, timedelta
import database as db
from notification_system import notification_system

class AppointmentScheduler:
    """Scheduler para recordatorios de citas (profesional + cliente)"""
    
    def __init__(self):
        print("⏰ Scheduler iniciado")
        self.en_ejecucion = True
        self.ultima_ejecucion = None
        self.ultimo_log = None
    
    # ==================== FUNCIONES PRINCIPALES ====================
    
    def verificar_recordatorios(self):
        """Verificar y enviar recordatorios a profesionales y clientes"""
        try:
            ahora = datetime.now()
            
            # Solo log cada 10 minutos para no saturar
            if not hasattr(self, 'ultimo_log') or self.ultimo_log is None or \
               (ahora - self.ultimo_log).seconds >= 600:
                print(f"⏰ [{ahora.strftime('%H:%M')}] Scheduler activo")
                self.ultimo_log = ahora
            
            # Obtener citas pendientes de recordatorio
            citas_pendientes = self.obtener_citas_pendientes_recordatorio()
            
            if not citas_pendientes:
                return
            
            recordatorios_enviados = 0
            
            for cita in citas_pendientes:
                try:
                    cita_id = cita['id']
                    cita_fecha = cita.get('fecha')
                    cita_hora = cita.get('hora')
                    
                    if not cita_fecha or not cita_hora:
                        continue
                    
                    # Convertir a datetime
                    if isinstance(cita_fecha, str):
                        cita_fecha = datetime.strptime(cita_fecha, '%Y-%m-%d').date()
                    if isinstance(cita_hora, str):
                        cita_hora = datetime.strptime(cita_hora, '%H:%M').time()
                    
                    cita_datetime = datetime.combine(cita_fecha, cita_hora)
                    
                    # Calcular tiempo restante
                    tiempo_restante = cita_datetime - ahora
                    horas_restantes = tiempo_restante.total_seconds() / 3600
                    
                    # ============================================
                    # RECORDATORIO 24 HORAS
                    # ============================================
                    if 23 <= horas_restantes <= 25 and not cita.get('recordatorio_24h_enviado'):
                        # 1. Notificar al profesional (BD)
                        notif_id = notification_system.notify_appointment_reminder(
                            cita['profesional_id'], cita, hours_before=24
                        )
                        # 2. Enviar push al cliente
                        self.enviar_recordatorio_push_cliente(cita, 24)
                        # 3. Marcar como enviado
                        self.marcar_recordatorio_enviado(cita_id, '24h')
                        recordatorios_enviados += 1
                        print(f"📨 Recordatorio 24h enviado para cita #{cita_id}")
                    
                    # ============================================
                    # RECORDATORIO 1 HORA
                    # ============================================
                    elif 0.5 <= horas_restantes <= 1.5 and not cita.get('recordatorio_1h_enviado'):
                        # 1. Notificar al profesional (BD)
                        notif_id = notification_system.notify_appointment_reminder(
                            cita['profesional_id'], cita, hours_before=1
                        )
                        # 2. Enviar push al cliente
                        self.enviar_recordatorio_push_cliente(cita, 1)
                        # 3. Marcar como enviado
                        self.marcar_recordatorio_enviado(cita_id, '1h')
                        recordatorios_enviados += 1
                        print(f"📨 Recordatorio 1h enviado para cita #{cita_id}")
                            
                except Exception as e:
                    print(f"⚠️ Error procesando cita #{cita.get('id', '?')}: {e}")
                    continue
            
            if recordatorios_enviados > 0:
                print(f"📨 Total: {recordatorios_enviados} recordatorio(s) enviado(s)")
                        
        except Exception as e:
            print(f"❌ Error en recordatorios: {e}")
    
    def obtener_citas_pendientes_recordatorio(self):
        """Obtener citas confirmadas que necesitan recordatorios"""
        conn = db.get_db_connection()
        if not conn:
            return []
        
        cursor = conn.cursor()
        try:
            fecha_hoy = datetime.now().strftime('%Y-%m-%d')
            fecha_manana = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            fecha_pasadomanana = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
            
            sql = '''
                SELECT c.id, c.negocio_id, c.profesional_id, c.cliente_telefono,
                       COALESCE(cl.nombre, c.cliente_nombre) as cliente_nombre,
                       c.fecha, c.hora, c.servicio_id, c.estado,
                       c.recordatorio_24h_enviado, c.recordatorio_1h_enviado,
                       c.notificado_profesional, c.created_at,
                       s.nombre as servicio_nombre, s.precio, s.duracion,
                       p.nombre as profesional_nombre
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                JOIN profesionales p ON c.profesional_id = p.id
                LEFT JOIN clientes cl ON c.cliente_telefono = cl.telefono 
                    AND cl.negocio_id = c.negocio_id
                WHERE c.estado = 'confirmado'
                AND c.fecha IN (%s, %s, %s)
                AND (c.recordatorio_24h_enviado = FALSE OR c.recordatorio_1h_enviado = FALSE)
                ORDER BY c.fecha, c.hora
            '''
            
            cursor.execute(sql, (fecha_hoy, fecha_manana, fecha_pasadomanana))
            citas = cursor.fetchall()
            
            # Convertir a diccionarios con todas las claves necesarias
            citas_dict = []
            for row in citas:
                if hasattr(row, 'keys'):  # RealDictCursor
                    citas_dict.append(dict(row))
                else:  # Tupla
                    citas_dict.append({
                        'id': row[0],
                        'negocio_id': row[1],
                        'profesional_id': row[2],
                        'cliente_telefono': row[3],
                        'cliente_nombre': row[4] or 'Cliente',
                        'fecha': row[5],
                        'hora': row[6],
                        'servicio_id': row[7],
                        'estado': row[8],
                        'recordatorio_24h_enviado': row[9],
                        'recordatorio_1h_enviado': row[10],
                        'notificado_profesional': row[11],
                        'servicio_nombre': row[13] if len(row) > 13 else '',
                        'precio': row[14] if len(row) > 14 else 0,
                        'duracion': row[15] if len(row) > 15 else 0,
                        'profesional_nombre': row[16] if len(row) > 16 else ''
                    })
            
            return citas_dict
            
        except Exception as e:
            print(f"❌ Error obteniendo citas: {e}")
            return []
        finally:
            conn.close()
    
    def enviar_recordatorio_push_cliente(self, cita, horas_antes):
        """Enviar recordatorio push al cliente"""
        try:
            from push_notifications import enviar_recordatorio_cita
            
            # Validar datos necesarios
            if 'cliente_telefono' not in cita or not cita.get('cliente_telefono'):
                print(f"⚠️ Cita #{cita.get('id')} no tiene teléfono de cliente")
                return
            
            if 'negocio_id' not in cita or not cita.get('negocio_id'):
                # Obtener negocio_id del profesional
                conn = db.get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT negocio_id FROM profesionales WHERE id = %s', 
                    (cita.get('profesional_id'),)
                )
                result = cursor.fetchone()
                conn.close()
                if result:
                    cita['negocio_id'] = result[0] if isinstance(result, tuple) else result.get('negocio_id')
            
            if not cita.get('negocio_id'):
                print(f"⚠️ No se pudo obtener negocio_id para cita #{cita.get('id')}")
                return
            
            # Enviar recordatorio push
            success = enviar_recordatorio_cita(cita, horas_antes)
            
            if success:
                print(f"✅ Push {horas_antes}h enviado al cliente {cita.get('cliente_telefono')}")
            else:
                print(f"⚠️ Cliente {cita.get('cliente_telefono')} no tiene suscripciones push")
        
        except ImportError:
            print(f"⚠️ Módulo push_notifications no disponible")
        except Exception as e:
            print(f"❌ Error enviando recordatorio push al cliente: {e}")
    
    def enviar_notificaciones_profesionales_hoy(self):
        """Enviar notificaciones a profesionales sobre citas de HOY"""
        try:
            conn = db.get_db_connection()
            if not conn:
                return
            
            cursor = conn.cursor()
            fecha_hoy = datetime.now().strftime('%Y-%m-%d')
            
            cursor.execute('''
                SELECT DISTINCT c.profesional_id, p.nombre as profesional_nombre,
                    COUNT(c.id) as total_citas_hoy
                FROM citas c
                JOIN profesionales p ON c.profesional_id = p.id
                WHERE c.estado = 'confirmado'
                AND c.fecha = %s
                AND c.profesional_id NOT IN (
                    SELECT DISTINCT np.profesional_id 
                    FROM notificaciones_profesional np
                    WHERE np.fecha_creacion::date = %s
                    AND np.metadata::jsonb->>'tipo' = 'cita_hoy'
                )
                GROUP BY c.profesional_id, p.nombre
            ''', (fecha_hoy, fecha_hoy))
            
            profesionales_con_citas = cursor.fetchall()
            conn.close()
            
            if not profesionales_con_citas:
                return
            
            notificaciones_enviadas = 0
            
            for prof in profesionales_con_citas:
                try:
                    if hasattr(prof, 'keys'):
                        profesional_id = prof['profesional_id']
                        profesional_nombre = prof['profesional_nombre']
                        total_citas = prof['total_citas_hoy']
                    else:
                        profesional_id = prof[0]
                        profesional_nombre = prof[1]
                        total_citas = prof[2]
                    
                    if not profesional_id or profesional_id <= 0:
                        continue
                    
                    titulo = "📋 Citas Programadas para Hoy"
                    mensaje = f"Tienes {total_citas} cita(s) programada(s) para hoy."
                    
                    metadata = {
                        'tipo': 'cita_hoy',
                        'total_citas': total_citas,
                        'fecha': fecha_hoy
                    }
                    
                    notif_id = notification_system._save_notification_db(
                        profesional_id, titulo, mensaje, 'info', metadata
                    )
                    
                    if notif_id:
                        notificaciones_enviadas += 1
                        print(f"✅ Notificado {profesional_nombre} ({total_citas} citas)")
                    
                except Exception as e:
                    print(f"⚠️ Error notificando profesional: {e}")
                    continue
            
        except Exception as e:
            print(f"❌ Error enviando notificaciones profesionales: {e}")
    
    def marcar_recordatorio_enviado(self, cita_id, tipo_recordatorio):
        """Marcar que se envió un recordatorio"""
        conn = db.get_db_connection()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            
            if tipo_recordatorio == '24h':
                sql = "UPDATE citas SET recordatorio_24h_enviado = TRUE WHERE id = %s"
            else:
                sql = "UPDATE citas SET recordatorio_1h_enviado = TRUE WHERE id = %s"
            
            cursor.execute(sql, (cita_id,))
            conn.commit()
            return True
            
        except Exception as e:
            print(f"❌ Error marcando recordatorio: {e}")
            return False
        finally:
            conn.close()
    
    # ==================== FUNCIÓN DE CONFIRMACIÓN INMEDIATA ====================
    
    def enviar_confirmacion_inmediata(self, cita_data):
        """Enviar notificación inmediata después de crear una cita"""
        try:
            if not cita_data or 'profesional_id' not in cita_data or not cita_data['profesional_id']:
                return False
            
            # 1. Notificar al profesional (BD)
            notif_id = notification_system.notify_appointment_created(
                cita_data['profesional_id'], cita_data
            )
            
            # 2. Intentar push al profesional
            try:
                from web_chat_handler import enviar_notificacion_push_local
                enviar_notificacion_push_local(
                    profesional_id=cita_data['profesional_id'],
                    titulo="📅 Nueva Cita Agendada",
                    mensaje=f"{cita_data.get('cliente_nombre', 'Cliente')} - {cita_data.get('fecha', '')} {cita_data.get('hora', '')}",
                    cita_id=cita_data.get('id')
                )
            except Exception as e:
                print(f"⚠️ Error enviando push al profesional: {e}")
            
            # 3. Intentar push al cliente
            try:
                from push_notifications import enviar_notificacion_cliente
                enviar_notificacion_cliente(
                    telefono=cita_data.get('cliente_telefono', ''),
                    negocio_id=cita_data.get('negocio_id'),
                    titulo="✅ ¡Cita Confirmada!",
                    mensaje=f"Hola {cita_data.get('cliente_nombre', 'Cliente')}, tu cita ha sido agendada para el {cita_data.get('fecha', '')} a las {cita_data.get('hora', '')}",
                    cita_id=cita_data.get('id'),
                    url=f"/cliente/{cita_data.get('negocio_id')}?cita={cita_data.get('id')}"
                )
            except Exception as e:
                print(f"⚠️ Error enviando push al cliente: {e}")
            
            if notif_id:
                print(f"✅ Notificación enviada al profesional #{cita_data['profesional_id']}")
                return True
            else:
                return False
                
        except Exception as e:
            print(f"❌ Error en confirmación: {e}")
            return False
    
    # ==================== FUNCIÓN DE RESUMEN DIARIO ====================
    
    def enviar_resumen_diario_profesionales(self):
        """Enviar resumen diario de citas a cada profesional (8:00 AM)"""
        try:
            ahora = datetime.now()
            print(f"📋 [{ahora.strftime('%H:%M')}] Enviando resumen diario...")
            
            conn = db.get_db_connection()
            if not conn:
                return
            
            cursor = conn.cursor()
            fecha_hoy = ahora.strftime('%Y-%m-%d')
            
            cursor.execute('''
                SELECT p.id, p.nombre,
                       COUNT(c.id) as citas_hoy,
                       STRING_AGG(
                           CONCAT(c.hora, ' - ', COALESCE(cl.nombre, c.cliente_nombre)), 
                           ', ' 
                           ORDER BY c.hora
                       ) as detalle_citas
                FROM profesionales p
                LEFT JOIN citas c ON p.id = c.profesional_id 
                    AND c.fecha = %s 
                    AND c.estado = 'confirmado'
                LEFT JOIN clientes cl ON c.cliente_telefono = cl.telefono
                WHERE p.activo = TRUE
                GROUP BY p.id, p.nombre
                HAVING COUNT(c.id) > 0
            ''', (fecha_hoy,))
            
            profesionales = cursor.fetchall()
            conn.close()
            
            notificaciones_enviadas = 0
            
            for prof in profesionales:
                if hasattr(prof, 'keys'):
                    prof_id = prof['id']
                    prof_nombre = prof['nombre']
                    citas_hoy = prof['citas_hoy']
                else:
                    prof_id = prof[0]
                    prof_nombre = prof[1]
                    citas_hoy = prof[2]
                
                if citas_hoy > 0:
                    titulo = "🌅 Resumen del Día"
                    mensaje = f"Hola {prof_nombre},\n\nTienes {citas_hoy} cita(s) programada(s) para hoy."
                    
                    metadata = {
                        'tipo': 'resumen_diario',
                        'total_citas': citas_hoy,
                        'fecha': fecha_hoy
                    }
                    
                    notif_id = notification_system._save_notification_db(
                        prof_id, titulo, mensaje, 'info', metadata
                    )
                    
                    if notif_id:
                        notificaciones_enviadas += 1
                        print(f"✅ Resumen enviado a {prof_nombre} ({citas_hoy} citas)")
            
            if notificaciones_enviadas > 0:
                print(f"📨 {notificaciones_enviadas} resumen(es) enviado(s)")
            
        except Exception as e:
            print(f"❌ Error enviando resumen diario: {e}")
    
    # ==================== INICIAR SCHEDULER ====================
    
    def iniciar(self):
        """Iniciar el scheduler principal"""
        print("🔄 Iniciando scheduler...")
        
        # Programar verificaciones cada minuto
        schedule.every(1).minutes.do(self.verificar_recordatorios)
        
        # Programar resumen diario a las 8:00 AM
        schedule.every().day.at("08:00").do(self.enviar_resumen_diario_profesionales)
        
        # Ejecutar inmediatamente
        self.verificar_recordatorios()
        
        print("✅ Scheduler iniciado")
        
        # Bucle principal
        while self.en_ejecucion:
            schedule.run_pending()
            time.sleep(1)
    
    def detener(self):
        """Detener el scheduler"""
        self.en_ejecucion = False
        print("🛑 Scheduler detenido")
    
    def iniciar_en_segundo_plano(self):
        """Iniciar scheduler en segundo plano"""
        scheduler_thread = threading.Thread(target=self.iniciar, daemon=True)
        scheduler_thread.start()
        return scheduler_thread

# Instancia global
appointment_scheduler = AppointmentScheduler()

# Función para iniciar desde app.py
def iniciar_scheduler_en_segundo_plano():
    """Iniciar scheduler en segundo plano (para importar desde app.py)"""
    return appointment_scheduler.iniciar_en_segundo_plano()

# Si se ejecuta directamente, iniciar el scheduler
if __name__ == "__main__":
    appointment_scheduler.iniciar()