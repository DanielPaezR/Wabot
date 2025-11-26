# verificar_hashes.py - Verificar y corregir hashes SHA256
import sqlite3
import hashlib

def verificar_hashes_existentes():
    """Verificar los hashes existentes en la base de datos"""
    print("🔍 VERIFICANDO HASHES EXISTENTES...")
    
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    # Obtener todos los usuarios
    cursor.execute('SELECT id, email, password_hash FROM usuarios')
    usuarios = cursor.fetchall()
    
    print(f"📊 Total de usuarios: {len(usuarios)}")
    print("\n" + "="*60)
    
    for usuario_id, email, hash_actual in usuarios:
        print(f"👤 Usuario: {email} (ID: {usuario_id})")
        print(f"   Hash almacenado: {hash_actual}")
        
        # Determinar contraseña esperada según el email
        if email == 'admin@negociobot.com':
            password_esperada = 'admin123'
        elif email == 'juan@negocio.com':
            password_esperada = 'propietario123'
        elif email in ['carlos@negocio.com', 'ana@negocio.com']:
            password_esperada = 'profesional123'
        else:
            password_esperada = None
            print("   ⚠️  Contraseña desconocida (usuario personalizado)")
            continue
        
        if password_esperada:
            # Calcular hash SHA256 de la contraseña esperada
            hash_calculado = hashlib.sha256(password_esperada.encode()).hexdigest()
            
            if hash_actual == hash_calculado:
                print("   ✅ Hash CORRECTO - SHA256 válido")
            else:
                print("   ❌ Hash INCORRECTO - No coincide con SHA256")
                print(f"   Contraseña esperada: {password_esperada}")
                print(f"   Hash esperado: {hash_calculado}")
                
                # Preguntar si corregir
                corregir = input("   ¿Corregir este hash? (s/n): ").lower().strip()
                if corregir == 's':
                    cursor.execute(
                        'UPDATE usuarios SET password_hash = ? WHERE id = ?',
                        (hash_calculado, usuario_id)
                    )
                    conn.commit()
                    print("   ✅ Hash corregido exitosamente")
        
        print("-" * 40)
    
    conn.close()
    print("🎉 Verificación completada")

def probar_login(email, password):
    """Probar login con un usuario específico"""
    import hashlib
    
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT password_hash FROM usuarios WHERE email = ?', (email,))
    resultado = cursor.fetchone()
    
    if resultado:
        hash_almacenado = resultado[0]
        hash_calculado = hashlib.sha256(password.encode()).hexdigest()
        
        print(f"🔐 Probando login: {email}")
        print(f"   Hash almacenado: {hash_almacenado}")
        print(f"   Hash calculado:  {hash_calculado}")
        print(f"   Coinciden: {'✅ SÍ' if hash_almacenado == hash_calculado else '❌ NO'}")
        
        if hash_almacenado == hash_calculado:
            print("   🎉 ¡Login debería funcionar correctamente!")
        else:
            print("   💡 El login fallará con esta contraseña")
    else:
        print(f"❌ Usuario {email} no encontrado")
    
    conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("🔧 VERIFICADOR DE HASHES SHA256")
    print("=" * 60)
    
    # Verificar todos los hashes
    verificar_hashes_existentes()
    
    print("\n" + "=" * 60)
    print("🔐 PRUEBAS DE LOGIN")
    print("=" * 60)
    
    # Probar logins principales
    probar_login('admin@negociobot.com', 'admin123')
    probar_login('juan@negocio.com', 'propietario123') 
    probar_login('carlos@negocio.com', 'profesional123')
    probar_login('ana@negocio.com', 'profesional123')