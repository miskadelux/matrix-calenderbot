import asyncio
import aiohttp
import pickle
import os
import re
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

def create_calendar_event(summary, date, start_hour, end_hour):
    """Skapa händelse i Google Calendar."""
    service = get_calendar_service()
    start_time = f"{date}T{start_hour:02d}:00:00"
    end_time   = f"{date}T{end_hour:02d}:00:00"
    event = {
        'summary': summary,
        'start': {'dateTime': start_time, 'timeZone': 'Europe/Stockholm'},
        'end':   {'dateTime': end_time,   'timeZone': 'Europe/Stockholm'},
    }
    result = service.events().insert(calendarId='primary', body=event).execute()
    return f"✅ Lagt till: '{summary}' den {date} kl {start_hour:02d}:00–{end_hour:02d}:00"

async def ask_ollama_for_json(conversation: list) -> str:
    """Be Ollama tolka bokning och returnera JSON."""
    messages = [
        {
            "role": "system",
            "content": (
                "Du är en kalenderassistent. När användaren vill boka något, "
                "extrahera informationen och svara ENDAST med JSON i detta format:\n"
                '{"action": "book", "title": "...", "date": "YYYY-MM-DD", "start": HH, "end": HH}\n'
                "Om användaren INTE vill boka något, svara med:\n"
                '{"action": "none"}\n'
                "Svara BARA med JSON, inget annat."
            )
        }
    ] + conversation[-6:]

    payload = {"model": OLLAMA_MODEL, "messages": messages, "stream": False}
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(OLLAMA_URL, json=payload) as response:
            data = await response.json()
            return data["message"]["content"]

async def ask_ollama(room_id: str, message: str) -> str:
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
                "Svara på svenska. Håll svaren kortfattade. "
                "När du bokar något, bekräfta tydligt vad du bokade. "
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

    # Kolla om vi ska boka något
    booking_words = ["boka", "lägg till", "skapa", "schemalägger", "lägg in", "skapa denna"]
    if any(word in message.lower() for word in booking_words):
        try:
            import json
            json_reply = await ask_ollama_for_json(conversation_history[room_id])
            # Rensa bort eventuella markdown-tecken
            json_reply = json_reply.strip().strip('`').replace('json\n', '')
            booking = json.loads(json_reply)
            if booking.get("action") == "book":
                result = create_calendar_event(
                    summary=booking["title"],
                    date=booking["date"],
                    start_hour=int(booking["start"]),
                    end_hour=int(booking["end"])
                )
                reply = result
        except Exception as e:
            print(f"Bokningsfel: {e}")

    conversation_history[room_id].append({"role": "assistant", "content": reply})
    return reply

async def message_callback(room: MatrixRoom, event: RoomMessageText) -> None:
    if event.sender == BOT_USER:
        return
    print(f"📨 [{room.display_name}] {event.sender}: {event.body}")
    print("🤔 Tänker...")
    reply = await ask_ollama(room.room_id, event.body)
    print(f"💬 Svar: {reply}")
    await client.room_send(
        room_id=room.room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": reply}
    )

async def main():
    global client
    client = AsyncClient(MATRIX_SERVER, BOT_USER)
    print("🔑 Loggar in...")
    await client.login(BOT_PASSWORD)
    print(f"✅ Inloggad som {BOT_USER}")
    response = await client.sync(timeout=3000)
    if isinstance(response, SyncResponse):
        client.next_batch = response.next_batch
        print("⏩ Skippar gamla meddelanden, startar från nu")
    for room_id in list(client.invited_rooms.keys()):
        await client.join(room_id)
        print(f"✅ Gick med i rum: {room_id}")
    client.add_event_callback(message_callback, RoomMessageText)
    print("👂 Lyssnar på meddelanden... (Ctrl+C för att avsluta)")
    await client.sync_forever(timeout=30000, full_state=True)

if __name__ == "__main__":
    asyncio.run(main())
