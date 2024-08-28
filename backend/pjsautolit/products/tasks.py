# tasks.py

import asyncio

from asgiref.sync import sync_to_async

from .views import daily_update


async def run_daily_update_async():
    await sync_to_async(daily_update)()