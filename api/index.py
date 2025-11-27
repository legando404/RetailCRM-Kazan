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
