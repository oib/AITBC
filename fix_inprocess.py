import asyncio
from contextlib import asynccontextmanager
from typing import Any

class _InProcessSubscriber:
    def __init__(self, queue, release):
        self._queue = queue
        self._release = release
    def __aiter__(self):
        return self._iterator()
    async def _iterator(self):
        try:
            while True:
                yield await self._queue.get()
        finally:
            pass

@asynccontextmanager
async def subscribe():
    queue = asyncio.Queue()
    try:
        yield _InProcessSubscriber(queue, lambda: None)
    finally:
        pass

async def main():
    async with subscribe() as sub:
        print("Success")

asyncio.run(main())
