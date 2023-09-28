class BadHTTPStatusError(Exception):
    """При обработке статус-кода запроса возникла ошибка"""


class BadRequestError(Exception):
    """При обработке вашего запроса произошло неоднозначное исключение."""


class HomeworkError(Exception):
    """При обработке параметров домашнего задания возникло неоднозначное исключение"""
