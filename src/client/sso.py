# -*- coding: utf-8 -*-
# SSO统一认证登录接口
import asyncio
import logging
from typing import Optional

import httpx

from . import patterns
from config import config


class SsoApi:

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._session: Optional[httpx.AsyncClient] = None
        self._url = ''

    async def _get_execution(self):
        resp = await self._session.get(self._url, follow_redirects=True)
        result = patterns.execution.search(resp.text)
        assert result, 'unexpected behavior: execution code not retrieved'
        return result.group(1)

    async def _get_login_form(self):
        return {
            'username': self._username,
            'password': self._password,
            'submit': '登录',
            'type': 'username_password',
            'execution': await self._get_execution(),
            '_eventId': 'submit',
        }

    async def login_sso(self, url):
        """
        北航统一认证接口
        :param url: 不同网站向sso发送自己的域名，此时sso即了解是那个网站和应该返回何种token
        :return: token的返回形式为一个带有ticket的url，一般访问这个url即可在cookies中或者storages中储存凭证
        不同的网站有不同的处理形式
        """
        self._url = url
        async with httpx.AsyncClient() as self._session:
            self._session.headers['User-Agent'] = config.get('user_agent')
            login_form = await self._get_login_form()
            resp = await self._session.post('https://sso.buaa.edu.cn/login', data=login_form, follow_redirects=False)
            assert resp.status_code == 302, 'maybe your username or password is invalid'
            location = resp.headers['Location']
            logging.info('location: ' + location)
            return location


async def test():
    from config import config
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    sso = SsoApi(config.get('sso_username'), config.get('sso_password'))
    location = await sso.login_sso(
        'https://sso.buaa.edu.cn/login?TARGET=http%3A%2F%2Fbykc.buaa.edu.cn%2Fsscv%2FcasLogin')
    print(location)


if __name__ == '__main__':
    asyncio.run(test())
