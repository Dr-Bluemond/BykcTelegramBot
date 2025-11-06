import asyncio

from client import Client
from config import config

c = Client(config.get('sso_username'), config.get('sso_password'))


async def test():
    x = await c.query_student_semester_course_by_page(1, 20)
    print(x)


if __name__ == '__main__':
    asyncio.run(test())
