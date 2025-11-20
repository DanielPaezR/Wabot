import sqlite3
import hashlib

def actualizar_hashes():
    conn = sqlite3.connect('agendamiento.db')
    cursor = conn.cursor()
    
    # Actualizar todos los usuarios a SHA256
    usuarios = [
        ('admin123', 'admin@negociobot.com'),
        ('propietario123', 'juan@negocio.com'), 
        ('profesional123', 'carlos@negocio.com'),
        ('profesional123', 'ana@negocio.com')
    ]
    
    for password, email in usuarios:
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute('UPDATE usuarios SET password_hash = ? WHERE email = ?', 
                      (password_hash, email))
        print(f"✅ Actualizado: {email}")
    
    conn.commit()
    conn.close()
    print("\n🎯 TODAS LAS CONTRASEÑAS ACTUALIZADAS A SHA256")

actualizar_hashes()