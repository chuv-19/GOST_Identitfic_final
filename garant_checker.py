import time
import re
import urllib.parse
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import concurrent.futures
import threading

from references_extractor import Reference
from garant_cache import GarantCache

class GarantChecker:
    """Проверка документов через систему ГАРАНТ"""
    
    def __init__(self, headless: bool = False, cache_db_path: str = "garant_cache.db", cache_ttl_hours: int = 24 * 7):
        # Используем SQLite-кеш для сохранения результатов
        self.headless = headless
        self.cache = GarantCache(cache_db_path, cache_ttl_hours)
        self.driver = None
        self.lock = threading.Lock()
        
    def _setup_driver(self):
        """Настройка Chrome WebDriver"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
    def _close_driver(self):
        """Закрытие WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def _wait_for_page_ready(self):
        """Ждет полной загрузки страницы и исчезновения модальных окон"""
        try:
            # Ждем пока исчезнут все маски
            WebDriverWait(self.driver, 10).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.x-mask'))
            )
        except:
            pass
        
        try:
            # Ждем пока исчезнут загрузочные индикаторы
            WebDriverWait(self.driver, 5).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.x-mask-loading'))
            )
        except:
            pass
        
        try:
            # Пытаемся закрыть любые модальные окна с помощью Escape
            from selenium.webdriver.common.keys import Keys
            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except:
            pass
        
        # Дополнительная пауза для стабилизации
        time.sleep(2)
    
    def _format_query(self, ref: Reference) -> str:
        """Форматирование запроса для поиска"""
        query_parts = []
        
        if ref.number:
            query_parts.append(f"№ {ref.number}")
        if ref.date:
            query_parts.append(f"от {ref.date}")
        if ref.title and not ref.number:
            # Если нет номера, используем название
            query_parts.append(ref.title[:50])
            
        return " ".join(query_parts)
    
    def check_document(self, ref: Reference) -> Dict[str, str]:
        """
        Проверка одного документа через ГАРАНТ с повторными попытками
        
        Args:
            ref: Reference объект с информацией о документе
            
        Returns:
            Dict с результатами проверки
        """
        max_chrome_retries = 3  # Максимум попыток для ошибок Chrome
        max_not_found_retries = 2  # Максимум попыток для случаев "не найден"
        chrome_retry_count = 0
        not_found_retry_count = 0
        
        while chrome_retry_count < max_chrome_retries:
            try:
                if not self.driver:
                    self._setup_driver()
                
                # Формируем поисковый запрос и кодируем его для URL
                query = self._format_query(ref)
                encoded_query = urllib.parse.quote(query)
                
                # Проверяем кеш перед запросом (thread-safe)
                with self.lock:
                    cached = self.cache.get_cached_result(query)
                    if cached:
                        cached["из_кеша"] = True
                        return cached
                
                # Переходим напрямую на страницу поиска с закодированным запросом
                search_url = f"https://ivo.garant.ru/#/basesearch/{encoded_query}/all:0"
                self.driver.get(search_url)
                
                # Ждем 2 секунды как указано в требованиях
                time.sleep(2)
                
                # Ждем появления результатов и кликаем на первый результат
                wait = WebDriverWait(self.driver, 15)  # Увеличиваем timeout
                
                try:
                    # Ждем загрузки результатов поиска
                    wait.until(
                        EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[2]/div[2]/div/div/div/div[2]/div/div/div[2]/div/div/div[4]/div/div/ul[1]/li[1]/a'))
                    )
                    
                    # Дополнительная пауза для полной загрузки
                    time.sleep(1)
                    
                    # Ждем исчезновения модальных окон и масок
                    try:
                        # Ждем пока исчезнут все маски и загрузочные индикаторы
                        self._wait_for_page_ready()
                    except:
                        pass  # Если маски нет, продолжаем
                    
                    # Кликаем на первый результат с улучшенной обработкой
                    result_link = wait.until(
                        EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[2]/div[2]/div/div/div/div[2]/div/div/div[2]/div/div/div[4]/div/div/ul[1]/li[1]/a'))
                    )
                    
                    # Извлекаем URL напрямую из ссылки и переходим к нему
                    try:
                        href = result_link.get_attribute('href')
                        if href:
                            print(f"✅ Найдена ссылка на документ: {href[:100]}...")
                            # Переходим напрямую по ссылке, минуя модальные окна
                            self.driver.get(href)
                            print("✅ Переход по прямой ссылке выполнен")
                        else:
                            # Если href пустой, пробуем JavaScript клик
                            print("🔄 Href пустой, пробуем JavaScript клик...")
                            self.driver.execute_script("arguments[0].click();", result_link)
                    except Exception as link_error:
                        print(f"🔄 Ошибка перехода по ссылке: {str(link_error)[:100]}...")
                        # Если не получилось, пробуем альтернативные методы
                        return self._try_alternative_click(wait, query, not_found_retry_count + 1)
                    
                    # Ждем загрузки страницы с документом
                    time.sleep(3)
                    
                    # Проверяем, что мы действительно перешли на новую страницу
                    current_url = self.driver.current_url
                    if "basesearch" in current_url:
                        # Документ не найден - пробуем еще раз
                        if not_found_retry_count < max_not_found_retries:
                            not_found_retry_count += 1
                            print(f"🔄 Документ не найден, попытка {not_found_retry_count}/{max_not_found_retries}: {ref.raw[:50]}...")
                            time.sleep(2)  # Пауза перед повторной попыткой
                            continue
                        else:
                            # Пробуем альтернативный способ клика
                            return self._try_alternative_click(wait, query, not_found_retry_count + 1)
                    
                    # Проверяем наличие message box и обрабатываем его
                    self._handle_message_box()
                    
                    # Извлекаем текст напрямую из указанного элемента
                    date_status = self._extract_document_info(ref)
                    
                    if date_status == "действительно":
                        # Если информация указывает на действительность документа
                        return self._cache_and_return(query, {
                            "источник": "ГАРАНТ",
                            "статус": "действительно",
                            "url": self.driver.current_url,
                            "запрос": query,
                            "метод_проверки": "извлечение_информации",
                            "попытки_chrome": chrome_retry_count + 1,
                            "попытки_поиска": not_found_retry_count + 1
                        })
                    
                    # Если информация не подтверждает действительность, анализируем содержимое страницы
                    page_source = self.driver.page_source.lower()
                    status = self._analyze_document_status(page_source)
                    
                    return self._cache_and_return(query, {
                        "источник": "ГАРАНТ",
                        "статус": status,
                        "url": self.driver.current_url,
                        "запрос": query,
                        "метод_проверки": "анализ_содержимого",
                        "попытки_chrome": chrome_retry_count + 1,
                        "попытки_поиска": not_found_retry_count + 1
                    })
                    
                except TimeoutException:
                    # Результат не найден - пробуем еще раз
                    if not_found_retry_count < max_not_found_retries:
                        not_found_retry_count += 1
                        print(f"🔄 Timeout при поиске, попытка {not_found_retry_count}/{max_not_found_retries}: {ref.raw[:50]}...")
                        time.sleep(2)  # Пауза перед повторной попыткой
                        continue
                    else:
                        return self._cache_and_return(query, {
                            "источник": "ГАРАНТ", 
                            "статус": "не найден",
                            "url": search_url,
                            "запрос": query,
                            "попытки_поиска": not_found_retry_count + 1
                        })
                        
            except Exception as e:
                error_message = str(e)
                print(f"⚠️  Ошибка: {error_message}")
                
                # Проверяем, является ли это ошибкой Chrome/сессии
                chrome_errors = [
                    "invalid session id", "session deleted", "chrome not reachable",
                    "chrome failed to start", "connection refused", "webdriver exception",
                    "no such session", "session not created", "chrome crashed"
                ]
                
                is_chrome_error = any(error in error_message.lower() for error in chrome_errors)
                
                if is_chrome_error:
                    chrome_retry_count += 1
                    print(f"🔄 Ошибка Chrome, перезапуск драйвера {chrome_retry_count}/{max_chrome_retries}")
                    
                    # Закрываем текущий драйвер и создаем новый
                    self._close_driver()
                    time.sleep(3)  # Увеличенная пауза перед перезапуском Chrome
                    continue
                else:
                    # Если это не ошибка Chrome, не повторяем
                    return self._cache_and_return(query, {
                        "источник": "ГАРАНТ",
                        "статус": "ошибка",
                        "url": "https://ivo.garant.ru",
                        "запрос": query if 'query' in locals() else ref.raw,
                        "ошибка": error_message,
                        "попытки_chrome": chrome_retry_count + 1,
                        "попытки_поиска": not_found_retry_count + 1
                    })
        
        # Если все попытки Chrome исчерпаны
        return self._cache_and_return(query, {
            "источник": "ГАРАНТ",
            "статус": "ошибка",
            "url": "https://ivo.garant.ru",
            "запрос": ref.raw,
            "ошибка": f"Все попытки Chrome исчерпаны ({max_chrome_retries} попыток)",
            "попытки_chrome": chrome_retry_count,
            "попытки_поиска": not_found_retry_count + 1
                })

    def _try_alternative_click(self, wait, query, attempt):
        """Альтернативный способ клика на результат"""
        try:
            # Ждем исчезновения модальных окон
            try:
                WebDriverWait(self.driver, 5).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.x-mask'))
                )
            except:
                pass
            
            # Пробуем найти элемент по более общему XPath
            alternative_xpaths = [
                '/html/body/div[1]/div[2]/div[2]/div[2]/div[2]/div/div/div/div[2]/div/div/div[2]/div/div/div[4]/div/div/ul[1]/li[1]/a',
                '//a[contains(@class, "search-result")]',
                '//div[contains(@class, "search-results")]//a[1]',
                '//ul[contains(@class, "search-list")]//li[1]//a',
                '//ul//li[1]//a',
                '//a[contains(@href, "document")]'
            ]
            
            click_successful = False
            for xpath in alternative_xpaths:
                try:
                    element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                    
                    # Пробуем извлечь URL и перейти напрямую
                    try:
                        href = element.get_attribute('href')
                        if href:
                            print(f"✅ Альтернативная ссылка найдена: {href[:100]}...")
                            self.driver.get(href)
                            print(f"✅ Переход по альтернативной ссылке выполнен")
                            click_successful = True
                            break
                        else:
                            print(f"🔄 Href пустой для XPath: {xpath}")
                    except Exception as href_error:
                        print(f"🔄 Ошибка извлечения href для {xpath}: {str(href_error)[:50]}...")
                    
                    # Если href не получился, пробуем JavaScript клик
                    try:
                        self.driver.execute_script("arguments[0].click();", element)
                        print(f"✅ Альтернативный JavaScript клик сработал для XPath: {xpath}")
                        click_successful = True
                        break
                    except Exception as js_error:
                        print(f"🔄 JavaScript клик не сработал для {xpath}: {str(js_error)[:50]}...")
                        
                except Exception as find_error:
                    print(f"🔄 Не найден элемент для XPath {xpath}: {str(find_error)[:50]}...")
                    continue
            
            if not click_successful:
                print("❌ Все альтернативные XPath не сработали")
                return self._cache_and_return(query, {
                    "источник": "ГАРАНТ",
                    "статус": "не найден",
                    "url": self.driver.current_url,
                    "запрос": query,
                    "попытки_поиска": attempt
                })
            
            # Проверяем результат
            current_url = self.driver.current_url
            if "basesearch" in current_url:
                return self._cache_and_return(query, {
                    "источник": "ГАРАНТ",
                    "статус": "не найден",
                    "url": current_url,
                    "запрос": query,
                    "попытки_поиска": attempt
                })
            
            return self._cache_and_return(query, {
                "источник": "ГАРАНТ",
                "статус": "неизвестно",
                "url": current_url,
                "запрос": query,
                "метод_проверки": "альтернативный_клик",
                "попытки_поиска": attempt
            })
            
        except Exception as e:
            return self._cache_and_return(query, {
                "источник": "ГАРАНТ",
                "статус": "ошибка",
                "url": self.driver.current_url,
                "запрос": query,
                "ошибка": str(e),
                "попытки_поиска": attempt
            })
    
    def _extract_document_info(self, ref: Reference) -> str:
        """
        Извлечение информации о документе из указанного элемента
        
        Args:
            ref: Reference объект с информацией о документе
            
        Returns:
            Статус документа на основе извлеченной информации
        """
        try:
            wait = WebDriverWait(self.driver, 10)
            
            # Ждем загрузки страницы
            time.sleep(2)
            
            # Ищем "Актуальная ред." с датой на странице
            page_source = self.driver.page_source
            
            # Ищем паттерн "Актуальная ред. dd.mm.yyyy"
            import re
            actual_date_pattern = r'Актуальная ред\.\s*(\d{1,2}\.\d{1,2}\.\d{4})'
            match = re.search(actual_date_pattern, page_source)
            
            if match:
                actual_date = match.group(1)
                
                # Проверяем совпадение с датой документа, если она есть
                if ref.date and self._dates_match(ref.date, actual_date):
                    return "действительно"
                else:
                    # Если даты не совпадают, документ может быть устаревшим
                    return "просрочено"
            else:
                # Если не найдена актуальная редакция, анализируем общее содержимое
                if self._analyze_info_text(page_source):
                    return "действительно"
                else:
                    return "неизвестно"
                
        except Exception as e:
            return "неизвестно"
    
    def _analyze_info_text(self, info_text: str) -> bool:
        """
        Анализирует текст информации о документе для определения его статуса
        
        Args:
            info_text: Текст с информацией о документе
            
        Returns:
            True если документ считается действительным
        """
        info_text_lower = info_text.lower()
        
        # Ключевые слова, указывающие на действительность
        positive_keywords = [
            "действует", "действующий", "действующая", "действующее",
            "в силе", "актуально", "актуальная", "актуальный"
        ]
        
        # Ключевые слова, указывающие на недействительность
        negative_keywords = [
            "не действует", "утратил силу", "утратила силу", "утратило силу",
            "отменен", "отменена", "отменено", "признан утратившим силу"
        ]
        
        # Проверяем на положительные индикаторы
        for keyword in positive_keywords:
            if keyword in info_text_lower:
                return True
                
        # Проверяем на отрицательные индикаторы
        for keyword in negative_keywords:
            if keyword in info_text_lower:
                return False
                
        # Если ничего определенного не найдено, возвращаем False (неизвестно)
        return False
    
    def _dates_match(self, ref_date: str, garant_date: str) -> bool:
        """
        Проверяет совпадение дат с учетом различных форматов
        
        Args:
            ref_date: Дата из документа (например, "27.07.2006")
            garant_date: Дата из ГАРАНТ (может быть в разных форматах)
            
        Returns:
            True если даты совпадают
        """
        import re
        from datetime import datetime
        
        try:
            # Нормализуем дату из документа
            ref_date_clean = ref_date.strip()
            
            # Ищем все даты в тексте из ГАРАНТ (формат ДД.ММ.ГГГГ)
            date_patterns = re.findall(r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b', garant_date)
            
            for day, month, year in date_patterns:
                # Приводим к формату ДД.ММ.ГГГГ
                normalized_date = f"{day.zfill(2)}.{month.zfill(2)}.{year}"
                
                # Сравниваем с датой документа
                if ref_date_clean == normalized_date:
                    return True
                    
                # Также пробуем без ведущих нулей
                short_date = f"{int(day)}.{int(month)}.{year}"
                if ref_date_clean == short_date:
                    return True
            
            # Дополнительно ищем даты в других форматах
            if ref_date_clean in garant_date:
                return True
                
            return False
            
        except Exception as e:
            print(f"❌ Ошибка при сравнении дат: {e}")
            return False
    
    def _analyze_document_status(self, page_source: str) -> str:
        """Анализ статуса документа на основе содержимого страницы"""
        
        # Ключевые слова для определения статуса
        expired_keywords = [
            "не действует", "утратил силу", "утратила силу", "утратило силу",
            "признан утратившим силу", "отменен", "отменена", "заменен", "заменена",
            "недействующий", "недействующая", "недействующее"
        ]
        
        active_keywords = [
            "действует", "действующая редакция", "актуально", "в силе",
            "действующий", "действующая", "действующее"
        ]
        
        # Подсчитываем вхождения ключевых слов
        expired_count = sum(page_source.count(keyword) for keyword in expired_keywords)
        active_count = sum(page_source.count(keyword) for keyword in active_keywords)
        
        if expired_count > active_count and expired_count > 0:
            return "просрочено"
        elif active_count > expired_count and active_count > 0:
            return "действительно"
        else:
            return "неизвестно"
    
    def _handle_message_box(self):
        """Обработка message box если он появляется"""
        try:
            # Проверяем наличие message box
            message_box = self.driver.find_elements(By.XPATH, '/html/body/div[13]')
            
            if message_box:
                print("🔍 Обнаружен message box, обрабатываем...")
                
                # Ждем появления кнопки в message box
                wait = WebDriverWait(self.driver, 5)
                message_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, '/html/body/div[13]/div[3]/div/div/a[1]/span/span/span[2]'))
                )
                
                # Кликаем на кнопку в message box
                message_button.click()
                print("✅ Кликнули на кнопку в message box")
                
                # Ждем 1 секунду как указано в требованиях
                time.sleep(1)
                print("⏱️  Подождали 1 секунду после обработки message box")
                
        except Exception as e:
            print(f"⚠️  Ошибка при обработке message box: {e}")
            # Продолжаем выполнение даже если message box не найден или не обработан

    def check_multiple_documents(self, refs: List[Reference], keep_windows_open: bool = False) -> Dict[str, Dict]:
        """
        Параллельная проверка нескольких документов с ротацией сессий
        
        Args:
            refs: Список Reference объектов
            keep_windows_open: Оставить окна Chrome открытыми после завершения
            
        Returns:
            Словарь с результатами проверки
        """
        results = {}
        drivers = []  # Список для хранения драйверов
        search_count = 0  # Счетчик поисков для ротации сессий
        
        print(f"🚀 Запускаем параллельную проверку {len(refs)} документов с {self.max_workers} Chrome инстансами")
        print(f"🔄 Ротация сессий каждые 2 поиска для обхода детекции")
        
        try:
            # Используем ThreadPoolExecutor для параллельной обработки
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Создаем задачи для каждого документа
                future_to_ref = {}
                
                for i, ref in enumerate(refs):
                    # Принудительная ротация сессии каждые 2 поиска
                    if i > 0 and i % 2 == 0:
                        with self.lock:
                            print(f"🔄 Принудительная ротация сессии после {i} поисков")
                        # Сбрасываем счетчик сессий для принудительной ротации
                        self.session_counter = (self.session_counter + 10) % len(self.session_data_pool)
                    
                    future = executor.submit(self._check_single_document, ref, i % self.max_workers)
                    future_to_ref[future] = ref
                
                # Собираем результаты по мере их завершения
                for future in concurrent.futures.as_completed(future_to_ref):
                    ref_raw, result = future.result()
                    results[ref_raw] = result
                    search_count += 1
                    
                    with self.lock:
                        print(f"✅ Завершена проверка ({search_count}/{len(refs)}): {ref_raw[:50]}... - {result.get('статус', 'неизвестно')}")
            
            print(f"🎉 Параллельная проверка завершена! Обработано {len(results)} документов")
            print(f"🔄 Всего ротаций сессий: {search_count // 2}")
            
            if keep_windows_open:
                print("🔍 Chrome окна остались открытыми для инспекции")
                print("💡 Закройте окна вручную когда закончите анализ")
            else:
                print("🔒 Chrome окна закрыты")
                
        except Exception as e:
            print(f"❌ Ошибка при параллельной проверке: {e}")
            if not keep_windows_open:
                # Закрываем драйверы в случае ошибки, если не нужно оставлять окна открытыми
                for driver in drivers:
                    try:
                        driver.quit()
                    except:
                        pass
        
        return results
    
    def __enter__(self):
        self._setup_driver()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._close_driver()

    def _save_to_cache(self, query: str, result: Dict):
        """Сохраняет результат поиска в SQLite-кеш"""
        try:
            self.cache.save_result(query, result)
        except Exception as e:
            print(f"⚠️ Ошибка сохранения в кеш: {e}")

    def _cache_and_return(self, query: str, result: Dict):
        """Хелпер: сохранить и вернуть результат"""
        self._save_to_cache(query, result)
        return result

def should_use_garant_check(validation_results: Dict[str, Dict]) -> bool:
    """
    Определяет, нужно ли использовать проверку через ГАРАНТ
    
    Args:
        validation_results: Результаты предыдущей валидации
        
    Returns:
        True если неизвестных статусов больше 10
    """
    unknown_count = sum(
        1 for result in validation_results.values() 
        if result.get("статус", "").lower() == "неизвестно"
    )
    
    return unknown_count > 10


def enhance_validation_with_garant(refs: List[Reference], validation_results: Dict[str, Dict]) -> Dict[str, Dict]:
    """
    Улучшение результатов валидации с помощью проверки через ГАРАНТ
    
    Args:
        refs: Список Reference объектов
        validation_results: Исходные результаты валидации
        
    Returns:
        Обновленные результаты валидации
    """
    if not should_use_garant_check(validation_results):
        print("🔍 Проверка через ГАРАНТ не требуется (неизвестных статусов <= 10)")
        return validation_results
    
    print("🔍 Запускаем дополнительную проверку через ГАРАНТ...")
    
    # Находим документы с неизвестным статусом
    unknown_refs = []
    for ref in refs:
        if validation_results.get(ref.raw, {}).get("статус", "").lower() == "неизвестно":
            unknown_refs.append(ref)
    
    if not unknown_refs:
        return validation_results
    
    # Проверяем через ГАРАНТ (параллельная версия)
    checker = GarantCheckerParallel(max_workers=5, headless=False)
    garant_results = checker.check_multiple_documents(unknown_refs)
    
    # Обновляем результаты
    updated_results = validation_results.copy()
    
    for ref_raw, garant_result in garant_results.items():
        if ref_raw in updated_results:
            # Обновляем статус если ГАРАНТ дал определенный результат
            garant_status = garant_result.get("статус", "неизвестно")
            if garant_status in ["действительно", "просрочено"]:
                updated_results[ref_raw]["статус"] = garant_status.title()
                updated_results[ref_raw]["уверенность"] = 0.8  # Высокая уверенность для ГАРАНТ
                updated_results[ref_raw]["источник_проверки"] = "ГАРАНТ"
    
    return updated_results

class GarantCheckerParallel:
    """Параллельная проверка документов через систему ГАРАНТ с несколькими Chrome инстансами"""
    
    def __init__(self, max_workers: int = 5, headless: bool = False, cache_db_path: str = "garant_cache_parallel.db", cache_ttl_hours: int = 24 * 7):
        self.max_workers = max_workers
        self.headless = headless
        self.cache = GarantCache(cache_db_path, cache_ttl_hours)
        self.lock = threading.Lock()
        self.session_counter = 0  # Счетчик для отслеживания количества поисков
        self.session_data_pool = self._generate_session_data_pool()
        
    def _generate_session_data_pool(self):
        """Генерация пула различных данных сессии для ротации"""
        user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]
        
        window_sizes = [
            "1920,1080",
            "1366,768", 
            "1440,900",
            "1536,864",
            "1280,720"
        ]
        
        session_pool = []
        for i in range(20):  # Создаем 20 различных конфигураций
            session_pool.append({
                'user_agent': user_agents[i % len(user_agents)],
                'window_size': window_sizes[i % len(window_sizes)],
                'session_id': f"session_{i}_{hash(str(i)) % 10000}",
                'debug_port': 9222 + (i % 10),  # Ротация портов
                'user_data_dir': f"/tmp/chrome_session_{i}_{hash(str(i)) % 10000}"
            })
        
        return session_pool
    
    def _get_next_session_data(self):
        """Получение следующих данных сессии для ротации"""
        with self.lock:
            session_data = self.session_data_pool[self.session_counter % len(self.session_data_pool)]
            self.session_counter += 1
            return session_data
    
    def _create_driver(self, instance_id: int):
        """Создание отдельного Chrome WebDriver для каждого инстанса с ротацией сессий"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        
        # Получаем данные для новой сессии
        session_data = self._get_next_session_data()
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"--window-size={session_data['window_size']}")
        chrome_options.add_argument(f"--user-agent={session_data['user_agent']}")
        
        # Уникальные настройки для каждой сессии
        chrome_options.add_argument(f"--remote-debugging-port={session_data['debug_port']}")
        chrome_options.add_argument(f"--user-data-dir={session_data['user_data_dir']}")
        
        # Дополнительные настройки для обхода детекции
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Случайные настройки для имитации реального браузера
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Устанавливаем скрипт для скрытия автоматизации
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    
    def _wait_for_page_ready_parallel(self, driver):
        """Ждет полной загрузки страницы и исчезновения модальных окон для параллельной версии"""
        try:
            # Ждем пока исчезнут все маски
            WebDriverWait(driver, 10).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.x-mask'))
            )
        except:
            pass
        
        try:
            # Ждем пока исчезнут загрузочные индикаторы
            WebDriverWait(driver, 5).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.x-mask-loading'))
            )
        except:
            pass
        
        try:
            # Пытаемся закрыть любые модальные окна с помощью Escape
            from selenium.webdriver.common.keys import Keys
            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except:
            pass
        
        # Дополнительная пауза для стабилизации
        time.sleep(2)

    def _save_to_cache_parallel(self, query: str, result: Dict):
        """Сохраняет результат поиска в SQLite-кеш (параллельная версия)"""
        try:
            with self.lock:  # Thread-safe caching
                self.cache.save_result(query, result)
        except Exception as e:
            print(f"⚠️ Ошибка сохранения в кеш: {e}")

    def _cache_and_return_parallel(self, query: str, result: Dict):
        """Хелпер: сохранить и вернуть результат (параллельная версия)"""
        self._save_to_cache_parallel(query, result)
        return result

    def _check_single_document(self, ref: Reference, instance_id: int) -> tuple:
        """Проверка одного документа в отдельном Chrome инстансе с повторными попытками"""
        max_chrome_retries = 3  # Максимум попыток для ошибок Chrome
        max_not_found_retries = 2  # Максимум попыток для случаев "не найден"
        chrome_retry_count = 0
        not_found_retry_count = 0
        query = self._format_query(ref)  # Move query definition to the top
        
        while chrome_retry_count < max_chrome_retries:
            driver = None
            try:
                driver = self._create_driver(instance_id)
                
                # Очищаем данные сессии для обхода детекции
                self._clear_session_data(driver)
                
                # Кодируем запрос для URL
                encoded_query = urllib.parse.quote(query)
                
                # Проверяем кеш перед запросом (thread-safe)
                with self.lock:
                    cached = self.cache.get_cached_result(query)
                    if cached:
                        cached["из_кеша"] = True
                        cached["инстанс"] = instance_id
                        return ref.raw, cached
                
                # Переходим напрямую на страницу поиска с закодированным запросом
                search_url = f"https://ivo.garant.ru/#/basesearch/{encoded_query}/all:0"
                driver.get(search_url)
                
                # Ждем 2 секунды как указано в требованиях
                time.sleep(2)
                
                # Ждем появления результатов и кликаем на первый результат
                wait = WebDriverWait(driver, 15)
                
                try:
                    # Ждем загрузки результатов поиска
                    wait.until(
                        EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[2]/div[2]/div/div/div/div[2]/div/div/div[2]/div/div/div[4]/div/div/ul[1]/li[1]/a'))
                    )
                    
                    # Дополнительная пауза для полной загрузки
                    time.sleep(1)
                    
                    # Ждем исчезновения модальных окон и масок
                    try:
                        # Ждем пока исчезнут все маски и загрузочные индикаторы
                        self._wait_for_page_ready_parallel(driver)
                    except:
                        pass  # Если маски нет, продолжаем
                    
                    # Кликаем на первый результат с улучшенной обработкой
                    result_link = wait.until(
                        EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[2]/div[2]/div/div/div/div[2]/div/div/div[2]/div/div/div[4]/div/div/ul[1]/li[1]/a'))
                    )
                    
                    # Извлекаем URL напрямую из ссылки и переходим к нему
                    try:
                        href = result_link.get_attribute('href')
                        if href:
                            print(f"✅ Найдена ссылка на документ: {href[:100]}...")
                            # Переходим напрямую по ссылке, минуя модальные окна
                            driver.get(href)
                            print(f"✅ Переход по прямой ссылке выполнен")
                        else:
                            # Если href пустой, пробуем JavaScript клик
                            print("🔄 Href пустой, пробуем JavaScript клик...")
                            driver.execute_script("arguments[0].click();", result_link)
                    except Exception as link_error:
                        print(f"🔄 Ошибка перехода по ссылке: {str(link_error)[:100]}...")
                        # Если не получилось, пробуем альтернативные методы
                        return self._try_alternative_click(wait, query, not_found_retry_count + 1, driver, instance_id)
                    
                    # Ждем загрузки страницы с документом
                    time.sleep(3)
                    
                    # Проверяем, что мы действительно перешли на новую страницу
                    current_url = driver.current_url
                    if "basesearch" in current_url:
                        # Документ не найден - пробуем еще раз
                        if not_found_retry_count < max_not_found_retries:
                            not_found_retry_count += 1
                            print(f"🔄 [Инстанс {instance_id}] Документ не найден, попытка {not_found_retry_count}/{max_not_found_retries}: {ref.raw[:50]}...")
                            time.sleep(2)  # Пауза перед повторной попыткой
                            continue
                        else:
                            result = self._cache_and_return_parallel(query, {
                                "источник": "ГАРАНТ", 
                                "статус": "не найден",
                                "url": search_url,
                                "запрос": query,
                                "попытки_поиска": not_found_retry_count + 1
                            })
                            return ref.raw, result
                    
                    # Проверяем наличие message box и обрабатываем его
                    self._handle_message_box_parallel(driver, instance_id)
                    
                    # Извлекаем текст напрямую из указанного элемента
                    date_status = self._extract_document_info_parallel(driver, ref, instance_id)
                    
                    if date_status == "действительно":
                        result = self._cache_and_return_parallel(query, {
                            "источник": "ГАРАНТ",
                            "статус": "действительно",
                            "url": driver.current_url,
                            "запрос": query,
                            "метод_проверки": "извлечение_информации",
                            "попытки_chrome": chrome_retry_count + 1,
                            "попытки_поиска": not_found_retry_count + 1
                        })
                        return ref.raw, result
                    
                    # Если информация не подтверждает действительность, анализируем содержимое страницы
                    page_source = driver.page_source.lower()
                    status = self._analyze_document_status(page_source)
                    
                    result = self._cache_and_return_parallel(query, {
                        "источник": "ГАРАНТ",
                        "статус": status,
                        "url": driver.current_url,
                        "запрос": query,
                        "метод_проверки": "анализ_содержимого",
                        "попытки_chrome": chrome_retry_count + 1,
                        "попытки_поиска": not_found_retry_count + 1
                    })
                    return ref.raw, result
                    
                except TimeoutException:
                    # Результат не найден - пробуем еще раз
                    if not_found_retry_count < max_not_found_retries:
                        not_found_retry_count += 1
                        print(f"🔄 [Инстанс {instance_id}] Timeout при поиске, попытка {not_found_retry_count}/{max_not_found_retries}: {ref.raw[:50]}...")
                        time.sleep(2)  # Пауза перед повторной попыткой
                        continue
                    else:
                        result = self._cache_and_return_parallel(query, {
                            "источник": "ГАРАНТ", 
                            "статус": "не найден",
                            "url": search_url,
                            "запрос": query,
                            "попытки_поиска": not_found_retry_count + 1
                        })
                        return ref.raw, result
                    
            except Exception as e:
                error_message = str(e)
                print(f"⚠️  [Инстанс {instance_id}] Ошибка: {error_message}")
                
                # Проверяем, является ли это ошибкой Chrome/сессии
                chrome_errors = [
                    "invalid session id", "session deleted", "chrome not reachable",
                    "chrome failed to start", "connection refused", "webdriver exception",
                    "no such session", "session not created", "chrome crashed"
                ]
                
                is_chrome_error = any(error in error_message.lower() for error in chrome_errors)
                
                if is_chrome_error:
                    chrome_retry_count += 1
                    print(f"🔄 [Инстанс {instance_id}] Ошибка Chrome, перезапуск инстанса {chrome_retry_count}/{max_chrome_retries}")
                    time.sleep(3)  # Увеличенная пауза перед перезапуском Chrome
                    continue
                else:
                    # Если это не ошибка Chrome, не повторяем
                    result = self._cache_and_return_parallel(query, {
                        "источник": "ГАРАНТ",
                        "статус": "ошибка",
                        "url": "https://ivo.garant.ru",
                        "запрос": query if 'query' in locals() else ref.raw,
                        "ошибка": error_message,
                        "попытки_chrome": chrome_retry_count + 1,
                        "попытки_поиска": not_found_retry_count + 1
                    })
                    return ref.raw, result
            finally:
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass  # Игнорируем ошибки при закрытии драйвера
        
        # Если все попытки Chrome исчерпаны
        result = self._cache_and_return_parallel(query, {
            "источник": "ГАРАНТ",
            "статус": "ошибка",
            "url": "https://ivo.garant.ru",
            "запрос": ref.raw,
            "ошибка": f"Все попытки Chrome исчерпаны ({max_chrome_retries} попыток)",
            "попытки_chrome": chrome_retry_count,
            "попытки_поиска": not_found_retry_count + 1
        })
        return ref.raw, result
    
    def _clear_session_data(self, driver):
        """Очистка данных сессии для обхода детекции"""
        try:
            # Очищаем cookies
            driver.delete_all_cookies()
            
            # Очищаем localStorage и sessionStorage
            driver.execute_script("window.localStorage.clear();")
            driver.execute_script("window.sessionStorage.clear();")
            
            # Устанавливаем случайные значения для обхода детекции
            driver.execute_script("""
                // Скрываем признаки автоматизации
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                
                // Устанавливаем случайные значения
                window.chrome = {
                    runtime: {},
                };
                
                // Скрываем автоматизацию
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
            """)
            
        except Exception as e:
            # Игнорируем ошибки при очистке данных
            pass
    
    def _format_query(self, ref: Reference) -> str:
        """Форматирование запроса для поиска"""
        query_parts = []
        
        if ref.number:
            query_parts.append(f"№ {ref.number}")
        if ref.date:
            query_parts.append(f"от {ref.date}")
        if ref.title and not ref.number:
            # Если нет номера, используем название
            query_parts.append(ref.title[:50])
            
        return " ".join(query_parts)
    
    def _handle_message_box_parallel(self, driver, instance_id: int):
        """Обработка message box если он появляется (для параллельного режима)"""
        try:
            # Проверяем наличие message box
            message_box = driver.find_elements(By.XPATH, '/html/body/div[13]')
            
            if message_box:
                print(f"🔍 [Инстанс {instance_id}] Обнаружен message box, обрабатываем...")
                
                # Ждем появления кнопки в message box
                wait = WebDriverWait(driver, 5)
                message_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, '/html/body/div[13]/div[3]/div/div/a[1]/span/span/span[2]'))
                )
                
                # Кликаем на кнопку в message box
                message_button.click()
                print(f"✅ [Инстанс {instance_id}] Кликнули на кнопку в message box")
                
                # Ждем 1 секунду как указано в требованиях
                time.sleep(1)
                
        except Exception as e:
            print(f"⚠️  [Инстанс {instance_id}] Ошибка при обработке message box: {e}")
    
    def _extract_document_info_parallel(self, driver, ref: Reference, instance_id: int) -> str:
        """Извлечение информации о документе (для параллельного режима)"""
        try:
            wait = WebDriverWait(driver, 10)
            
            # Ждем загрузки страницы
            time.sleep(2)
            
            # Ищем "Актуальная ред." с датой на странице
            page_source = driver.page_source
            
            # Ищем паттерн "Актуальная ред. dd.mm.yyyy"
            import re
            actual_date_pattern = r'Актуальная ред\.\s*(\d{1,2}\.\d{1,2}\.\d{4})'
            match = re.search(actual_date_pattern, page_source)
            
            if match:
                actual_date = match.group(1)
                
                # Проверяем совпадение с датой документа, если она есть
                if ref.date and self._dates_match(ref.date, actual_date):
                    return "действительно"
                else:
                    # Если даты не совпадают, документ может быть устаревшим
                    return "просрочено"
            else:
                # Если не найдена актуальная редакция, анализируем общее содержимое
                if self._analyze_info_text(page_source):
                    return "действительно"
                else:
                    return "неизвестно"
                
        except Exception as e:
            return "неизвестно"
    
    def _dates_match(self, ref_date: str, garant_date: str) -> bool:
        """Проверяет совпадение дат с учетом различных форматов"""
        import re
        from datetime import datetime
        
        try:
            # Нормализуем дату из документа
            ref_date_clean = ref_date.strip()
            
            # Ищем все даты в тексте из ГАРАНТ (формат ДД.ММ.ГГГГ)
            date_patterns = re.findall(r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b', garant_date)
            
            for day, month, year in date_patterns:
                # Приводим к формату ДД.ММ.ГГГГ
                normalized_date = f"{day.zfill(2)}.{month.zfill(2)}.{year}"
                
                # Сравниваем с датой документа
                if ref_date_clean == normalized_date:
                    return True
                    
                # Также пробуем без ведущих нулей
                short_date = f"{int(day)}.{int(month)}.{year}"
                if ref_date_clean == short_date:
                    return True
            
            # Дополнительно ищем даты в других форматах
            if ref_date_clean in garant_date:
                return True
                
            return False
            
        except Exception as e:
            print(f"❌ Ошибка при сравнении дат: {e}")
            return False
    
    def _analyze_info_text(self, info_text: str) -> bool:
        """Анализирует текст информации о документе для определения его статуса"""
        info_text_lower = info_text.lower()
        
        # Ключевые слова, указывающие на действительность
        positive_keywords = [
            "действует", "действующий", "действующая", "действующее",
            "в силе", "актуально", "актуальная", "актуальный"
        ]
        
        # Ключевые слова, указывающие на недействительность
        negative_keywords = [
            "не действует", "утратил силу", "утратила силу", "утратило силу",
            "отменен", "отменена", "отменено", "признан утратившим силу"
        ]
        
        # Проверяем на положительные индикаторы
        for keyword in positive_keywords:
            if keyword in info_text_lower:
                return True
                
        # Проверяем на отрицательные индикаторы
        for keyword in negative_keywords:
            if keyword in info_text_lower:
                return False
                
        # Если ничего определенного не найдено, возвращаем False (неизвестно)
        return False
    
    def _analyze_document_status(self, page_source: str) -> str:
        """Анализ статуса документа на основе содержимого страницы"""
        
        # Ключевые слова для определения статуса
        expired_keywords = [
            "не действует", "утратил силу", "утратила силу", "утратило силу",
            "признан утратившим силу", "отменен", "отменена", "заменен", "заменена",
            "недействующий", "недействующая", "недействующее"
        ]
        
        active_keywords = [
            "действует", "действующая редакция", "актуально", "в силе",
            "действующий", "действующая", "действующее"
        ]
        
        # Подсчитываем вхождения ключевых слов
        expired_count = sum(page_source.count(keyword) for keyword in expired_keywords)
        active_count = sum(page_source.count(keyword) for keyword in active_keywords)
        
        if expired_count > active_count and expired_count > 0:
            return "просрочено"
        elif active_count > expired_count and active_count > 0:
            return "действительно"
        else:
            return "неизвестно"
    
    def _try_alternative_click(self, wait, query, attempt, driver, instance_id):
        """Альтернативный способ клика на результат (параллельная версия)"""
        try:
            # Ждем исчезновения модальных окон
            try:
                self._wait_for_page_ready_parallel(driver)
            except:
                pass
            
            # Пробуем найти элемент по более общему XPath
            alternative_xpaths = [
                '/html/body/div[1]/div[2]/div[2]/div[2]/div[2]/div/div/div/div[2]/div/div/div[2]/div/div/div[4]/div/div/ul[1]/li[1]/a',
                '//a[contains(@class, "search-result")]',
                '//div[contains(@class, "search-results")]//a[1]',
                '//ul[contains(@class, "search-list")]//li[1]//a',
                '//ul//li[1]//a',
                '//a[contains(@href, "document")]'
            ]
            
            click_successful = False
            for xpath in alternative_xpaths:
                try:
                    element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                    
                    # Пробуем извлечь URL и перейти напрямую
                    try:
                        href = element.get_attribute('href')
                        if href:
                            print(f"✅ [Инстанс {instance_id}] Альтернативная ссылка найдена: {href[:100]}...")
                            driver.get(href)
                            print(f"✅ [Инстанс {instance_id}] Переход по альтернативной ссылке выполнен")
                            click_successful = True
                            break
                        else:
                            print(f"🔄 [Инстанс {instance_id}] Href пустой для XPath: {xpath}")
                    except Exception as href_error:
                        print(f"🔄 [Инстанс {instance_id}] Ошибка извлечения href для {xpath}: {str(href_error)[:50]}...")
                    
                    # Если href не получился, пробуем JavaScript клик
                    try:
                        driver.execute_script("arguments[0].click();", element)
                        print(f"✅ [Инстанс {instance_id}] Альтернативный JavaScript клик сработал для XPath: {xpath}")
                        click_successful = True
                        break
                    except Exception as js_error:
                        print(f"🔄 [Инстанс {instance_id}] JavaScript клик не сработал для {xpath}: {str(js_error)[:50]}...")
                         
                except Exception as find_error:
                    print(f"🔄 [Инстанс {instance_id}] Не найден элемент для XPath {xpath}: {str(find_error)[:50]}...")
                    continue
            
            if not click_successful:
                print(f"❌ [Инстанс {instance_id}] Все альтернативные XPath не сработали")
                result = self._cache_and_return_parallel(query, {
                    "источник": "ГАРАНТ",
                    "статус": "не найден",
                    "url": driver.current_url,
                    "запрос": query,
                    "попытки_поиска": attempt
                })
                return ref.raw, result
                
            # Проверяем результат
            current_url = driver.current_url
            if "basesearch" in current_url:
                result = self._cache_and_return_parallel(query, {
                    "источник": "ГАРАНТ",
                    "статус": "не найден",
                    "url": current_url,
                    "запрос": query,
                    "попытки_поиска": attempt
                })
                return ref.raw, result
            
            result = self._cache_and_return_parallel(query, {
                "источник": "ГАРАНТ",
                "статус": "неизвестно",
                "url": current_url,
                "запрос": query,
                "метод_проверки": "альтернативный_клик",
                "попытки_поиска": attempt
            })
            return ref.raw, result
            
        except Exception as e:
            result = self._cache_and_return_parallel(query, {
                "источник": "ГАРАНТ",
                "статус": "ошибка",
                "url": driver.current_url,
                "запрос": query,
                "ошибка": str(e),
                "попытки_поиска": attempt
            })
            return ref.raw, result
    
    def check_multiple_documents(self, refs: List[Reference], keep_windows_open: bool = False) -> Dict[str, Dict]:
        """
        Параллельная проверка нескольких документов с ротацией сессий
        
        Args:
            refs: Список Reference объектов
            keep_windows_open: Оставить окна Chrome открытыми после завершения
            
        Returns:
            Словарь с результатами проверки
        """
        results = {}
        drivers = []  # Список для хранения драйверов
        search_count = 0  # Счетчик поисков для ротации сессий
        
        print(f"🚀 Запускаем параллельную проверку {len(refs)} документов с {self.max_workers} Chrome инстансами")
        print(f"🔄 Ротация сессий каждые 2 поиска для обхода детекции")
        
        try:
            # Используем ThreadPoolExecutor для параллельной обработки
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Создаем задачи для каждого документа
                future_to_ref = {}
                
                for i, ref in enumerate(refs):
                    # Принудительная ротация сессии каждые 2 поиска
                    if i > 0 and i % 2 == 0:
                        with self.lock:
                            print(f"🔄 Принудительная ротация сессии после {i} поисков")
                        # Сбрасываем счетчик сессий для принудительной ротации
                        self.session_counter = (self.session_counter + 10) % len(self.session_data_pool)
                    
                    future = executor.submit(self._check_single_document, ref, i % self.max_workers)
                    future_to_ref[future] = ref
                
                # Собираем результаты по мере их завершения
                for future in concurrent.futures.as_completed(future_to_ref):
                    ref_raw, result = future.result()
                    results[ref_raw] = result
                    search_count += 1
                    
                    with self.lock:
                        print(f"✅ Завершена проверка ({search_count}/{len(refs)}): {ref_raw[:50]}... - {result.get('статус', 'неизвестно')}")
            
            print(f"🎉 Параллельная проверка завершена! Обработано {len(results)} документов")
            print(f"🔄 Всего ротаций сессий: {search_count // 2}")
            
            if keep_windows_open:
                print("🔍 Chrome окна остались открытыми для инспекции")
                print("💡 Закройте окна вручную когда закончите анализ")
            else:
                print("🔒 Chrome окна закрыты")
                
        except Exception as e:
            print(f"❌ Ошибка при параллельной проверке: {e}")
            if not keep_windows_open:
                # Закрываем драйверы в случае ошибки, если не нужно оставлять окна открытыми
                for driver in drivers:
                    try:
                        driver.quit()
                    except:
                        pass
        
        return results 