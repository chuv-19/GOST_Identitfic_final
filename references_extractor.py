import re
from dataclasses import dataclass
from typing import List, Dict, Pattern

from utils import normalize_whitespace

# ---------------------------
# Data structures
# ---------------------------
@dataclass
class Reference:
    raw: str
    type: str
    number: str | None
    date: str | None
    title: str | None

    def to_record(self) -> Dict:
        return {
            "Тип": self.type,
            "Номер": self.number or "",
            "Дата": self.date or "",
            "Название": self.title or "",
            "raw": self.raw,
        }


class RegexRule:
    def __init__(self, doc_type: str, pattern: str):
        self.doc_type = doc_type
        self.regex: Pattern = re.compile(pattern, flags=re.IGNORECASE | re.UNICODE)

    def extract(self, text: str) -> List[Reference]:
        refs: List[Reference] = []
        for m in self.regex.finditer(text):
            gd = m.groupdict()
            # Get title from either quoted or unquoted group
            title = gd.get("title") or gd.get("title_unquoted")
            if title:
                title = title.strip()
                if not title:
                    title = None
            
            refs.append(
                Reference(
                    raw=m.group(0).strip(),
                    type=self.doc_type,
                    number=gd.get("number") or gd.get("number2"),
                    date=gd.get("date"),
                    title=title,
                )
            )
        return refs


# ---------------------------
# Rule generation
# ---------------------------
DOC_TOKENS = [
    "Федеральный закон",
    "Закон",
    "Конституция",
    "Кодекс",
    "Приказ",
    "Распоряжение",
    "Постановление",
    "Указ",
    "Декрет",
    "Регламент",
    "Технический регламент",
    "ТР ТС",
    "ТР ЕАЭС",
    "ГОСТ",
    "ГОСТ Р",
    "ISO",
    "IEC",
    "СНиП",
    "СП",
    "СанПиН",
    "ПНСТ",
    "ФНП",
]


def _escape_token(token: str) -> str:
    return re.escape(token).replace("\\ ", "\\s+")  # allow any whitespace between words


RULES: List[RegexRule] = []

# Generic pattern template (date/number/title optional)
# Improved template to handle long organization names and flexible order
# Also captures titles without quotes
# Enhanced to better capture dates in various formats
TEMPLATE = r"{token}(?:[^«»\"]*от\s+(?P<date>\d{{1,2}}\.\d{{1,2}}\.\d{{4}}|\d{{1,2}}\.\d{{1,2}}\.\d{{2}}|\d{{4}}-\d{{2}}-\d{{2}}))?(?:[^«»\"]*№\s*(?P<number>[A-Za-zА-Яа-я0-9\-\.\/]+))?(?:[^«»\"]*[«\"](?P<title>[^»\"]+)[»\"]|(?P<title_unquoted>(?:\s+[А-Я][^.;]*)?))?"

for tok in DOC_TOKENS:
    # Skip ГОСТ tokens - they will be handled by specialized rules
    if tok in ["ГОСТ", "ГОСТ Р"]:
        continue
    pattern = TEMPLATE.format(token=_escape_token(tok))
    RULES.append(RegexRule(tok, pattern))

# Add additional patterns for better date and number extraction
# Pattern for documents with date first
# RULES.append(
#     RegexRule(
#         "Документ с датой",
#         r"(?P<date>\d{1,2}\.\d{1,2}\.\d{4})\s+(?:от\s+)?(?:Федеральный\s+)?(?:закон|приказ|постановление|указ|распоряжение)\s+(?:№\s*)?(?P<number>[A-Za-zА-Яа-я0-9\-\.\/]+)?",
#     )
# )

# Pattern for documents with number first
# RULES.append(
#     RegexRule(
#         "Документ с номером",
#         r"(?:Федеральный\s+)?(?:закон|приказ|постановление|указ|распоряжение)\s+(?:№\s*)?(?P<number>[A-Za-zА-Яа-я0-9\-\.\/]+)\s+(?:от\s+)?(?P<date>\d{1,2}\.\d{1,2}\.\d{4})?",
#     )
# )

# Enhanced ГОСТ patterns with better date capture
# Pattern for ГОСТ with date
RULES.append(
    RegexRule(
        "ГОСТ с датой",
        r"ГОСТ\s+(?P<number>[\d]{1,3}(?:\.\d{3})?(?:-\d{2,4})+)\s+(?:от\s+)?(?P<date>\d{1,2}\.\d{1,2}\.\d{4})\s*[«\"](?P<title>[^»\"]{1,200})[»\"]",
    )
)

# Pattern for ГОСТ Р with date
RULES.append(
    RegexRule(
        "ГОСТ Р с датой",
        r"ГОСТ\s+Р\s+(?:ИСО|ISO)?(?:/МЭК|/IEC)?\s+(?P<number>[\d\.\-]+(?:-\d{1,4})+)\s+(?:от\s+)?(?P<date>\d{1,2}\.\d{1,2}\.\d{4})\s*[«\"](?P<title>[^»\"]{1,200})[»\"]",
    )
)

# Improved ГОСТ patterns to prevent capturing too much text
# Pattern for simple ГОСТ with quotes
RULES.append(
    RegexRule(
        "ГОСТ",
        r"ГОСТ\s+(?P<number>[\d]{1,3}(?:\.\d{3})?(?:-\d{2,4})+)\s*[«\"](?P<title>[^»\"]{1,200})[»\"]",
    )
)

# Pattern for ГОСТ R ISO/IEC with quotes  
RULES.append(
    RegexRule(
        "ГОСТ Р",
        r"ГОСТ\s+Р\s+(?:ИСО|ISO)(?:/МЭК|/IEC)?\s+(?P<number>[\d\.\-]+(?:-\d{1,4})+)\s*[«\"](?P<title>[^»\"]{1,200})[»\"]",
    )
)

# Pattern for ГОСТ without quotes - limited title length and stop at next ГОСТ
RULES.append(
    RegexRule(
        "ГОСТ", 
        r"ГОСТ\s+(?P<number>[\d]{1,3}(?:\.\d{3})?(?:-\d{2,4})+)(?:\s+(?P<title>(?:(?!ГОСТ\s+[\d]).){1,200}?))?(?=\s+ГОСТ\s+[\d]|\s*$|[;.])",
    )
)

# Pattern for ГОСТ R without quotes - limited title length and stop at next ГОСТ  
RULES.append(
    RegexRule(
        "ГОСТ Р",
        r"ГОСТ\s+Р\s+(?:ИСО|ISO)?(?:/МЭК|/IEC)?\s*(?P<number>[\d\.\-]+(?:-\d{1,4})+)(?:\s+(?P<title>(?:(?!ГОСТ\s+[\d]).){1,200}?))?(?=\s+ГОСТ\s+[\d]|\s*$|[;.])",
    )
)

# Additional pattern for ГОСТ Р with ИСО/МЭК numbers
RULES.append(
    RegexRule(
        "ГОСТ Р",
        r"ГОСТ\s+Р\s+ИСО(?:/МЭК)?\s+(?P<number>[\d\.\-]+(?:-\d{1,4})+)(?:\s+(?P<title>(?:(?!ГОСТ\s+[\d]).){1,200}?))?",
    )
)

# Add comprehensive text preprocessing for better GOST extraction
def preprocess_text_for_gosts(text: str) -> str:
    """Preprocess text to better separate GOST references"""
    # Add separators before ГОСТ patterns to help with splitting, but preserve quotes
    text = re.sub(r'([»\"]);?\s+(ГОСТ\s+(?:Р\s+)?)', r'\1; \2', text)
    # Normalize common variations
    text = re.sub(r'ГОСТ\s+Р\s+ИСО\s*/\s*МЭК', 'ГОСТ Р ИСО/МЭК', text)
    text = re.sub(r'ГОСТ\s+Р\s+ИСО(?!\s*/)', 'ГОСТ Р ИСО', text)
    return text

# Add post-processing to split long titles that contain multiple GOSTs
def split_multiple_gosts(refs: List[Reference]) -> List[Reference]:
    """Split references that contain multiple GOSTs in the title"""
    result = []
    
    for ref in refs:
        if not ref.title:
            result.append(ref)
            continue
            
        # Look for ГОСТ patterns in the title
        gost_pattern = r'ГОСТ\s+(?:Р\s+)?(?:ИСО|ISO)?(?:/МЭК|/IEC)?\s*([\d\.\-]+(?:-\d{1,4})+)'
        gost_matches = list(re.finditer(gost_pattern, ref.title))
        
        if len(gost_matches) <= 1:
            # Clean up the title - remove trailing ГОСТ references
            clean_title = re.sub(r'\s+ГОСТ\s+.*$', '', ref.title).strip()
            if clean_title and len(clean_title) < len(ref.title):
                ref.title = clean_title
            result.append(ref)
        else:
            # Split into multiple references
            title_parts = re.split(r'(?=ГОСТ\s+(?:Р\s+)?(?:ИСО|ISO)?(?:/МЭК|/IEC)?)', ref.title)
            
            for i, part in enumerate(title_parts):
                if not part.strip():
                    continue
                    
                part = part.strip()
                match = re.match(r'ГОСТ\s+(Р\s+)?(?:(ИСО|ISO)(?:/МЭК|/IEC)?\s+)?([\d\.\-]+(?:-\d{1,4})+)', part)
                
                if match:
                    gost_type = "ГОСТ Р" if match.group(1) else "ГОСТ"
                    number = match.group(3)
                    # Extract title after the number
                    title_match = re.search(r'ГОСТ\s+(?:Р\s+)?(?:ИСО|ISO)?(?:/МЭК|/IEC)?\s*[\d\.\-]+(?:-\d{1,4})+\s*(.+)', part)
                    title = title_match.group(1).strip() if title_match else None
                    
                    # Clean title - stop at next ГОСТ or certain punctuation
                    if title:
                        title = re.sub(r'\s+ГОСТ\s+.*', '', title)
                        title = re.sub(r'\s*[;].*', '', title) 
                        title = title[:200].strip()  # Limit length
                        if not title:
                            title = None
                    
                    result.append(Reference(
                        raw=part[:100] + "..." if len(part) > 100 else part,
                        type=gost_type,
                        number=number,
                        date=ref.date,
                        title=title
                    ))
                elif i == 0:
                    # Keep the original reference if first part doesn't match
                    result.append(ref)
    
    return result


# ---------------------------
# LLM fallback (optional)
# ---------------------------
try:
    from mistralai.client import MistralClient
    from mistralai.models.chat_completion import ChatMessage

    _MISTRAL_AVAILABLE = True
except ImportError:
    _MISTRAL_AVAILABLE = False

MISTRAL_MODEL = "mistral-tiny"


def _extract_with_llm(text: str, api_key: str) -> List[Reference]:
    if not _MISTRAL_AVAILABLE:
        return []

    client = MistralClient(api_key=api_key)
    system = (
        "You are a smart assistant that analyzes user requests carefully and answers in Russian.\n"
        "Найди в тексте все нормативные документы (ГОСТ, Приказ, Постановление и т.д.).\n"
        "Для каждого выведи в формате: Тип документа; Номер; Дата.\n"
        "Отвечай построчно, каждую запись на новой строке, поля разделяй точкой с запятой ';'.\n"
        "Если дата отсутствует, оставь поле пустым.\n"
        "Пример:\n"
        "ГОСТ; 1234-56; 01.01.2000\n"
        "Приказ; 12; 05.05.2022\n"
    )
    resp = client.chat(
        model=MISTRAL_MODEL,
        messages=[
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=text[:8000]),
        ],
    )

    content = resp.choices[0].message.content.strip()
    refs: List[Reference] = []
    for line in content.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 2:
            continue
        doc_type = parts[0]
        number = parts[1] if len(parts) >= 2 else None
        date = parts[2] if len(parts) >= 3 else None
        refs.append(
            Reference(raw=line.strip(), type=doc_type, number=number, date=date, title=None)
        )
    return refs


# ---------------------------
# Public API
# ---------------------------

def extract_gost_from_long_text(text: str) -> List[Reference]:
    """Extract individual GOST references from long concatenated text"""
    refs = []
    
    # Split by semicolons and quotes to separate individual references
    parts = re.split(r'[;]+\s*(?=ГОСТ)|(?<=[»\"])\s*(?=ГОСТ)', text)
    
    for part in parts:
        part = part.strip()
        if not part or not re.search(r'ГОСТ', part):
            continue
            
        # Try to extract GOST from this part
        gost_match = re.search(r'ГОСТ\s+(Р\s+)?(?:(ИСО|ISO)(?:/МЭК|/IEC)?\s+)?([\d\.\-]+(?:-\d{1,4})+)', part)
        if gost_match:
            gost_r = gost_match.group(1) is not None
            gost_type = "ГОСТ Р" if gost_r else "ГОСТ"
            number = gost_match.group(3)
            
            # Extract title - look for quoted text
            title_match = re.search(r'[«\"](.*?)[»\"]', part)
            title = title_match.group(1) if title_match else None
            
            # If no quoted title, try to extract unquoted title
            if not title:
                title_match = re.search(r'ГОСТ\s+(?:Р\s+)?(?:ИСО|ISO)?(?:/МЭК|/IEC)?\s*[\d\.\-]+(?:-\d{1,4})+\s+(.+)', part)
                if title_match:
                    title = title_match.group(1).strip()
                    # Clean up title - remove trailing ГОСТ references
                    title = re.sub(r'\s+ГОСТ\s+.*$', '', title).strip()
                    if len(title) > 200:
                        title = title[:200].strip()
            
            refs.append(Reference(
                raw=part[:100] + "..." if len(part) > 100 else part,
                type=gost_type,
                number=number,
                date=None,
                title=title
            ))
    
    return refs

def extract_references(text: str, mistral_api_key: str | None = None, use_llm: bool = True) -> List[Reference]:
    text = normalize_whitespace(text)
    text = preprocess_text_for_gosts(text)
    
    refs: List[Reference] = []
    
    # First try direct extraction with improved patterns
    for rule in RULES:
        refs.extend(rule.extract(text))

    # Then try to extract from long concatenated texts
    # Look for very long GOST sequences that weren't properly split
    long_gost_pattern = r'ГОСТ[^;]{200,}'
    for match in re.finditer(long_gost_pattern, text):
        long_text = match.group(0)
        extra_refs = extract_gost_from_long_text(long_text)
        refs.extend(extra_refs)

    if use_llm and mistral_api_key:
        refs.extend(_extract_with_llm(text, mistral_api_key))

    # Apply post-processing to split multiple GOSTs
    refs = split_multiple_gosts(refs)

    # Enhance references by looking for missing dates and numbers
    refs = enhance_references(refs)

    # Validate and clean up references
    refs = validate_and_clean_references(refs)

    # Smart deduplication to avoid duplicates like "Федеральный закон" and "Закон"
    seen = set()
    unique: List[Reference] = []
    
    # Sort by type specificity (longer types first)
    refs.sort(key=lambda x: len(x.type), reverse=True)
    
    for r in refs:
        # Create a key based on content, not just type
        content_key = f"{r.number or ''}|{r.date or ''}|{(r.title or '')[:50]}"
        
        # Check if we already have a more specific version of this document
        is_duplicate = False
        for existing_key in seen:
            existing_content = existing_key.split('|', 1)[1] if '|' in existing_key else ''
            if content_key == existing_content and content_key.strip('|'):
                is_duplicate = True
                break
                
        if not is_duplicate:
            full_key = f"{r.type}|{content_key}"
            seen.add(full_key)
            unique.append(r)
    
    return unique

# Add function to enhance references with missing fields
def enhance_references(refs: List[Reference]) -> List[Reference]:
    """Enhance references by looking for missing dates and numbers in raw text"""
    enhanced_refs = []
    
    for ref in refs:
        enhanced_ref = ref
        
        # If missing date, try to extract from raw text
        if not ref.date:
            date_patterns = [
                r'\d{1,2}\.\d{1,2}\.\d{4}',  # DD.MM.YYYY
                r'\d{1,2}\.\d{1,2}\.\d{2}',  # DD.MM.YY
                r'\d{4}-\d{2}-\d{2}',        # YYYY-MM-DD
            ]
            
            for pattern in date_patterns:
                date_match = re.search(pattern, ref.raw)
                if date_match:
                    enhanced_ref = Reference(
                        raw=ref.raw,
                        type=ref.type,
                        number=ref.number,
                        date=date_match.group(0),
                        title=ref.title
                    )
                    break
        
        # If missing number, try to extract from raw text
        if not ref.number:
            # Look for number patterns after the document type
            number_patterns = [
                r'№\s*([A-Za-zА-Яа-я0-9\-\.\/]+)',
                r'номер\s+([A-Za-zА-Яа-я0-9\-\.\/]+)',
                r'(?:от\s+)?([A-Za-zА-Яа-я0-9\-\.\/]{2,})\s+(?:от|дата|«)',
            ]
            
            for pattern in number_patterns:
                number_match = re.search(pattern, ref.raw)
                if number_match:
                    potential_number = number_match.group(1).strip()
                    # Avoid extracting document types as numbers
                    if potential_number.lower() not in ['приказ', 'постановление', 'указ', 'закон', 'распоряжение', 'федеральный']:
                        enhanced_ref = Reference(
                            raw=ref.raw,
                            type=ref.type,
                            number=potential_number,
                            date=enhanced_ref.date,
                            title=ref.title
                        )
                        break
        
        enhanced_refs.append(enhanced_ref)
    
    return enhanced_refs

# Add function to validate and clean up references
def validate_and_clean_references(refs: List[Reference]) -> List[Reference]:
    """Validate and clean up references to ensure proper formatting"""
    validated_refs = []
    
    for ref in refs:
        # Clean up type field
        if ref.type:
            ref.type = ref.type.strip()
            # Remove extra whitespace and normalize
            ref.type = re.sub(r'\s+', ' ', ref.type)
        
        # Clean up number field
        if ref.number:
            ref.number = ref.number.strip()
            # Remove extra whitespace and normalize
            ref.number = re.sub(r'\s+', ' ', ref.number)
        
        # Clean up date field
        if ref.date:
            ref.date = ref.date.strip()
            # Normalize date format
            date_match = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', ref.date)
            if date_match:
                day, month, year = date_match.groups()
                if len(year) == 2:
                    year = '20' + year if int(year) < 50 else '19' + year
                ref.date = f"{day.zfill(2)}.{month.zfill(2)}.{year}"
        
        # Clean up title field
        if ref.title:
            ref.title = ref.title.strip()
            # Remove extra whitespace and normalize
            ref.title = re.sub(r'\s+', ' ', ref.title)
            # Limit title length
            if len(ref.title) > 200:
                ref.title = ref.title[:200].strip()
        
        # Only include references with valid type
        if ref.type and ref.type.strip():
            validated_refs.append(ref)
    
    return validated_refs 