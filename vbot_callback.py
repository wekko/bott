# Standart library
import logging
from os import getenv

from aiohttp import web, asyncio

from database import *
from vbot import Bot
from vkplus import MessageEventData


class CallbackBot(Bot):
    CONF_CODE = ""  # Введите код подтверждения тут

    async def process_callback(self, request):
        """Функция для обработки запроса от VK Callback API группы"""
        try:
            data = await request.json()
        except Exception:
            # Почти невозможно, что будет эта ошибка
            return web.Response(text="ok")

        type = data['type']
        if type == 'confirmation':
            # Нам нужно подтвердить наш сервер
            return web.Response(text=self.CONF_CODE)
        obj = data['object']

        if type in ('message_new', 'message_reply'):
            user_id = int(obj['user_id'])

            data = MessageEventData.from_message_body(obj)

            user, create = await db.get_or_create(User, user_id=user_id)

            await self.check_if_command(data, user)
        if type == 'group_join':
            # Человек присоединился к группе
            user_id = int(obj['user_id'])

            user, create = await db.get_or_create(user_id=user_id)

            user.in_group = True

            await db.update(user)

        if type == 'group_leave':
            # Человек вышел из группы
            user_id = int(obj['user_id'])

            user, create = await db.get_or_create(user_id=user_id)

            user.in_group = False

            await db.update(user)

        return web.Response(text='ok')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    bot = CallbackBot()
    app = web.Application(loop=loop)
    app.router.add_post('/', bot.process_callback)

    hues.success("Приступаю к приему сообщений")

    try:
        IP = getenv('IP', '0.0.0.0')
        PORT = int(getenv('PORT', 8000))

        web.run_app(app, host=IP, port=PORT)
    except (KeyboardInterrupt, SystemExit):
        hues.warn("Выключение бота...")

    except Exception as ex:
        import traceback

        logging.warning("Fatal error:\n")
        traceback.print_exc()

        exit(1)
