import asyncio
from datetime import datetime, timedelta
from calendar_service import get_calendar_service

# Håll koll på vilka påminnelser som redan skickats
sent_reminders = set()

async def send_message(client, room_id, message):
    """Skicka ett meddelande till Matrix-rummet."""
    await client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": message}
    )

def get_todays_events():
    """Hämta alla händelser idag."""
    service = get_calendar_service()
    now = datetime.now()
    start_of_day = now.replace(hour=0, minute=0, second=0).isoformat() + '+01:00'
    end_of_day   = now.replace(hour=23, minute=59, second=59).isoformat() + '+01:00'
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_of_day,
        timeMax=end_of_day,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    return events_result.get('items', [])

def get_upcoming_30min():
    """Hämta händelser som börjar om 25-35 minuter."""
    service = get_calendar_service()
    now = datetime.now()
    window_start = (now + timedelta(minutes=25)).isoformat() + '+01:00'
    window_end   = (now + timedelta(minutes=35)).isoformat() + '+01:00'
    events_result = service.events().list(
        calendarId='primary',
        timeMin=window_start,
        timeMax=window_end,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    return events_result.get('items', [])

async def reminder_loop(client, room_id):
    """Huvudloop som körs varje minut."""
    print("⏰ Påminnelsetjänst startad!")
    morning_sent_date = None

    while True:
        now = datetime.now()

        # ── Morgonsammanfattning kl 06:00 ──────────────────
        if now.hour == 6 and now.minute == 0:
            if morning_sent_date != now.date():
                morning_sent_date = now.date()
                events = get_todays_events()
                if events:
                    msg = "🌅 God morgon! Här är ditt schema för idag:\n"
                    for event in events:
                        start = event['start'].get('dateTime', event['start'].get('date'))
                        time_str = start[11:16] if 'T' in start else start
                        msg += f"• {event['summary']} kl {time_str}\n"
                else:
                    msg = "🌅 God morgon! Du har inga aktiviteter idag."
                await send_message(client, room_id, msg)

        # ── Påminnelse 30 min innan möte ───────────────────
        upcoming = get_upcoming_30min()
        for event in upcoming:
            event_id = event['id']
            if event_id not in sent_reminders:
                sent_reminders.add(event_id)
                start = event['start'].get('dateTime', '')
                time_str = start[11:16] if 'T' in start else start
                msg = f"⏰ Påminnelse: '{event['summary']}' börjar om 30 minuter (kl {time_str})!"
                await send_message(client, room_id, msg)

        # Vänta 60 sekunder innan nästa kontroll
        await asyncio.sleep(60)