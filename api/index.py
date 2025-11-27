from fastapi import FastAPI, Request, Body
from pydantic import BaseModel
from time import time
import httpx
import asyncio
import json
import imaplib
import email
from imap_tools import MailBox, AND
from email.header import decode_header
import base64
import re
import os
import retailcrm
import yadisk
import aiofiles
import http.client 
from dotenv import load_dotenv

load_dotenv()
#res = #conn.getresponse() data = res.read() print()

app = FastAPI()
url = os.getenv("URL")#'https://laminat77.retailcrm.ru'
site = os.getenv('site')#= 'kazan-novers-ru'
apikey = os.getenv('key') #'vikuHSdIKilFPMr0oyj5LpemwHvEPjVw'
retail_client = retailcrm.v5(url, apikey)
#headers = {'X-API-KEY' : apikey}
conn = http.client.HTTPSConnection('laminat77.retailcrm.ru')
headers = { 'X-API-KEY': apikey, 'Content-Type': 'image/jpeg' }  
password = os.getenv('password')  #"r4ZuvyWydYMktHuTn3uJ"
username = os.getenv('user')#"novers495@mail.ru"
imap_server = os.getenv('imap')#"imap.mail.ru"

def safe_filename(filename: str) -> str:
    """
    Преобразует имя файла в безопасное:
    - оставляет только буквы, цифры, _, -, .
    - заменяет пробелы на подчёркивания
    """
    filename = re.sub(r'[^a-zA-Z0-9_.- ]', '', filename)  # удаляем опасные символы
    filename = filename.replace(' ', '_')  # заменяем пробелы на _
    return filename

async def upload_file(client, file, order):
    print(file.filename, file.content_disposition)
    try:
        # Отправляем файл на сервер
        response = await client.post(
            url + "/api/v5/files/upload",
            data=file.payload,
            headers=headers
        )
        file_id = response.json()["file"]["id"]

        # Формируем безопасное имя файла
        filename = safe_filename(file.filename)

        # Данные для редактирования файла
        data = {
            'id': file_id,
            'filename': filename,
            'attachment': [{'order': {'id': order}}]
        }

        # Редактируем файл через retail_client
        response = retail_client.files_edit(data)
        print(response.get_response())

    except Exception as e:
        print('Exception:', e)

# ------------------------------ Остальной код без изменений ------------------------------

async def main(client):
    messages = await get_mail(username, password, imap_server)
    for msg in messages : 
        for a in msg["attachments"]:
            print(a.filename)
        response = await post_order(retail_client, msg["first_name"], msg["last_name"], msg["email"], msg["subject"], msg["text"], msg["html"], msg["attachments"])
        order = response.get_response()["id"]
        for a in msg["attachments"]: 
            if a.content_disposition == 'attachment':
                await upload_file(client, a, order)
        return response    

async def post_order(client, first_name, last_name, email, subject, text, html, attachments):
    print('posting...')
    try: 
       filter = {'email': email}
       customers = client.customers(filter).get_response()["customers"]        
    except Exception as e:
        print('exception: ', e)
        return e
    try: 
        print('posting.... ', customers)
        order = {'customerComment': text, 'status': 'novoe-pismo', 'orderMethod': 'e-mail', 'customFields': { 'tema_pisma1': subject, 'tekst_pisma': text}, 'lastName': last_name, 'firstName': first_name, 'email': email}
        if len(customers) > 0:
            order["customer"] = { 'id': customers[0]["id"]}
            print('customer: ', customers[0]["email"])
        result = client.order_create(order, site)
    except Exception as e:
        print('exception: ', e)
    print('result: ', result.get_response())
    return result 

async def get_mail(username, password, imap_server):
    array = []
    print('connecting to imap server...')
    with MailBox(imap_server).login(username, password, initial_folder='Novers Казань') as mailbox:
        print('fetching...')
        exists = mailbox.folder.exists('Novers Казань/INBOX|Казань')
        if not exists:
            mailbox.folder.create('Novers Казань/INBOX|Казань')
       
        # Берём все письма, вне зависимости от прочитанности
        for msg in mailbox.fetch():
            mailbox.move(msg.uid, 'Novers Казань/INBOX|Казань') 
            
            attachments = []
            for a in msg.attachments:
                print(a.filename)
                attachments.append(a)
            
            name = re.search('(.*) <' + msg.from_ + '>', msg.from_values.full).group(1).split(' ')
            lastName = name[-1]
            name.pop(-1)
            firstName = ' '.join(name)
            
            data = {
                "email": msg.from_,
                "first_name": firstName,
                "last_name": lastName,
                "subject": msg.subject,
                "text": msg.text,
                "html": msg.html,
                "attachments": attachments
            }
            print(data["email"])
            print(msg.date, msg.from_, msg.subject, msg.from_values, name, len(msg.text or msg.html))
            array.append(data)
        return array


async def task():
    async with httpx.AsyncClient() as client:
        tasks = [main(client) for i in range(1)]
        result = await asyncio.gather(*tasks)
        return result

@app.get('/api')
async def api():
    output = await task()
    return output
