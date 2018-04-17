import asyncio
import json
import re
from urllib.parse import urlparse, parse_qsl

import aiohttp
import hues

import settings
import vkplus
from utils import fatal, schedule_coroutine

AUTHORIZATION_FAILED = 5
CAPTCHA_IS_NEEDED = 14
ACCESS_DENIED = 15
INTERNAL_ERROR = 10


class VkClient:
    __slots__ = ("token", "session", "req_kwargs", "retry",
                 "username", "password", "app_id", "scope",
                 "queue", "requests")

    def __init__(self, proxy: list = None):
        self.req_kwargs = {}
        if proxy:
            url, username, password, encoding = *proxy, None, None, None

            self.req_kwargs["proxy"] = url

            if username:
                self.req_kwargs["proxy_auth"] = aiohttp.BasicAuth(username,
                                                                  password if password else "",
                                                                  encoding if encoding else "latin1")

        self.session = aiohttp.ClientSession()

        self.queue = asyncio.Queue()
        self.requests = 0

        self.username = ""
        self.password = ""
        self.app_id = -1
        self.scope = -1

        self.token = ""

        self.retry = 0

        schedule_coroutine(self.update_requests())
        schedule_coroutine(self.process_queue())

    async def update_requests(self):
        while True:
            if self.requests > 0:
                await asyncio.sleep(settings.REQUEST_INTERVAL)
                self.requests = 0

            await asyncio.sleep(0.1)

    async def process_queue(self):
        while True:
            try:
                if self.queue.empty() or self.requests >= settings.REQUESTS_QUANTITY:
                    await asyncio.sleep(0.1)
                    continue

                await self.execute_queue()

            except Exception as e:
                import traceback
                hues.error("Ошибка во время обработки запросов к ВК")
                traceback.print_exc()

    async def execute_queue(self):
        execute = "return ["

        tasks = []

        for i in range(25):
            task = self.queue.get_nowait()

            if task.data is None:
                task.data = {}

            execute += 'API.' + task.key + '({'
            execute += ", ".join((f"{k}: \"" + str(v).replace('"', '\\"') + "\"") for k, v in task.data.items())
            execute += '}), '

            tasks.append(task)

            if self.queue.empty():
                break

        execute += "];"

        try:
            self.requests += 1
            result = await asyncio.shield(self.execute(execute))

        except (asyncio.TimeoutError, json.decoder.JSONDecodeError):
            self.requests += 1
            result = await asyncio.shield(self.execute(execute))

        for task in tasks:
            try:
                if result:
                    task_result = result.pop(0)
                    task.set_result(task_result)
                else:
                    task.set_result(None)

            except (asyncio.InvalidStateError, IndexError, KeyError):
                pass

    async def execute(self, code, **additional_values):
        if self.retry > 10:
            hues.warn("Не могу войти в ВК!")

            return False

        new = code.replace("\n", "<br>")

        url = f"https://api.vk.com/method/execute?access_token={self.token}&v=5.64"

        async with self.session.post(url, data={"code": new, **additional_values}, **self.req_kwargs) as resp:
            errors = []
            error_codes = []

            for data in json_iter_parse(await resp.text()):
                if 'error' in data:
                    error_data = data['error']
                    if error_data['error_code'] == CAPTCHA_IS_NEEDED:
                        captcha_key = await vkplus.enter_captcha(error_data["captcha_img"])

                        if not captcha_key:
                            return False

                        new_data = {"captcha_key": captcha_key, "captcha_sid": error_data["captcha_sid"]}
                        new_data.update(additional_values)

                        return await self.execute(code, **new_data)

                    error_codes.append(error_data['error_code'])
                    errors.append(error_data)

                if 'response' in data:
                    for error in errors:
                        hues.warn(str(error))

                    self.retry = 0

                    if isinstance(data['response'], list) and data['response'] and data['response'][0] is False:
                        error_codes.append("...")
                        errors.append(data.get("execute_errors", "unknown"))

                        hues.error(data.get("execute_errors", "unknown"))

                    if data['response'] is None:
                        error_codes.append(INTERNAL_ERROR)
                        errors.append("unknown")

                    return data['response']

            if INTERNAL_ERROR in error_codes:
                hues.warn("Ошибка у ВК")

                if self.app_id != -1:
                    await self.user(self.username, self.password, self.app_id, self.scope)

                self.retry += 1

                await asyncio.sleep(1)

                return await self.execute(code)

            if AUTHORIZATION_FAILED in error_codes:
                hues.warn("Пользователь не отвечает. Попробую переполучить токен.")

                if self.app_id != -1:
                    await self.user(self.username, self.password, self.app_id, self.scope)

                self.retry += 1

                return await self.execute(code)

            hues.error(errors)

        return False

    async def user(self, username, password, app_id, scope):
        self.username = username
        self.password = password
        self.app_id = app_id
        self.scope = scope

        retries = 5
        for i in range(retries):
            self.token = await get_token(username, password, app_id, scope)

            if self.token:
                break

        if not self.token:
            return hues.error("Can't get token!")

        self_data = await self.execute("return API.account.getProfileInfo();")

        hues.info(f"Вошёл как: {self_data['first_name']} {self_data['last_name']} "
                  f"(https://vk.com/{self_data['screen_name']})")

    async def group(self, token):
        self.token = token

        self_data = (await self.execute("return API.groups.getById();"))[0]

        hues.info(f"Вошёл как: {self_data['name']} (https://vk.com/{self_data['screen_name']})")


############################################################################
# Thanks to: https://github.com/pohmelie/aiovk


def get_form_action(html):
    form_action = re.findall(r'<form(?= ).* action="(.+)"', html)
    if form_action:
        return form_action[0]


def get_token_from_url(url):
    if not isinstance(url, str):
        url = str(url)

    url = url.split("access_token=")

    if len(url) < 2:
        return None

    url = url[1].split("&")

    return url[0]


def get_url_query(url):
    if not isinstance(url, str):
        url = str(url)

    parsed_url = urlparse(url)
    url_query = parse_qsl(parsed_url.fragment or parsed_url.query)

    # login_response_url_query can have multiple key
    url_query = dict(url_query)

    token = get_token_from_url(url)
    if token:
        url_query["access_token"] = token

    return url_query


def json_iter_parse(response_text):
    decoder = json.JSONDecoder(strict=False)
    idx = 0
    while idx < len(response_text):
        obj, idx = decoder.raw_decode(response_text, idx)
        yield obj


############################################################################
async def auth_check_is_needed(html, session):
    auth_check_form_action = get_form_action(html)
    auth_check_code = await vkplus.enter_confirmation_сode()

    auth_check_data = {
        'code': auth_check_code,
        '_ajax': '1',
        'remember': '1'
    }

    async with session.post(auth_check_form_action, data=auth_check_data) as resp:
        await resp.text()


async def auth_captcha_is_needed(response, login_form_data, captcha_url, session):
    response_url_dict = get_url_query(response.url)

    captcha_form_action = get_form_action((await response.text()))
    if not captcha_form_action:
        fatal('Cannot find form url in captcha')

    captcha_url = '%s?s=%s&sid=%s' % (captcha_url, response_url_dict['s'], response_url_dict['sid'])

    login_form_data['captcha_sid'] = response_url_dict['sid']
    login_form_data['captcha_key'] = await vkplus.enter_captcha(captcha_url)

    async with session.post(captcha_form_action, data=login_form_data) as resp:
        await resp.text()


#############################################################################
async def get_token(username, password, app_id, scope):
    url_get_token = "https://oauth.vk.com/authorize"

    with aiohttp.ClientSession() as session:
        await login(username, password, session)

        token_data = {
            "client_id": app_id,
            "redirect_uri": "https://oauth.vk.com/blank.html?",
            "response_type": "token",
            "scope": scope,
            "display": "mobile",
            "v": 5.64
        }

        headers = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36",
            "accept-language": "ru-RU,ru;q=0.8,en-US;q=0.6,en;q=0.4",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

        async with session.post(url_get_token, data=token_data, headers=headers) as resp:
            html = await resp.text()

            response_url_query1 = get_url_query(resp.url)

            if resp.history:
                response_url_query2 = get_url_query(resp.history[-1].headers["Location"])
            else:
                response_url_query2 = {}

            if 'access_token' in response_url_query1:
                return response_url_query1['access_token']

            elif 'access_token' in response_url_query2:
                return response_url_query2['access_token']

            else:
                form_action = get_form_action(html)

        if form_action:
            async with session.post(form_action, headers=headers) as resp:
                html = await resp.text()

                response_url_query1 = get_url_query(resp.url)

                if resp.history:
                    response_url_query2 = get_url_query(resp.history[-1].headers["Location"])
                else:
                    response_url_query2 = {}

                if 'access_token' in response_url_query1:
                    return response_url_query1['access_token']

                elif 'access_token' in response_url_query2:
                    return response_url_query2['access_token']

        return None


async def login(username, password, session):
    captcha_url = 'https://m.vk.com/captcha.php'
    url_login = "https://m.vk.com"

    login_form_data = {
        'email': username,
        'pass': password,
    }

    async with session.get(url_login) as resp:
        html = await resp.text()

        login_form_action = get_form_action(html)

    if not login_form_action:
        fatal("VK changed authentication flow")

    async with session.post(login_form_action, data=login_form_data) as resp:
        html = await resp.text()

        response_url_query = get_url_query(resp.url)

        cookies = [cookie.key for cookie in session.cookie_jar]

        if 'remixsid' in cookies or 'remixsid6' in cookies:
            return

        if 'sid' in response_url_query:
            await auth_captcha_is_needed(resp, login_form_data, captcha_url, session)

        elif response_url_query.get('act') == 'authcheck':
            await auth_check_is_needed(await resp.text(), session)

        elif 'security_check' in response_url_query:
            hues.error("Phone number is needed")

        else:
            hues.error("Authorization error (incorrect password)")
