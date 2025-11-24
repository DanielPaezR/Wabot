# limpiar_horarios.py
from database import limpiar_registros_duplicados_horarios, get_db_connection

def main():
    print("🧹 Limpiando y corrigiendo configuración de horarios...")
    
    # Conectar a la base de datos para ver el antes/después
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Contar antes
    cursor.execute('SELECT COUNT(*) FROM configuracion_horarios WHERE negocio_id = 1')
    count_antes = cursor.fetchone()[0]
    print(f"📊 Registros antes: {count_antes}")
    
    # Mostrar configuración actual
    print("🔍 CONFIGURACIÓN ACTUAL:")
    cursor.execute('SELECT dia_semana, activo, hora_inicio, hora_fin FROM configuracion_horarios WHERE negocio_id = 1 ORDER BY dia_semana')
    dias_bd = cursor.fetchall()
    for dia_num, activo, inicio, fin in dias_bd:
        estado = "✅ ACTIVO" if activo else "❌ INACTIVO"
        print(f"  Día {dia_num}: {estado} ({inicio} - {fin})")
    
    conn.close()
    
    # Ejecutar limpieza
    if limpiar_registros_duplicados_horarios(1):
        print("✅ Limpieza de duplicados completada")
        
        # ELIMINAR DÍA 7 (no existe en semana real)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM configuracion_horarios WHERE negocio_id = 1 AND dia_semana = 7')
        eliminados = cursor.rowcount
        if eliminados > 0:
            print(f"✅ Día 7 eliminado ({eliminados} registro(s))")
        
        # Contar después
        cursor.execute('SELECT COUNT(*) FROM configuracion_horarios WHERE negocio_id = 1')
        count_despues = cursor.fetchone()[0]
        
        # Mostrar configuración final
        print("🔍 CONFIGURACIÓN FINAL:")
        cursor.execute('SELECT dia_semana, activo, hora_inicio, hora_fin FROM configuracion_horarios WHERE negocio_id = 1 ORDER BY dia_semana')
        dias_bd = cursor.fetchall()
        for dia_num, activo, inicio, fin in dias_bd:
            estado = "✅ ACTIVO" if activo else "❌ INACTIVO"
            print(f"  Día {dia_num}: {estado} ({inicio} - {fin})")
        
        conn.commit()
        conn.close()
        
        print(f"📊 Registros después: {count_despues}")
        print(f"🗑️  Registros eliminados: {count_antes - count_despues}")
        print("🎯 Configuración lista para usar con la nueva conversión de días")
    else:
        print("❌ Error en la limpieza")

if __name__ == "__main__":
    main()