import datetime
import logging
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, \
    Defaults
from telegram.ext import filters
from telegram.error import TelegramError

import html_process
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


class ReceivedCourseData:
    def __init__(self):
        self.id = None
        self.name = None
        self.teacher = None
        self.position = None
        self.start_date = None
        self.end_date = None
        self.select_start_date = None
        self.select_end_date = None
        self.cancel_end_date = None
        self.selected = None
        self.current_count = None
        self.max_count = None
        self.description = None

        self.__model_synced = False
        self.__notified = None
        self.__select_start_date_changed = False
        self.__status = None

    def sync_model(self):
        """
        sync model in database
        after which we know `__is_notified`, `__is_select_start_date_changed`, `__status`
        :return:
        """
        if self.__model_synced:
            return
        with Session(engine) as session:
            stmt = select(Course).where(Course.id == self.id)
            course: Course = session.execute(stmt).scalar()
            start_date = self.start_date and datetime.datetime.strptime(self.start_date, '%Y-%m-%d %H:%M:%S')
            end_date = self.end_date and datetime.datetime.strptime(self.end_date, '%Y-%m-%d %H:%M:%S')
            select_start_date = self.select_start_date and datetime.datetime.strptime(self.select_start_date,
                                                                                      '%Y-%m-%d %H:%M:%S')
            select_end_date = self.select_end_date and datetime.datetime.strptime(self.select_end_date,
                                                                                  '%Y-%m-%d %H:%M:%S')
            cancel_end_date = self.cancel_end_date and datetime.datetime.strptime(self.cancel_end_date,
                                                                                  '%Y-%m-%d %H:%M:%S')
            if course is None:
                if self.selected:
                    status = Course.STATUS_SELECTED
                else:
                    status = Course.STATUS_NOT_SELECTED
                course = Course(id=self.id, name=self.name, start_date=start_date, end_date=end_date,
                                select_start_date=select_start_date, select_end_date=select_end_date,
                                cancel_end_date=cancel_end_date, status=status)
                self.__notified = False
                self.__status = status
                session.add(course)
                session.commit()
            else:
                course.name = self.name
                course.start_date = start_date
                course.end_date = end_date
                if course.select_start_date != select_start_date:
                    self.__select_start_date_changed = True
                course.select_start_date = select_start_date
                course.select_end_date = select_end_date
                course.cancel_end_date = cancel_end_date
                if self.selected and course.status != Course.STATUS_SELECTED:
                    course.status = Course.STATUS_SELECTED
                elif not self.selected and course.status == Course.STATUS_SELECTED:
                    course.status = Course.STATUS_NOT_SELECTED
                session.commit()
                self.__notified = course.notified
                self.__status = course.status
        self.__model_synced = True

    def is_notified(self):
        if not self.__model_synced:
            self.sync_model()
        return self.__notified

    def set_notified(self, value):
        self.__notified = value
        with Session(engine) as session:
            stmt = select(Course).where(Course.id == self.id)
            course: Course = session.execute(stmt).scalar()
            course.notified = value
            session.commit()

    def get_status(self):
        if not self.__model_synced:
            self.sync_model()
        return self.__status

    def is_select_start_date_changed(self):
        if not self.__model_synced:
            self.sync_model()
        return self.__select_start_date_changed

    def get_info(self, is_detail, title=None):
        if not self.__model_synced:
            self.sync_model()
        if self.__status == Course.STATUS_NOT_SELECTED:
            status = "⚪️未选择"
        elif self.__status == Course.STATUS_SELECTED:
            status = "🟢已选中"
        elif self.__status == Course.STATUS_BOOKED:
            status = "♥️预约抢选"
        elif self.__status == Course.STATUS_WAITING:
            status = "🕓预约补选"
        else:
            status = "系统错误"

        if is_detail == "no":
            return (f"{title}\n" if title else "") + \
                f"ID：{self.id}\n" \
                f"名称：{self.name}\n" \
                f"地点：{self.position}\n" \
                f"课程开始：{self.start_date}\n" \
                f"课程结束：{self.end_date}\n" \
                f"选课开始：{self.select_start_date}\n" \
                f"人数：{self.current_count}/{self.max_count}\n" \
                f"状态：{status}\n"
        else:
            return (f"{title}\n" if title else "【课程详情】\n") + \
                f"ID：{self.id}\n" \
                f"名称：{self.name}\n" \
                f"教师：{self.teacher}\n" \
                f"地点：{self.position}\n" \
                f"课程开始：{self.start_date}\n" \
                f"课程结束：{self.end_date}\n" \
                f"选课开始：{self.select_start_date}\n" \
                f"选课结束：{self.select_end_date}\n" \
                f"退课截止：{self.cancel_end_date}\n" \
                f"人数：{self.current_count}/{self.max_count}\n" \
                f"课程简介：\n{self.description}\n" \
                f"状态：{status}\n"

    async def refresh(self):
        self.__model_synced = False
        data = await client.query_course_by_id(self.id)
        self.id = data['id']
        self.name = data['courseName']
        self.teacher = data['courseTeacher']
        self.position = data['coursePosition']
        self.start_date = data['courseStartDate']
        self.end_date = data['courseEndDate']
        self.select_start_date = data['courseSelectStartDate']
        self.select_end_date = data['courseSelectEndDate']
        self.cancel_end_date = data['courseCancelEndDate']
        self.current_count = data['courseCurrentCount']
        self.max_count = data['courseMaxCount']
        self.selected = data['selected']
        self.description = html_process.transform(data['courseDesc'])

    def get_reply_markup(self, is_detail):
        keyboard = []
        if is_detail == "no":
            keyboard.append(InlineKeyboardButton("查看详情", callback_data=f'detail {self.id}'))
        if self.get_status() == Course.STATUS_NOT_SELECTED:
            keyboard.append(InlineKeyboardButton("我要选课", callback_data=f'choose {self.id} {is_detail}'))
        else:
            keyboard.append(InlineKeyboardButton("我要退课", callback_data=f'cancel {self.id} {is_detail}'))
        keyboard = [keyboard]
        return InlineKeyboardMarkup(keyboard)


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
        course_data = ReceivedCourseData()
        course_data.id = course['id']
        course_data.name = course['courseName']
        course_data.position = course['coursePosition']
        course_data.start_date = course['courseStartDate']
        course_data.end_date = course['courseEndDate']
        course_data.select_start_date = course['courseSelectStartDate']
        course_data.select_end_date = course['courseSelectEndDate']
        course_data.cancel_end_date = course['courseCancelEndDate']
        if datetime.datetime.now() > datetime.datetime.strptime(course_data.select_end_date, '%Y-%m-%d %H:%M:%S'):
            continue
        course_data.current_count = course['courseCurrentCount']
        course_data.max_count = course['courseMaxCount']
        course_data.selected = course['selected']
        message = course_data.get_info(is_detail="no")
        reply_markup = course_data.get_reply_markup("no")
        task = context.application.create_task(update.message.reply_text(message, reply_markup=reply_markup))
        tasks.append(task)
    await asyncio.gather(*tasks)
    if len(tasks) == 0:
        await update.message.reply_text("未查询到")


async def query_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays what courses are chosen."""
    logging.info(f"handler called: query_chosen")
    resp = await client.query_chosen_course()
    tasks = []
    for course in resp['courseList']:
        course = course['courseInfo']
        course_data = ReceivedCourseData()
        course_data.id = course['id']
        course_data.name = course['courseName']
        course_data.position = course['coursePosition']
        course_data.start_date = course['courseStartDate']
        course_data.end_date = course['courseEndDate']
        course_data.select_start_date = course['courseSelectStartDate']
        course_data.select_end_date = course['courseSelectEndDate']
        course_data.cancel_end_date = course['courseCancelEndDate']
        course_data.current_count = course['courseCurrentCount']
        course_data.max_count = course['courseMaxCount']
        course_data.selected = True
        message = course_data.get_info(is_detail="no")
        reply_markup = course_data.get_reply_markup("no")
        task = context.application.create_task(update.message.reply_text(message, reply_markup=reply_markup))
        tasks.append(task)
    await asyncio.gather(*tasks)
    if len(tasks) == 0:
        await update.message.reply_text("未查询到")


async def detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays detail of a course."""
    logging.info(f"handler called: detail")
    query = update.callback_query
    course_id = int(query.data.split(' ')[1])
    course_data = ReceivedCourseData()
    course_data.id = course_id
    await course_data.refresh()
    message = course_data.get_info(is_detail="yes")
    reply_markup = course_data.get_reply_markup("yes")
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
            __add_rush_job(context.job_queue, course.id, course.select_start_date)
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
    course_data = ReceivedCourseData()
    course_data.id = course_id
    await course_data.refresh()
    course_data.current_count = current_count
    message = course_data.get_info(is_detail=is_detail)
    reply_markup = course_data.get_reply_markup(is_detail)
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
    course_data = ReceivedCourseData()
    course_data.id = course_id
    await course_data.refresh()
    course_data.current_count = current_count
    message = course_data.get_info(is_detail=is_detail)
    reply_markup = course_data.get_reply_markup(is_detail)
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
        course_data = ReceivedCourseData()
        course_data.id = course['id']
        course_data.name = course['courseName']
        course_data.position = course['coursePosition']
        course_data.start_date = course['courseStartDate']
        course_data.end_date = course['courseEndDate']
        course_data.select_start_date = course['courseSelectStartDate']
        course_data.select_end_date = course['courseSelectEndDate']
        course_data.cancel_end_date = course['courseCancelEndDate']
        if datetime.datetime.now() > datetime.datetime.strptime(course_data.select_end_date, '%Y-%m-%d %H:%M:%S'):
            continue
        course_data.current_count = course['courseCurrentCount']
        course_data.max_count = course['courseMaxCount']
        course_data.selected = course['selected']
        course_data.sync_model()
        if course_data.is_select_start_date_changed():
            __add_rush_job(context.job_queue, course_data.id,
                           datetime.datetime.strptime(course_data.select_start_date, '%Y-%m-%d %H:%M:%S'))
        if not course_data.is_notified():
            message = course_data.get_info(is_detail="no", title='【新的博雅】')
            reply_markup = course_data.get_reply_markup("no")
            try:
                await context.bot.send_message(
                    config.get('telegram_owner_id'), message, reply_markup=reply_markup)
                course_data.set_notified(True)
            except:
                # retry in 10 seconds
                for job in context.job_queue.get_jobs_by_name('refresh_retry'):
                    job.schedule_removal()  # prevent job blood
                context.job_queue.run_once(refresh_course_list, 10, name='refresh_retry')


async def wait_for_others_cancellation(context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        courses = session.query(Course).filter(Course.status == Course.STATUS_WAITING).all()
        for course in courses:
            course_id = course.id
            if course.select_end_date > datetime.datetime.now():
                try:
                    await client.chose_course(course_id)
                    course.status = Course.STATUS_SELECTED
                    session.commit()
                    keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {course_id}'),
                                 InlineKeyboardButton("我要退课", callback_data=f'cancel {course_id} no')]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(config.get('telegram_owner_id'), f"【补选成功】\n{course.name}",
                                                   reply_markup=reply_markup)
                except ApiException:
                    if course.cancel_end_date < datetime.datetime.now():
                        course.status = Course.STATUS_NOT_SELECTED
                        session.commit()
                        keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {course_id}'),
                                     InlineKeyboardButton("我要选课", callback_data=f'choose {course_id} no')]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await context.bot.send_message(config.get('telegram_owner_id'), f"【补选失败】\n{course.name}",
                                                       reply_markup=reply_markup)
            else:
                course.status = Course.STATUS_NOT_SELECTED
                session.commit()
                keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {course_id}'),
                             InlineKeyboardButton("我要选课", callback_data=f'choose {course_id} no')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(config.get('telegram_owner_id'), f"【补选失败】\n{course.name}",
                                               reply_markup=reply_markup)


def __add_rush_job(job_queue, course_id, select_start_date):
    job_name = f'rush_select_{course_id}'
    for exist in job_queue.get_jobs_by_name(job_name):
        exist.schedule_removal()
    select_date = select_start_date - datetime.timedelta(seconds=60)
    if datetime.datetime.now() > select_date:
        job_queue.run_once(rush_select, 0, name=job_name, data=course_id, job_kwargs={
            'misfire_grace_time': None  # no matter how late, run it immediately
        })
    else:
        job_queue.run_once(rush_select, select_date, name=job_name, data=course_id, job_kwargs={
            'misfire_grace_time': None  # no matter how late, run it immediately
        })


async def __rush_select_one(course_id, finish_event: asyncio.Future):
    try:
        result = await client.chose_course(course_id)
        print(result)
        if not finish_event.done():
            finish_event.set_result(True)
    except AlreadyChosen as e:
        print(e)
        if not finish_event.done():
            finish_event.set_result(True)
    except CourseIsFull as e:
        print(e)
        if not finish_event.done():
            finish_event.set_exception(e)
    except Exception as e:
        print(e)
        pass


async def __rush_select_generator(course_id,
                                  select_start_date: datetime.datetime,
                                  finish_event: asyncio.Future):
    TIMEOUT = datetime.timedelta(seconds=30)
    now = datetime.datetime.now()
    select_date = select_start_date - datetime.timedelta(seconds=10)
    if now < select_date:
        await asyncio.sleep((select_date - now).total_seconds())
    while not finish_event.done() and datetime.datetime.now() < select_start_date + TIMEOUT:
        asyncio.create_task(__rush_select_one(course_id, finish_event))
        await asyncio.sleep(0.5)
    if not finish_event.done():
        finish_event.set_exception(TimeoutError())


async def rush_select(context: ContextTypes.DEFAULT_TYPE):
    course_id = context.job.data
    with Session(engine) as session:
        course = session.query(Course).filter(Course.id == course_id).scalar()
        if course.status != Course.STATUS_BOOKED:
            return
        await context.bot.send_message(config.get('telegram_owner_id'), f"【抢选即将开始】\n{course.name}")
        select_start_date = course.select_start_date
        finish_event = asyncio.Future()
        asyncio.create_task(__rush_select_generator(course_id, select_start_date, finish_event))
        try:
            await finish_event
            finish_event.result()
            course.status = Course.STATUS_SELECTED
            session.commit()
            keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {course_id}'),
                         InlineKeyboardButton("我要退课", callback_data=f'cancel {course_id} no')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(config.get('telegram_owner_id'), f"【抢选成功】\n{course.name}",
                                           reply_markup=reply_markup)
        except CourseIsFull:
            course.status = Course.STATUS_WAITING
            session.commit()
            keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {course_id}'),
                         InlineKeyboardButton("我要退课", callback_data=f'cancel {course_id} no')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(config.get('telegram_owner_id'),
                                           f"【抢选失败：课程已满】\n{course.name}\n已自动进入补选模式",
                                           reply_markup=reply_markup)
        except TimeoutError:
            course.status = Course.STATUS_WAITING
            session.commit()
            keyboard = [[InlineKeyboardButton("查看详情", callback_data=f'detail {course_id}'),
                         InlineKeyboardButton("我要退课", callback_data=f'cancel {course_id} no')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(config.get('telegram_owner_id'),
                                           f"【抢选失败：超时】\n{course.name}\n已自动进入补选模式",
                                           reply_markup=reply_markup)


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
    application.job_queue.run_repeating(refresh_course_list, 300, first=10, name='refresh')
    application.job_queue.run_repeating(wait_for_others_cancellation, 30, first=10, name='wait_for_others_cancellation')

    with Session(engine) as session:
        courses = session.query(Course).filter(Course.status == Course.STATUS_BOOKED).all()
        for course in courses:
            __add_rush_job(application.job_queue, course.id, course.select_start_date)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, ApiException):
        await context.bot.send_message(config.get('telegram_owner_id'),
                                       f"【与博雅服务器交互时发生错误】\n{context.error}")
    elif not isinstance(context.error, TelegramError):
        await context.bot.send_message(config.get('telegram_owner_id'),
                                       f"【未知错误】\n{context.error}")


if __name__ == '__main__':
    application_builder = ApplicationBuilder()
    application_builder.defaults(Defaults(block=False, parse_mode='HTML'))
    application_builder.token(config.get('telegram_token'))
    if config.get('proxy_url'):
        application_builder.proxy_url(config.get('proxy_url'))
    application = application_builder.build()

    init_handlers(application)
    init_jobs(application)
    application.add_error_handler(error_handler)

    application.run_polling()
