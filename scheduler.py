# scheduler.py - VERSIÓN CON LOGS LIMITADOS
import schedule
import time
import threading
from datetime import datetime, timedelta
import database as db
from notification_system import notification_system

class AppointmentScheduler:
    """Scheduler para recordatorios de citas (SOLO notificaciones web)"""
    
    def __init__(self):
        print("⏰ Scheduler iniciado")
        self.en_ejecucion = True
        self.ultima_ejecucion = None
    
    # ==================== FUNCIONES PRINCIPALES ====================
    
    def verificar_recordatorios(self):
        """Verificar y enviar recordatorios - VERSIÓN SUPER SIMPLE"""
        try:
            ahora = datetime.now()
            
            # Solo log cada 10 minutos
            if not hasattr(self, 'ultimo_log') or (ahora - self.ultimo_log).seconds >= 600:
                print(f"⏰ [{ahora.strftime('%H:%M')}] Scheduler activo")
                self.ultimo_log = ahora
            
            # Obtener citas
            citas_pendientes = self.obtener_citas_pendientes_recordatorio()
            
            if not citas_pendientes:
                return
            
            recordatorios_enviados = 0
            
            for cita in citas_pendientes:
                try:
                    cita_id = cita['id']
                    cita_fecha = datetime.strptime(cita['fecha'], '%Y-%m-%d').date()
                    cita_hora = datetime.strptime(cita['hora'], '%H:%M').time()
                    cita_datetime = datetime.combine(cita_fecha, cita_hora)
                    
                    # Calcular tiempo restante
                    tiempo_restante = cita_datetime - ahora
                    horas_restantes = tiempo_restante.total_seconds() / 3600
                    
                    # Recordatorio 24h
                    if 23 <= horas_restantes <= 25 and not cita.get('recordatorio_24h_enviado'):
                        notif_id = notification_system.notify_appointment_reminder(
                            cita['profesional_id'], cita, hours_before=24
                        )
                        if notif_id:
                            self.marcar_recordatorio_enviado(cita_id, '24h')
                            recordatorios_enviados += 1
                    
                    # Recordatorio 1h
                    elif 0.5 <= horas_restantes <= 1.5 and not cita.get('recordatorio_1h_enviado'):
                        notif_id = notification_system.notify_appointment_reminder(
                            cita['profesional_id'], cita, hours_before=1
                        )
                        if notif_id:
                            self.marcar_recordatorio_enviado(cita_id, '1h')
                            recordatorios_enviados += 1
                            
                except Exception:
                    continue
            
            if recordatorios_enviados > 0:
                print(f"📨 {recordatorios_enviados} recordatorio(s) enviado(s)")
                        
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
                SELECT c.*, 
                       COALESCE(cl.nombre, c.cliente_nombre) as cliente_nombre,
                       s.nombre as servicio_nombre, s.precio,
                       p.nombre as profesional_nombre
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                JOIN profesionales p ON c.profesional_id = p.id
                LEFT JOIN clientes cl ON c.cliente_telefono = cl.telefono
                WHERE c.estado = 'confirmado'
                AND c.fecha IN (%s, %s, %s)
                AND (c.recordatorio_24h_enviado = FALSE OR c.recordatorio_1h_enviado = FALSE)
                ORDER BY c.fecha, c.hora
            '''
            
            cursor.execute(sql, (fecha_hoy, fecha_manana, fecha_pasadomanana))
            citas = cursor.fetchall()
            
            # Convertir a diccionarios
            citas_dict = []
            for row in citas:
                if hasattr(row, 'keys'):
                    citas_dict.append(dict(row))
                else:
                    citas_dict.append({
                        'id': row[0],
                        'profesional_id': row[2],
                        'cliente_nombre': row[12] if len(row) > 12 else row[4],
                        'fecha': row[5],
                        'hora': row[6],
                        'servicio_nombre': row[13] if len(row) > 13 else '',
                        'profesional_nombre': row[15] if len(row) > 15 else '',
                        'recordatorio_24h_enviado': row[9],
                        'recordatorio_1h_enviado': row[10]
                    })
            
            return citas_dict
            
        except Exception as e:
            print(f"❌ Error obteniendo citas: {e}")
            return []
        finally:
            conn.close()
    
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
                    WHERE np.fecha_creacion = %s
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
                    
                except Exception:
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
    
    def marcar_cita_notificada_hoy(self, cita_id):
        """Marcar que una cita fue notificada hoy"""
        return True
    
    # ==================== FUNCIÓN DE CONFIRMACIÓN INMEDIATA ====================
    
    def enviar_confirmacion_inmediata(self, cita_data):
        """Llamar esta función después de crear una cita"""
        try:
            if not cita_data or 'profesional_id' not in cita_data or not cita_data['profesional_id']:
                return False
            
            notif_id = notification_system.notify_appointment_created(
                cita_data['profesional_id'], cita_data
            )
            
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