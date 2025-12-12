# sms_manager_vonage_new.py
import os
import json
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

class SMSManagerVonageNew:
    """Manejador de SMS usando Vonage Messages API (la nueva)"""
    
    def __init__(self):
        self.api_key = os.getenv('VONAGE_API_KEY')
        self.api_secret = os.getenv('VONAGE_API_SECRET')
        self.sender = os.getenv('SMS_FROM', 'BarberiaElite')
        
        print(f"📱 Vonage Messages API Manager inicializado")
        print(f"   API Key: {self.api_key}")
        
        if not self.api_key or not self.api_secret:
            print("❌ ERROR: Faltan credenciales de Vonage en .env")
            print("💡 Agrega: VONAGE_API_KEY y VONAGE_API_SECRET")
    
    def _get_auth_header(self):
        """Generar header de autenticación Basic"""
        credentials = f"{self.api_key}:{self.api_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    def enviar_sms(self, telefono, mensaje):
        """Enviar SMS usando Vonage Messages API"""
        try:
            if not self.api_key or not self.api_secret:
                print("❌ Vonage no configurado")
                return False
            
            # Asegurar formato E.164 SIN el +
            if telefono.startswith('+57'):
                telefono = telefono[1:]  # Quita el +
            elif telefono.startswith('57'):
                pass  # Ya está bien
            else:
                telefono = '57' + telefono
            
            print(f"📤 Enviando SMS Vonage a {telefono}")
            print(f"   Mensaje: {mensaje[:80]}...")
            
            # URL de la API Messages (la que mostraste)
            url = "https://api.nexmo.com/v1/messages"
            
            # Payload según documentación
            payload = {
                "message_type": "text",
                "text": mensaje,
                "to": telefono,  # Sin +, solo números
                "from": self.sender,  # Puede ser texto o número
                "channel": "sms"
            }
            
            headers = {
                "Authorization": self._get_auth_header(),
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            print(f"   URL: {url}")
            print(f"   Payload: {json.dumps(payload, ensure_ascii=False)}")
            
            # Enviar solicitud
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=15
            )
            
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
            
            if response.status_code == 201:
                result = response.json()
                message_uuid = result.get('message_uuid')
                print(f"✅ SMS enviado. Message UUID: {message_uuid}")
                return True
            elif response.status_code == 202:
                print("✅ SMS aceptado para envío")
                return True
            else:
                print(f"❌ Error HTTP {response.status_code}")
                # Intentar obtener más detalles del error
                try:
                    error_data = response.json()
                    print(f"   Error details: {error_data}")
                except:
                    pass
                return False
                
        except Exception as e:
            print(f"❌ Error enviando SMS: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def enviar_confirmacion_cita(self, cita):
        """Enviar confirmación de cita"""
        try:
            telefono = cita.get('cliente_telefono', '')
            if not telefono:
                print("❌ No hay teléfono para enviar confirmación")
                return False
            
            fecha = cita.get('fecha', '')
            hora = cita.get('hora', '')
            
            mensaje = f"✅ CONFIRMACIÓN DE CITA\n\n"
            mensaje += f"Hola {cita.get('cliente_nombre', 'Cliente')},\n"
            mensaje += f"Tu cita ha sido confirmada:\n\n"
            mensaje += f"📅 Fecha: {fecha}\n"
            mensaje += f"⏰ Hora: {hora}\n"
            mensaje += f"💈 Negocio: {cita.get('negocio_nombre', '')}\n"
            mensaje += f"📍 Dirección: {cita.get('negocio_direccion', '')}\n"
            mensaje += f"👨‍💼 Profesional: {cita.get('profesional_nombre', '')}\n"
            mensaje += f"✂️ Servicio: {cita.get('servicio_nombre', '')}\n"
            mensaje += f"💰 Precio: ${cita.get('precio', 0):,}\n\n"
            mensaje += f"📱 Para cambios: {telefono}\n\n"
            mensaje += f"¡Te esperamos!"
            
            return self.enviar_sms(telefono, mensaje)
            
        except Exception as e:
            print(f"❌ Error en confirmación: {e}")
            return False
    
    def enviar_recordatorio_24h(self, cita):
        """Enviar recordatorio 24 horas antes"""
        try:
            telefono = cita.get('cliente_telefono', '')
            if not telefono:
                return False
            
            mensaje = f"⏰ RECORDATORIO DE CITA (24h)\n\n"
            mensaje += f"Hola {cita.get('cliente_nombre', 'Cliente')},\n"
            mensaje += f"Recuerda tu cita mañana:\n\n"
            mensaje += f"📅 Fecha: {cita.get('fecha', '')}\n"
            mensaje += f"⏰ Hora: {cita.get('hora', '')}\n"
            mensaje += f"💈 {cita.get('negocio_nombre', '')}\n"
            mensaje += f"📍 {cita.get('negocio_direccion', '')}\n\n"
            mensaje += f"Por favor confirma tu asistencia."
            
            return self.enviar_sms(telefono, mensaje)
            
        except Exception as e:
            print(f"❌ Error en recordatorio 24h: {e}")
            return False
    
    def enviar_recordatorio_1h(self, cita):
        """Enviar recordatorio 1 hora antes"""
        try:
            telefono = cita.get('cliente_telefono', '')
            if not telefono:
                return False
            
            mensaje = f"🚀 RECORDATORIO DE CITA (1h)\n\n"
            mensaje += f"Hola {cita.get('cliente_nombre', 'Cliente')},\n"
            mensaje += f"Tu cita es en 1 hora:\n\n"
            mensaje += f"⏰ Hora: {cita.get('hora', '')}\n"
            mensaje += f"💈 {cita.get('negocio_nombre', '')}\n"
            mensaje += f"📍 {cita.get('negocio_direccion', '')}\n\n"
            mensaje += f"¡Nos vemos pronto!"
            
            return self.enviar_sms(telefono, mensaje)
            
        except Exception as e:
            print(f"❌ Error en recordatorio 1h: {e}")
            return False

# Instancia global
sms_manager = SMSManagerVonageNew()