# diagnostico_rapido.py
import sqlite3

def diagnostico_rapido():
    conn = sqlite3.connect('barberia.db')
    cursor = conn.cursor()
    
    print("🔍 DIAGNÓSTICO RÁPIDO")
    print("=" * 40)
    
    # 1. Usuarios barbero
    cursor.execute('SELECT id, nombre, negocio_id FROM usuarios WHERE rol = "barbero"')
    usuarios_barbero = cursor.fetchall()
    print(f"👤 USUARIOS BARBERO: {len(usuarios_barbero)}")
    for u in usuarios_barbero:
        print(f"   - {u[1]} (ID: {u[0]}, Negocio: {u[2]})")
    
    # 2. Barberos existentes
    cursor.execute('SELECT id, nombre, usuario_id, negocio_id FROM barberos')
    barberos = cursor.fetchall()
    print(f"\n💈 BARBEROS EXISTENTES: {len(barberos)}")
    for b in barberos:
        estado = f"Vinculado: {b[2]}" if b[2] else "SIN USUARIO"
        print(f"   - {b[1]} (ID: {b[0]}, {estado}, Negocio: {b[3]})")
    
    # 3. Usuarios sin barbero
    print(f"\n❌ USUARIOS BARBERO SIN BARBERO:")
    for usuario in usuarios_barbero:
        usuario_id, usuario_nombre, negocio_id = usuario
        cursor.execute(
            'SELECT id FROM barberos WHERE usuario_id = ? OR (nombre = ? AND negocio_id = ?)', 
            (usuario_id, usuario_nombre, negocio_id)
        )
        barbero = cursor.fetchone()
        if not barbero:
            print(f"   - {usuario_nombre} (ID: {usuario_id})")
    
    conn.close()

if __name__ == '__main__':
    diagnostico_rapido()