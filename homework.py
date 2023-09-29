import logging
import os
import sys
import time
import requests
import telegram

from http import HTTPStatus
from typing import Dict
from dotenv import load_dotenv

from exceptions import BadHTTPStatusError, BadRequestError, HomeworkError

load_dotenv()

PRACTICUM_TOKEN: str = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID: str = os.getenv('CHAT_ID')

RETRY_PERIOD: int = 600
ENDPOINT: str = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS: Dict[str, str] = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS: Dict[str, str] = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

EXCEPTION_MESSAGES: Dict[str, str] = {
    'token_not_found': 'Отсутствует обязательная переменная окружения: "{}"',
    'endpoint_denied': ('Сбой в работе программы: '
                        f'Эндпоинт [{ENDPOINT}]{ENDPOINT} недоступен'),
    'bad_response_format': ('Неверный формат данных "response", '
                            'ожидался словарь'),
    'bad_homework_format': 'Неверный формат данных "homework"',
    'missing_homework': 'Отсутствует ключ "homework"',
    'has_not_homework': 'Отсутствует домашняя работа',
    'bad_verdict_status': ('Полученный статус не входит '
                           'в список ожидаемых в HOMEWORK_VERDICTS'),
    'server_error': 'Сбой в работе программы',
    'bad_request': 'При обработке вашего запроса '
                   'произошло неоднозначное исключение.',
    'base_message': ('HTTP Status: {}; '
                     'Parameters: {}; '
                     'Message: {}; '
                     'Response: {}')
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens() -> bool:
    """
    Данная функция проверяет наличие токенов.
    К списку относится PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID.
    В случае их отсутствия программа возвращает False, иначе True.
    """
    logging.debug('Проверка наличия требуемых токенов...')

    for param in (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID):
        if not param:
            logging.critical(
                EXCEPTION_MESSAGES['token_not_found'].format(param)
            )
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def send_message(bot: telegram.Bot, message: str) -> None:
    """Данная функция выполняет отправку сообщений пользователю."""
    exception_message: str = ('Бот не отправил сообщение: '
                              f'{EXCEPTION_MESSAGES["endpoint_denied"]}')
    default_chat_message: str = ('Бот успешно отправил '
                                 f'сообщение {message} пользователю с '
                                 f'ID: {TELEGRAM_CHAT_ID}')

    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                         text=message)
    except telegram.TelegramError:
        logger.error(exception_message)
    else:
        logger.debug(default_chat_message)


def get_api_answer(timestamp) -> dict:
    """Данная функция выполняет проверку статус-кода запроса к ENDPOINT."""
    params: Dict[str, str | dict] = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    try:
        response = requests.get(**params)
        if response.status_code != HTTPStatus.OK:
            raise BadHTTPStatusError(
                EXCEPTION_MESSAGES['base_message'].format(
                    response.status_code,
                    params,
                    EXCEPTION_MESSAGES['endpoint_denied'],
                    response
                )
            )
    except requests.RequestException as error:
        message = EXCEPTION_MESSAGES['base_message'].format(
            response.status_code,
            params,
            EXCEPTION_MESSAGES['endpoint_denied'],
            response
        )
        raise BadRequestError(message + f"Error: {error}")
    return response.json()


def check_response(response):
    """
    Данная функция проверяет ответ (response) на требуемых тип данных.
    Далее проверяется наличие ключа "homeworks" и его тип данных
    Функция возвращает первый элемент в списке "homeworks"
    """
    if not isinstance(response, dict):
        message = (EXCEPTION_MESSAGES['bad_response_format']
                   + f'| Вернулся: {type(response)} ')
        raise TypeError(message)

    homeworks = response.get('homeworks')

    if homeworks is None:
        raise HomeworkError(EXCEPTION_MESSAGES['missing_homework'])
    if not isinstance(homeworks, list):
        raise TypeError(EXCEPTION_MESSAGES['bad_homework_format'])
    return homeworks[0]


def parse_status(homework) -> str:
    """
    Данная функция обрабатывает статус-код домашней работы (далее ДР).
    В случае, когда отсутствует название или статус
    ДР - выбрасывается исключения. Функция возвращает
    строку с вердиктом по ДР.
    """
    logger.debug(f'Обработка данных: {homework}')

    homework_name: str = homework.get('homework_name')
    current_status: str = homework.get('status')

    if not homework_name:
        raise HomeworkError(EXCEPTION_MESSAGES['has_not_homework'])

    if current_status not in HOMEWORK_VERDICTS:
        raise HomeworkError(EXCEPTION_MESSAGES['bad_status'])

    verdict = HOMEWORK_VERDICTS.get(current_status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Программа принудительно остановлена')
        exit('Программа остановлена: Отсутствуют требуемые токены')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            request = get_api_answer(timestamp)
            response = check_response(request)

            if response:
                message_by_status = parse_status(response)
                send_message(bot, message_by_status)
                logger.info(message_by_status)
        except (BadRequestError,
                BadHTTPStatusError,
                HomeworkError,
                TypeError) as error:
            logger.error(error)
            send_message(bot, error)
        except IndexError:
            message = 'Статус домашней работы не изменился!'
            send_message(bot, message)
            logging.info(message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
