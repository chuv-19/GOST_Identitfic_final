import time
import re
import urllib.parse
import random
import json
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException

try:
    from selenium_stealth import stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    print("⚠️ selenium-stealth не установлен. Для установки: pip install selenium-stealth")

try:
    import undetected_chromedriver as uc
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False
    print("⚠️ undetected-chromedriver не установлен. Для установки: pip install undetected-chromedriver")

from references_extractor import Reference

class StealthGarantChecker:
    """Проверка документов через систему ГАРАНТ с расширенными возможностями обхода детекции"""
    
    def __init__(self, headless: bool = False, use_stealth: bool = True, use_proxies: bool = False, 
                 proxy_list: List[str] = None, use_undetected_chrome: bool = False):
        self.headless = headless
        self.use_stealth = use_stealth and STEALTH_AVAILABLE
        self.use_undetected_chrome = use_undetected_chrome and UC_AVAILABLE
        self.use_proxies = use_proxies
        self.proxy_list = proxy_list or []
        self.driver = None
        self.current_proxy = None
        
        # Пул User-Agent строк для ротации
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        ]
        
        # Различные разрешения экрана
        self.screen_sizes = [
            (1920, 1080), (1366, 768), (1536, 864), (1440, 900), 
            (1280, 720), (1600, 900), (2560, 1440), (1920, 1200)
        ]

    def _setup_stealth_chrome(self):
        """Настройка Chrome с максимальными возможностями стелс"""
        if self.use_undetected_chrome and UC_AVAILABLE:
            return self._setup_undetected_chrome()
        else:
            return self._setup_regular_chrome_with_stealth()
    
    def _setup_undetected_chrome(self):
        """Настройка Undetected Chrome"""
        options = uc.ChromeOptions()
        
        if self.headless:
            options.add_argument("--headless=new")
        
        width, height = random.choice(self.screen_sizes)
        options.add_argument(f"--window-size={width},{height}")
        
        if self.use_proxies and self.proxy_list:
            proxy = random.choice(self.proxy_list)
            options.add_argument(f"--proxy-server={proxy}")
            self.current_proxy = proxy
                
        options.add_argument("--no-first-run")
        options.add_argument("--no-service-autorun")
        options.add_argument("--disable-default-apps")
        
        driver = uc.Chrome(options=options, version_main=None)
        return driver
    
    def _setup_regular_chrome_with_stealth(self):
        """Настройка обычного Chrome с максимальными настройками стелс"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless=new")
            
        width, height = random.choice(self.screen_sizes)
        chrome_options.add_argument(f"--window-size={width},{height}")
        
        user_agent = random.choice(self.user_agents)
        chrome_options.add_argument(f"--user-agent={user_agent}")
        
        if self.use_proxies and self.proxy_list:
            proxy = random.choice(self.proxy_list)
            chrome_options.add_argument(f"--proxy-server={proxy}")
            self.current_proxy = proxy
        
        # Основные настройки анти-детекции
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Дополнительные настройки стелс
        chrome_options.add_argument("--disable-plugins-discovery")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        
        # Настройки профиля браузера
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.cookies": 1,
            "profile.default_content_setting_values.javascript": 1,
            "profile.password_manager_enabled": False,
            "credentials_enable_service": False,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    def _apply_stealth_techniques(self, driver):
        """Применяет различные техники стелс"""
        # Selenium-stealth если доступен
        if self.use_stealth and STEALTH_AVAILABLE:
            stealth(driver,
                    languages=["ru-RU", "ru", "en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True,
                    run_on_insecure_origins=True
            )
        
        # Дополнительные скрипты для обхода детекции
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        driver.execute_script("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
        """)
        
        driver.execute_script("""
            Object.defineProperty(navigator, 'languages', {
                get: () => ['ru-RU', 'ru', 'en-US', 'en'],
            });
        """)

    def _simulate_human_behavior(self):
        """Симулирует человеческое поведение"""
        if not self.driver:
            return
            
        # Случайная пауза
        time.sleep(random.uniform(0.5, 2.0))
        
        # Случайные движения мыши
        try:
            actions = ActionChains(self.driver)
            for _ in range(random.randint(1, 3)):
                x_offset = random.randint(-100, 100)
                y_offset = random.randint(-100, 100)
                actions.move_by_offset(x_offset, y_offset)
                actions.perform()
                time.sleep(random.uniform(0.1, 0.5))
        except Exception:
            pass
            
        # Случайная прокрутка
        try:
            scroll_amount = random.randint(100, 500)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.2, 0.8))
            self.driver.execute_script(f"window.scrollBy(0, -{scroll_amount});")
        except Exception:
            pass

    def check_document(self, ref: Reference) -> Dict[str, str]:
        """Проверка одного документа с анти-детекцией"""
        try:
            # Настройка драйвера
            self.driver = self._setup_stealth_chrome()
            self._apply_stealth_techniques(self.driver)
            
            # Симулируем человеческое поведение
            self._simulate_human_behavior()
            
            # Формируем запрос
            query = self._format_query(ref)
            print(f"🔍 ГАРАНТ поиск (стелс): {query[:100]}...")
            
            # Переходим на сайт
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://ivo.garant.ru/#/basesearch/{encoded_query}/all:0"
            
            self.driver.get(search_url)
            time.sleep(random.uniform(3.0, 5.0))
            
            # Проверяем блокировку
            if self._check_if_blocked():
                return {
                    "источник": "ГАРАНТ",
                    "статус": "заблокировано",
                    "url": search_url,
                    "запрос": query
                }
            
            # Ищем результаты
            wait = WebDriverWait(self.driver, 20)
            
            try:
                result_xpath = '/html/body/div[1]/div[2]/div[2]/div[2]/div[2]/div/div/div/div[2]/div/div/div[2]/div/div/div[4]/div/div/ul[1]/li[1]/a'
                wait.until(EC.presence_of_element_located((By.XPATH, result_xpath)))
                
                # Человекоподобный клик
                result_link = wait.until(EC.element_to_be_clickable((By.XPATH, result_xpath)))
                self._human_like_click(result_link)
                
                time.sleep(random.uniform(3.0, 5.0))
                
                # Анализируем результат
                page_source = self.driver.page_source.lower()
                status = self._analyze_document_status(page_source)
                
                return {
                    "источник": "ГАРАНТ",
                    "статус": status,
                    "url": self.driver.current_url,
                    "запрос": query,
                    "метод": "stealth_check"
                }
                
            except TimeoutException:
                return {
                    "источник": "ГАРАНТ",
                    "статус": "не_найден",
                    "url": search_url,
                    "запрос": query
                }
                
        except Exception as e:
            return {
                "источник": "ГАРАНТ",
                "статус": "ошибка",
                "ошибка": str(e),
                "запрос": query if 'query' in locals() else "неизвестно"
            }
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None

    def _format_query(self, ref: Reference) -> str:
        """Форматирование запроса для поиска"""
        if ref.raw and len(ref.raw.strip()) > 10:
            return ref.raw.strip()[:200]
        
        query_parts = []
        
        if hasattr(ref, 'type') and ref.type:
            query_parts.append(ref.type)
        
        if ref.number:
            query_parts.append(f"№ {ref.number}")
            
        if ref.date:
            query_parts.append(f"от {ref.date}")
            
        if ref.title and not ref.number:
            query_parts.append(ref.title[:100])
            
        result = " ".join(query_parts)
        
        if not result and ref.number:
            result = ref.number
        elif not result and ref.title:
            result = ref.title[:100]
            
        return result or "документ"

    def _human_like_click(self, element):
        """Человекоподобный клик"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(random.uniform(0.3, 0.8))
            
            actions = ActionChains(self.driver)
            actions.move_to_element(element)
            
            x_offset = random.randint(-3, 3)
            y_offset = random.randint(-3, 3)
            actions.move_by_offset(x_offset, y_offset)
            
            time.sleep(random.uniform(0.1, 0.4))
            actions.click()
            actions.perform()
            
        except Exception:
            element.click()

    def _check_if_blocked(self) -> bool:
        """Проверяет блокировку"""
        try:
            page_source = self.driver.page_source.lower()
            
            block_indicators = [
                "cloudflare", "access denied", "blocked", "captcha",
                "please verify", "robot", "bot detection", "security check"
            ]
            
            return any(indicator in page_source for indicator in block_indicators)
            
        except Exception:
            return False

    def _analyze_document_status(self, page_source: str) -> str:
        """Анализ статуса документа"""
        if "информация по данному запросу отсутствует в вашем комплекте" in page_source:
            return "нет_информации"
        
        if any(phrase in page_source for phrase in ["не действует", "утратил силу", "отменен"]):
            return "не_действует"
        elif any(phrase in page_source for phrase in ["действует", "в силе", "актуален"]):
            return "действует"
        elif any(phrase in page_source for phrase in ["изменен", "дополнен", "новая редакция"]):
            return "изменен"
        else:
            return "не_определен"

