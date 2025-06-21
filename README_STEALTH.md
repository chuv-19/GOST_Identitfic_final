# 🕵️ Руководство по обходу детекции автоматизации GARANT

## Обзор проблемы

Современные веб-сайты используют сложные системы для обнаружения автоматизированного трафика. Сайт ГАРАНТ может использовать следующие методы детекции:

1. **Анализ User-Agent** - проверка строки браузера
2. **JavaScript детекция** - проверка `navigator.webdriver`
3. **Поведенческий анализ** - анализ паттернов кликов и движений мыши
4. **TLS отпечатки** - анализ SSL/TLS рукопожатий
5. **IP-адреса** - блокировка datacenter IP
6. **HTTP заголовки** - анализ порядка и значений заголовков

## 🛡️ Комплексная стратегия обхода

### 1. Использование специализированных библиотек

#### selenium-stealth
```bash
pip install selenium-stealth
```

Основные возможности:
- Скрывает `navigator.webdriver`
- Подделывает WebGL отпечатки
- Нормализует JavaScript API
- Исправляет Canvas отпечатки

#### undetected-chromedriver
```bash
pip install undetected-chromedriver
```

Преимущества:
- Автоматические патчи ChromeDriver
- Удаление automation flags
- Обход CDP (Chrome DevTools Protocol) детекции

### 2. Ротация User-Agent

Используйте реальные User-Agent строки от популярных браузеров:

```python
user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]
```

### 3. Настройки браузера для стелс

```python
chrome_options = Options()

# Основные флаги анти-детекции
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)

# Дополнительные настройки
chrome_options.add_argument("--disable-plugins-discovery")
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-default-apps")
chrome_options.add_argument("--disable-sync")
chrome_options.add_argument("--no-first-run")
chrome_options.add_argument("--no-default-browser-check")
chrome_options.add_argument("--disable-web-security")
chrome_options.add_argument("--disable-features=TranslateUI")
```

### 4. JavaScript патчи

Выполните эти скрипты после загрузки страницы:

```javascript
// Скрываем navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Подделываем plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Подделываем languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['ru-RU', 'ru', 'en-US', 'en'],
});

// Подделываем screen properties
Object.defineProperty(screen, 'colorDepth', {
    get: () => 24,
});
```

### 5. Симуляция человеческого поведения

#### Случайные движения мыши
```python
def simulate_mouse_movements(driver):
    actions = ActionChains(driver)
    for _ in range(random.randint(1, 3)):
        x_offset = random.randint(-100, 100)
        y_offset = random.randint(-100, 100)
        actions.move_by_offset(x_offset, y_offset)
        actions.perform()
        time.sleep(random.uniform(0.1, 0.5))
```

#### Человекоподобные клики
```python
def human_like_click(driver, element):
    # Прокрутка к элементу
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(random.uniform(0.3, 0.8))
    
    # Движение к элементу с небольшим смещением
    actions = ActionChains(driver)
    actions.move_to_element(element)
    x_offset = random.randint(-3, 3)
    y_offset = random.randint(-3, 3)
    actions.move_by_offset(x_offset, y_offset)
    
    # Пауза перед кликом
    time.sleep(random.uniform(0.1, 0.4))
    actions.click()
    actions.perform()
```

#### Случайные прокрутки
```python
def simulate_scrolling(driver):
    scroll_steps = random.randint(3, 8)
    for _ in range(scroll_steps):
        scroll_amount = random.randint(200, 600)
        driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        time.sleep(random.uniform(0.8, 2.0))
```

### 6. Использование прокси

#### Residential прокси (рекомендуется)
```python
# Список residential прокси
proxies = [
    "residential-proxy1.com:8080",
    "residential-proxy2.com:8080",
]

# Установка прокси
chrome_options.add_argument(f"--proxy-server={random.choice(proxies)}")
```

#### Ротация IP адресов
- Меняйте IP каждые 5-10 запросов
- Используйте прокси из разных стран/регионов
- Избегайте datacenter IP адресов

### 7. Временные задержки

#### Рандомные паузы
```python
# Между запросами
time.sleep(random.uniform(3.0, 8.0))

# Перед кликами
time.sleep(random.uniform(0.5, 2.0))

# После загрузки страницы
time.sleep(random.uniform(2.0, 4.0))
```

#### Перерывы в сессии
```python
# Перезапуск драйвера каждые N запросов
if request_count % 5 == 0:
    driver.quit()
    time.sleep(random.uniform(5.0, 15.0))
    driver = setup_new_driver()
```

### 8. Настройки профиля браузера

```python
prefs = {
    "profile.default_content_setting_values.notifications": 2,
    "profile.default_content_settings.popups": 0,
    "profile.managed_default_content_settings.images": 2,  # Отключаем изображения
    "profile.default_content_setting_values.cookies": 1,
    "profile.default_content_setting_values.javascript": 1,
    "profile.password_manager_enabled": False,
    "credentials_enable_service": False,
}
chrome_options.add_experimental_option("prefs", prefs)
```

## 🔧 Практическая реализация

### Базовый пример

```python
from garant_stealth_checker import StealthGarantChecker
from references_extractor import Reference

# Создание проверщика с максимальными настройками стелс
checker = StealthGarantChecker(
    headless=False,  # Лучше использовать видимый браузер
    use_stealth=True,  # Включить selenium-stealth
    use_undetected_chrome=True,  # Использовать undetected-chromedriver
    use_proxies=True,  # Включить прокси
    proxy_list=["proxy1:port", "proxy2:port"]
)

# Создание ссылки для проверки
ref = Reference(
    number="123-ФЗ",
    date="01.01.2024",
    title="Тестовый закон"
)

# Проверка документа
result = checker.check_document(ref)
print(result)
```

### Продвинутый пример с обработкой ошибок

```python
def advanced_check(refs: List[Reference]):
    checker = StealthGarantChecker(
        headless=False,
        use_stealth=True,
        use_undetected_chrome=True,
        use_proxies=True,
        proxy_list=load_proxy_list()
    )
    
    results = {}
    
    for i, ref in enumerate(refs):
        try:
            # Случайная пауза между проверками
            if i > 0:
                time.sleep(random.uniform(5.0, 15.0))
            
            result = checker.check_document(ref)
            
            # Проверяем, не заблокированы ли мы
            if result.get("статус") == "заблокировано":
                print("🚫 Обнаружена блокировка, меняем стратегию...")
                checker = reinitialize_checker_with_new_settings()
                continue
            
            results[f"ref_{i}"] = result
            
            # Периодический перезапуск
            if i > 0 and i % 3 == 0:
                print("🔄 Перезапуск для сброса отпечатков...")
                del checker
                time.sleep(random.uniform(10.0, 20.0))
                checker = StealthGarantChecker(...)
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            results[f"ref_{i}"] = {"статус": "ошибка", "описание": str(e)}
    
    return results
```

## 🚨 Важные рекомендации

### Что ДЕЛАТЬ:
1. ✅ Используйте residential прокси
2. ✅ Варьируйте время между запросами (3-15 секунд)
3. ✅ Периодически перезапускайте браузер
4. ✅ Используйте реальные User-Agent строки
5. ✅ Симулируйте человеческое поведение
6. ✅ Обрабатывайте ошибки и блокировки
7. ✅ Мониторьте успешность запросов

### Что НЕ ДЕЛАТЬ:
1. ❌ Не используйте datacenter прокси
2. ❌ Не делайте слишком быстрые запросы
3. ❌ Не используйте одинаковые паттерны поведения
4. ❌ Не игнорируйте CAPTCHA и блокировки
5. ❌ Не используйте устаревшие User-Agent
6. ❌ Не запускайте много параллельных сессий с одного IP

## 🛠️ Установка зависимостей

```bash
# Основные зависимости
pip install selenium selenium-stealth undetected-chromedriver

# Дополнительные инструменты
pip install requests fake-useragent

# Для работы с прокси
pip install requests[socks]
```

## 🔍 Тестирование настроек

Используйте эти сайты для проверки эффективности ваших настроек:

1. **bot.incolumitas.com** - комплексная проверка на ботов
2. **intoli.com/blog/not-possible-to-block-chrome-headless** - проверка headless детекции  
3. **deviceandbrowserinfo.com** - анализ отпечатков браузера
4. **whoer.net** - проверка прокси и анонимности

### Пример тестирования:

```python
def test_stealth_setup():
    checker = StealthGarantChecker(use_stealth=True, use_undetected_chrome=True)
    
    # Тест на bot.incolumitas.com
    checker.driver = checker._setup_stealth_chrome()
    checker._apply_stealth_techniques(checker.driver)
    
    checker.driver.get("https://bot.incolumitas.com/")
    time.sleep(5)
    
    # Проверяем результаты
    page_source = checker.driver.page_source
    if "You are NOT a bot" in page_source:
        print("✅ Стелс настройки работают!")
    else:
        print("❌ Обнаружена bot активность")
    
    checker.driver.quit()
```

## 📊 Мониторинг эффективности

```python
def monitor_success_rate(results):
    total = len(results)
    blocked = sum(1 for r in results.values() if r.get("статус") == "заблокировано")
    errors = sum(1 for r in results.values() if r.get("статус") == "ошибка")
    successful = total - blocked - errors
    
    print(f"📊 Статистика:")
    print(f"Всего запросов: {total}")
    print(f"Успешных: {successful} ({successful/total*100:.1f}%)")
    print(f"Заблокированных: {blocked} ({blocked/total*100:.1f}%)")
    print(f"Ошибок: {errors} ({errors/total*100:.1f}%)")
    
    # Если успешность < 80%, нужно менять стратегию
    if successful/total < 0.8:
        print("⚠️ Низкая успешность - требуется оптимизация настроек")
```

## 🔄 Адаптивная стратегия

```python
class AdaptiveStealthChecker:
    def __init__(self):
        self.success_rate = 1.0
        self.blocked_count = 0
        
    def adjust_strategy(self):
        if self.success_rate < 0.7:
            # Более агрессивные настройки стелс
            return {
                "longer_delays": True,
                "more_mouse_movements": True,
                "frequent_restarts": True,
                "change_proxy": True
            }
        elif self.blocked_count > 3:
            # Смена IP и длительная пауза
            return {
                "change_ip": True,
                "long_pause": random.uniform(300, 600)  # 5-10 минут
            }
        return {}
```

Этот комплексный подход поможет максимально эффективно обходить системы детекции автоматизации на сайте ГАРАНТ! 