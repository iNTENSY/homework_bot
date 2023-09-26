import logging
import os
import sys
import time
from http import HTTPStatus
from typing import Dict

import requests
import telegram

from dotenv import load_dotenv

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

EXCEPTION_MESSAGES: Dict[str, str] = {
    'token_not_found': 'Отсутствует обязательная переменная окружения: "{}"',
    'endpoint_denied': ('Сбой в работе программы: '
                        f'Эндпоинт [{ENDPOINT}]{ENDPOINT} недоступен'),
    'bad_response_format': 'Неверный формат данных "response"',
    'bad_homework_format': 'Неверный формат данных "homework"',
    'missing_homework': 'Отсутствует ключ "homework"',
    'has_not_homework': 'Отсутствует домашняя работа',
    'bad_verdict_status': ('Полученный статус не входит '
                           'в список ожидаемых в HOMEWORK_VERDICTS'),
    'server_error': 'Сбой в работе программы'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens():
    """
    Данная функция проверяет наличие токенов.
    К списку относится PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID.
    В случае их отсутствия - программа завершает свое выполнение.
    """
    logging.debug('Проверка наличия требуемых токенов...')

    for param in (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID):
        if not param:
            logging.critical(
                EXCEPTION_MESSAGES['token_not_found'].format(param)
            )
    if not all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)):
        exit('Программа принудительно остановлена.')


def send_message(bot: telegram.Bot, message: str) -> None:
    """Данная функция выполняет отправку сообщений пользователю."""
    exception_message: str = ('Бот отправил сообщение '
                              f'{EXCEPTION_MESSAGES["endpoint_denied"]}')
    default_chat_message: str = ('Бот успешно отправил '
                                 f'сообщение {message} пользователю с '
                                 f'ID: {TELEGRAM_CHAT_ID}')

    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                         text=message)
    except telegram.TelegramError:
        logger.error(exception_message)
        bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                         text=EXCEPTION_MESSAGES['endpoint_denied'])
        logger.debug(exception_message)
    else:
        logger.debug(default_chat_message)


def get_api_answer(timestamp):
    """Данная функция выполняет проверку статус-кода запроса к ENDPOINT."""
    params: Dict[str, int] = {'from_date': timestamp}
    try:
        response = requests.get(url=ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != HTTPStatus.OK:
            raise requests.exceptions.HTTPError(
                EXCEPTION_MESSAGES['endpoint_denied']
            )
    except requests.exceptions.HTTPError as http_error:
        logger.error(http_error)
        raise TypeError(http_error)
    except requests.RequestException as error:
        logger.error(error)
        raise TypeError(error)
    else:
        return response.json()


def check_response(response):
    """
    Данная функция проверяет ответ (response) на требуемых тип данных.
    Далее проверяется наличие ключа "homeworks" и его тип данных
    Функция возвращает первый элемент в списке "homeworks"
    """
    if not isinstance(response, dict):
        logger.error(EXCEPTION_MESSAGES['bad_response_format'])
        raise TypeError(EXCEPTION_MESSAGES['bad_response_format'])

    homeworks = response.get('homeworks')

    if homeworks is None:
        logger.error(EXCEPTION_MESSAGES['missing_homework'])
        raise TypeError(EXCEPTION_MESSAGES['missing_homework'])
    if not isinstance(homeworks, list):
        logger.error(EXCEPTION_MESSAGES['bad_homework_format'])
        raise TypeError(EXCEPTION_MESSAGES['bad_homework_format'])
    return homeworks[0]


def parse_status(homework):
    """
    Данная функция обрабатывает статус-код домашней работы (далее ДР).
    В случае, когда отсутствует название или статус
    ДР - выбрасывается исключения. Функция возвращает
    строку с вердиктом по ДР.
    """
    logger.debug(f'Обработка данных: {homework}')

    homework_name = homework.get('homework_name')
    current_status = homework.get('status')

    if not homework_name:
        raise KeyError(EXCEPTION_MESSAGES['has_not_homework'])

    if current_status not in HOMEWORK_VERDICTS:
        raise NameError(EXCEPTION_MESSAGES['bad_status'])

    verdict = HOMEWORK_VERDICTS.get(current_status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()

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

        except IndexError:
            message = 'Статус домашней работы не изменился!'
            send_message(bot, message)
            logging.info(message)
        except Exception:
            send_message(bot, EXCEPTION_MESSAGES['server_error'])
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
