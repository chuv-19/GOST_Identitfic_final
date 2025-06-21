import asyncio
import re
from typing import List, Dict, Tuple, Optional
import logging

import httpx
from bs4 import BeautifulSoup
import urllib.parse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Импортируем улучшенный стелс-чекер ГАРАНТ
try:
    from garant_checker import GarantCheckerParallel, enhance_validation_with_garant
    GARANT_AVAILABLE = True
except ImportError:
    GARANT_AVAILABLE = False

EXPIRED_KEYWORDS = [
    "не действует",
    "утратил силу",
    "утратила силу",
    "утратило силу",
    "признан утратившим силу",
    "отменен",
    "отменена",
    "заменен",
    "заменена",
]
ACTIVE_KEYWORDS = [
    "действует",
    "действующая редакция",
    "актуально",
]

SOURCES = {
    # законодательство
    "pravo.gov.ru": "https://pravo.gov.ru/search/?query={query}",
    "consultant.ru": "https://www.consultant.ru/search/?q={query}",
    "garant.ru": "https://www.garant.ru/search/?q={query}",
    "rulaws.ru": "https://rulaws.ru/search/?q={query}",
    # стандарты
    "docs.cntd.ru": "https://docs.cntd.ru/search/?searchtext={query}",
    "gostrf.com": "https://gostrf.com/search/?q={query}",
    "standartgost.ru": "https://standartgost.ru/search/?q={query}",
    "gov.spb.ru": "https://www.gov.spb.ru/search/?q={query}",
    "gostassistent.ru": "https://gostassistent.ru/search?q={query}",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DocumentValidator/1.0; +https://example.com)"
}


async def _fetch(client: httpx.AsyncClient, url: str) -> Tuple[str, str]:
    try:
        logger.info(f"Checking source: {url}")
        resp = await client.get(url, timeout=10.0)  # Reduced timeout
        resp.raise_for_status()
        logger.info(f"Successfully checked {url}")
        return url, resp.text.lower()
    except httpx.TimeoutException:
        logger.warning(f"Timeout while checking {url}")
        return url, ""
    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error {e.response.status_code} while checking {url}")
        return url, ""
    except Exception as e:
        logger.warning(f"Error checking {url}: {str(e)}")
        return url, ""


async def _second_pass_check(query: str) -> Optional[Tuple[str, str]]:
    """Dedicated check against gostassistent.ru if first pass returned unknown."""
    url = f"https://gostassistent.ru/search?q={query}"
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        try:
            resp = await client.get(url, timeout=20)
            resp.raise_for_status()
            return url, resp.text.lower()
        except Exception:
            return None


async def validate_reference(ref_raw: str, max_sources: int | None = None) -> Dict:
    """Validate a reference across multiple sources.

    Returns dict with keys: source_results (dict of url -> html), status, confidence
    """
    tasks = []
    query = urllib.parse.quote_plus(ref_raw)

    # Add connection and rate limiting
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(
        headers=HEADERS, 
        follow_redirects=True,
        limits=limits,
        timeout=10.0  # Global timeout
    ) as client:
        logger.info(f"Starting validation for: {ref_raw}")
        for i, (name, tmpl) in enumerate(SOURCES.items()):
            if max_sources and i >= max_sources:
                break
            url = tmpl.format(query=query)
            tasks.append(_fetch(client, url))
        
        # Use timeout for gather to prevent infinite waiting
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error("Timeout while gathering results from all sources")
            results = [(url, "") for url in SOURCES.values()]

    status_counts = {"expired": 0, "active": 0, "unknown": 0}
    source_status: Dict[str, str] = {}

    for url, html in results:
        if not html:
            source_status[url] = "unknown"
            status_counts["unknown"] += 1
            continue
        html_lc = html.lower()
        expired = any(k in html_lc for k in EXPIRED_KEYWORDS)
        active = any(k in html_lc for k in ACTIVE_KEYWORDS)
        if expired and not active:
            st = "просрочено"
            status_counts["expired"] += 1
        elif active and not expired:
            st = "действительно"
            status_counts["active"] += 1
        else:
            st = "неизвестно"
            status_counts["unknown"] += 1
        source_status[url] = st

    total = sum(status_counts.values())
    if total == 0:
        final = "Неизвестно"
        conf = 0.0
    elif status_counts["expired"] >= status_counts["active"] and status_counts["expired"] > 0:
        final = "Просрочено"
        conf = status_counts["expired"] / total
    elif status_counts["active"] > status_counts["expired"]:
        final = "Действительно"
        conf = status_counts["active"] / total
    else:
        final = "Неизвестно"
        conf = 0.0

    # After final calculation, if status Unknown we call second pass
    if final == "Неизвестно":
        second = await _second_pass_check(query)
        if second:
            url2, html2 = second
            expired2 = any(k in html2 for k in EXPIRED_KEYWORDS)
            active2 = any(k in html2 for k in ACTIVE_KEYWORDS)
            if expired2 != active2:  # only if we can determine
                final = "Просрочено" if expired2 else "Действительно"
                conf = 1.0
            source_status[url2] = final.lower()

    return {
        "источник_статусы": source_status,
        "статус": final,
        "уверенность": round(conf, 2),
    }


async def bulk_validate(refs: List[str]) -> Dict[str, Dict]:
    """Validate multiple references concurrently."""
    tasks = [validate_reference(r) for r in refs]
    results_list = await asyncio.gather(*tasks)
    return {ref: res for ref, res in zip(refs, results_list)}


async def bulk_validate_enhanced(refs: List, use_garant: bool = True, progress_callback=None) -> Dict[str, Dict]:
    """
    Расширенная валидация с поддержкой проверки через ГАРАНТ
    
    Args:
        refs: Список объектов Reference или строк
        use_garant: Использовать ли проверку через ГАРАНТ
        progress_callback: Callback функция для отображения прогресса
        
    Returns:
        Словарь с результатами валидации
    """
    # Сначала выполняем стандартную валидацию
    ref_strings = []
    for ref in refs:
        if hasattr(ref, 'raw'):
            ref_strings.append(ref.raw)
        else:
            ref_strings.append(str(ref))
    
    if progress_callback:
        progress_callback("🔍 Выполняется базовая проверка через стандартные источники...")
    
    validation_results = await bulk_validate(ref_strings)
    
    # Показываем промежуточные результаты
    unknown_count = sum(
        1 for result in validation_results.values() 
        if result.get("статус", "").lower() == "неизвестно"
    )
    
    if progress_callback:
        progress_callback(f"📊 Базовая проверка завершена. Неизвестных статусов: {unknown_count}")
    
    # Если много неизвестных статусов и доступен ГАРАНТ - используем его
    if use_garant and GARANT_AVAILABLE and unknown_count > 10:
        if progress_callback:
            progress_callback(f"🎯 Запускается дополнительная проверка через ГАРАНТ для {unknown_count} документов...")
        
        # Преобразуем строки обратно в Reference объекты для ГАРАНТ
        ref_objects = []
        if hasattr(refs[0], 'raw'):  # Если уже Reference объекты
            ref_objects = refs
        else:
            # Если строки, создаем базовые Reference объекты
            from references_extractor import Reference
            ref_objects = [
                Reference(raw=ref_str, type="Документ", number=None, date=None, title=None)
                for ref_str in ref_strings
            ]
        
        # Используем интегрированную функцию с параллельной обработкой (5 Chrome инстансов)
        validation_results = enhance_validation_with_garant(ref_objects, validation_results)
        
        # Показываем финальную статистику
        final_unknown_count = sum(
            1 for result in validation_results.values() 
            if result.get("статус", "").lower() == "неизвестно"
        )
        
        improved_count = unknown_count - final_unknown_count
        if progress_callback:
            progress_callback(f"✅ Параллельная проверка через ГАРАНТ (5 Chrome инстансов) улучшила статус для {improved_count} документов")
        
    elif use_garant and unknown_count > 10 and not GARANT_AVAILABLE:
        if progress_callback:
            progress_callback("⚠️  Нужна проверка через ГАРАНТ, но модуль недоступен")
        
    return validation_results 