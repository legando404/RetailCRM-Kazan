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
#url = 'https://mdevelopeur.retailcrm.ru/api/v5/'
url = os.getenv("URL")#'https://laminat77.retailcrm.ru'
site = os.getenv('site')#= 'kazan-novers-ru'
apikey = os.getenv('key') #'vikuHSdIKilFPMr0oyj5LpemwHvEPjVw'
#apikey = 'nHY0H7zd7UWwcEiwN0EbwhXz2eGY9o9G'
retail_client = retailcrm.v5(url, apikey)
#headers = {'X-API-KEY' : apikey}
conn = http.client.HTTPSConnection('laminat77.retailcrm.ru')
headers = { 'X-API-KEY': apikey, 'Content-Type': 'image/jpeg' }  
#password = "zrAUqnFWgD14Ygkq13VK"
#username = "kworktestbox@mail.ru"
password = os.getenv('password')  #"r4ZuvyWydYMktHuTn3uJ"
username = os.getenv('user')#"novers495@mail.ru"
imap_server = os.getenv('imap')#"imap.mail.ru"

async def upload_file(client, file, order):
    print(file.filename, file.content_disposition)
    try:
        response = await client.post(url + "/api/v5/files/upload", data = file.payload, headers = headers)
        id = response.json()["file"]["id"]
        filename = ''.join(re.findall(r"\w+| |\.", file.filename))
        data = { 'id': id, 'filename': file.filename, 'attachment': [{'order':{'id': order}}]}
        response = retail_client.files_edit(data)
        print(response.get_response())
    except Exception as e:
                print('exception: ', e)

async def main(client):
    messages = await get_mail(username, password, imap_server)
    all_responses = []  # 1. Создаем список для хранения результатов
    
    for msg in messages: 
        # Печатаем для отладки
        for a in msg["attachments"]:
            print(f"Обработка вложения: {a.filename}")

        # Создаем заказ
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
        
        # Получаем ID созданного заказа
        order_res_data = response.get_response()
        order_id = order_res_data.get("id")
        
        # Загружаем файлы к этому заказу
        if order_id:
            for a in msg["attachments"]: 
                if a.content_disposition == 'attachment':
                    await upload_file(client, a, order_id)
        
        # 2. Вместо return добавляем результат в список
        all_responses.append(order_res_data)


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
    with MailBox(imap_server).login(username, password, initial_folder='6 Другие города/Novers Казань') as mailbox:
        print('fetching...')
        exists = mailbox.folder.exists('6 Другие города/Novers Казань/INBOX|Казань')
        if not exists:
            mailbox.folder.create('6 Другие города/Novers Казань/INBOX|Казань')
       
        for msg in mailbox.fetch(limit=5):
            try:
                attachments = []
                for a in msg.attachments:
                    attachments.append(a)

                # 2. Безопасное получение имени (чтобы скрипт не падал на пустых именах)
                full_name = msg.from_values.name or "No Name"
                name_parts = full_name.split(' ')
                
                if len(name_parts) > 1:
                    lastName = name_parts[-1]
                    firstName = ' '.join(name_parts[:-1])
                else:
                    firstName = name_parts[0]
                    lastName = ""

                data = {
                    "email": msg.from_, 
                    "first_name": firstName, 
                    "last_name": lastName, 
                    "subject": msg.subject, 
                    "text": msg.text, 
                    "html": msg.html, 
                    "attachments": attachments
                }
                
                # Добавляем в массив для CRM
                array.append(data)

                # 3. Перемещаем уже после того, как данные собраны
                mailbox.move(msg.uid,'6 Другие города/Novers Казань/INBOX|Казань') 
                print(f"Письмо {msg.uid} обработано и перемещено в INBOX|Казань")

            except Exception as e:
                print(f"Ошибка при обработке конкретного письма: {e}")
                continue

        return array


async def task():
    async with httpx.AsyncClient() as client:
        tasks = [main(client) for i in range(1)]
        result = await asyncio.gather(*tasks)
        return result

@app.get('/api')
async def api():
    #start = time()
    output = await task()
    #print("time: ", time() - start)
    return output
