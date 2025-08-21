# FFyB Bot de Monitoreo

Este proyecto permite monitorear el estado de distintas URLs, enviar notificaciones a Telegram cuando una URL esté caída, y exponer una interfaz web (Flask) para consultar el historial de chequeos y un resumen diario.

---

## Requisitos

- Python 3.9 o superior
- pip (administrador de paquetes de Python)

Librerías necesarias (se instalan desde `requirements.txt`):
- requests
- python-telegram-bot
- flask

---

## Instalación

1. Clonar este repositorio:

```bash
git clone https://github.com/mr1306/Bot_urls.git
cd Bot_urls

python3 -m venv ent_virtual    # crea el entorno virtual 
source venv/bin/activate       # ingresa al entorno
pip install -r requirements.txt    # instala paquete de librerías

---

## Inicializa la BD
sqlite3 monitoreo.db < init_db.sql

## Comandos para correr los script
python3 check_urls_bot.py
python3 web.py

## Url para consultar la web
http://157.92.151.243:5000/  # deatalle_diario
http://157.92.151.243:5000/resumen  # resumen del día


