# limpiar_horarios.py
from database import limpiar_registros_duplicados_horarios, get_db_connection

def main():
    print("🧹 Limpiando registros duplicados de horarios...")
    
    # Conectar a la base de datos para ver el antes/después
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Contar antes
    cursor.execute('SELECT COUNT(*) FROM configuracion_horarios WHERE negocio_id = 1')
    count_antes = cursor.fetchone()[0]
    print(f"📊 Registros antes: {count_antes}")
    
    conn.close()
    
    # Ejecutar limpieza
    if limpiar_registros_duplicados_horarios(1):
        print("✅ Limpieza completada")
        
        # Contar después
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM configuracion_horarios WHERE negocio_id = 1')
        count_despues = cursor.fetchone()[0]
        conn.close()
        
        print(f"📊 Registros después: {count_despues}")
        print(f"🗑️  Registros eliminados: {count_antes - count_despues}")
    else:
        print("❌ Error en la limpieza")

if __name__ == "__main__":
    main()