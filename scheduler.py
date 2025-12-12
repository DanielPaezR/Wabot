# scheduler.py - VERSIÓN COMPLETA SIN SMS, SOLO NOTIFICACIONES WEB
import schedule
import time
import threading
from datetime import datetime, timedelta
import database as db
from notification_system import notification_system

class AppointmentScheduler:
    """Scheduler para recordatorios de citas (SOLO notificaciones web)"""
    
    def __init__(self):
        print("⏰ Scheduler de recordatorios iniciado (SOLO notificaciones web)")
        self.en_ejecucion = True
    
    # ==================== FUNCIONES PRINCIPALES ====================
    
    def verificar_recordatorios(self):
        """Verificar y enviar recordatorios: 24h y 1h antes"""
        try:
            ahora = datetime.now()
            print(f"⏰ [{ahora.strftime('%H:%M:%S')}] Verificando recordatorios...")
            
            # OBTENER CITAS PENDIENTES DE RECORDATORIO
            citas_pendientes = self.obtener_citas_pendientes_recordatorio()
            
            if not citas_pendientes:
                print("   ℹ️ No hay citas pendientes de recordatorio")
                # Verificar notificaciones para profesionales de hoy
                self.enviar_notificaciones_profesionales_hoy()
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
                    print(f"     👨‍💼 Profesional: {cita.get('profesional_id', 'N/A')}")
                    
                    # DECIDIR QUÉ RECORDATORIO ENVIAR
                    enviado = False
                    
                    # Recordatorio 24h (entre 23 y 25 horas antes)
                    if 23 <= horas_restantes <= 25 and not cita.get('recordatorio_24h_enviado'):
                        print(f"     📅 Enviando recordatorio 24h...")
                        
                        # Notificar al profesional
                        notif_id = notification_system.notify_appointment_reminder(
                            cita['profesional_id'], cita, hours_before=24
                        )
                        
                        if notif_id:
                            self.marcar_recordatorio_enviado(cita_id, '24h')
                            print(f"     ✅ Recordatorio 24h enviado al profesional (Notif #{notif_id})")
                        else:
                            print(f"     ❌ Error enviando recordatorio 24h")
                        
                        enviado = True
                    
                    # Recordatorio 1h (entre 0.5 y 1.5 horas antes)
                    elif 0.5 <= horas_restantes <= 1.5 and not cita.get('recordatorio_1h_enviado'):
                        print(f"     ⏰ Enviando recordatorio 1h...")
                        
                        # Notificar al profesional
                        notif_id = notification_system.notify_appointment_reminder(
                            cita['profesional_id'], cita, hours_before=1
                        )
                        
                        if notif_id:
                            self.marcar_recordatorio_enviado(cita_id, '1h')
                            print(f"     ✅ Recordatorio 1h enviado al profesional (Notif #{notif_id})")
                        else:
                            print(f"     ❌ Error enviando recordatorio 1h")
                        
                        enviado = True
                    
                    # Si la cita es para hoy y no se ha notificado aún
                    elif cita_fecha == ahora.date() and horas_restantes > 0:
                        # Notificar cita de hoy al profesional (si aún no se ha notificado)
                        if not cita.get('notificado_hoy'):
                            notif_id = notification_system.notify_appointment_today(
                                cita['profesional_id'], cita
                            )
                            if notif_id:
                                self.marcar_cita_notificada_hoy(cita_id)
                                print(f"     📋 Notificada cita de hoy (Notif #{notif_id})")
                    
                    if not enviado and horas_restantes > 0:
                        print(f"     ℹ️ No requiere recordatorio aún")
                        
                except Exception as e:
                    print(f"     ❌ Error procesando cita #{cita.get('id')}: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Enviar notificaciones generales para profesionales
            self.enviar_notificaciones_profesionales_hoy()
                    
        except Exception as e:
            print(f"❌ Error en verificar_recordatorios: {e}")
            import traceback
            traceback.print_exc()
    
    def obtener_citas_pendientes_recordatorio(self):
        """Obtener citas confirmadas que necesitan recordatorios"""
        conn = db.get_db_connection()
        if not conn:
            return []
        
        cursor = conn.cursor()
        try:
            # Obtener citas confirmadas para hoy y los próximos 2 días
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
                    # Convertir tupla a dict
                    citas_dict.append({
                        'id': row[0],
                        'negocio_id': row[1],
                        'profesional_id': row[2],
                        'cliente_telefono': row[3],
                        'cliente_nombre': row[12] if len(row) > 12 else row[4],
                        'fecha': row[5],
                        'hora': row[6],
                        'servicio_id': row[7],
                        'estado': row[8],
                        'recordatorio_24h_enviado': row[9],
                        'recordatorio_1h_enviado': row[10],
                        'servicio_nombre': row[13] if len(row) > 13 else '',
                        'precio': row[14] if len(row) > 14 else 0,
                        'profesional_nombre': row[15] if len(row) > 15 else ''
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
            ahora = datetime.now()
            print(f"👨‍💼 [{ahora.strftime('%H:%M:%S')}] Enviando notificaciones de citas hoy...")
            
            # 1. Obtener citas para hoy
            conn = db.get_db_connection()
            if not conn:
                return
            
            cursor = conn.cursor()
            
            # Obtener citas confirmadas para hoy que NO han sido notificadas hoy
            fecha_hoy = ahora.strftime('%Y-%m-%d')
            
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
                print("   ℹ️ Todos los profesionales ya fueron notificados hoy")
                return
            
            # 2. Enviar notificaciones a cada profesional
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
                    
                    # Crear notificación de resumen del día
                    titulo = "📋 Citas Programadas para Hoy"
                    mensaje = f"""RESUMEN DEL DÍA

Hola {profesional_nombre},

Tienes {total_citas} cita(s) programada(s) para hoy.

¡Que tengas un excelente día de trabajo!"""
                    
                    metadata = {
                        'tipo': 'cita_hoy',
                        'total_citas': total_citas,
                        'fecha': fecha_hoy,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    notif_id = notification_system._save_notification_db(
                        profesional_id, titulo, mensaje, 'info', metadata
                    )
                    
                    if notif_id:
                        notificaciones_enviadas += 1
                        print(f"   ✅ Notificado {profesional_nombre} ({total_citas} citas)")
                    
                except Exception as e:
                    print(f"   ❌ Error notificando profesional: {e}")
            
            print(f"   📨 {notificaciones_enviadas} notificaciones de resumen enviadas")
            
        except Exception as e:
            print(f"❌ Error enviando notificaciones profesionales: {e}")
            import traceback
            traceback.print_exc()
    
    def marcar_recordatorio_enviado(self, cita_id, tipo_recordatorio):
        """Marcar que se envió un recordatorio"""
        conn = db.get_db_connection()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            
            if tipo_recordatorio == '24h':
                sql = "UPDATE citas SET recordatorio_24h_enviado = TRUE WHERE id = %s"
            else:  # '1h'
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
        # Podemos agregar un campo en la BD o manejarlo con metadata
        # Por ahora solo log
        print(f"   📝 Cita #{cita_id} marcada como notificada hoy")
        return True
    
    # ==================== FUNCIÓN DE CONFIRMACIÓN INMEDIATA ====================
    
    def enviar_confirmacion_inmediata(self, cita_data):
        """Llamar esta función después de crear una cita"""
        try:
            print(f"📧 Enviando confirmación para cita #{cita_data.get('id')}")
            
            # Verificar que tenga profesional_id
            if 'profesional_id' not in cita_data or not cita_data['profesional_id']:
                print("⚠️ Cita sin profesional_id, no se puede notificar")
                return False
            
            # Notificar al profesional sobre la nueva cita
            notif_id = notification_system.notify_appointment_created(
                cita_data['profesional_id'], cita_data
            )
            
            if notif_id:
                print(f"👨‍💼 Notificación #{notif_id} enviada al profesional {cita_data['profesional_id']}")
                return True
            else:
                print("❌ Error enviando notificación al profesional")
                return False
                
        except Exception as e:
            print(f"❌ Error confirmación: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # ==================== FUNCIÓN DE RESUMEN DIARIO ====================
    
    def enviar_resumen_diario_profesionales(self):
        """Enviar resumen diario de citas a cada profesional (8:00 AM)"""
        try:
            ahora = datetime.now()
            print(f"📋 [{ahora.strftime('%H:%M:%S')}] Enviando resumen diario a profesionales...")
            
            conn = db.get_db_connection()
            if not conn:
                return
            
            cursor = conn.cursor()
            
            # Obtener todos los profesionales activos con citas hoy
            fecha_hoy = ahora.strftime('%Y-%m-%d')
            
            cursor.execute('''
                SELECT p.id, p.nombre, p.email,
                       COUNT(c.id) as citas_hoy,
                       STRING_AGG(
                           CONCAT(c.hora, ' - ', COALESCE(cl.nombre, c.cliente_nombre), 
                                  ' (', s.nombre, ')'), 
                           ', ' 
                           ORDER BY c.hora
                       ) as detalle_citas
                FROM profesionales p
                LEFT JOIN citas c ON p.id = c.profesional_id 
                    AND c.fecha = %s 
                    AND c.estado = 'confirmado'
                LEFT JOIN clientes cl ON c.cliente_telefono = cl.telefono
                LEFT JOIN servicios s ON c.servicio_id = s.id
                WHERE p.activo = TRUE
                GROUP BY p.id, p.nombre, p.email
                HAVING COUNT(c.id) > 0
            ''', (fecha_hoy,))
            
            profesionales = cursor.fetchall()
            conn.close()
            
            for prof in profesionales:
                if hasattr(prof, 'keys'):
                    prof_id = prof['id']
                    prof_nombre = prof['nombre']
                    citas_hoy = prof['citas_hoy']
                    detalle_citas = prof['detalle_citas']
                else:
                    prof_id = prof[0]
                    prof_nombre = prof[1]
                    citas_hoy = prof[3]
                    detalle_citas = prof[4] if len(prof) > 4 else ''
                
                if citas_hoy > 0:
                    # Enviar notificación con resumen detallado
                    titulo = "🌅 Resumen del Día"
                    mensaje = f"""RESUMEN MATUTINO

Hola {prof_nombre},

Tienes {citas_hoy} cita(s) programada(s) para hoy:

{detalle_citas if detalle_citas else 'No hay detalles disponibles'}

¡Que tengas un excelente día!"""
                    
                    metadata = {
                        'tipo': 'resumen_diario',
                        'total_citas': citas_hoy,
                        'fecha': fecha_hoy,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    notif_id = notification_system._save_notification_db(
                        prof_id, titulo, mensaje, 'info', metadata
                    )
                    
                    if notif_id:
                        print(f"   📨 Resumen enviado a {prof_nombre} ({citas_hoy} citas)")
            
            if profesionales:
                print(f"✅ Resumen diario enviado a {len(profesionales)} profesionales")
            else:
                print("ℹ️ No hay profesionales con citas hoy")
            
        except Exception as e:
            print(f"❌ Error enviando resumen diario: {e}")
            import traceback
            traceback.print_exc()
    
    # ==================== INICIAR SCHEDULER ====================
    
    def iniciar(self):
        """Iniciar el scheduler principal"""
        print("🔄 Iniciando scheduler de recordatorios...")
        print("🔔 Notificaciones web para profesionales activas")
        
        # Programar verificaciones cada minuto
        schedule.every(1).minutes.do(self.verificar_recordatorios)
        
        # Programar resumen diario a las 8:00 AM
        schedule.every().day.at("08:00").do(self.enviar_resumen_diario_profesionales)
        
        # Ejecutar inmediatamente
        self.verificar_recordatorios()
        
        print("✅ Scheduler iniciado correctamente")
        print("   • Recordatorios cada 1 minuto")
        print("   • Resumen diario a las 8:00 AM")
        print("   • Notificaciones web para profesionales activas")
        
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
        print("✅ Scheduler ejecutándose en segundo plano")
        return scheduler_thread

# Instancia global
appointment_scheduler = AppointmentScheduler()

# Función para iniciar desde app.py
def iniciar_scheduler_en_segundo_plano():
    """Iniciar scheduler en segundo plano (para importar desde app.py)"""
    return appointment_scheduler.iniciar_en_segundo_plano()

# Si se ejecuta directamente, iniciar el scheduler
if __name__ == "__main__":
    print("🚀 Iniciando scheduler de forma independiente...")
    appointment_scheduler.iniciar()