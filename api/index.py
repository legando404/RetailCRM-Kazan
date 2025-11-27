from fastapi import FastAPI
import httpx
import asyncio
import re
import os
import retailcrm
from imap_tools import MailBox
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# --- Настройки ---
URL = os.getenv("URL")  # 'https://laminat77.retailcrm.ru'
SITE = os.getenv('site')  # 'kazan-novers-ru'
APIKEY = os.getenv('key') #'vikuHSdIKilFPMr0oyj5LpemwHvEPjVw'
USERNAME = os.getenv('user')  # "novers495@mail.ru"
PASSWORD = os.getenv('password')  #"r4ZuvyWydYMktHuTn3uJ"
IMAP_SERVER = os.getenv('imap')  # "imap.mail.ru"

HEADERS = {'X-API-KEY': APIKEY, 'Content-Type': 'image/jpeg'}
retail_client = retailcrm.v5(URL, APIKEY)


# --- Функция загрузки файла ---
async def upload_file(client, file, order_id):
    try:
        response = await client.post(f"{URL}/api/v5/files/upload", data=file.payload, headers=HEADERS)
        file_id = response.json()["file"]["id"]
        filename = ''.join(re.findall(r"\w+| |\.", file.filename))
        data = {
            'id': file_id,
            'filename': file.filename,
            'attachment': [{'order': {'id': order_id}}]
        }
        retail_client.files_edit(data)
        print(f"Uploaded {file.filename} to order {order_id}")
    except Exception as e:
        print("Upload exception:", e)


# --- Получение писем ---
async def get_mail(username, password, imap_server):
    print("Connecting to IMAP server...")
    with MailBox(imap_server).login(username, password, initial_folder='Novers Казань') as mailbox:
        # Проверим, существует ли папка назначения
        if not mailbox.folder.exists('Novers Казань/INBOX|Казань'):
            mailbox.folder.create('Novers Казань/INBOX|Казань')

        messages = list(mailbox.fetch())
        if not messages:
            print("No emails in 'Novers Казань'. Nothing to do.")
            return []

        result = []
        for msg in messages:
            attachments = [a for a in msg.attachments]

            name_match = re.search(r'(.*) <' + re.escape(msg.from_) + '>', msg.from_values.full)
            if name_match:
                name_parts = name_match.group(1).split()
                last_name = name_parts[-1]
                first_name = ' '.join(name_parts[:-1])
            else:
                first_name, last_name = '', ''

            # Перемещаем письмо в папку INBOX|Казань после добавления в список
            mailbox.move(msg.uid, 'Novers Казань/INBOX|Казань')

            result.append({
                "email": msg.from_,
                "first_name": first_name,
                "last_name": last_name,
                "subject": msg.subject,
                "text": msg.text,
                "html": msg.html,
                "attachments": attachments
            })

        return result


# --- Создание заказа ---
async def post_order(client, first_name, last_name, email, subject, text, html, attachments):
    print(f"Posting order for {email}...")
    try:
        customers = client.customers({'email': email}).get_response().get("customers", [])
    except Exception as e:
        print("Customer fetch exception:", e)
        customers = []

    order_data = {
        'customerComment': text,
        'status': 'novoe-pismo',
        'orderMethod': 'e-mail',
        'customFields': {
            'tema_pisma1': subject,
            'tekst_pisma': text
        },
        'lastName': last_name,
        'firstName': first_name,
        'email': email
    }

    if customers:
        order_data["customer"] = {'id': customers[0]["id"]}
        print(f"Existing customer found: {customers[0]['email']}")

    try:
        result = client.order_create(order_data, SITE)
        print("Order created:", result.get_response())
        return result
    except Exception as e:
        print("Order creation exception:", e)
        return None


# --- Обработка всех писем ---
async def process_mail(client):
    messages = await get_mail(USERNAME, PASSWORD, IMAP_SERVER)
    if not messages:
        return "No emails to process."

    results = []
    for msg in messages:
        response = await post_order(
            retail_client,
            msg["first_name"],
            msg["last_name"],
            msg["email"],
            msg["subject"],
            msg["text"],
            msg["html"],
            msg["attachments"]
        )

        if response:
            order_id = response.get_response()["id"]
            for attachment in msg["attachments"]:
                if attachment.content_disposition == 'attachment':
                    await upload_file(client, attachment, order_id)
        results.append(response)

    return results


# --- Основная задача ---
async def task():
    async with httpx.AsyncClient() as client:
        return await process_mail(client)


# --- FastAPI endpoint ---
@app.get('/api')
async def api():
    output = await task()
    return output
