import datetime
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, \
    Defaults
from telegram.ext import filters
from client import Client, FailedToChoose, AlreadyChosen, CourseIsFull, ApiException, TooEarlyToChoose, \
    FailedToDelChosen
from config import config
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import Course, engine

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

client = Client(config.get('sso_username'), config.get('sso_password'))


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


async def __get_message_and_keyboard(course_id, is_detail, current_count=None):
    """
    :param current_count: for some strange reason
    :return:
    """
    course = await client.query_course_by_id(course_id)
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
                status = "⚪️未选择"
            case Course.STATUS_SELECTED:
                status = "🟢已选中"
            case Course.STATUS_BOOKED:
                status = "♥️预约抢选"
            case Course.STATUS_WAITING:
                status = "🕓预约补选"
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


### callbacks ###

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"handler called: start")
    message = "你好呀~我是北航博雅课程小助手喵！我可以帮你完成以下操作：\n" \
              "/query_avail 查询可选课程\n\n" \
              "/query_chosen 查询已选课程\n\n" \
              "/preferences 修改偏好配置\n\n" \
              "/status 查看系统当前运行状态"
    await update.message.reply_text(message)


async def query_avail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays what courses are available for selection."""
    logging.info(f"handler called: query_avail")
    resp = await client.query_student_semester_course_by_page(1, 100)
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
                    status = "⚪️未选择"
                case Course.STATUS_SELECTED:
                    status = "🟢已选中"
                case Course.STATUS_BOOKED:
                    status = "♥️预约抢选"
                case Course.STATUS_WAITING:
                    status = "🕓预约补选"

            message = __brief_info(id, name, position, start_date, end_date, count, status)
            if course.status == Course.STATUS_NOT_SELECTED:
                keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                             InlineKeyboardButton("我要选课", callback_data=f'choose {id} no')]]
            else:
                keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                             InlineKeyboardButton("我要退课", callback_data=f'cancel {id} no')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            task = context.application.create_task(update.message.reply_text(message, reply_markup=reply_markup))
            tasks.append(task)
    await asyncio.gather(*tasks)


async def query_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays what courses are chosen."""
    logging.info(f"handler called: query_chosen")
    resp = await client.query_chosen_course()
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
        task = context.application.create_task(update.message.reply_text(message, reply_markup=reply_markup))
        tasks.append(task)
    await asyncio.gather(*tasks)


async def detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays detail of a course."""
    logging.info(f"handler called: detail")
    query = update.callback_query
    course_id = int(query.data.split(' ')[1])
    message, reply_markup = await __get_message_and_keyboard(course_id, "yes")
    await asyncio.gather(query.answer(),
                         query.message.edit_text(message, reply_markup=reply_markup))


async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choose a course."""
    logging.info(f"handler called: choose")
    query = update.callback_query
    course_id, is_detail = query.data.split(' ')[1:]
    course_id = int(course_id)
    current_count = None
    try:
        resp = await client.chose_course(course_id)
        context.application.create_task(query.answer("选课成功"))
        current_count = resp['courseCurrentCount']
    except TooEarlyToChoose:
        with Session(engine) as session:
            course = session.query(Course).filter(Course.id == course_id).first()
            course.status = Course.STATUS_BOOKED
            session.commit()
            __add_rush_job(context.job_queue, course)
            context.application.create_task(query.answer("还未开始，预约选课成功"))
    except CourseIsFull:
        with Session(engine) as session:
            course = session.query(Course).filter(Course.id == course_id).first()
            if course.cancel_end_date > datetime.datetime.now() and course.select_end_date > datetime.datetime.now():
                course.status = Course.STATUS_WAITING
                session.commit()
                context.application.create_task(query.answer("课程已满，预约补选成功"))
            else:
                context.application.create_task(query.answer("课程已满，选课失败"))
    except AlreadyChosen:
        context.application.create_task(query.answer("选课失败:已经选过该课程"))
    except FailedToChoose as e:
        context.application.create_task(query.answer("选课失败:" + str(e)))
    except ApiException:
        context.application.create_task(query.message.reply_text("选课失败:原因未知"))
    message, reply_markup = await __get_message_and_keyboard(course_id, is_detail, current_count)
    context.application.create_task(update.callback_query.message.edit_text(message, reply_markup=reply_markup))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """cancel a course"""
    logging.info(f"handler called: cancel")
    query = update.callback_query
    course_id, is_detail = query.data.split(' ')[1:]
    course_id = int(course_id)
    current_count = None
    with Session(engine) as session:
        course = session.query(Course).filter(Course.id == course_id).scalar()
        if course.status in [Course.STATUS_BOOKED, Course.STATUS_WAITING]:
            course.status = Course.STATUS_NOT_SELECTED
            session.commit()
    try:
        resp = await client.del_chosen_course(course_id)
        current_count = resp['courseCurrentCount']
        context.application.create_task(query.answer("退课成功"))
    except FailedToDelChosen as e:
        context.application.create_task(query.answer("退课失败:" + str(e)))
    message, reply_markup = await __get_message_and_keyboard(course_id, is_detail, current_count)
    context.application.create_task(update.callback_query.message.edit_text(message, reply_markup=reply_markup))


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject the current user"""
    await update.message.reply_text(f"您的id是{update.effective_user.id}，您没有权限使用本机器人。\n"
                                    f"如果该机器人是您的，请在config.json中填入您的id。")


### jobs ###

async def refresh_course_list(context: ContextTypes.DEFAULT_TYPE):
    """Refresh the course list"""
    resp = await client.query_student_semester_course_by_page(1, 100)
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
            resp = await client.query_student_semester_course_by_page(1, 100)
            course = __query_and_update_model(session, id, name, start_date, end_date,
                                              select_start_date, select_end_date, cancel_end_date, selected)
            match course.status:
                case Course.STATUS_NOT_SELECTED:
                    status = "⚪️未选择"
                case Course.STATUS_SELECTED:
                    status = "🟢已选中"
                case Course.STATUS_BOOKED:
                    status = "♥️预约抢选"
                case Course.STATUS_WAITING:
                    status = "🕓预约补选"

            if not course.notified:
                message = __brief_info(id, name, position, start_date, end_date, count, status)
                if course.status == Course.STATUS_NOT_SELECTED:
                    keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                                 InlineKeyboardButton("我要选课", callback_data=f'choose {id} no')]]
                else:
                    keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                                 InlineKeyboardButton("我要退课", callback_data=f'cancel {id} no')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                try:
                    rtv = await context.bot.send_message(
                        config.get('telegram_owner_id'), "【新的博雅】\n" + message, reply_markup=reply_markup)
                    course.notified = True
                    session.commit()
                except:
                    # retry in 10 seconds
                    for job in context.job_queue.get_jobs_by_name('refresh_retry'):
                        job.schedule_removal()  # prevent job blood
                    context.job_queue.run_once(refresh_course_list, 10, name='refresh_retry')


async def wait_for_others_cancellation(context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        courses = session.query(Course).filter(Course.status == Course.STATUS_WAITING).all()
        for course in courses:
            if course.select_end_date < datetime.datetime.now():
                try:
                    await client.chose_course(course.id)
                    course.status = Course.STATUS_SELECTED
                    session.commit()
                    keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                                 InlineKeyboardButton("我要退课", callback_data=f'cancel {id} no')]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(config.get('telegram_owner_id'), f"【补选成功】\n{course.name}",
                                                   reply_markup=reply_markup)
                    continue
                except ApiException:
                    pass
                if course.cancel_end_date < datetime.datetime.now():
                    course.status = Course.STATUS_NOT_SELECTED
                    session.commit()
                    keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                                 InlineKeyboardButton("我要选课", callback_data=f'choose {id} no')]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(config.get('telegram_owner_id'), f"【补选失败】\n{course.name}",
                                                   reply_markup=reply_markup)
            else:
                course.status = Course.STATUS_NOT_SELECTED
                session.commit()
                keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                             InlineKeyboardButton("我要选课", callback_data=f'choose {id} no')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(config.get('telegram_owner_id'), f"【补选失败】\n{course.name}",
                                               reply_markup=reply_markup)


def __add_rush_job(job_queue, course):
    select_start_date = course.select_start_date
    select_date = select_start_date - datetime.timedelta(seconds=10)
    if datetime.datetime.now() > select_date:
        job_queue.run_once(rush_select, 0, name=f'rush_select_{course.id}', data=course.id)
    else:
        job_queue.run_once(rush_select, select_date, name=f'rush_select_{course.id}',
                           data=course.id)


async def rush_select(context: ContextTypes.DEFAULT_TYPE):
    course_id = context.job.data
    with Session(engine) as session:
        course = session.query(Course).filter(Course.id == course_id).scalar()
        if course.status == Course.STATUS_BOOKED:
            while True:
                try:
                    await client.chose_course(course_id)
                    course.status = Course.STATUS_SELECTED
                    session.commit()
                    keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                                 InlineKeyboardButton("我要退课", callback_data=f'cancel {id} no')]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(config.get('telegram_owner_id'), f"【抢选成功】\n{course.name}",
                                                   reply_markup=reply_markup)
                    break
                except TooEarlyToChoose:
                    await asyncio.sleep(0.5)
                except AlreadyChosen:
                    course.status = Course.STATUS_SELECTED
                    session.commit()
                    break
                except CourseIsFull:
                    course.status = Course.STATUS_WAITING
                    session.commit()
                    keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {id}'),
                                 InlineKeyboardButton("我要退课", callback_data=f'cancel {id} no')]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(config.get('telegram_owner_id'),
                                                   f"【抢选失败】\n{course.name}\n已自动进入补选模式",
                                                   reply_markup=reply_markup)
                    break
                except ApiException:
                    await asyncio.sleep(0.5)


def init_handlers(application):
    private_filter = filters.User(user_id=int(config.get('telegram_owner_id')))
    start_handler = CommandHandler('start', start, filters=private_filter)
    query_avail_handler = CommandHandler('query_avail', query_avail, filters=private_filter)
    query_chosen_handler = CommandHandler('query_chosen', query_chosen, filters=private_filter)
    detail_handler = CallbackQueryHandler(detail, pattern=r'^detail \d+$')
    choose_handler = CallbackQueryHandler(choose, pattern=r'^choose \d+ \w+$')
    cancel_handler = CallbackQueryHandler(cancel, pattern=r'^cancel \d+ \w+$')

    reject_handler = MessageHandler(filters=~private_filter, callback=reject)

    application.add_handler(start_handler)
    application.add_handler(query_avail_handler)
    application.add_handler(query_chosen_handler)
    application.add_handler(detail_handler)
    application.add_handler(choose_handler)
    application.add_handler(cancel_handler)
    application.add_handler(reject_handler)


def init_jobs(application):
    application.job_queue.run_repeating(refresh_course_list, 600, first=10, name='refresh')
    application.job_queue.run_repeating(wait_for_others_cancellation, 60, name='wait_for_others_cancellation')

    with Session(engine) as session:
        courses = session.query(Course).filter(Course.status == Course.STATUS_BOOKED).all()
        for course in courses:
            __add_rush_job(application.job_queue, course)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(config.get('telegram_owner_id'),
                                   f"【发生错误】\n{context.error}")


if __name__ == '__main__':
    application_builder = ApplicationBuilder()
    application_builder.defaults(Defaults(block=False))
    application_builder.token(config.get('telegram_token'))
    if config.get('proxy_url'):
        application_builder.proxy_url(config.get('proxy_url'))
    application = application_builder.build()

    init_handlers(application)
    init_jobs(application)
    application.add_error_handler(error_handler)

    application.run_polling()
