import asyncio
import logging
import traceback

import binascii
import datetime
import json
import time
import warnings
from typing import overload

import httpx

from . import patterns
from .exceptions import LoginError, AlreadyChosen, FailedToChoose, FailedToDelChosen, TooEarlyToChoose, \
    LoginExpired, UnknownError, CourseIsFull
from .sso import SsoApi
from .crypto import *

from config import config
from storage import storage


class Client:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.token: str = ''
        self.zero_trust_engine: str = ''

    async def soft_login(self):
        """
        first try to login with token that is stored in config file, if failed, login with username and password
        """
        if storage.get('token'):
            self.token = storage.get('token')
            try:
                result = await self._unsafe_get_user_profile()
                if result['employeeId'] == config.get('sso_username'):
                    print("soft login success")
                    return True
            except Exception:
                pass
        return await self.login()

    async def login(self):
        """
        login through sso
        """
        try:
            async with httpx.AsyncClient() as session:
                url = config.get('bykc_root') + "/sscv/cas/login"
                resp = await session.get(url, follow_redirects=False)
                if resp.status_code in [301, 302]:
                    url = resp.headers['Location']
                url = await SsoApi(self.username, self.password).login_sso(url)
                while True:
                    resp = await session.get(url, follow_redirects=False)  # manually redirect
                    searching_token = patterns.token.search(url)
                    if searching_token:
                        self.token = searching_token.group(1)
                        storage.set('token', self.token)
                        print('login success')
                        break
                    elif resp.status_code in [301, 302]:
                        url = resp.headers['Location']
                        continue
                    else:
                        raise LoginError("登录错误:未找到token")
        except httpx.HTTPError:
            raise LoginError("登录错误:网络错误")

    def logout(self):
        """
        clear session and logout
        """
        self.token = ''
        self.zero_trust_engine = ''

    async def __call_api(self, api_name: str, data: dict):
        """call api and try to deal with some exceptions"""
        last_exception = None
        for retry in range(3):
            try:
                return await self.__call_api_raw(api_name, data)
            except LoginExpired as e:
                logging.info('login expired, retrying...' + repr(e))
                last_exception = e
                try:
                    await self.soft_login()
                except LoginError as e:
                    last_exception = e
                    await asyncio.sleep(1)
            except UnknownError as e:
                last_exception = e
                await asyncio.sleep(1)
        raise last_exception

    async def __call_api_raw(self, api_name: str, data: dict):
        """
        an intermediate method to call api which deals with crypto and auth
        :param api_name: could be found in `app.js`
        :param data: could also be found in `app.js`
        :return: raw data returned by the api
        """
        if not self.token:
            raise LoginExpired("login expired")
        url = config.get('bykc_root') + '/sscv/' + api_name
        data_str = json.dumps(data).encode()
        aes_key = generate_aes_key()
        ak = rsa_encrypt(aes_key).decode()
        data_sign = sign(data_str)
        sk = rsa_encrypt(data_sign).decode()
        ts = str(int(time.time() * 1000))

        data_encrypted = base64.b64encode(aes_encrypt(data_str, aes_key))
        headers = {
            'Content-Type': 'application/json;charset=utf-8',
            'User-Agent': config.get('user_agent'),
            'auth_token': self.token,
            'authtoken': self.token,
            'ak': ak,
            'sk': sk,
            'ts': ts,
        }

        try:
            async with httpx.AsyncClient() as session:
                resp = await session.post(url, content=data_encrypted, headers=headers)
                text = resp.content
                if resp.status_code == 302:
                    raise LoginExpired("login expired")
                if resp.status_code != 200:
                    raise UnknownError(f"server panics with http status code: {resp.status_code}")
                try:
                    message_decode_b64 = base64.b64decode(text)
                except binascii.Error:
                    raise UnknownError(f"unable to parse response: {text}")

                try:
                    api_resp = json.loads(aes_decrypt(message_decode_b64, aes_key))
                except ValueError:
                    raise LoginExpired("failed to decrypt response, it's usually because your login has expired")

                if api_resp['status'] == '98005399':
                    raise LoginExpired("login expired")
                elif api_resp['status'] != '0':
                    if api_resp['errmsg'].find('已报名过该课程，请不要重复报名') >= 0:
                        raise AlreadyChosen("已报名过该课程，请不要重复报名")
                    if api_resp['errmsg'].find('该课程还未开始选课，请耐心等待') >= 0:
                        raise TooEarlyToChoose("该课程还未开始选课，请耐心等待")
                    if api_resp['errmsg'].find('选课失败，该课程不可选择') >= 0:
                        raise FailedToChoose('选课失败，该课程不可选择')
                    if api_resp['errmsg'].find('报名失败，该课程人数已满！') >= 0:
                        raise CourseIsFull("报名失败，该课程人数已满！")
                    if api_resp['errmsg'].find('退选失败，未找到退选课程或已超过退选时间') >= 0:
                        raise FailedToDelChosen("退选失败，未找到退选课程或已超过退选时间")
                    raise UnknownError(f"server returns a non zero api status code: {api_resp['status']}")
                return api_resp['data']
        except httpx.HTTPError as e:
            traceback.print_exc()
            raise UnknownError("网络错误" + str(e))

    async def _unsafe_get_user_profile(self):
        """
        get your profile
        :return: an object contains your profile
        """
        result = await self.__call_api_raw('getUserProfile', {})
        return result

    async def get_user_profile(self):
        """
        get your profile
        :return: an object contains your profile
        """
        result = await self.__call_api('getUserProfile', {})
        return result

    async def query_student_semester_course_by_page(self, page_number: int, page_size: int):
        """
        query all recent courses
        :param page_number: page number
        :param page_size: page size
        :return: an object contains a list of courses and a total count
        """
        result = await self.__call_api('queryStudentSemesterCourseByPage',
                                       {'pageNumber': page_number, 'pageSize': page_size})
        return result

    async def query_course_by_id(self, course_id: int):
        """
        query a course by id
        :param course_id: course id
        :return: an object contains a course
        """
        result = await self.__call_api('queryCourseById', {'id': course_id})
        return result

    async def query_fore_course(self):
        warnings.warn('this api is not officially supported by bykc system, \n'
                      'use query_student_semester_course_by_page instead', DeprecationWarning)
        result = await self.__call_api('queryForeCourse', {})
        return result

    async def query_selectable_course(self):
        warnings.warn('this api is not officially supported by bykc system, \n'
                      'use query_student_semester_course_by_page instead', DeprecationWarning)
        result = await self.__call_api('querySelectableCourse', {})
        return result

    async def get_all_config(self):
        """
        :return: all config contains campus, college, role, semester, term
        """
        result = await self.__call_api('getAllConfig', {})
        return result

    @overload
    async def query_chosen_course(self):
        """
        :return: the chosen courses of current semester
        """
        ...

    @overload
    async def query_chosen_course(self, semester_id: int):
        """
        :param semester_id: the semester id, could be obtained from `get_all_config`
        :return: the chosen courses of the semester
        """
        ...

    @overload
    async def query_chosen_course(self, start_date: datetime.datetime, end_date: datetime.datetime):
        """
        :param start_date: the start date to query
        :param end_date: the end date to query
        :return: the chosen courses in the period
        """
        ...

    async def query_chosen_course(self, arg0=None, arg1=None):  # get chosen courses in the specified time range
        if arg0 is None:
            all_config = await self.get_all_config()
            semester_start_date = all_config['semester'][0]['semesterStartDate']
            semester_end_date = all_config['semester'][0]['semesterEndDate']
            data = {
                "startDate": semester_start_date,
                "endDate": semester_end_date,
            }
        elif isinstance(arg0, int):
            all_config = await self.get_all_config()
            semester = None
            for s in all_config['semester']:
                if s['id'] == arg0:
                    semester = s
                    break
            if semester is None:
                raise UnknownError(f"no such semester: {arg0}")
            semester_start_date = semester['semesterStartDate']
            semester_end_date = semester['semesterEndDate']
            data = {
                "startDate": semester_start_date,
                "endDate": semester_end_date,
            }
        else:
            data = {
                "startDate": arg0.strftime("%Y-%m-%d %H:%M:%S"),
                "endDate": arg1.strftime("%Y-%m-%d %H:%M:%S")
            }
        result = await self.__call_api('queryChosenCourse', data)
        return result

    async def chose_course(self, course_id: int):
        """
        choose a course
        :param course_id: the course id, could be obtained from `query_student_semester_course_by_page`
        :return: some useless data if success
        :raise AlreadyChosen: if the course has already been chosen
        :raise FailedToChoose: if failed to choose the course
        """
        result = await self.__call_api('choseCourse', {'courseId': course_id})
        return result

    async def del_chosen_course(self, course_id: int):
        """
        delete a chosen course
        :param course_id: the course id, could be obtained from `query_chosen_course`
        :return: some useless data if success
        :raise FailedToDelChosen: if failed to delete the chosen course
        """
        result = await self.__call_api('delChosenCourse', {'id': course_id})
        return result
