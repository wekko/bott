# Standart library
import asyncio
import json
import random
import string
from typing import Optional, List, Dict, Union, BinaryIO, Tuple

import aiohttp
from captcha_solver import CaptchaSolver

import settings
from database import *
from methods import is_available_from_group
from methods import is_available_from_public
from utils import chunks, Attachment, RequestFuture, SenderGroup, SenderUser, Wait
from vkapi import VkClient

solver = None

from settings import CAPTCHA_KEY, CAPTCHA_SERVER, GROUP_ID

if CAPTCHA_KEY and CAPTCHA_KEY:
    solver = CaptchaSolver(CAPTCHA_SERVER, api_key=CAPTCHA_KEY)

MAX_MESSAGE_LENGTH = 3584


class NoPermissions(Exception):
    pass


async def enter_captcha(url: str):
    if not solver:
        return hues.warn('Введите данные для сервиса решения капч в settings.py!')

    with aiohttp.ClientSession() as session:
        try:
            with session as ses:
                async with ses.get(url) as resp:
                    img_data = await resp.read()
                    data = solver.solve_captcha(img_data)
                    return data
        except Exception as e:
            hues.error(e)

            return "0"


async def enter_confirmation_сode():
    hues.error("Похоже, у вас установлена двухфакторная авторизация!")
    hues.error("Пожалуйста, введите код подтверждения:")

    code = input()

    hues.success("Спасибо! Продолжаю приём сообщений")

    return code


class VkPlus(object):
    def __init__(self, bot, users_data: list=None, proxies: list=None, app_id: int=5982451, scope=140489887):
        self.bot = bot
        self.users = []
        self.tokens = []
        self.scope = scope
        self.group = False
        self.app_id = app_id
        self.current_user = 0
        self.current_token = 0

        self.proxies = proxies
        if not proxies:
            self.proxies = []

        self.users_data = users_data
        if not users_data:
            self.users_data = []

        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.init_vk())

    def get_default_sender(self, key: str) -> Union[SenderUser, SenderGroup]:
        if self.group and is_available_from_group(key):
            send_from = SenderGroup(self.current_token)

        elif is_available_from_public(key):
            send_from = SenderUser(self.current_user)

        else:
            send_from = SenderUser(self.current_user)

        return send_from

    async def init_vk(self):
        """Инициализация сессий ВК API"""
        current_proxy = 0

        for user in self.users_data:
            if self.proxies:
                proxy = self.proxies[current_proxy % len(self.proxies)]
                current_proxy += 1

            else:
                proxy = None

            if len(user) == 1:
                client = VkClient(proxy)
                await client.group(user[0])

                self.tokens.append(client)
                self.group = True

            else:
                client = VkClient(proxy)
                await client.user(user[0], user[1], self.app_id, self.scope)

                self.users.append(client)

    async def method(self, key: str, data=None, send_from=None, wait=Wait.YES):
        """Выполнение метода API VK с дополнительными параметрами"""
        if send_from is None:
            send_from = self.get_default_sender(key)

        task = RequestFuture(key, data, send_from)

        client = None

        if self.users and send_from.USER:
            client = self.users[send_from.target % len(self.users)]
            self.current_user += 1

        elif self.tokens and send_from.GROUP:
            client = self.tokens[send_from.target % len(self.tokens)]
            self.current_token += 1

        if not client:
            hues.error(f"Для выполнения метода({task.key}) необходимо ввести недостающие данные пользователя "
                       f"или токен группы.")
            return None

        client.queue.put_nowait(task)

        if wait == Wait.NO:
            return None

        elif wait == Wait.YES:
            try:
                return await asyncio.wait_for(task, 90)
            except Exception as e:
                import traceback
                hues.error("Запрос к вк завершился с ошибкой")
                traceback.print_exc()

        elif wait == Wait.CUSTOM:
            return task

    async def upload_doc(self, multipart_data: BinaryIO, filename="image.png") -> Optional[Attachment]:
        sender = self.get_default_sender("docs.getWallUploadServer")

        data = aiohttp.FormData()
        data.add_field('file',
                       multipart_data,
                       filename=filename,
                       content_type='multipart/form-data')

        v = {}
        if GROUP_ID:
            v = {'group_id': GROUP_ID}

        upload_url = (await self.method('docs.getWallUploadServer', v, send_from=sender))['upload_url']

        async with aiohttp.ClientSession() as sess:
            async with sess.post(upload_url, data=data) as resp:
                result = json.loads(await resp.text())

        if not result:
            return None

        data = dict(file=result['file'])
        result = (await self.method('docs.save', data, send_from=sender))[0]

        url = ""

        if "url" in result:
            url = result["url"]

        for k in result:
            if "photo_" in k:
                url = result[k]

        return Attachment("doc", result["owner_id"], result["id"], "", url)

    async def upload_photo(self, multipart_data: BinaryIO) -> Optional[Attachment]:
        # Лимит загрузки фотографий на сервера вк - 7000 в день
        if isinstance(db, peewee_async.Manager):
            status, created = await db.get_or_create(BotStatus, id=0)

            if status:
                if time.time() - status.timestamp > 60 * 60 * 24:
                    status.timestamp = time.time()
                    status.photos = 0

                elif status.photos >= 6969:
                    return None

                else:
                    status.photos += 1

                await db.update(status)

        sender = self.get_default_sender("photos.getMessagesUploadServer")

        data = aiohttp.FormData()
        data.add_field('photo',
                       multipart_data,
                       filename='picture.png',
                       content_type='multipart/form-data')

        upload_url = (await self.method('photos.getMessagesUploadServer', send_from=sender))['upload_url']

        async with aiohttp.ClientSession() as sess:
            async with sess.post(upload_url, data=data) as resp:
                result = json.loads(await resp.text())

        if not result:
            return None

        data = dict(photo=result['photo'], hash=result['hash'], server=result['server'])
        result = (await self.method('photos.saveMessagesPhoto', data, send_from=sender))[0]

        url = ""

        for k in result:
            if "photo_" in k:
                url = result[k]

        return Attachment("photo", result["owner_id"], result["id"], "", url)

    @staticmethod
    def anti_flood() -> str:
        """Возвращает строку из 5 символов (букв и цифр)"""
        return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(5))

    async def mark_as_read(self, message_ids) -> None:
        """Отмечает сообщение(я) как прочитанное(ые)"""
        await self.method('messages.markAsRead', {'message_ids': message_ids})

    async def resolve_name(self, screen_name) -> Optional[int]:
        """Функция для перевода короткого имени в числовой ID"""

        try:
            for val in ('club', 'public', 'event'):
                screen_name = screen_name.replace(val, '')
            possible_id = int(screen_name)
            return possible_id

        except ValueError:
            result = await self.method('utils.resolveScreenName',
                                       {'screen_name': screen_name})
            if not result:
                return None

            return int(result.get('object_id'))


class MessageEventData(object):
    __slots__ = ('conf', 'peer_id', 'user_id', 'body', "full_message_data",
                 'time', "msg_id", "attaches", "out", "forwarded")

    @staticmethod
    def from_message_body(obj: Dict) -> 'MessageEventData':
        brief_attachments = {}
        brief_forwarded = []

        c = 0

        for a in obj.get("attachments", {}):
            c += 1

            brief_attachments[f'attach{c}_type'] = a['type']
            brief_attachments[f'attach{c}'] = f'{a[a["type"]]["owner_id"]}_{a[a["type"]]["id"]}'

        if 'fwd_messages' in obj:
            brief_forwarded = MessageEventData.parse_brief_forwarded_messages(obj)

        return MessageEventData(False, obj.get('from_id', None), int(obj['user_id']), obj['body'], obj['date'],
                                obj.get("id", None), type == 'message_reply', brief_attachments, brief_forwarded, obj)

    @staticmethod
    def parse_brief_forwarded_messages(obj: Dict) -> List:
        if 'fwd_messages' not in obj:
            return []

        result = []

        for mes in obj['fwd_messages']:
            result.append((mes.get('id', None), MessageEventData.parse_brief_forwarded_messages(mes)))

        return result

    def __init__(self, conf: bool, pid: (int, None), uid: int, body: str,
                 time: int, msg_id: (int, None), out: bool, attaches: Dict=None,
                 forwarded: List=None, full_message_data: Dict=None):
        self.conf = conf
        self.peer_id = pid
        self.user_id = uid
        self.body = body
        self.time = time
        self.msg_id = msg_id
        self.out = out
        self.attaches = attaches
        self.forwarded = forwarded

        self.full_message_data = full_message_data


class Message(object):
    """Класс, объект которого передаётся в плагин для упрощённого ответа"""

    __slots__ = ('_data', 'vk', 'conf', 'user', 'cid', 'user_id', "peer_id", "text", "prefix", "is_out",
                 'body', 'timestamp', 'answer_values', 'msg_id', 'command',
                 'brief_attaches', '_full_attaches',
                 'brief_forwarded', '_full_forwarded')

    def __init__(self, vk_api_object: VkPlus, data: MessageEventData, user: User):
        self._data = data
        self.vk = vk_api_object
        self.user = user

        # Если сообщение из конференции
        if data.conf:
            self.conf = True
            self.cid = int(data.peer_id)
        else:
            self.conf = False
            self.cid = None

        self.prefix = False

        self.user_id = data.user_id
        self.peer_id = data.peer_id
        self.body = data.body
        self.text = self.body
        self.msg_id = data.msg_id
        self.is_out = data.out

        self.timestamp = data.time

        self.brief_forwarded = data.forwarded
        self._full_forwarded = None
        self.brief_attaches = data.attaches
        self._full_attaches = None

        self.command = ""

        # Словарь для отправки к ВК при ответе
        if self.conf:
            self.answer_values = {'chat_id': self.cid}
        else:
            self.answer_values = {'user_id': self.user_id}

    @property
    async def full_attaches(self) -> List:
        if self._full_attaches is None:
            await self.get_full_data()

        return self._full_attaches

    @property
    async def full_forwarded(self) -> List:
        if self._full_forwarded is None:
            await self.get_full_data()

        return self._full_forwarded

    async def get_full_data(self, message_data: Dict=None) -> None:
        self._full_attaches = []
        self._full_forwarded = []

        if not message_data:
            values = {'message_ids': self.msg_id}

            # Получаем полную информацию о сообщении в ВК
            full_message_data = await self.vk.method('messages.getById', values)

            if not full_message_data or not full_message_data['items']:  # Если пришёл пустой ответ от VK API
                return

            message = full_message_data['items'][0]

        else:
            message = message_data

        if "attachments" in message:
            for raw_attach in message["attachments"]:
                attach = Attachment.from_raw(raw_attach) # Создаём аттач

                self._full_attaches.append(attach)  # Добавляем к нашему внутреннему списку аттачей

        if 'fwd_messages' in message:
            self._full_forwarded, self.brief_forwarded = await self.parse_forwarded_messages(message)

    async def parse_forwarded_messages(self, im: Dict) -> Tuple[List, List]:
        if 'fwd_messages' not in im:
            return [], []

        result = []
        brief_result = []

        for mes in im['fwd_messages']:
            obj = MessageEventData.from_message_body(mes)

            obj.msg_id = self.msg_id
            obj.peer_id = self.peer_id
            obj.conf = self.conf

            m = await create_message(self.vk, obj, self.user)

            big_result, small_result = await self.parse_forwarded_messages(mes)

            result.append((m, big_result))
            brief_result.append((m.msg_id, small_result))

        return result, brief_result

    async def send(self, msg: str, **additional_values) -> None:
        if 'forward_messages' not in additional_values:
            additional_values['forward_messages'] = ''

        await self.answer(msg, **additional_values)

    async def answer(self, msg: str, wait=Wait.NO, **additional_values) -> List:
        """Функция ответа на сообщение для плагинов"""
        if len(msg) > MAX_MESSAGE_LENGTH:  # Если сообщение слишком длинное - делим его на несколько коротких сообщений
            msgs = list(chunks(msg, MAX_MESSAGE_LENGTH))
        else:
            msgs = [msg]

        if additional_values is None:
            additional_values = dict()

        sender = self.vk.get_default_sender("messages.send")

        def post_process(i, values):
            if i == len(msgs) - 1:
                values['forward_messages'] = self.msg_id

        if not settings.FORWARD_MESSAGES or settings.READ_OUT \
                or additional_values.get('forward_messages', None) is not None:
            def post_process(*args):
                pass

        result = []

        for i in range(len(msgs)):  # Отправляем каждое сообщение из списка
            msg = msgs[i]

            values = dict(**self.answer_values, message=msg, **additional_values)

            post_process(i, values)

            r = await self.vk.method('messages.send', values, send_from=sender, wait=wait)

            result.append(r)

        return result


async def create_message(vk_api_object: VkPlus, data: MessageEventData, user: User) -> Message:
    msg = Message(vk_api_object, data, user)

    if data.full_message_data:
        await msg.get_full_data(data.full_message_data)

    return msg
