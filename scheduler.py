# scheduler.py
import schedule
import time
import threading
from datetime import datetime
from whatsapp_handler import enviar_recordatorio_24h, enviar_recordatorio_1h
import database as db

def verificar_recordatorios():
    """Verificar y enviar recordatorios automáticos"""
    try:
        print(f"⏰ Verificando recordatorios... {datetime.now().strftime('%H:%M')}")
        
        citas = db.obtener_citas_proximas_recordatorio()
        
        # Recordatorios 24 horas antes
        for cita in citas['citas_24h']:
            try:
                enviar_recordatorio_24h(cita)
                db.marcar_recordatorio_enviado(cita['id'], '24h')
                print(f"✅ Recordatorio 24h enviado para cita #{cita['id']}")
            except Exception as e:
                print(f"❌ Error enviando recordatorio 24h: {e}")
        
        # Recordatorios 1 hora antes
        for cita in citas['citas_1h']:
            try:
                enviar_recordatorio_1h(cita)
                db.marcar_recordatorio_enviado(cita['id'], '1h')
                print(f"✅ Recordatorio 1h enviado para cita #{cita['id']}")
            except Exception as e:
                print(f"❌ Error enviando recordatorio 1h: {e}")
                
    except Exception as e:
        print(f"❌ Error en recordatorios automáticos: {e}")

def iniciar_scheduler():
    """Iniciar el scheduler de recordatorios"""
    # Programar verificación cada minuto
    schedule.every(1).minutes.do(verificar_recordatorios)
    
    print("🔄 Scheduler de recordatorios iniciado")
    
    while True:
        schedule.run_pending()
        time.sleep(1)