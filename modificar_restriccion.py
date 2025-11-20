import sqlite3

def modificar_restriccion():
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    try:
        print("🔍 Buscando restricciones en la tabla usuarios...")
        
        # 1. Obtener información sobre la tabla
        cursor.execute("PRAGMA table_info(usuarios)")
        columnas = cursor.fetchall()
        print("📋 Columnas de la tabla usuarios:")
        for col in columnas:
            print(f"  - {col[1]} (Tipo: {col[2]})")
        
        # 2. Buscar el nombre de la restricción CHECK
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type = 'table' AND name = 'usuarios'
        """)
        tabla_sql = cursor.fetchone()
        
        if tabla_sql:
            print(f"📄 SQL de la tabla usuarios:")
            print(tabla_sql[0])
        
        # 3. Crear una tabla temporal con la estructura EXACTA pero nueva restricción
        print("🔄 Creando tabla temporal...")
        cursor.execute("""
            CREATE TABLE usuarios_temp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                negocio_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                rol TEXT CHECK(rol IN ('superadmin', 'propietario', 'profesional')) DEFAULT 'propietario',
                activo BOOLEAN DEFAULT 1,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ultimo_login TIMESTAMP,
                FOREIGN KEY (negocio_id) REFERENCES negocios (id)
            )
        """)
        
        # 4. Copiar los datos cambiando 'barbero' por 'profesional'
        print("📤 Copiando datos...")
        cursor.execute("""
            INSERT INTO usuarios_temp 
            SELECT 
                id,
                negocio_id,
                nombre,
                email,
                password_hash,
                CASE WHEN rol = 'barbero' THEN 'profesional' ELSE rol END as rol,
                activo,
                fecha_creacion,
                ultimo_login
            FROM usuarios
        """)
        
        # 5. Eliminar la tabla original
        print("🗑️ Eliminando tabla original...")
        cursor.execute("DROP TABLE usuarios")
        
        # 6. Renombrar la tabla temporal
        print("🔄 Renombrando tabla...")
        cursor.execute("ALTER TABLE usuarios_temp RENAME TO usuarios")
        
        # 7. Confirmar cambios
        conn.commit()
        print("✅ Restricción modificada exitosamente!")
        
        # 8. Verificar los cambios
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'profesional'")
        count_profesionales = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'barbero'")
        count_barberos = cursor.fetchone()[0]
        
        print(f"👥 Usuarios con rol 'profesional': {count_profesionales}")
        print(f"👥 Usuarios con rol 'barbero': {count_barberos}")
        
        # Mostrar todos los usuarios y sus roles
        cursor.execute("SELECT id, nombre, rol FROM usuarios ORDER BY id")
        usuarios = cursor.fetchall()
        print("📊 Lista de usuarios:")
        for usuario in usuarios:
            print(f"  - {usuario[1]} (ID: {usuario[0]}, Rol: {usuario[2]})")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        # Intentar recuperar la tabla original si hay error
        try:
            cursor.execute("DROP TABLE IF EXISTS usuarios_temp")
        except:
            pass
    finally:
        conn.close()

if __name__ == "__main__":
    modificar_restriccion()