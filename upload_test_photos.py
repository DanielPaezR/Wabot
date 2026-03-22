# upload_test_photos.py
import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

# Configurar Cloudinary
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

# URLs de imágenes de ejemplo (descarga rápida)
imagenes = {
    # Fotos de perfil profesional
    'barbero1': 'https://randomuser.me/api/portraits/men/1.jpg',
    'barbero2': 'https://randomuser.me/api/portraits/men/2.jpg',
    'barbera': 'https://randomuser.me/api/portraits/women/1.jpg',
    
    # Fotos de trabajos (cortes de pelo)
    'corte1': 'https://images.unsplash.com/photo-1599351431202-1e0f0137899a?w=400',
    'corte2': 'https://images.unsplash.com/photo-1621605815971-fbc98d665033?w=400',
    'corte3': 'https://images.unsplash.com/photo-1585747860714-2ba6c204d875?w=400',
    'corte4': 'https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=400',
    
    # Fotos de negocio
    'portada': 'https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=800',
    'perfil': 'https://images.unsplash.com/photo-1585747860714-2ba6c204d875?w=200',
    'local1': 'https://images.unsplash.com/photo-1504753793650-d4a2b783c15e?w=400',
    'local2': 'https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?w=400',
    'local3': 'https://images.unsplash.com/photo-1527799820374-dcf8d9d4a388?w=400',
}

def subir_imagen(url, public_id):
    """Sube una imagen desde URL a Cloudinary"""
    try:
        result = cloudinary.uploader.upload(url, public_id=public_id)
        print(f"✅ Subido: {public_id} -> {result['secure_url']}")
        return result['secure_url']
    except Exception as e:
        print(f"❌ Error subiendo {public_id}: {e}")
        return None

if __name__ == "__main__":
    print("📤 Subiendo imágenes de prueba a Cloudinary...")
    
    for nombre, url in imagenes.items():
        subir_imagen(url, f"wabot_test/{nombre}")
    
    print("\n✨ Proceso completado!")