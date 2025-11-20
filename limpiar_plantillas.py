# limpiar_plantillas.py
import sqlite3

def limpiar_plantillas():
    conn = sqlite3.connect('barberia.db')
    cursor = conn.cursor()
    
    # 1. Contar plantillas actuales
    cursor.execute('SELECT COUNT(*) FROM plantillas_mensajes')
    total_antes = cursor.fetchone()[0]
    print(f"📊 Plantillas antes: {total_antes}")
    
    # 2. Mostrar qué plantillas hay
    cursor.execute('SELECT negocio_id, nombre FROM plantillas_mensajes')
    plantillas_actuales = cursor.fetchall()
    print("📝 Plantillas actuales:")
    for p in plantillas_actuales:
        print(f"   - Negocio {p[0]}: {p[1]}")
    
    # 3. Eliminar todas las plantillas
    cursor.execute('DELETE FROM plantillas_mensajes')
    print("🗑️  Eliminando todas las plantillas...")
    
    # 4. Insertar plantillas maestras (solo 8)
    plantillas_maestras = [
        ('saludo_inicial_nuevo', '🤖 *Bienvenido a {nombre_negocio}* {emoji_negocio}\n\n{saludo_personalizado}\n\nPara comenzar, ¿cuál es tu nombre?\n\n💡 *Siempre puedes volver al menú principal con* *0*', 'Saludo para clientes nuevos', '["nombre_negocio", "emoji_negocio", "saludo_personalizado"]'),
        ('saludo_inicial_existente', '👋 ¡Hola {cliente_nombre}!\n\n*{nombre_negocio}* - ¿En qué te puedo ayudar?\n\n*1* {emoji_servicio} - Agendar cita\n*2* 📋 - Ver mis reservas\n*3* ❌ - Cancelar reserva\n*4* 🆘 - Ayuda\n\n💡 *Siempre puedes volver al menú principal con* *0*', 'Saludo para clientes existentes', '["cliente_nombre", "nombre_negocio", "emoji_servicio"]'),
        ('menu_principal', '*{nombre_negocio}* - ¿En qué te puedo ayudar?\n\n*1* {emoji_servicio} - Agendar cita\n*2* 📋 - Ver mis reservas\n*3* ❌ - Cancelar reserva\n*4* 🆘 - Ayuda\n\n💡 *Siempre puedes volver al menú principal con* *0*', 'Menú principal de opciones', '["nombre_negocio", "emoji_servicio"]'),
        ('ayuda_general', '🆘 *AYUDA - {nombre_negocio}*\n\n*1* {emoji_servicio} - Agendar cita con {texto_profesional}\n*2* 📋 - Ver tus reservas activas\n*3* ❌ - Cancelar una reserva\n*4* 🆘 - Mostrar esta ayuda\n\n💡 *Siempre puedes volver al menú principal con* *0*', 'Mensaje de ayuda general', '["nombre_negocio", "emoji_servicio", "texto_profesional"]'),
        ('error_generico', '❌ Ocurrió un error en {nombre_negocio}\n\nPor favor, intenta nuevamente o contacta a soporte.\n\n💡 *Vuelve al menú principal con* *0*', 'Mensaje de error genérico', '["nombre_negocio"]'),
        ('turno_confirmado', '✅ *¡Turno confirmado!*\n\n👤 *Cliente:* {cliente_nombre}\n{emoji_profesional} *{texto_profesional_title}:* {barbero_nombre}\n💈 *Servicio:* {servicio_nombre}\n💰 *Precio:* {precio_formateado}\n📅 *Fecha:* {fecha}\n⏰ *Hora:* {hora}\n🎫 *ID:* #{turno_id}\n\n📍 *Dirección:* {direccion}\n📞 *Contacto:* {telefono_contacto}\n\nTe enviaremos recordatorios 24 horas y 1 hora antes de tu cita.', 'Confirmación de turno agendado', '["cliente_nombre", "emoji_profesional", "texto_profesional_title", "barbero_nombre", "servicio_nombre", "precio_formateado", "fecha", "hora", "turno_id", "direccion", "telefono_contacto"]'),
        ('sin_turnos', '📋 No tienes turnos programados en {nombre_negocio}.\n\n💡 *Vuelve al menú principal con* *0*', 'Cuando el cliente no tiene turnos', '["nombre_negocio"]'),
        ('turno_cancelado', '❌ *Turno cancelado*\n\nHola {cliente_nombre}, has cancelado tu turno del {fecha} a las {hora} en {nombre_negocio}.\n\nEsperamos verte pronto en otra ocasión.', 'Confirmación de cancelación', '["cliente_nombre", "fecha", "hora", "nombre_negocio"]')
    ]
    
    for nombre, plantilla, descripcion, variables in plantillas_maestras:
        cursor.execute(
            'INSERT INTO plantillas_mensajes (negocio_id, nombre, plantilla, descripcion, variables_disponibles) VALUES (?, ?, ?, ?, ?)',
            (1, nombre, plantilla, descripcion, variables)
        )
        print(f"✅ Insertada: {nombre}")
    
    conn.commit()
    
    # 5. Verificar
    cursor.execute('SELECT COUNT(*) FROM plantillas_mensajes')
    total_despues = cursor.fetchone()[0]
    print(f"📊 Plantillas después: {total_despues}")
    
    conn.close()
    print("🎉 ¡Limpieza completada! Ahora deberías ver solo 8 plantillas.")

if __name__ == '__main__':
    limpiar_plantillas()