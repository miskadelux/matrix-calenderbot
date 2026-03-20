import asyncio
import aiohttp
import pickle
import os
import json
from datetime import datetime, timedelta
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from nio import AsyncClient, MatrixRoom, RoomMessageText, SyncResponse

MATRIX_SERVER = "http://100.109.27.41:8008"
BOT_USER      = "@matrixbot:localhost"
BOT_PASSWORD  = "BotMiska2024"
OLLAMA_URL    = "http://localhost:11434/api/chat"
OLLAMA_MODEL  = "mistral"

conversation_history = {}

def get_calendar_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('calendar', 'v3', credentials=creds)

def get_upcoming_events(days=7):
    service = get_calendar_service()
    now = datetime.utcnow()
    end = now + timedelta(days=days)
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now.isoformat() + 'Z',
        timeMax=end.isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])
    if not events:
        return "Inga kommande händelser."
    result = ""
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        result += f"- {event['summary']}: {start}\n"
    return result

def check_conflicts(date, start_hour, end_hour):
    """Kolla om det redan finns en händelse på den tiden."""
    service = get_calendar_service()
    start_time = f"{date}T{start_hour:02d}:00:00+01:00"
    end_time   = f"{date}T{end_hour:02d}:00:00+01:00"
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_time,
        timeMax=end_time,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])
    if events:
        conflict_names = [e['summary'] for e in events]
        return conflict_names
    return []

def create_calendar_event(summary, date, start_hour, end_hour):
    """Skapa händelse i Google Calendar med exakt titel."""
    # Kolla konflikter först
    conflicts = check_conflicts(date, start_hour, end_hour)
    if conflicts:
        return f"Du är redan bokad den {date} kl {start_hour:02d}:00-{end_hour:02d}:00 med: {', '.join(conflicts)}. Vill du boka ändå?"

    service = get_calendar_service()
    start_time = f"{date}T{start_hour:02d}:00:00"
    end_time   = f"{date}T{end_hour:02d}:00:00"
    event = {
        'summary': summary,  # Exakt titel från användaren
        'start': {'dateTime': start_time, 'timeZone': 'Europe/Stockholm'},
        'end':   {'dateTime': end_time,   'timeZone': 'Europe/Stockholm'},
    }
    result = service.events().insert(calendarId='primary', body=event).execute()
    # Verifiera att det faktiskt skapades
    if result.get('id'):
        return f"Lagt till: '{summary}' den {date} kl {start_hour:02d}:00-{end_hour:02d}:00"
    else:
        return f"Något gick fel, händelsen skapades inte."

def delete_calendar_event(title, date):
    """Ta bort en händelse baserat på titel och datum."""
    service = get_calendar_service()
    # Sök händelser den dagen
    start_of_day = f"{date}T00:00:00Z"
    end_of_day   = f"{date}T23:59:59Z"
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_of_day,
        timeMax=end_of_day,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    # Hitta händelse med matchande titel (okänslig för versaler)
    matches = [e for e in events if title.lower() in e['summary'].lower()]

    if not matches:
        return f" Hittade ingen händelse med titeln '{title}' den {date}."
    if len(matches) > 1:
        names = ', '.join([e['summary'] for e in matches])
        return f"Hittade flera händelser: {names}. Var mer specifik."

    event = matches[0]
    service.events().delete(calendarId='primary', eventId=event['id']).execute()
    return f"Jag har tagit bort '{event['summary']}' den {date}."

async def ask_ollama_for_json(conversation):
    """Be Ollama tolka bokning och returnera JSON med exakt titel."""
    messages = [
        {
            "role": "system",
            "content": (
                "Du är en kalenderassistent. Analysera vad användaren vill göra och svara ENDAST med JSON.\n\n"
                "För att BOKA:\n"
                '{"action": "book", "title": "EXAKT_TITEL", "date": "YYYY-MM-DD", "start": HH, "end": HH}\n\n'
                "För att TA BORT:\n"
                '{"action": "delete", "title": "EXAKT_TITEL", "date": "YYYY-MM-DD"}\n\n'
                "Om varken bokning eller borttagning:\n"
                '{"action": "none"}\n\n'
                "VIKTIGT: Använd EXAKT titeln användaren angav. Svara BARA med JSON.\n"
                f"Aktuellt år är 2026. Använd alltid 2026 om inget annat år anges.\n"
                "Om användaren refererar till 'den aktiviteten' eller 'det mötet', "
                "leta i konversationshistoriken efter senast nämnda händelse och använd den titeln och datumet."
            )
        }
    ] + conversation[-6:]
    payload = {"model": OLLAMA_MODEL, "messages": messages, "stream": False}
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(OLLAMA_URL, json=payload) as response:
            data = await response.json()
            return data["message"]["content"]

async def ask_ollama(room_id, message):
    try:
        calendar_context = get_upcoming_events(days=7)
    except Exception as e:
        calendar_context = f"Kunde inte hämta kalender: {e}"

    if room_id not in conversation_history:
        conversation_history[room_id] = []

    conversation_history[room_id].append({"role": "user", "content": message})

    messages = [
        {
            "role": "system",
            "content": (
                "Du är en personlig kalenderassistent. "
                "Du kan läsa och boka händelser i användarens Google Calendar. "
                "Svara på svenska om användaren skriver svenska, annars engelska. "
                "Håll svaren kortfattade. "
                "VIKTIGT: Säg ALDRIG att du gjort något om du inte faktiskt gjort det. "
                "Om du är osäker, säg det istället. "
                f"\nAktuell tid: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                f"\nKalender:\n{calendar_context}"
            )
        }
    ] + conversation_history[room_id][-10:]

    payload = {"model": OLLAMA_MODEL, "messages": messages, "stream": False}
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(OLLAMA_URL, json=payload) as response:
            data = await response.json()
            reply = data["message"]["content"]

    action_words = ["boka", "lägg till", "skapa", "lägg in", "add", "create",
                "ta bort", "radera", "delete", "remove", "avboka"]
    if any(word in message.lower() for word in action_words):
        try:
            json_reply = await ask_ollama_for_json(conversation_history[room_id])
            json_reply = json_reply.strip().strip('`').replace('json\n', '').replace('json', '')
            booking = json.loads(json_reply)

            if booking.get("action") == "book":
                reply = create_calendar_event(
                    summary=booking["title"],
                    date=booking["date"],
                    start_hour=int(booking["start"]),
                    end_hour=int(booking["end"])
                )
            elif booking.get("action") == "delete":
                reply = delete_calendar_event(
                    title=booking["title"],
                    date=booking["date"]
                )
        except Exception as e:
            print(f"Åtgärdsfel: {e}")

    conversation_history[room_id].append({"role": "assistant", "content": reply})
    return reply

async def message_callback(room, event):
    if event.sender == BOT_USER:
        return
    print(f"[{room.display_name}] {event.sender}: {event.body}")
    print("jag Tänker... du får mitt svar snat")
    reply = await ask_ollama(room.room_id, event.body)
    print(f"här får du mitt svar: {reply}")
    await client.room_send(
        room_id=room.room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": reply}
    )

async def main():
    global client
    client = AsyncClient(MATRIX_SERVER, BOT_USER)
    print("Loggar in...")
    await client.login(BOT_PASSWORD)
    print(f"Inloggad som {BOT_USER}")
    response = await client.sync(timeout=3000)
    if isinstance(response, SyncResponse):
        client.next_batch = response.next_batch
        print(" Skippar gamla meddelanden, startar från nu")
    for room_id in list(client.invited_rooms.keys()):
        await client.join(room_id)
        print(f"Gick med i rum: {room_id}")
    client.add_event_callback(message_callback, RoomMessageText)
    print("👂 Lyssnar på meddelanden... (Ctrl+C för att avsluta)")
    await client.sync_forever(timeout=30000, full_state=True)

if __name__ == "__main__":
    asyncio.run(main())