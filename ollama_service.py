import aiohttp
import json
from datetime import datetime
from config import OLLAMA_URL, OLLAMA_MODEL
from calendar_service import (
    get_upcoming_events,
    create_calendar_event,
    delete_calendar_event,
    delete_event_by_time
)

conversation_history = {}

async def ask_ollama_for_json(conversation):
    messages = [
        {
            "role": "system",
            "content": (
                "Du är en kalenderassistent. Analysera vad användaren vill göra och svara ENDAST med JSON.\n\n"
                "För att BOKA:\n"
                '{"action": "book", "title": "EXAKT_TITEL", "date": "YYYY-MM-DD", "start": HH, "end": HH}\n\n'
                "För att TA BORT med titel:\n"
                '{"action": "delete", "title": "EXAKT_TITEL", "date": "YYYY-MM-DD"}\n\n'
                "För att TA BORT med tid:\n"
                '{"action": "delete_by_time", "date": "YYYY-MM-DD", "hour": HH}\n\n'
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
                "Du kan läsa, boka och ta bort händelser i användarens Google Calendar. "
                "Svara på svenska om användaren skriver svenska, annars engelska. "
                "Håll svaren kortfattade. "
                "VIKTIGT: Säg ALDRIG att du gjort något om du inte faktiskt gjort det. "
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
            elif booking.get("action") == "delete_by_time":
                reply = delete_event_by_time(
                    date=booking["date"],
                    hour=int(booking["hour"])
                )
        except Exception as e:
            print(f"Åtgärdsfel: {e}")

    conversation_history[room_id].append({"role": "assistant", "content": reply})
    return reply