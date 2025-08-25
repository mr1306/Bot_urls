import requests
import asyncio
import time
import datetime
import sqlite3
from telegram import Bot

# ===============================
# Configuración
# ===============================
TELEGRAM_BOT_TOKEN = '7501953959:AAHl2cPmK-dVbIMvj2WOhC-_A9zMhCakWE4'   # reemplazar por token real
TELEGRAM_CHAT_ID = '5107165446'
SITES_FILE = '/home/mariana/Bot_urls/sitios.txt'

RETRIES = 3                # Reintentos por verificación
DELAY_BETWEEN_RETRIES = 5  # Segundos entre reintentos
DELAY_BETWEEN_CHECKS = 300 # 5 minutos

DB = "monitoreo.db"
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# ===============================
# Funciones de Base de Datos
# ===============================
def init_db():
    """Inicializa las tablas si no existen."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registros_detalle (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        servidor TEXT NOT NULL,
        fecha_hora TEXT NOT NULL,
        estado TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS resumen_diario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        servidor TEXT NOT NULL,
        fecha TEXT NOT NULL,
        estado_final TEXT NOT NULL,
        up_count INTEGER DEFAULT 0,
        down_count INTEGER DEFAULT 0,
        UNIQUE(servidor, fecha)
    )
    """)

    conn.commit()
    conn.close()

def guardar_resultado(servidor, estado):
    """Guarda el resultado de un chequeo en la tabla de detalle."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    fecha_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO registros_detalle (servidor, fecha_hora, estado) VALUES (?, ?, ?)",
                   (servidor, fecha_hora, estado))
    conn.commit()
    conn.close()
    
    # Llamar a actualizar_resumen_diario con su propia conexión
    actualizar_resumen_diario(servidor)


def actualizar_resumen_diario(servidor):
    """Actualiza la tabla de resumen diario según los registros del día."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    hoy = datetime.datetime.now().strftime("%Y-%m-%d")

    try:
        # Contar UP y DOWN para el día actual
        cursor.execute("""
            SELECT estado, COUNT(*) as conteo 
            FROM registros_detalle
            WHERE servidor = ? AND fecha_hora LIKE ?
            GROUP BY estado
        """, (servidor, hoy + "%"))
        
        resultados = cursor.fetchall()
        
        up_count = 0
        down_count = 0
        
        for estado, conteo in resultados:
            if estado == 'UP':
                up_count = conteo
            elif estado == 'DOWN':
                down_count = conteo

        # Regla: si hay algún DOWN → estado_final = DOWN, sino = UP
        estado_final = "DOWN" if down_count > 0 else "UP"

        # Verificar si la tabla tiene las columnas up_count y down_count
        cursor.execute("PRAGMA table_info(resumen_diario)")
        columnas = [col[1] for col in cursor.fetchall()]
        
        if 'up_count' in columnas and 'down_count' in columnas:
            # Usar la versión con conteos
            cursor.execute("""
                INSERT INTO resumen_diario (servidor, fecha, estado_final, up_count, down_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(servidor, fecha) DO UPDATE SET 
                    estado_final=excluded.estado_final,
                    up_count=excluded.up_count,
                    down_count=excluded.down_count
            """, (servidor, hoy, estado_final, up_count, down_count))
        else:
            # Usar la versión sin conteos (backward compatibility)
            cursor.execute("""
                INSERT INTO resumen_diario (servidor, fecha, estado_final)
                VALUES (?, ?, ?)
                ON CONFLICT(servidor, fecha) DO UPDATE SET estado_final=excluded.estado_final
            """, (servidor, hoy, estado_final))
        
        conn.commit()
        
    except Exception as e:
        print(f"Error al actualizar resumen diario: {e}")
        conn.rollback()
        
    finally:
        conn.close()

# ===============================
# Funciones de Monitoreo
# ===============================
def load_sites_from_file(filename):
    """Carga las URLs a verificar desde un archivo de texto."""
    sites = []
    try:
        with open(filename, 'r') as file:
            for line in file:
                site = line.strip()
                if site:
                    sites.append(site)
    except FileNotFoundError:
        print(f"Error: El archivo {filename} no existe.")
    return sites

def check_website(url):
    """Verifica si un sitio responde correctamente."""
    for attempt in range(RETRIES):
        try:
            response = requests.get(url, timeout=10)
            if url == "https://diaguita.ffyb.uba.ar/api/webhook":
                if response.status_code == 404:
                    return True
                else:
                    print(f"{url} no está devolviendo el código esperado (404).")
                    return False
            if response.status_code == 200:
                return True
        except requests.RequestException as e:
            print(f"Intento {attempt + 1} fallido para {url}: {e}")
        if attempt < RETRIES - 1:
            time.sleep(DELAY_BETWEEN_RETRIES)
    return False

async def send_telegram_message(message):
    """Envía un mensaje al chat de Telegram."""
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"Error al enviar mensaje a Telegram: {e}")

# ===============================
# Lógica Principal
# ===============================
async def main():
    init_db()  # crea las tablas si no existen

    websites = load_sites_from_file(SITES_FILE)
    if not websites:
        print("No se encontraron sitios para verificar.")
        return

    site_status = {site: True for site in websites}
    last_all_up_notification_time = datetime.datetime.min  # Inicializar con tiempo muy antiguo
    down_sites = set()  # Conjunto para llevar registro de sitios caídos
    last_summary_sent_time = datetime.datetime.min  # Para controlar el envío de resúmenes

    while True:
        all_sites_up = True
        status_changed = False  # Para detectar si hubo cambios en esta iteración
        current_time = datetime.datetime.now()

        for website in websites:
            is_up = check_website(website)

            if not is_up and site_status[website]:
                print(f"{website} ahora está caído, esperando 5 minutos para verificar de nuevo...")
                await asyncio.sleep(DELAY_BETWEEN_CHECKS)
                second_check = check_website(website)

                if not second_check:
                    # Enviar mensaje individual de caída
                    await send_telegram_message(f"⚠️ El sitio web {website} no funciona en los últimos 10 minutos.")
                    
                    # Actualizar estado del sitio
                    site_status[website] = False
                    down_sites.add(website)
                    status_changed = True
                    guardar_resultado(website, "DOWN")
                    print(f"{website} sigue caído, pero ya se notificó.")
                else:
                    print(f"{website} volvió a estar activo en la segunda verificación.")
                    site_status[website] = True
                    guardar_resultado(website, "UP")
                    print(f"{website} está activo.")

            elif is_up and not site_status[website]:
                # Sitio recuperado después de estar caído
                await send_telegram_message(f"✅ El sitio web {website} volvió a estar disponible.")
                site_status[website] = True
                if website in down_sites:
                    down_sites.remove(website)
                status_changed = True
                guardar_resultado(website, "UP")
                print(f"{website} está activo.")

            elif is_up:
                guardar_resultado(website, "UP")
                print(f"{website} está activo.")

            else:
                guardar_resultado(website, "DOWN")
                if website not in down_sites:
                    down_sites.add(website)
                all_sites_up = False
                print(f"{website} sigue caído, pero ya se notificó.")

            # Verificar si el sitio está caído para el resumen
            if not site_status[website]:
                all_sites_up = False

        # Enviar resumen solo si hubo cambios o ha pasado mucho tiempo desde el último resumen
        minutes_since_last_summary = (current_time - last_summary_sent_time).total_seconds() / 60
        
        if status_changed or (not all_sites_up and minutes_since_last_summary >= 60):
            if all_sites_up:
                # Todos los sitios funcionan
                await send_telegram_message("✅ Todos los sitios responden correctamente.")
                last_all_up_notification_time = current_time
                down_sites.clear()  # Limpiar el registro de sitios caídos
                last_summary_sent_time = current_time
            elif down_sites:
                # Algunos sitios están caídos - enviar resumen
                if len(down_sites) == 1:
                    message = f"📊 Resumen: Todas las URLs funcionan con normalidad excepto:\n• {list(down_sites)[0]}"
                else:
                    message = "📊 Resumen: Todas las URLs funcionan con normalidad excepto:\n" + "\n".join([f"• {site}" for site in down_sites])
                await send_telegram_message(message)
                last_summary_sent_time = current_time

        # También enviar resumen positivo cada hora si todo está bien
        if all_sites_up:
            now = datetime.datetime.now()
            minutes_since_last = (now - last_all_up_notification_time).total_seconds() / 60
            if minutes_since_last >= 60:
                await send_telegram_message("✅ Todos los sitios responden correctamente.")
                last_all_up_notification_time = now
                down_sites.clear()

        print()  # Línea en blanco para separar ciclos en la terminal
        await asyncio.sleep(DELAY_BETWEEN_CHECKS)

# ===============================
# Ejecución
# ===============================
if __name__ == "__main__":
    asyncio.run(main())