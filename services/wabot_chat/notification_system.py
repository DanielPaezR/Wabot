# notification_system.py - VERSIÓN CORREGIDA COMPLETA
import os
import json
from datetime import datetime, timedelta
import database as db
from psycopg2.extras import RealDictCursor

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
        """Guardar notificación en PostgreSQL - VERSIÓN CORREGIDA"""
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
            
            print(f"🔔 Guardando notificación para profesional {profesional_id}")
            cursor.execute(query, (profesional_id, titulo, mensaje, tipo, metadata_json))
            
            result = cursor.fetchone()
            
            # ✅ CORRECCIÓN: Manejar cualquier tipo de resultado
            notif_id = None
            if result:
                print(f"🔍 Resultado crudo: {result}")
                print(f"🔍 Tipo de resultado: {type(result)}")
                
                if isinstance(result, dict):
                    # RealDictRow (diccionario)
                    notif_id = result.get('id')
                    if notif_id is None:
                        # Intentar con índice 0 como clave
                        notif_id = result.get(0)
                elif isinstance(result, (tuple, list)) and len(result) > 0:
                    # Tupla tradicional
                    notif_id = result[0]
                else:
                    # Último recurso: intentar obtener primer elemento
                    try:
                        notif_id = result[0]
                    except:
                        pass
            
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)  # ✅ Usar RealDictCursor
            
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
                    # ✅ CORRECCIÓN: row ya es un diccionario por RealDictCursor
                    metadata_value = row['metadata']
                    
                    # ⚠️ IMPORTANTE: metadata puede ser string JSON o ya diccionario
                    if isinstance(metadata_value, dict):
                        metadata_dict = metadata_value
                    elif metadata_value:
                        try:
                            metadata_dict = json.loads(metadata_value)
                        except:
                            metadata_dict = {}
                    else:
                        metadata_dict = {}
                    
                    notif = {
                        'id': row['id'],
                        'titulo': row['titulo'] or '',
                        'mensaje': row['mensaje'] or '',
                        'tipo': row['tipo'] or 'info',
                        'fecha_creacion': str(row['fecha_creacion']) if row['fecha_creacion'] else '',
                        'metadata': metadata_dict,  # ✅ Ya es diccionario
                        'leida': row['leida'] or False
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
                    if unread_only and not notif['leida']:
                        notifications.append(notif)
                    elif not unread_only:
                        notifications.append(notif)
                        
                except Exception as e:
                    print(f"⚠️ Error procesando fila: {e}")
                    print(f"⚠️ Row keys: {list(row.keys())}")
                    print(f"⚠️ metadata type: {type(row.get('metadata'))}")
                    print(f"⚠️ metadata value: {row.get('metadata')}")
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
        """Contar notificaciones no leídas - VERSIÓN CORREGIDA DEFINITIVA"""
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
                SELECT COUNT(*) as total
                FROM notificaciones_profesional
                WHERE profesional_id = %s AND leida = FALSE
            """
            cursor.execute(query, (profesional_id,))
            
            result = cursor.fetchone()
            
            # ✅ CORRECCIÓN: Manejar cualquier tipo de resultado
            count = 0
            
            if result:
                print(f"🔍 Resultado crudo: {result}")
                print(f"🔍 Tipo de resultado: {type(result)}")
                
                if isinstance(result, dict):
                    # RealDictCursor devuelve diccionario
                    count = result.get('total', 0) or result.get('count', 0) or result.get(0, 0)
                elif isinstance(result, (tuple, list)):
                    # Cursor normal devuelve tupla/lista
                    if len(result) > 0:
                        count = result[0] if result[0] is not None else 0
                else:
                    # Otro tipo
                    try:
                        count = int(result)
                    except:
                        count = 0
            
            print(f"✅ {count} notificaciones no leídas encontradas")
            return count
            
        except Exception as e:
            print(f"❌ Error contando notificaciones: {str(e)}")
            import traceback
            traceback.print_exc()
            return 0
        finally:
            if conn:
                conn.close()

# Instancia global
notification_system = ProfessionalNotificationSystem()