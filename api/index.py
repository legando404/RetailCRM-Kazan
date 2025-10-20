import os
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from imap_tools import MailBox, AND
from dotenv import load_dotenv

# Загружаем переменные окружения (.env)
load_dotenv()

# Настройки почты
IMAP_SERVER = os.getenv('IMAP_SERVER', 'imap.yandex.ru')
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')

# Папки (можно переопределить в .env)
MAIL_FOLDER_MAIN = os.getenv('MAIL_FOLDER_MAIN', 'Novers Казань')
MAIL_FOLDER_DONE = os.getenv('MAIL_FOLDER_DONE', 'Novers Казань/INBOX|Казань')

# Ограничение количества писем за одно выполнение
MAX_MESSAGES_PER_INVOCATION = 10

# Пул потоков для выполнения блокирующих операций
executor = ThreadPoolExecutor(max_workers=4)


# --- Асинхронный вызов IMAP в отдельном потоке ---
async def fetch_mail_blocking():
    """
    Получение непрочитанных писем и перемещение их в подпапку.
    Работает неблокирующе (через run_in_executor).
    """

    def _fetch():
        results = []
        try:
            with MailBox(IMAP_SERVER).login(EMAIL_USER, EMAIL_PASS, initial_folder=MAIL_FOLDER_MAIN) as mailbox:
                print(f"[OK] Подключено к {IMAP_SERVER}, папка '{MAIL_FOLDER_MAIN}'")

                # Проверяем и создаём папку для перемещения писем
                if not mailbox.folder.exists(MAIL_FOLDER_DONE):
                    print(f"[INFO] Папка '{MAIL_FOLDER_DONE}' не найдена, создаю...")
                    mailbox.folder.create(MAIL_FOLDER_DONE)

                # Получаем только непрочитанные письма
                for i, msg in enumerate(mailbox.fetch(AND(seen=False))):
                    if i >= MAX_MESSAGES_PER_INVOCATION:
                        print("[INFO] Достигнут лимит писем за одно выполнение.")
                        break

                    attachments = list(msg.attachments)

                    try:
                        name_match = re.search(r'(.*) <' + re.escape(msg.from_) + r'>', msg.from_values.full)
                        if name_match:
                            name = name_match.group(1).split(' ')
                        else:
                            name = msg.from_values.full.split(' ')
                    except Exception:
                        name = []

                    last_name = name[-1] if name else ''
                    first_name = ' '.join(name[:-1]) if len(name) > 1 else ''

                    data = {
                        "email": msg.from_,
                        "first_name": first_name,
                        "last_name": last_name,
                        "subject": msg.subject,
                        "text": msg.text,
                        "html": msg.html,
                        "attachments": attachments,
                        "uid": msg.uid
                    }
                    results.append(data)

                    # Перемещаем письмо в подкаталог после обработки
                    try:
                        mailbox.move(msg.uid, MAIL_FOLDER_DONE)
                        print(f"[MOVE] Письмо UID {msg.uid} → {MAIL_FOLDER_DONE}")
                    except Exception as e:
                        print(f"[ERROR] Не удалось переместить письмо UID {msg.uid}: {e}")

            print(f"[DONE] Всего обработано писем: {len(results)}")
            return results

        except Exception as e:
            print(f"[ERROR] Ошибка IMAP: {e}")
            return results

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _fetch)


# --- Основная функция (точка входа для Vercel или локального запуска) ---
async def main():
    print("[START] Запуск обработки писем...")
    mails = await fetch_mail_blocking()

    if not mails:
        print("[INFO] Новых писем не найдено.")
    else:
        print(f"[INFO] Получено {len(mails)} писем.")
        # Здесь можно добавить дальнейшую обработку (отправку в CRM и т.д.)

    print("[END] Обработка завершена.")
    return {"processed": len(mails)}


# --- Для локального теста ---
if __name__ == "__main__":
    asyncio.run(main())
