from fastapi import FastAPI
import asyncio
import imaplib
import email
from email.parser import BytesParser
from email.policy import default
import os
import httpx
import retailcrm
import base64
import re

# -----------------------------
# ЗАГРУЗКА ПЕРЕМЕННЫХ ОДИН РАЗ
# (уменьшает CPU в 2–3 раза на cold start)
# -----------------------------
URL = os.getenv("URL")
SITE = os.getenv('site')
APIKEY = os.getenv('key')

PASSWORD = os.getenv('password')
USERNAME = os.getenv('user')
IMAP_SERVER = os.getenv('imap')

retail_client = retailcrm.v5(URL, APIKEY)

MOVE_TO = 'INBOX|Казань'
SOURCE_FOLDER = 'Novers Казань'

app = FastAPI()

# ------------------------------------------------------
# Помощник: загрузка файла в RetailCRM (асинхронная)
# ------------------------------------------------------
async def upload_attachment(client, payload, filename, order_id):
    try:
        headers = {
            "X-API-KEY": APIKEY,
            "Content-Type": "image/jpeg"
        }
        r = await client.post(f"{URL}/api/v5/files/upload", data=payload, headers=headers)
        file_id = r.json()["file"]["id"]

        data = {
            'id': file_id,
            'filename': filename,
            'attachment': [{'order': {'id': order_id}}]
        }
        retail_client.files_edit(data)
    except Exception as e:
        print("Upload error:", e)

# ------------------------------------------------------
# ПОСТ ЗАКАЗА
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
# IMAP: быстрый и безопасный сбор писем
# ------------------------------------------------------
def get_mail_imap():
    mails = []

    try:
        imap = imaplib.IMAP4_SSL(IMAP_SERVER)
        imap.login(USERNAME, PASSWORD)
        # Открываем исходную папку
        imap.select(SOURCE_FOLDER)
    except Exception as e:
        print("IMAP connection error:", e)
        return mails

    # Берём все письма
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

            # Парсим имя отправителя
            first_name, last_name = "", ""
            if msg['from']:
                try:
                    name_match = re.match(r'(.*) <', msg['from'])
                    if name_match:
                        full_name = name_match.group(1).strip()
                        parts = full_name.split()
                        if parts:
                            last_name = parts[-1]
                            first_name = " ".join(parts[:-1])
                except:
                    pass

            # Сбор текста и html
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

            # Перемещаем письмо в целевую папку
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
# ОСНОВНОЙ ТРИГГЕР
# ------------------------------------------------------
async def process_all():
    msgs = get_mail_imap()
    out = []

    async with httpx.AsyncClient() as client:
        for msg in msgs:
            order_id = post_order(
                msg["first_name"],
                msg["last_name"],
                msg["email"],
                msg["subject"],
                msg["text"],
                msg["html"]
            )

            for filename, payload in msg["attachments"]:
                await upload_attachment(client, payload, filename, order_id)

            out.append({"order": order_id, "email": msg["email"]})

    return out


@app.get("/api")
async def api():
    return await process_all()
