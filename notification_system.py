# notification_system.py - VERSIÓN CORREGIDA
import os
import json
from datetime import datetime, timedelta  # AÑADE timedelta aquí
import database as db

class ProfessionalNotificationSystem:
    """Sistema de notificaciones para profesionales"""
    
    def __init__(self):
        print("🔔 Sistema de Notificaciones Profesionales")
    
    # ==================== FUNCIONES PRINCIPALES ====================
    
    def notify_appointment_created(self, profesional_id, cita_data):
        """Notificar nueva cita al profesional"""
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
            'timestamp': datetime.now().isoformat()  # Guardamos hora real en metadata
        }
        
        return self._save_notification_db(profesional_id, titulo, mensaje, 'success', metadata)
    
    def notify_appointment_reminder(self, profesional_id, cita_data, hours_before):
        """Recordatorio de cita próxima"""
        if hours_before == 24:
            titulo = "⏰ Recordatorio - Cita Mañana"
            mensaje = f"""RECORDATORIO - CITA MAÑANA

Recuerda tu cita de mañana:
Hora: {cita_data.get('hora', '')}
Cliente: {cita_data.get('cliente_nombre', 'Cliente')}
Servicio: {cita_data.get('servicio_nombre', 'Servicio')}"""
        else:  # 1 hora
            titulo = "🚀 Cita Próxima - 1 Hora"
            mensaje = f"""CITA EN 1 HORA

Tu cita es en 1 hora:
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
        """Guardar notificación en PostgreSQL - USANDO DATE"""
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
            notif_id = cursor.fetchone()[0]
            
            conn.commit()
            
            print(f"✅ Notificación #{notif_id} guardada en BD")
            print(f"   Profesional: {profesional_id}")
            print(f"   Tipo: {tipo}")
            print(f"   Título: {titulo}")
            
            return notif_id
            
        except Exception as e:
            print(f"❌ Error guardando notificación: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_professional_notifications(self, profesional_id, unread_only=True):
        """Obtener notificaciones del profesional"""
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
                    ORDER BY id DESC  # Ordenar por ID para ver las más recientes primero
                """
                cursor.execute(query, (profesional_id,))
            else:
                query = """
                    SELECT id, titulo, mensaje, tipo, fecha_creacion, metadata, leida
                    FROM notificaciones_profesional
                    WHERE profesional_id = %s
                    ORDER BY id DESC
                    LIMIT 50
                """
                cursor.execute(query, (profesional_id,))
            
            notifications = []
            for row in cursor.fetchall():
                fecha_str = str(row[4]) if row[4] else None
                
                notif = {
                    'id': row[0],
                    'titulo': row[1],
                    'mensaje': row[2],
                    'tipo': row[3],
                    'fecha_creacion': fecha_str,  # Solo fecha
                    'fecha_display': self._format_date_display(fecha_str),  # Formato amigable
                    'metadata': json.loads(row[5]) if row[5] else {}
                }
                if not unread_only:
                    notif['leida'] = row[6]
                
                # Ordenar por timestamp en metadata si está disponible
                notif['_timestamp'] = notif['metadata'].get('timestamp', '')
                
                notifications.append(notif)
            
            # Ordenar por timestamp real (guardado en metadata) si está disponible
            notifications.sort(key=lambda x: x['_timestamp'], reverse=True)
            
            return notifications
            
        except Exception as e:
            print(f"❌ Error obteniendo notificaciones: {e}")
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
            elif fecha == hoy - timedelta(days=1):  # Aquí está corregido
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
            print(f"⚠️ Error formateando fecha {fecha_str}: {e}")
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
            print(f"❌ Error marcando como leída: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    def get_unread_count(self, profesional_id):
        """Contar notificaciones no leídas"""
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
            count = cursor.fetchone()[0]
            return count
            
        except Exception as e:
            print(f"❌ Error contando notificaciones: {e}")
            return 0
        finally:
            if conn:
                conn.close()

# Instancia global
notification_system = ProfessionalNotificationSystem()