# reset_hashes.py - Resetear todos los hashes a SHA256
import sqlite3
import hashlib

def resetear_todos_los_hashes():
    """Resetear todos los hashes a SHA256 correctos"""
    print("🔄 RESETEANDO TODOS LOS HASHES A SHA256...")
    
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    # Mapeo de emails a contraseñas
    usuarios_config = {
        'admin@negociobot.com': 'admin123',
        'juan@negocio.com': 'propietario123', 
        'carlos@negocio.com': 'profesional123',
        'ana@negocio.com': 'profesional123'
    }
    
    try:
        for email, password in usuarios_config.items():
            # Calcular hash SHA256
            nuevo_hash = hashlib.sha256(password.encode()).hexdigest()
            
            # Actualizar usuario
            cursor.execute(
                'UPDATE usuarios SET password_hash = ? WHERE email = ?',
                (nuevo_hash, email)
            )
            
            print(f"✅ {email} -> {password} (Hash: {nuevo_hash[:20]}...)")
        
        conn.commit()
        print("\n🎉 ¡Todos los hashes han sido reseteados!")
        print("🔐 Ahora puedes iniciar sesión con:")
        for email, password in usuarios_config.items():
            print(f"   📧 {email} / 🔒 {password}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 50)
    print("🔄 RESETEO DE HASHES SHA256")
    print("=" * 50)
    
    confirmacion = input("¿Estás seguro de que quieres resetear todos los hashes? (s/n): ")
    
    if confirmacion.lower() == 's':
        resetear_todos_los_hashes()
    else:
        print("❌ Operación cancelada")