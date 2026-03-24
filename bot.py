import asyncio
from nio import AsyncClient, MatrixRoom, RoomMessageText, SyncResponse
from config import MATRIX_SERVER, BOT_USER, BOT_PASSWORD
from ollama_service import ask_ollama
from reminder_service import reminder_loop

client = None

async def message_callback(room, event):
    global BOT_ROOM_ID
    BOT_ROOM_ID = room.room_id
    if event.sender == BOT_USER:
        return
    print(f"[{room.display_name}] {event.sender}: {event.body}")
    print("Tänker...")
    reply = await ask_ollama(room.room_id, event.body)
    print(f"Svar: {reply}")
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
        print("Skippar gamla meddelanden, startar från nu")
    for room_id in list(client.invited_rooms.keys()):
        await client.join(room_id)
        print(f"Gick med i rum: {room_id}")

    # Hämta första rum-ID från redan gick med i rum
    joined_rooms = list(client.rooms.keys())
    if joined_rooms:
        room_id = joined_rooms[0]
        print(f"Startar påminnelsetjänst för rum: {room_id}")
        asyncio.create_task(reminder_loop(client, room_id))

    client.add_event_callback(message_callback, RoomMessageText)
    print("Lyssnar på meddelanden... (Ctrl+C för att avsluta)")
    await client.sync_forever(timeout=30000, full_state=True)


if __name__ == "__main__":
    asyncio.run(main())