import datetime
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from client import Client, FailedToChoose, AlreadyChosen, ApiError, TooEarlyToChoose, FailedToDelChosen
from config import config
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import Course, engine

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

client = Client(config.get('sso_username'), config.get('sso_password'))
client.soft_login()


def __brief_info(id, name, position, start_date, end_date, count, status):
    return f"ID：{id}\n" \
           f"名称：{name}\n" \
           f"地点：{position}\n" \
           f"课程开始：{start_date}\n" \
           f"课程结束：{end_date}\n" \
           f"人数：{count}\n" \
           f"状态：{status}\n"


def __detailed_info(id, name, teacher, position, start_date, end_date,
                    select_start_date, select_end_date, cancel_end_date, count, status):
    return f"【课程详情】\n" \
           f"ID：{id}\n" \
           f"名称：{name}\n" \
           f"教师：{teacher}\n" \
           f"地点：{position}\n" \
           f"课程开始：{start_date}\n" \
           f"课程结束：{end_date}\n" \
           f"选课开始：{select_start_date}\n" \
           f"选课结束：{select_end_date}\n" \
           f"退选截止：{cancel_end_date}\n" \
           f"人数：{count}\n" \
           f"状态：{status}\n"


def __get_message_and_keyboard(course_id, is_detail, current_count=None):
    """
    :param current_count: for some strange reason
    :return:
    """
    course = client.query_course_by_id(course_id)
    id = course['id']
    name = course['courseName']
    teacher = course['courseTeacher']
    position = course['coursePosition']
    start_date = course['courseStartDate']
    end_date = course['courseEndDate']
    select_start_date = course['courseSelectStartDate']
    select_end_date = course['courseSelectEndDate']
    cancel_end_date = course['courseCancelEndDate']
    if current_count is not None:
        count = f"{current_count}/{course['courseMaxCount']}"
    else:
        count = f"{course['courseCurrentCount']}/{course['courseMaxCount']}"
    selected = course['selected']
    with Session(engine) as session:
        course = __query_and_update_model(session, id, name, start_date, end_date,
                                          select_start_date, select_end_date, cancel_end_date, selected)
        match course.status:
            case Course.STATUS_NOT_SELECTED:
                status = "未选择"
            case Course.STATUS_SELECTED:
                status = "已选中"
            case Course.STATUS_BOOKED:
                status = "预约抢选"
            case Course.STATUS_WAITING:
                status = "预约补选"
        if is_detail == "yes":
            message = __detailed_info(id, name, teacher, position, start_date, end_date, select_start_date,
                                      select_end_date, cancel_end_date, count, status)
            if course.status == Course.STATUS_NOT_SELECTED:
                keyboard = [[InlineKeyboardButton("我要选课", callback_data=f'choose {id} yes')]]
            else:
                keyboard = [[InlineKeyboardButton("我要退课", callback_data=f'cancel {id} yes')]]
        else:
            message = __brief_info(id, name, position, start_date, end_date, count, status)
            if course.status == Course.STATUS_NOT_SELECTED:
                keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                             InlineKeyboardButton("我要选课", callback_data=f'choose {id} no')]]
            else:
                keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                             InlineKeyboardButton("我要退课", callback_data=f'cancel {id} no')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
    return message, reply_markup


def __query_and_update_model(session: Session, id, name, start_date, end_date,
                             select_start_date, select_end_date, cancel_end_date, selected):
    stmt = select(Course).where(Course.id == id)
    course = session.execute(stmt).scalar()
    if isinstance(start_date, str):
        start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S')
    if isinstance(end_date, str):
        end_date = datetime.datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S')
    if isinstance(select_start_date, str):
        select_start_date = datetime.datetime.strptime(select_start_date, '%Y-%m-%d %H:%M:%S')
    if isinstance(select_end_date, str):
        select_end_date = datetime.datetime.strptime(select_end_date, '%Y-%m-%d %H:%M:%S')
    if isinstance(cancel_end_date, str):
        cancel_end_date = datetime.datetime.strptime(cancel_end_date, '%Y-%m-%d %H:%M:%S')
    if course is None:
        if selected:
            status = Course.STATUS_SELECTED
        else:
            status = Course.STATUS_NOT_SELECTED
        course = Course(id=id, name=name, start_date=start_date, end_date=end_date,
                        select_start_date=select_start_date, select_end_date=select_end_date,
                        cancel_end_date=cancel_end_date, status=status)
        session.add(course)
        session.commit()
    else:
        course.name = name
        course.start_date = start_date
        course.end_date = end_date
        course.select_start_date = select_start_date
        course.select_end_date = select_end_date
        course.cancel_end_date = cancel_end_date
        if selected and course.status != Course.STATUS_SELECTED:
            course.status = Course.STATUS_SELECTED
            session.commit()
        elif not selected and course.status == Course.STATUS_SELECTED:
            course.status = Course.STATUS_NOT_SELECTED
            session.commit()

    return course


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = "你好呀~我是北航博雅课程小助手，我可以帮你完成以下操作：\n\n" \
              "/query_avail 查询可选课程\n\n" \
              "/query_chosen 查询已选课程\n\n" \
              "/preferences 修改偏好配置\n\n" \
              "/status 查看系统当前运行状态"
    await update.message.reply_text(message)


async def query_avail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays what courses are available for selection."""
    resp = client.query_student_semester_course_by_page(1, 100)
    tasks = []
    for course in resp['content']:
        id = course['id']
        name = course['courseName']
        position = course['coursePosition']
        start_date = course['courseStartDate']
        end_date = course['courseEndDate']
        select_start_date = course['courseSelectStartDate']
        select_end_date = course['courseSelectEndDate']
        cancel_end_date = course['courseCancelEndDate']
        if datetime.datetime.now() > datetime.datetime.strptime(select_end_date, '%Y-%m-%d %H:%M:%S'):
            continue
        count = f"{course['courseCurrentCount']}/{course['courseMaxCount']}"
        selected = course['selected']
        with Session(engine) as session:
            course = __query_and_update_model(session, id, name, start_date, end_date,
                                              select_start_date, select_end_date, cancel_end_date, selected)
            match course.status:
                case Course.STATUS_NOT_SELECTED:
                    status = "未选择"
                case Course.STATUS_SELECTED:
                    status = "已选中"
                case Course.STATUS_BOOKED:
                    status = "预约抢选"
                case Course.STATUS_WAITING:
                    status = "预约补选"

            message = __brief_info(id, name, position, start_date, end_date, count, status)
            if course.status == Course.STATUS_NOT_SELECTED:
                keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                             InlineKeyboardButton("我要选课", callback_data=f'choose {id} no')]]
            else:
                keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                             InlineKeyboardButton("我要退课", callback_data=f'cancel {id} no')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            task = asyncio.create_task(update.message.reply_text(message, reply_markup=reply_markup))
            tasks.append(task)
    await asyncio.gather(*tasks)


async def query_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays what courses are chosen."""
    resp = client.query_chosen_course()
    tasks = []
    for course in resp['courseList']:
        course = course['courseInfo']
        id = course['id']
        name = course['courseName']
        position = course['coursePosition']
        start_date = course['courseStartDate']
        end_date = course['courseEndDate']
        count = f"{course['courseCurrentCount']}/{course['courseMaxCount']}"
        message = __brief_info(id, name, position, start_date, end_date, count, "已选中")
        keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                     InlineKeyboardButton("我要退课", callback_data=f'cancel {id} no')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        task = asyncio.create_task(update.message.reply_text(message, reply_markup=reply_markup))
        tasks.append(task)
    await asyncio.gather(*tasks)


async def detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays detail of a course."""
    query = update.callback_query
    course_id = int(query.data.split(' ')[1])
    message, reply_markup = __get_message_and_keyboard(course_id, "yes")
    await asyncio.gather(query.answer(),
                         query.message.edit_text(message, reply_markup=reply_markup))


async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choose a course."""
    query = update.callback_query
    course_id, is_detail = query.data.split(' ')[1:]
    course_id = int(course_id)
    update_info = False
    try:
        resp = client.chose_course(course_id)
        asyncio.create_task(query.answer("选课成功"))
        update_info = True
        current_count = resp['courseCurrentCount']
    except TooEarlyToChoose:
        asyncio.create_task(query.answer("选课失败:还未到选课时间"))
    except AlreadyChosen:
        asyncio.create_task(query.answer("选课失败:已经选过该课程"))
        update_info = True
        current_count = None
    except FailedToChoose as e:
        asyncio.create_task(query.answer("选课失败:" + str(e)))
    except ApiError:
        asyncio.create_task(query.message.reply_text("选课失败:原因未知"))
    if update_info:
        message, reply_markup = __get_message_and_keyboard(course_id, is_detail, current_count)
        asyncio.create_task(update.callback_query.message.edit_text(message, reply_markup=reply_markup))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """cancel a course"""
    query = update.callback_query
    course_id, is_detail = query.data.split(' ')[1:]
    course_id = int(course_id)
    update_info = False
    try:
        resp = client.del_chosen_course(course_id)
        current_count = resp['courseCurrentCount']
        update_info = True
        asyncio.create_task(query.answer("退课成功"))
    except FailedToDelChosen as e:
        asyncio.create_task(query.answer("退课失败:" + str(e)))
    if update_info:
        message, reply_markup = __get_message_and_keyboard(course_id, is_detail, current_count)
        asyncio.create_task(update.callback_query.message.edit_text(message, reply_markup=reply_markup))


if __name__ == '__main__':
    application = ApplicationBuilder() \
        .token(config.get('telegram_token')) \
        .proxy_url('http://127.0.0.1:7890') \
        .build()

    start_handler = CommandHandler('start', start)
    query_avail_handler = CommandHandler('query_avail', query_avail)
    query_chosen_handler = CommandHandler('query_chosen', query_chosen)
    detail_handler = CallbackQueryHandler(detail, pattern=r'^detail \d+$')
    choose_handler = CallbackQueryHandler(choose, pattern=r'^choose \d+ \w+$')
    cancel_handler = CallbackQueryHandler(cancel, pattern=r'^cancel \d+ \w+$')

    application.add_handler(start_handler)
    application.add_handler(query_avail_handler)
    application.add_handler(query_chosen_handler)
    application.add_handler(detail_handler)
    application.add_handler(choose_handler)
    application.add_handler(cancel_handler)

    application.run_polling()
