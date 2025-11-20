import sqlite3

# Conectar a la base de datos
conn = sqlite3.connect('negocio.db')
cursor = conn.cursor()

try:
    # Ejecutar el UPDATE
    cursor.execute("UPDATE usuarios SET rol = 'profesional' WHERE rol = 'barbero'")
    
    # Verificar cuántas filas fueron afectadas
    print(f"✅ Filas actualizadas: {cursor.rowcount}")
    
    # Confirmar los cambios
    conn.commit()
    print("✅ Roles actualizados exitosamente")
    
    # Verificar los cambios
    cursor.execute("SELECT id, nombre, rol FROM usuarios WHERE rol = 'profesional'")
    usuarios_actualizados = cursor.fetchall()
    
    print(f"👥 Usuarios con rol 'profesional': {len(usuarios_actualizados)}")
    for usuario in usuarios_actualizados:
        print(f"  - {usuario[1]} (ID: {usuario[0]})")
        
except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()
finally:
    conn.close()