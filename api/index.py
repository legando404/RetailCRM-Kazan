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
site = os.getenv('site')#= 'novers-spb'
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
        filename = ''.join(re.findall("\w+| |\.", file.filename))
        data = { 'id': id, 'filename': file.filename, 'attachment': [{'order':{'id': order}}]}
        response = retail_client.files_edit(data)
        print(response.get_response())
    except Exception as e:
                print('exception: ', e)

async def main(client):
    messages = await get_mail(username, password, imap_server)
    for msg in messages : 
        for a in msg["attachments"]:
            print(a.filename)
        #for a in msg["attachments"]: 
            #files = {'file': a.payload}
            #try:                       
                #conn.request("POST", "/api/v5/files/upload", a.payload, headers)
                #file = conn.getresponse().read().decode("utf-8")
                #file = await client.post(url + '/api/v5/files/upload', payload=a.payload, headers=headers)
            #except Exception as e:
                #print('exception: ', e)
            #print(file.content, file.json()["file"]["id"])
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
    with MailBox(imap_server).login(username, password, initial_folder='Novers СПБ') as mailbox:
        print('fetching...')
        exists = mailbox.folder.exists('Novers СПБ/INBOX|СПБ')
        if not exists:
            mailbox.folder.create('Novers СПБ/INBOX|СПБ')
       
        # Берём все письма, вне зависимости от прочитанности
        for msg in mailbox.fetch():
            mailbox.move(msg.uid, 'Novers СПБ/INBOX|СПБ') 
            
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
    #start = time()
    output = await task()
    #print("time: ", time() - start)
    return output