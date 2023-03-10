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
        self.__is_notified = None
        self.__status = None

    def sync_model(self):
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
                self.__is_notified = False
                self.__status = status
                session.add(course)
                session.commit()
            else:
                course.name = self.name
                course.start_date = start_date
                course.end_date = end_date
                course.select_start_date = select_start_date
                course.select_end_date = select_end_date
                course.cancel_end_date = cancel_end_date
                if self.selected and course.status != Course.STATUS_SELECTED:
                    course.status = Course.STATUS_SELECTED
                    session.commit()
                elif not self.selected and course.status == Course.STATUS_SELECTED:
                    course.status = Course.STATUS_NOT_SELECTED
                    session.commit()
                self.__is_notified = course.notified
                self.__status = course.status
            self.__model_synced = True

    def is_notified(self):
        if not self.__model_synced:
            self.sync_model()
        return self.__is_notified

    def set_notified(self, value):
        self.__is_notified = value
        with Session(engine) as session:
            stmt = select(Course).where(Course.id == self.id)
            course: Course = session.execute(stmt).scalar()
            course.notified = value
            session.commit()

    def get_status(self):
        if not self.__model_synced:
            self.sync_model()
        return self.__status

    def get_info(self, is_detail, title=None):
        if not self.__model_synced:
            self.sync_model()
        if self.__status == Course.STATUS_NOT_SELECTED:
            status = "???????????????"
        elif self.__status == Course.STATUS_SELECTED:
            status = "?????????????"
        elif self.__status == Course.STATUS_BOOKED:
            status = "??????????????????"
        elif self.__status == Course.STATUS_WAITING:
            status = "????????????????"
        else:
            status = "????????????"

        if is_detail == "no":
            return (f"{title}\n" if title else "") + \
                f"ID???{self.id}\n" \
                f"?????????{self.name}\n" \
                f"?????????{self.position}\n" \
                f"???????????????{self.start_date}\n" \
                f"???????????????{self.end_date}\n" \
                f"?????????{self.current_count}/{self.max_count}\n" \
                f"?????????{status}\n"
        else:
            return (f"{title}\n" if title else "??????????????????") + \
                f"ID???{self.id}\n" \
                f"?????????{self.name}\n" \
                f"?????????{self.teacher}\n" \
                f"?????????{self.position}\n" \
                f"???????????????{self.start_date}\n" \
                f"???????????????{self.end_date}\n" \
                f"???????????????{self.select_start_date}\n" \
                f"???????????????{self.select_end_date}\n" \
                f"???????????????{self.cancel_end_date}\n" \
                f"?????????{self.current_count}/{self.max_count}\n" \
                f"???????????????\n{self.description}\n" \
                f"?????????{status}\n"

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
            keyboard.append(InlineKeyboardButton("????????????", callback_data=f'detail {self.id}'))
        if self.get_status() == Course.STATUS_NOT_SELECTED:
            keyboard.append(InlineKeyboardButton("????????????", callback_data=f'choose {self.id} {is_detail}'))
        else:
            keyboard.append(InlineKeyboardButton("????????????", callback_data=f'cancel {self.id} {is_detail}'))
        keyboard = [keyboard]
        return InlineKeyboardMarkup(keyboard)


### callbacks ###

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"handler called: start")
    message = "?????????~???????????????????????????????????????????????????????????????????????????\n" \
              "/query_avail ??????????????????\n\n" \
              "/query_chosen ??????????????????\n\n" \
              "/preferences ??????????????????\n\n" \
              "/status ??????????????????????????????"
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
        await update.message.reply_text("????????????")


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
        await update.message.reply_text("????????????")


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
        context.application.create_task(query.answer("????????????"))
        current_count = resp['courseCurrentCount']
    except TooEarlyToChoose:
        with Session(engine) as session:
            course = session.query(Course).filter(Course.id == course_id).first()
            course.status = Course.STATUS_BOOKED
            session.commit()
            __add_rush_job(context.job_queue, course)
            context.application.create_task(query.answer("?????????????????????????????????"))
    except CourseIsFull:
        with Session(engine) as session:
            course = session.query(Course).filter(Course.id == course_id).first()
            if course.cancel_end_date > datetime.datetime.now() and course.select_end_date > datetime.datetime.now():
                course.status = Course.STATUS_WAITING
                session.commit()
                context.application.create_task(query.answer("?????????????????????????????????"))
            else:
                context.application.create_task(query.answer("???????????????????????????"))
    except AlreadyChosen:
        context.application.create_task(query.answer("????????????:?????????????????????"))
    except FailedToChoose as e:
        context.application.create_task(query.answer("????????????:" + str(e)))
    except ApiException:
        context.application.create_task(query.message.reply_text("????????????:????????????"))
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
        context.application.create_task(query.answer("????????????"))
    except FailedToDelChosen as e:
        context.application.create_task(query.answer("????????????:" + str(e)))
    course_data = ReceivedCourseData()
    course_data.id = course_id
    await course_data.refresh()
    course_data.current_count = current_count
    message = course_data.get_info(is_detail=is_detail)
    reply_markup = course_data.get_reply_markup(is_detail)
    context.application.create_task(update.callback_query.message.edit_text(message, reply_markup=reply_markup))


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject the current user"""
    await update.message.reply_text(f"??????id???{update.effective_user.id}???????????????????????????????????????\n"
                                    f"????????????????????????????????????config.json???????????????id???")


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
        if not course_data.is_notified():
            message = course_data.get_info(is_detail="no", title='??????????????????')
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
                    keyboard = [[InlineKeyboardButton("????????????", callback_data=f'detail {course_id}'),
                                 InlineKeyboardButton("????????????", callback_data=f'cancel {course_id} no')]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(config.get('telegram_owner_id'), f"??????????????????\n{course.name}",
                                                   reply_markup=reply_markup)
                except ApiException:
                    if course.cancel_end_date < datetime.datetime.now():
                        course.status = Course.STATUS_NOT_SELECTED
                        session.commit()
                        keyboard = [[InlineKeyboardButton("????????????", callback_data=f'detail {course_id}'),
                                     InlineKeyboardButton("????????????", callback_data=f'choose {course_id} no')]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await context.bot.send_message(config.get('telegram_owner_id'), f"??????????????????\n{course.name}",
                                                       reply_markup=reply_markup)
            else:
                course.status = Course.STATUS_NOT_SELECTED
                session.commit()
                keyboard = [[InlineKeyboardButton("????????????", callback_data=f'detail {course_id}'),
                             InlineKeyboardButton("????????????", callback_data=f'choose {course_id} no')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(config.get('telegram_owner_id'), f"??????????????????\n{course.name}",
                                               reply_markup=reply_markup)


def __add_rush_job(job_queue, course):
    select_start_date = course.select_start_date
    select_date = select_start_date - datetime.timedelta(seconds=10)
    if datetime.datetime.now() > select_date:
        job_queue.run_once(rush_select, 0, name=f'rush_select_{course.id}', data=course.id, job_kwargs={
            'misfire_grace_time': None  # no matter how late, run it immediately
        })
    else:
        job_queue.run_once(rush_select, select_date, name=f'rush_select_{course.id}', data=course.id, job_kwargs={
            'misfire_grace_time': None  # no matter how late, run it immediately
        })


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
                    keyboard = [[InlineKeyboardButton("????????????", callback_data=f'detail {course_id}'),
                                 InlineKeyboardButton("????????????", callback_data=f'cancel {course_id} no')]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(config.get('telegram_owner_id'), f"??????????????????\n{course.name}",
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
                    keyboard = [[InlineKeyboardButton("????????????", callback_data=f'detail {course_id}'),
                                 InlineKeyboardButton("????????????", callback_data=f'cancel {course_id} no')]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(config.get('telegram_owner_id'),
                                                   f"??????????????????\n{course.name}\n???????????????????????????",
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
    application.job_queue.run_repeating(refresh_course_list, 300, first=10, name='refresh')
    application.job_queue.run_repeating(wait_for_others_cancellation, 30, first=10, name='wait_for_others_cancellation')

    with Session(engine) as session:
        courses = session.query(Course).filter(Course.status == Course.STATUS_BOOKED).all()
        for course in courses:
            __add_rush_job(application.job_queue, course)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, ApiException):
        await context.bot.send_message(config.get('telegram_owner_id'),
                                       f"?????????????????????????????????????????????\n{context.error}")
    elif not isinstance(context.error, TelegramError):
        await context.bot.send_message(config.get('telegram_owner_id'),
                                       f"??????????????????\n{context.error}")


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
