import asyncio
from broadcaster import Broadcast

async def main():
    broadcast = Broadcast("redis://localhost:6379")
    await broadcast.connect()
    print("connected")
    async with broadcast.subscribe("test") as sub:
        print("subscribed")
        await broadcast.publish("test", "hello")
        async for msg in sub:
            print("msg:", msg.message)
            break
    await broadcast.disconnect()

asyncio.run(main())
