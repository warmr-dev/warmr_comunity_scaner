Нужно разработать систему для автоматического поиска и сбора данных о профессиональных сообществах.

Что система делает:

Генерирует сотни поисковых запросов по заданным параметрам: география, ниша, аудитория, тип сообщества.
Получает результаты поисковой выдачи, находит сайты потенциальных сообществ.
Парсит публичные страницы и собирает: название, сайт, нишу, аудиторию, ссылку на вступление, цену, размер и контакты.
Удаляет дубли и нерелевантные результаты.
Классифицирует сообщества: Join, Apply, Watch, Reject.
Выгружает чистые данные в Google Sheets, Airtable или базу данных.
Запускается регулярно и добавляет только новые/изменённые сообщества.


Ключевое ограничение: не строить решение на прямом массовом скрейпинге Google.
Поиск использовать для discovery через API и/или SearXNG, а основной парсинг выполнять по публичным сайтам найденных сообществ.

Полезные ссылки:

SearXNG - GitHub
SearXNG - документация
Google Custom Search JSON API
Playwright
Scrapy


Ожидаемый результат: поддерживаемый pipeline, который еженедельно находит тысячи уникальных релевантных сообществ с минимальной ручной проверкой.playwright.devFast and reliable end-to-end testing for modern web apps | PlaywrightWeb automation and testing for apps, scripts, and AI agentsScrapyScrapy — open source web scraping framework for PythonScrapy is the leading open source Python framework for web scraping — fast, asynchronous, extensible, and BSD-licensed. Trusted by millions of developers.
