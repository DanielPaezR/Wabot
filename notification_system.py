# notification_system.py - CORRECCIÓN DE ERROR KeyError: 0
import os
import json
from datetime import datetime, timedelta
import database as db

class ProfessionalNotificationSystem:
    """Sistema de notificaciones para profesionales"""
    
    def __init__(self):
        print("🔔 Sistema de Notificaciones Profesionales")
    
    # ==================== FUNCIONES PRINCIPALES ====================
    
    def notify_appointment_created(self, profesional_id, cita_data):
        """Notificar nueva cita al profesional"""
        # VALIDACIÓN CRÍTICA
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
        """Notificar citas de HOY al profesional (llamada desde scheduler)"""
        # VALIDACIÓN CRÍTICA
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
        # VALIDACIÓN CRÍTICA
        if not profesional_id or profesional_id <= 0:
            print(f"⚠️ Profesional ID inválido: {profesional_id}")
            return False
            
        if hours_before == 24:
            titulo = "⏰ Recordatorio - Cita Mañana"
            tiempo = "mañana"
        else:  # 1 hora
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
        """Guardar notificación en PostgreSQL - VERSIÓN CORREGIDA"""
        # VALIDACIÓN CRÍTICA
        if not profesional_id or profesional_id <= 0:
            print(f"❌ Profesional ID inválido: {profesional_id}")
            return False
        
        conn = db.get_db_connection()
        if not conn:
            print("❌ Error: No hay conexión a la base de datos")
            return False
        
        try:
            cursor = conn.cursor()
            
            # Usar CURRENT_DATE porque el campo es DATE
            query = """
                INSERT INTO notificaciones_profesional 
                (profesional_id, titulo, mensaje, tipo, leida, metadata, fecha_creacion)
                VALUES (%s, %s, %s, %s, FALSE, %s, CURRENT_DATE)
                RETURNING id
            """
            
            metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else '{}'
            
            cursor.execute(query, (profesional_id, titulo, mensaje, tipo, metadata_json))
            
            # ✅ CORRECCIÓN: Obtener ID de forma segura para PostgreSQL y SQLite
            result = cursor.fetchone()
            
            # PostgreSQL devuelve una tupla, SQLite también
            # En PostgreSQL con RealDictCursor podría ser diccionario, pero aquí usamos cursor normal
            if result:
                if isinstance(result, dict):  # Si es diccionario (RealDictCursor)
                    notif_id = result.get('id') or result.get(0)
                else:  # Si es tupla o lista
                    notif_id = result[0] if len(result) > 0 else None
            else:
                notif_id = None
            
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
        """Obtener notificaciones del profesional"""
        if not profesional_id or profesional_id <= 0:
            print(f"⚠️ Profesional ID inválido: {profesional_id}")
            return []
            
        conn = db.get_db_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            
            if unread_only:
                query = """
                    SELECT id, titulo, mensaje, tipo, fecha_creacion, metadata
                    FROM notificaciones_profesional
                    WHERE profesional_id = %s AND leida = FALSE
                    ORDER BY id DESC
                    LIMIT %s
                """
                cursor.execute(query, (profesional_id, limit))
            else:
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
                # PostgreSQL devuelve tuplas, no diccionarios (a menos que uses RealDictCursor)
                # row[0] = id, row[1] = titulo, row[2] = mensaje, row[3] = tipo, row[4] = fecha_creacion, row[5] = metadata
                
                fecha_str = str(row[4]) if len(row) > 4 and row[4] else None
                
                notif = {
                    'id': row[0] if len(row) > 0 else 0,
                    'titulo': row[1] if len(row) > 1 else '',
                    'mensaje': row[2] if len(row) > 2 else '',
                    'tipo': row[3] if len(row) > 3 else 'info',
                    'fecha_creacion': fecha_str,
                    'fecha_display': self._format_date_display(fecha_str),
                    'metadata': json.loads(row[5]) if len(row) > 5 and row[5] else {}
                }
                
                if not unread_only and len(row) > 6:
                    notif['leida'] = row[6]
                
                # Timestamp para ordenar
                timestamp = notif['metadata'].get('timestamp', '')
                try:
                    notif['_timestamp'] = datetime.fromisoformat(timestamp) if timestamp else datetime.min
                except:
                    notif['_timestamp'] = datetime.min
                
                notifications.append(notif)
            
            # Ordenar por timestamp real (más reciente primero)
            notifications.sort(key=lambda x: x['_timestamp'], reverse=True)
            
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
            # Parsear fecha (YYYY-MM-DD)
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            hoy = datetime.now().date()
            
            # Comparar fechas
            if fecha == hoy:
                return "Hoy"
            elif fecha == hoy - timedelta(days=1):
                return "Ayer"
            else:
                # Meses en español
                meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 
                        'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
                
                dia = fecha.day
                mes = meses[fecha.month - 1]
                
                # Si es de otro año, mostrar año
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
            # Usar CURRENT_DATE porque el campo es DATE
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
            import traceback
            traceback.print_exc()
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
        """Contar notificaciones no leídas"""
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
            # PostgreSQL devuelve una tupla
            count = result[0] if result and len(result) > 0 else 0
            return count
            
        except Exception as e:
            print(f"❌ Error contando notificaciones: {str(e)}")
            return 0
        finally:
            if conn:
                conn.close()

# Instancia global
notification_system = ProfessionalNotificationSystem()