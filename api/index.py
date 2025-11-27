from fastapi import FastAPI
import asyncio
import imaplib
from email.parser import BytesParser
from email.policy import default
import os
import httpx
import retailcrm
import re

# -----------------------------
# Переменные окружения
# -----------------------------
URL = os.getenv("URL")
APIKEY = os.getenv("APIKEY")
SITE = os.getenv("SITE")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
IMAP_SERVER = os.getenv("IMAP_SERVER")

MOVE_TO = 'Novers Казань/INBOX|Казань'
SOURCE_FOLDER = 'Novers Казань'

# Проверка переменных окружения
if not all([URL, APIKEY, SITE, USERNAME, PASSWORD, IMAP_SERVER]):
    raise RuntimeError("Не все переменные окружения установлены!")

# Клиент RetailCRM
retail_client = retailcrm.v5(URL, APIKEY)

# FastAPI для Vercel
app = FastAPI()

# ------------------------------------------------------
# Асинхронная загрузка вложений в RetailCRM
# ------------------------------------------------------
async def upload_attachment(client, payload, filename, order_id):
    try:
        headers = {"X-API-KEY": APIKEY, "Content-Type": "image/jpeg"}
        r = await client.post(f"{URL}/api/v5/files/upload", data=payload, headers=headers)
        file_id = r.json()["file"]["id"]
        data = {'id': file_id, 'filename': filename, 'attachment':[{'order':{'id': order_id}}]}
        retail_client.files_edit(data)
    except Exception as e:
        print("Upload error:", e)

# ------------------------------------------------------
# Создание заказа
# ------------------------------------------------------
def post_order(first_name, last_name, email_addr, subject, text, html):
    try:
        customers = retail_client.customers({'email': email_addr}).get_response().get("customers", [])
    except:
        customers = []

    order = {
        'customerComment': text,
        'status': 'novoe-pismo',
        'orderMethod': 'e-mail',
        'customFields': {'tema_pisma1': subject, 'tekst_pisma': text},
        'lastName': last_name,
        'firstName': first_name,
        'email': email_addr
    }

    if customers:
        order["customer"] = {'id': customers[0]["id"]}

    result = retail_client.order_create(order, SITE)
    return result.get_response()["id"]

# ------------------------------------------------------
# Получение писем через IMAP
# ------------------------------------------------------
def get_mail_imap():
    mails = []
    try:
        imap = imaplib.IMAP4_SSL(IMAP_SERVER)
        imap.login(USERNAME, PASSWORD)
        imap.select(SOURCE_FOLDER)
    except Exception as e:
        print("IMAP connection error:", e)
        return mails

    status, data = imap.search(None, "ALL")
    if status != "OK":
        print("IMAP search failed")
        imap.close()
        imap.logout()
        return mails

    for num in data[0].split():
        try:
            status, msg_data = imap.fetch(num, "(RFC822)")
            if status != "OK":
                continue

            msg = BytesParser(policy=default).parsebytes(msg_data[0][1])

            # Парсим имя
            first_name, last_name = "", ""
            if msg['from']:
                try:
                    match = re.match(r'(.*) <', msg['from'])
                    if match:
                        full_name = match.group(1).strip()
                        parts = full_name.split()
                        if parts:
                            last_name = parts[-1]
                            first_name = " ".join(parts[:-1])
                except:
                    pass

            # Текст + HTML
            text, html = "", ""
            attachments = []

            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    disp = str(part.get("Content-Disposition") or "")
                    if "attachment" in disp:
                        filename = part.get_filename() or "unknown"
                        payload = part.get_payload(decode=True)
                        attachments.append((filename, payload))
                    else:
                        if ctype == "text/plain":
                            text = part.get_content()
                        elif ctype == "text/html":
                            html = part.get_content()
            else:
                if msg.get_content_type() == "text/plain":
                    text = msg.get_content()

            mails.append({
                "email": msg['from'],
                "first_name": first_name,
                "last_name": last_name,
                "subject": msg['subject'] or "",
                "text": text,
                "html": html,
                "attachments": attachments
            })

            # Перемещение письма
            try:
                imap.copy(num, MOVE_TO)
                imap.store(num, '+FLAGS', '\\Deleted')
            except Exception as e:
                print(f"Error moving message {num}:", e)

        except Exception as e:
            print(f"Error processing message {num}:", e)
            continue

    imap.expunge()
    imap.close()
    imap.logout()

    return mails

# ------------------------------------------------------
# Основной асинхронный процесс
# ------------------------------------------------------
async def process_all():
    msgs = get_mail_imap()
    out = []

    async with httpx.AsyncClient() as client:
        for msg in msgs:
            order_id = post_order(
                msg["first_name"], msg["last_name"], msg["email"],
                msg["subject"], msg["text"], msg["html"]
            )

            for filename, payload in msg["attachments"]:
                await upload_attachment(client, payload, filename, order_id)

            out.append({"order": order_id, "email": msg["email"]})

    return out

# ------------------------------------------------------
# FastAPI route для Vercel
# ------------------------------------------------------
@app.get("/api")
async def api():
    return await process_all()
