# Kino

[English](#english) · [Русский](#русский)

**[Website](https://idlorem.github.io/kino/) · [Сайт](https://idlorem.github.io/kino/ru.html)**

[![Kino](docs/images/kino-library.jpg)](https://idlorem.github.io/kino/)

## English

A catalog for your local movies and series on Windows, with an Android TV and phone client that streams from the PC.

### Features

- Catalog of your media folders with posters, descriptions, genres, countries and ratings (IMDb first, then Kinopoisk, TMDB, Letterboxd)
- Tabs Not watched, Watchlist and Watched, filters by type and genre, sorting, search
- Watchlist with title search and import from a Letterboxd profile
- Pin, hide, mark as watched; right-click menus on cards and posters; choose a poster source or remove it; fix a wrong match
- Russian and English interface with metadata in your language: Kinopoisk for Russian, OMDb and IMDb for English
- Open the library of another PC on your network, or from anywhere through the built-in AmneziaWG VPN
- Android TV and phone app: the same catalog, audio and subtitle selection, resume where you stopped, watched marks
- Updates from GitHub releases, minimize to tray

### Install

1. Download `installer.exe` from [Releases](../../releases/latest) and run it.
2. On first launch pick your media folder and a language.
3. API keys are optional: [Kinopoisk Unofficial](https://kinopoiskapiunofficial.tech) for Russian and [OMDb](https://www.omdbapi.com/apikey.aspx) for English make matching faster and more precise. IMDb ratings are filled in even without a key.

### Android TV and phone

1. In Kino open Settings, TV access, and turn on the server. A PIN is optional.
2. Install `kino.apk` from [Releases](../../releases/latest) on the TV or phone.
3. Open the app, pick your PC or enter its address, enter the PIN.

If Windows asks, allow Kino through the firewall on private networks. Audio that the device cannot decode (like DTS) is converted or skipped automatically.

### Library of another PC

Turn on the server in Kino on the PC that holds the films, then on the second PC press the PC button in the toolbar and pick the computer or enter its address and PIN. Kino can reconnect to it automatically on startup (the Auto connect switch). Pins, hidden and watched marks stay on the viewing PC and never change the library at home.

### Over the internet with VPN

Kino has a built-in AmneziaWG client, so no extra VPN app is needed.

1. Export a config from Amnezia in the AmneziaWG native format (a `.conf` file).
2. In the remote library window pick the file under VPN (AmneziaWG) or paste the text, and turn on Connect through VPN.
3. Enter the address of the PC inside your home network, like `192.168.0.10:8765`, and its PIN.

The VPN is used only to reach the other PC. Posters are loaded through it too.

### Letterboxd watchlist

Settings, Letterboxd, enter your username. The watchlist must be public.

## Русский

Каталог локальных фильмов и сериалов для Windows и клиент для Android TV и телефона, который показывает фильмы с компьютера.

### Возможности

- Каталог ваших папок с постерами, описаниями, жанрами, странами и рейтингами (сначала IMDb, затем Кинопоиск, TMDB, Letterboxd)
- Вкладки «Не просмотрено», «Хочу посмотреть» и «Просмотрено», фильтры по типу и жанру, сортировка, поиск
- Список «Хочу посмотреть» с поиском по названию и импортом из профиля Letterboxd
- Закрепить, скрыть, отметить просмотренным; меню по правой кнопке на карточках и постерах; выбор источника постера или его удаление; исправление неверного совпадения
- Интерфейс на русском и английском, метаданные на вашем языке: Кинопоиск для русского, OMDb и IMDb для английского
- Библиотека другого компьютера в сети или из любой точки через встроенный VPN AmneziaWG
- Приложение для Android TV и телефона: тот же каталог, выбор аудио и субтитров, продолжение с места остановки, отметки просмотра
- Обновления из релизов GitHub, сворачивание в трей

### Установка

1. Скачайте `installer.exe` из [Releases](../../releases/latest) и запустите его.
2. При первом запуске выберите папку с фильмами и язык.
3. Ключи API необязательны: [Кинопоиск Unofficial](https://kinopoiskapiunofficial.tech) для русского и [OMDb](https://www.omdbapi.com/apikey.aspx) для английского делают поиск быстрее и точнее. Рейтинг IMDb подтягивается и без ключа.

### Android TV и телефон

1. В Kino откройте «Настройки», «Доступ с телевизора» и включите сервер. PIN необязателен.
2. Установите `kino.apk` из [Releases](../../releases/latest) на ТВ или телефон.
3. Откройте приложение, выберите компьютер или введите его адрес, введите PIN.

Если Windows спросит, разрешите Kino в брандмауэре для частной сети. Звук, который устройство не может декодировать (например, DTS), конвертируется или пропускается автоматически.

### Библиотека другого компьютера

Включите сервер в Kino на компьютере с фильмами, а на втором нажмите кнопку «Другой ПК» на панели, выберите компьютер или введите его адрес и PIN. Kino может подключаться к нему сам при запуске (переключатель «Автоподключение»). Закрепления, скрытые и просмотренные хранятся на том компьютере, где вы смотрите, и не меняют библиотеку дома.

### Через интернет по VPN

В Kino встроен клиент AmneziaWG, отдельное приложение VPN не нужно.

1. Экспортируйте конфиг из Amnezia в формате AmneziaWG native (файл `.conf`).
2. В окне удалённой библиотеки в блоке «VPN (AmneziaWG)» выберите файл или вставьте текст и включите «Подключаться через VPN».
3. Введите адрес компьютера в домашней сети, например `192.168.0.10:8765`, и PIN.

VPN используется только для доступа к другому компьютеру. Постеры тоже грузятся через него.

### Список Letterboxd

«Настройки», Letterboxd, введите ник. Список должен быть открыт для всех.
