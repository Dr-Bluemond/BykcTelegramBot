class ApiException(Exception):
    """
    调用API时出现错误
    """
    pass


class LoginExpired(ApiException):
    """
    登录过期:通常重新登陆即可
    """
    pass


class LoginError(ApiException):
    """
    严重错误:登录失败
    """
    pass


class AlreadyChosen(ApiException):
    """
    已报名过该课程，请不要重复报名
    """


class FailedToChoose(ApiException):
    """
    选课失败，该课程不可选择
    """


class CourseIsFull(ApiException):
    """
    选课失败，该课程已满
    """


class TooEarlyToChoose(ApiException):
    """
    选课时间未到
    """


class FailedToDelChosen(ApiException):
    """
    退选失败，未找到退选课程或已超过退选时间
    """


class UnknownError(ApiException):
    """
    未知错误
    """
