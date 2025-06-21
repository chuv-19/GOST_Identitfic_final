"""
Модуль для проверки правовых документов
"""

import os
import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
import typer

from doc_parser import extract_text
from references_extractor import extract_references
from validator import bulk_validate_enhanced
from excel_report_generator import ExcelReportGenerator, Document

# Document validation modules
try:
    from document_validator import DocumentValidator, DocumentType
    VALIDATOR_AVAILABLE = True
except ModuleNotFoundError:
    VALIDATOR_AVAILABLE = False
    # Fallback stubs to keep rest of the script functional
    from enum import Enum

    class DocumentType(str, Enum):
        UNKNOWN = "UNKNOWN"

    class DocumentValidator:  # type: ignore
        def __getattr__(self, item):
            raise NotImplementedError("DocumentValidator has been removed from this project")

app = typer.Typer(add_completion=False, help="Анализ .docx на актуальность ссылок на нормативные документы.")
console = Console()


def _human_status(status: str) -> str:
    color = {
        "Действительно": "green",
        "Просрочено": "red",
        "Неизвестно": "yellow",
    }.get(status, "white")
    return f"[{color}]{status}[/{color}]"


def build_report(docx_path: Path, mistral_api_key: str | None = None, use_validator: bool = True):
    console = Console()
    
    console.rule(f"📑 Обработка: {docx_path.name}")
    text = extract_text(docx_path)

    with Progress(SpinnerColumn(), "Извлечение ссылок", TimeElapsedColumn(), console=console) as progress:
        t1 = progress.add_task("extract", total=None)
        refs = extract_references(text, mistral_api_key=mistral_api_key)
        progress.remove_task(t1)

    console.print(f"Найдено ссылок: [bold]{len(refs)}[/bold]")

    if not refs:
        console.print("[yellow]Ссылки не найдены — отчет не сформирован.[/yellow]")
        return

    # Filter references to ensure they have required fields: Type, (number or name), and date
    filtered_refs = []
    skipped_count = 0
    
    for ref in refs:
        # Check if reference has required fields
        has_type = ref.type and ref.type.strip()
        has_number_or_name = (ref.number and ref.number.strip()) or (ref.title and ref.title.strip())
        has_date = ref.date and ref.date.strip()
        
        missing_fields = []
        if not has_type:
            missing_fields.append("Тип")
        if not has_number_or_name:
            missing_fields.append("Номер/Название")
        if not has_date:
            missing_fields.append("Дата")
        
        if has_type and has_number_or_name and has_date:
            filtered_refs.append(ref)
        else:
            skipped_count += 1
            console.print(f"[yellow]⚠️  Пропущена ссылка без полей {', '.join(missing_fields)}: {ref.raw[:100]}...[/yellow]")

    if not filtered_refs:
        console.print(f"[red]❌ Не найдено ссылок с обязательными полями (Тип, Номер/Название, Дата).[/red]")
        console.print(f"[yellow]📊 Всего найдено: {len(refs)}, пропущено: {skipped_count}[/yellow]")
        return

    console.print(f"✅ Ссылок с обязательными полями: [bold]{len(filtered_refs)}[/bold] из [bold]{len(refs)}[/bold]")
    if skipped_count > 0:
        console.print(f"[yellow]⚠️  Пропущено ссылок без обязательных полей: {skipped_count}[/yellow]")

    # Show initial table with found references before validation
    console.print(f"\n📋 [bold]Найденные ссылки (до проверки):[/bold]")
    initial_table = Table(show_header=True, header_style="bold blue")
    initial_table.add_column("№", justify="right")
    initial_table.add_column("Тип")
    initial_table.add_column("Номер")
    initial_table.add_column("Дата")
    initial_table.add_column("Название")
    initial_table.add_column("Статус")

    for idx, ref in enumerate(filtered_refs, 1):
        initial_table.add_row(
            str(idx), 
            ref.type, 
            ref.number or "", 
            ref.date or "", 
            ref.title or "", 
            "[yellow]Ожидает проверки...[/yellow]"
        )

    console.print(initial_table)

    # Progress callback function
    def progress_callback(message):
        console.print(f"[blue]{message}[/blue]")

    # Validate references
    console.print(f"\n🔍 [bold]Выполняется проверка статусов...[/bold]")
    
    # Additional validation if enabled
    if use_validator and VALIDATOR_AVAILABLE:
        console.print(f"[cyan]🔎 Дополнительная проверка документов...[/cyan]")
        validator = DocumentValidator()
        
        # Enhance validation with additional checks
        enhanced_refs = []
        
        with Progress(SpinnerColumn(), "Проверка документов", TimeElapsedColumn(), console=console) as progress:
            task = progress.add_task("checking", total=len(filtered_refs))
            
            for i, ref in enumerate(filtered_refs):
                # Format short description for progress
                short_desc = ref.raw[:50] + "..." if len(ref.raw) > 50 else ref.raw
                progress.update(task, advance=1, description=f"Проверка {i+1}/{len(filtered_refs)}: {short_desc}")
                
                # Initialize default status
                ref.validation_status = "Не проверено"
                ref.validation_url = None
                
                try:
                    # Determine document type
                    doc_type = None
                    ref_type_upper = ref.type.upper()
                    ref_number_upper = (ref.number or "").upper()
                    ref_title_upper = (ref.title or "").upper()
                    
                    if any(keyword in ref_type_upper or keyword in ref_number_upper or keyword in ref_title_upper 
                           for keyword in ["ГОСТ", "ОСТ", "ТУ", "СТАНДАРТ"]):
                        doc_type = DocumentType.GOST
                    elif any(keyword in ref_type_upper for keyword in ["ПРИКАЗ", "РАСПОРЯЖЕНИЕ"]):
                        doc_type = DocumentType.DECREE
                    elif "ПОСТАНОВЛЕНИЕ" in ref_type_upper:
                        doc_type = DocumentType.REGULATION
                    elif any(keyword in ref_type_upper for keyword in ["ЗАКОН", "КОДЕКС"]):
                        doc_type = DocumentType.LAW
                    elif "ИНСТРУКЦИЯ" in ref_type_upper:
                        doc_type = DocumentType.INSTRUCTION
                    elif "РЕГЛАМЕНТ" in ref_type_upper:
                        doc_type = DocumentType.TECHNICAL_REGULATION
                    
                    # Build search queries
                    search_queries = []
                    
                    if ref.type and ref.number:
                        search_queries.append(f"{ref.type} {ref.number}".strip())
                        if ref.date:
                            search_queries.append(f"{ref.type} {ref.number} от {ref.date}".strip())
                    
                    if ref.raw and len(ref.raw.strip()) > 10:
                        search_queries.insert(0, ref.raw.strip()[:200])
                    
                    if ref.title and len(ref.title.strip()) > 5:
                        search_queries.append(ref.title.strip()[:150])
                    
                    if ref.number and ref.title:
                        search_queries.append(f"{ref.number} {ref.title}"[:150])
                    
                    if not search_queries and ref.number:
                        search_queries.append(ref.number.strip())
                    
                    # Try each query until we find a match
                    found_doc = None
                    for query in search_queries:
                        try:
                            if doc_type:
                                found_docs = validator.search_documents(query, document_types=[doc_type], limit=1)
                            else:
                                found_docs = validator.search_documents(query, limit=1)
                                
                            if found_docs:
                                found_doc = found_docs[0]
                                break
                        except Exception as e:
                            console.print(f"[yellow]⚠️  Ошибка поиска по запросу '{query}': {str(e)}[/yellow]")
                            continue
                    
                    if found_doc:
                        ref.validation_status = found_doc.status.value
                        ref.validation_url = found_doc.url
                        
                        # Get detailed status if available
                        try:
                            detailed_status = validator.check_document_status(found_doc.id, found_doc.document_type)
                            ref.validation_status = f"{found_doc.status.value} ({detailed_status.value})"
                        except Exception as e:
                            console.print(f"[yellow]⚠️  Ошибка получения детального статуса: {str(e)}[/yellow]")
                    else:
                        ref.validation_status = "Не найден"
                        
                except Exception as e:
                    ref.validation_status = f"Ошибка поиска: {str(e)[:50]}"
                    console.print(f"[red]❌ Ошибка проверки документа: {str(e)}[/red]")
                
                enhanced_refs.append(ref)
            
            progress.update(task, completed=len(filtered_refs))
        
        # Show validation statistics
        validated_found = sum(1 for ref in filtered_refs if ref.validation_status and "найден" not in ref.validation_status.lower() and "ошибка" not in ref.validation_status.lower())
        not_found = sum(1 for ref in filtered_refs if "не найден" in (ref.validation_status or "").lower())
        errors = sum(1 for ref in filtered_refs if "ошибка" in (ref.validation_status or "").lower())
        
        console.print("\n📊 [bold]Результаты проверки:[/bold]")
        console.print(f"✅ Найдено: [green]{validated_found}[/green]")
        console.print(f"❌ Не найдено: [red]{not_found}[/red]")
        console.print(f"⚠️  Ошибки: [yellow]{errors}[/yellow]")
        
        filtered_refs = enhanced_refs
    
    # Validate using standard sources
    validation_results = asyncio.run(bulk_validate_enhanced(filtered_refs, progress_callback=progress_callback))

    # Generate report
    console.print("\n📝 [bold]Формирование отчета...[/bold]")
    
    report_data = []
    for ref in filtered_refs:
        validation_result = validation_results.get(ref.raw, {})
        validation_info = getattr(ref, 'validation_status', 'Не проверено')
        
        report_data.append({
            "Ссылка": ref.raw,
            "Тип документа": ref.type,
            "Номер": ref.number,
            "Дата": ref.date,
            "Название": ref.title,
            "Статус": validation_result.get("статус", "Неизвестно"),
            "Уверенность": validation_result.get("уверенность", 0),
            "Валидация": validation_info,
            "Источники": validation_result.get("источник_статусы", {})
        })

    # Create Excel report
    generator = ExcelReportGenerator()
    documents = []
    
    for data in report_data:
        try:
            # Get validation source and extract just the URL
            validation_source = data.get("Источники", {})
            if isinstance(validation_source, dict):
                # Find the first URL in the sources
                url_source = None
                for source in validation_source.keys():
                    if "http" in source.lower():
                        url_source = source
                        break
                validation_source = url_source if url_source else "Bulk Validator"
            elif not validation_source:
                validation_source = "Bulk Validator"
            
            doc = Document(
                doc_type=data["Тип документа"],
                number=data["Номер"],
                date=data["Дата"],
                title=data["Название"],
                status=data["Статус"],
                confidence=data["Уверенность"],
                validation_status=getattr(ref, 'validation_status', None),
                validation_url=getattr(ref, 'validation_url', None),
                validation_source=validation_source,
                validation_date=datetime.now()
            )
            documents.append(doc)
        except Exception as e:
            console.print(f"[yellow]⚠️  Ошибка при создании документа: {str(e)}[/yellow]")
            continue

    report_data = {
        'documents': documents,
        'source_file': str(docx_path),
        'extraction_method': 'Document Analysis',
        'processing_time': 0.0
    }
    
    # Create report path on desktop with timestamp
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_filename = f"legal_documents_search_report_{timestamp}.xlsx"
    report_path = os.path.join(desktop_path, report_filename)
    
    try:
        # Ensure desktop directory exists
        os.makedirs(desktop_path, exist_ok=True)
        
        # Generate report
        report_file = generator.create_report(report_data, report_path)
        if report_file:
            console.print(f"\n✨ [bold green]Отчет сохранен:[/bold green] {report_file}")
        else:
            console.print("[red]❌ Ошибка при сохранении отчета.[/red]")
    except Exception as e:
        console.print(f"[red]❌ Ошибка при создании отчета: {str(e)}[/red]")


@app.command("analyze")
def analyze(
    doc: Path = typer.Argument(..., exists=True, help="Путь к .docx файлу"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API ключ для Mistral"),
    use_validator: bool = typer.Option(True, "--validator/--no-validator", help="Использовать дополнительную валидацию")
):
    """Анализ документа и создание отчета."""
    if not doc.suffix.lower() == '.docx':
        console.print("[red]❌ Поддерживаются только файлы .docx[/red]")
        raise typer.Exit(1)

    try:
        if use_validator:
            console.print("[cyan]ℹ️  Включена дополнительная валидация документов[/cyan]")
        
        build_report(doc, mistral_api_key=api_key, use_validator=use_validator)
        
    except Exception as e:
        console.print(f"[red]❌ Ошибка: {str(e)}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app() 