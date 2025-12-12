# notification_system.py - VERSIÓN CORREGIDA COMPLETA
import os
import json
from datetime import datetime, timedelta
import database as db

class ProfessionalNotificationSystem:
    """Sistema de notificaciones para profesionales - VERSIÓN CORREGIDA"""
    
    def __init__(self):
        print("🔔 Sistema de Notificaciones Profesionales iniciado")
    
    # ==================== FUNCIONES PRINCIPALES ====================
    
    def notify_appointment_created(self, profesional_id, cita_data):
        """Notificar nueva cita al profesional"""
        if not profesional_id or profesional_id <= 0:
            print(f"⚠️ Profesional ID inválido: {profesional_id}")
            return False
            
        titulo = "📅 Nueva Cita Agendada"
        mensaje = f"""NUEVA CITA CONFIRMADA

Cliente: {cita_data.get('cliente_nombre', 'Nuevo Cliente')}
Servicio: {cita_data.get('servicio_nombre', 'Servicio')}
Fecha: {cita_data.get('fecha', '')}
Hora: {cita_data.get('hora', '')}
Precio: ${cita_data.get('precio', 0):,}

Estado: Confirmado"""
        
        metadata = {
            'cita_id': cita_data.get('id'),
            'tipo': 'nueva_cita',
            'timestamp': datetime.now().isoformat()
        }
        
        return self._save_notification_db(profesional_id, titulo, mensaje, 'success', metadata)
    
    def notify_appointment_today(self, profesional_id, cita_data):
        """Notificar citas de HOY al profesional"""
        if not profesional_id or profesional_id <= 0:
            print(f"⚠️ Profesional ID inválido: {profesional_id}")
            return False
            
        titulo = "📋 Cita de Hoy"
        mensaje = f"""CITA HOY - {cita_data.get('hora', '')}

Cliente: {cita_data.get('cliente_nombre', 'Cliente')}
Servicio: {cita_data.get('servicio_nombre', 'Servicio')}

¡Prepárate para la sesión!"""

        metadata = {
            'cita_id': cita_data.get('id'),
            'tipo': 'cita_hoy',
            'timestamp': datetime.now().isoformat()
        }
        
        return self._save_notification_db(profesional_id, titulo, mensaje, 'info', metadata)
    
    def notify_appointment_reminder(self, profesional_id, cita_data, hours_before):
        """Recordatorio de cita próxima"""
        if not profesional_id or profesional_id <= 0:
            print(f"⚠️ Profesional ID inválido: {profesional_id}")
            return False
            
        if hours_before == 24:
            titulo = "⏰ Recordatorio - Cita Mañana"
            tiempo = "mañana"
        else:
            titulo = "🚀 Cita Próxima - 1 Hora"
            tiempo = "en 1 hora"
        
        mensaje = f"""RECORDATORIO - CITA {tiempo.upper()}

Hora: {cita_data.get('hora', '')}
Cliente: {cita_data.get('cliente_nombre', 'Cliente')}
Servicio: {cita_data.get('servicio_nombre', 'Servicio')}"""
        
        metadata = {
            'cita_id': cita_data.get('id'),
            'tipo': 'recordatorio_cita',
            'horas_antes': hours_before,
            'timestamp': datetime.now().isoformat()
        }
        
        return self._save_notification_db(profesional_id, titulo, mensaje, 'warning', metadata)
    
    # ==================== FUNCIONES DE BASE DE DATOS ====================
    
    def _save_notification_db(self, profesional_id, titulo, mensaje, tipo, metadata=None):
        """Guardar notificación en PostgreSQL"""
        if not profesional_id or profesional_id <= 0:
            print(f"❌ Profesional ID inválido: {profesional_id}")
            return False
        
        conn = db.get_db_connection()
        if not conn:
            print("❌ Error: No hay conexión a la base de datos")
            return False
        
        try:
            cursor = conn.cursor()
            
            query = """
                INSERT INTO notificaciones_profesional 
                (profesional_id, titulo, mensaje, tipo, leida, metadata, fecha_creacion)
                VALUES (%s, %s, %s, %s, FALSE, %s, CURRENT_DATE)
                RETURNING id
            """
            
            metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else '{}'
            
            cursor.execute(query, (profesional_id, titulo, mensaje, tipo, metadata_json))
            
            result = cursor.fetchone()
            notif_id = result[0] if result and len(result) > 0 else None
            
            conn.commit()
            
            if notif_id:
                print(f"✅ Notificación #{notif_id} guardada para profesional {profesional_id}")
                return notif_id
            else:
                print("⚠️ Notificación guardada pero sin ID retornado")
                return True
                
        except Exception as e:
            print(f"❌ Error guardando notificación: {str(e)}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_professional_notifications(self, profesional_id, unread_only=True, limit=20):
        """Obtener notificaciones del profesional - VERSIÓN CORREGIDA DEFINITIVA"""
        print(f"🔔 Obteniendo notificaciones para profesional {profesional_id}")
        
        if not profesional_id or profesional_id <= 0:
            print(f"⚠️ Profesional ID inválido: {profesional_id}")
            return []
            
        conn = db.get_db_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            
            # QUERY SIMPLIFICADO Y SEGURO
            query = """
                SELECT id, titulo, mensaje, tipo, fecha_creacion, metadata, leida
                FROM notificaciones_profesional
                WHERE profesional_id = %s
                ORDER BY id DESC
                LIMIT %s
            """
            
            cursor.execute(query, (profesional_id, limit))
            rows = cursor.fetchall()
            
            notifications = []
            
            for row in rows:
                try:
                    # ACCESO SEGURO A TODOS LOS CAMPOS
                    row_list = list(row)
                    
                    notif = {
                        'id': row_list[0] if len(row_list) > 0 else 0,
                        'titulo': row_list[1] if len(row_list) > 1 else '',
                        'mensaje': row_list[2] if len(row_list) > 2 else '',
                        'tipo': row_list[3] if len(row_list) > 3 else 'info',
                        'fecha_creacion': str(row_list[4]) if len(row_list) > 4 and row_list[4] else '',
                        'metadata': json.loads(row_list[5]) if len(row_list) > 5 and row_list[5] else {},
                        'leida': row_list[6] if len(row_list) > 6 else False
                    }
                    
                    # Formatear fecha para display
                    notif['fecha_display'] = self._format_date_display(notif['fecha_creacion'])
                    
                    # Timestamp para ordenar
                    timestamp = notif['metadata'].get('timestamp', '')
                    try:
                        notif['_timestamp'] = datetime.fromisoformat(timestamp) if timestamp else datetime.min
                    except:
                        notif['_timestamp'] = datetime.min
                    
                    # Filtrar no leídas si se solicita
                    if unread_only and notif['leida']:
                        notifications.append(notif)
                    elif not unread_only:
                        notifications.append(notif)
                        
                except Exception as e:
                    print(f"⚠️ Error procesando fila: {e}")
                    print(f"⚠️ Row: {row}")
                    continue
            
            # Ordenar por timestamp
            notifications.sort(key=lambda x: x['_timestamp'], reverse=True)
            
            print(f"✅ {len(notifications)} notificaciones encontradas")
            return notifications
            
        except Exception as e:
            print(f"❌ Error obteniendo notificaciones: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            if conn:
                conn.close()
    
    def _format_date_display(self, fecha_str):
        """Formatear fecha para mostrar de forma amigable"""
        if not fecha_str:
            return "Hoy"
        
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            hoy = datetime.now().date()
            
            if fecha == hoy:
                return "Hoy"
            elif fecha == hoy - timedelta(days=1):
                return "Ayer"
            else:
                meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 
                        'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
                
                dia = fecha.day
                mes = meses[fecha.month - 1]
                
                if fecha.year != hoy.year:
                    return f"{dia} {mes} {fecha.year}"
                else:
                    return f"{dia} {mes}"
                    
        except Exception as e:
            print(f"⚠️ Error formateando fecha {fecha_str}: {str(e)}")
            return fecha_str
    
    def mark_as_read(self, notification_id):
        """Marcar notificación como leída"""
        conn = db.get_db_connection()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            query = """
                UPDATE notificaciones_profesional
                SET leida = TRUE, fecha_leida = CURRENT_DATE
                WHERE id = %s
            """
            cursor.execute(query, (notification_id,))
            conn.commit()
            
            return cursor.rowcount > 0
            
        except Exception as e:
            print(f"❌ Error marcando como leída: {str(e)}")
            return False
        finally:
            if conn:
                conn.close()
    
    def mark_all_as_read(self, profesional_id):
        """Marcar TODAS las notificaciones como leídas"""
        if not profesional_id or profesional_id <= 0:
            print(f"⚠️ Profesional ID inválido: {profesional_id}")
            return 0
            
        conn = db.get_db_connection()
        if not conn:
            return 0
        
        try:
            cursor = conn.cursor()
            query = """
                UPDATE notificaciones_profesional
                SET leida = TRUE, fecha_leida = CURRENT_DATE
                WHERE profesional_id = %s AND leida = FALSE
            """
            cursor.execute(query, (profesional_id,))
            conn.commit()
            
            return cursor.rowcount
            
        except Exception as e:
            print(f"❌ Error marcando todas como leídas: {str(e)}")
            return 0
        finally:
            if conn:
                conn.close()
    
    def get_unread_count(self, profesional_id):
        """Contar notificaciones no leídas - VERSIÓN CORREGIDA"""
        print(f"🔍 Contando notificaciones no leídas para profesional {profesional_id}")
        
        if not profesional_id or profesional_id <= 0:
            print(f"⚠️ Profesional ID inválido: {profesional_id}")
            return 0
            
        conn = db.get_db_connection()
        if not conn:
            return 0
        
        try:
            cursor = conn.cursor()
            query = """
                SELECT COUNT(*) 
                FROM notificaciones_profesional
                WHERE profesional_id = %s AND leida = FALSE
            """
            cursor.execute(query, (profesional_id,))
            
            result = cursor.fetchone()
            
            # ACCESO SEGURO AL RESULTADO
            if result:
                if isinstance(result, (tuple, list)):
                    count = result[0] if len(result) > 0 else 0
                else:
                    count = int(result) if result else 0
            else:
                count = 0
            
            print(f"✅ {count} notificaciones no leídas encontradas")
            return count
            
        except Exception as e:
            print(f"❌ Error contando notificaciones: {str(e)}")
            return 0
        finally:
            if conn:
                conn.close()

# Instancia global
notification_system = ProfessionalNotificationSystem()