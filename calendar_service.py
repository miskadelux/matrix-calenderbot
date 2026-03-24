import pickle
import os
from datetime import datetime, timedelta
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

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
    
    weekdays = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday",
        3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"
    }
    
    result = ""
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        # Räkna ut veckodagen från datumet
        date_str = start[:10]
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        weekday = weekdays[date_obj.weekday()]
        result += f"- {event['summary']}: {weekday} {start}\n"
    return result

def check_conflicts(date, start_hour, end_hour):
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
        return [e['summary'] for e in events]
    return []

def create_calendar_event(summary, date, start_hour, end_hour):
    conflicts = check_conflicts(date, start_hour, end_hour)
    if conflicts:
        return f"Du är redan bokad den {date} kl {start_hour:02d}:00-{end_hour:02d}:00 med: {', '.join(conflicts)}. Vill du boka ändå?"
    service = get_calendar_service()
    start_time = f"{date}T{start_hour:02d}:00:00"
    end_time   = f"{date}T{end_hour:02d}:00:00"
    event = {
        'summary': summary,
        'start': {'dateTime': start_time, 'timeZone': 'Europe/Stockholm'},
        'end':   {'dateTime': end_time,   'timeZone': 'Europe/Stockholm'},
    }
    result = service.events().insert(calendarId='primary', body=event).execute()
    if result.get('id'):
        return f"Lagt till: '{summary}' den {date} kl {start_hour:02d}:00-{end_hour:02d}:00"
    else:
        return f"Något gick fel, händelsen skapades inte."

def delete_calendar_event(title, date):
    service = get_calendar_service()
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
    matches = [e for e in events if title.lower() in e['summary'].lower()]
    if not matches:
        return f"Hittade ingen händelse med titeln '{title}' den {date}."
    if len(matches) > 1:
        names = ', '.join([e['summary'] for e in matches])
        return f"Hittade flera händelser: {names}. Var mer specifik."
    event = matches[0]
    service.events().delete(calendarId='primary', eventId=event['id']).execute()
    return f"Jag har tagit bort '{event['summary']}' den {date}."

def delete_event_by_time(date, hour):
    service = get_calendar_service()
    start_time = f"{date}T{hour:02d}:00:00+01:00"
    end_time   = f"{date}T{hour+1:02d}:00:00+01:00"
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_time,
        timeMax=end_time,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])
    if not events:
        return f"Hittade ingen händelse den {date} kl {hour:02d}:00."
    if len(events) > 1:
        names = ', '.join([e['summary'] for e in events])
        return f"Hittade flera händelser: {names}. Var mer specifik."
    event = events[0]
    service.events().delete(calendarId='primary', eventId=event['id']).execute()
    return f"Jag har tagit bort: '{event['summary']}' den {date} kl {hour:02d}:00."

def create_multiple_events(summary, start_date, end_date, start_hour, end_hour, weekdays_only=True):
    """Skapa händelser för flera dagar i rad."""
    service = get_calendar_service()
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    created = 0
    skipped = 0
    current = start
    
    while current <= end:
        # 0=Måndag, 4=Fredag, 5=Lördag, 6=Söndag
        if weekdays_only and current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        
        # Kolla konflikter
        date_str = current.strftime('%Y-%m-%d')
        conflicts = check_conflicts(date_str, start_hour, end_hour)
        
        if conflicts:
            skipped += 1
        else:
            event = {
                'summary': summary,
                'start': {'dateTime': f"{date_str}T{start_hour:02d}:00:00", 'timeZone': 'Europe/Stockholm'},
                'end':   {'dateTime': f"{date_str}T{end_hour:02d}:00:00", 'timeZone': 'Europe/Stockholm'},
            }
            service.events().insert(calendarId='primary', body=event).execute()
            created += 1
        
        current += timedelta(days=1)
    
    result = f"Skapade {created} händelser '{summary}' kl {start_hour:02d}:00-{end_hour:02d}:00"
    if weekdays_only:
        result += " (vardagar)"
    if skipped > 0:
        result += f"\n Hoppade över {skipped} dagar med konflikter"
    return result

def delete_multiple_events(summary, start_date, end_date, start_hour=None, end_hour=None, weekdays_only=True):
    """Ta bort flera händelser baserat på titel och datumspan."""
    service = get_calendar_service()
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Hämta alla händelser i spannet
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start.isoformat() + 'Z',
        timeMax=(end + timedelta(days=1)).isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    
    # Filtrera på titel
    matches = [e for e in events if summary.lower() in e['summary'].lower()]
    
    if not matches:
        return f"❌ Hittade inga händelser med titeln '{summary}' mellan {start_date} och {end_date}."
    
    deleted = 0
    for event in matches:
        service.events().delete(calendarId='primary', eventId=event['id']).execute()
        deleted += 1
    
    return f"🗑️ Tog bort {deleted} händelser med titeln '{summary}' mellan {start_date} och {end_date}."