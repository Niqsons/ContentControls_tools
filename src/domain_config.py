#!/usr/bin/env python3
"""
Domain Configuration Loader for Draft Builder

Загружает доменные конфиги из JSON, поддерживает наследование (extends),
компилирует regex-паттерны, автоопределяет домен по тексту документа.
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

DOMAINS_DIR = Path(__file__).parent / "domains"


@dataclass
class DomainConfig:
    """Доменная конфигурация"""
    domain_id: str
    display_name: str
    entity_hints: Dict[str, re.Pattern]
    type_hints: Dict[str, re.Pattern]
    field_name_map: Dict[str, str]
    optional_classifiers: List[dict]
    alternative_classifiers: List[dict]
    combo_options: Dict[str, List[Tuple[str, str]]]
    llm_system_prompt: str
    llm_user_prompt_template: str
    llm_document_type: str


def _compile_hints(hints_raw: dict) -> Dict[str, re.Pattern]:
    """Компилировать regex-паттерны из JSON"""
    compiled = {}
    for key, spec in hints_raw.items():
        flags = re.IGNORECASE if spec.get('case_insensitive') else 0
        compiled[key] = re.compile(spec['pattern'], flags)
    return compiled


def _merge_dicts(base: dict, override: dict) -> dict:
    """Shallow merge: override заменяет ключи base"""
    result = dict(base)
    result.update(override)
    return result


def _merge_lists(base: list, override: list) -> list:
    """Append: override добавляется к base"""
    return base + override


def _load_raw(name_or_path: str) -> dict:
    """Загрузить JSON конфиг по имени или пути"""
    path = Path(name_or_path)
    if not path.exists():
        path = DOMAINS_DIR / f"{name_or_path}.json"
    if not path.exists():
        raise FileNotFoundError(f"Domain config not found: {name_or_path}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_domain(name_or_path: str) -> DomainConfig:
    """Загрузить доменный конфиг с разрешением наследования"""
    raw = _load_raw(name_or_path)

    # Разрешить extends
    if raw.get('extends'):
        base_raw = _load_raw(raw['extends'])

        entity_hints = _merge_dicts(
            base_raw.get('entity_hints', {}),
            raw.get('entity_hints', {})
        )
        type_hints = _merge_dicts(
            base_raw.get('type_hints', {}),
            raw.get('type_hints', {})
        )
        field_name_map = _merge_dicts(
            base_raw.get('field_name_map', {}),
            raw.get('field_name_map', {})
        )
        optional_classifiers = _merge_lists(
            base_raw.get('optional_classifiers', []),
            raw.get('optional_classifiers', [])
        )
        alternative_classifiers = _merge_lists(
            base_raw.get('alternative_classifiers', []),
            raw.get('alternative_classifiers', [])
        )
        combo_options = _merge_dicts(
            base_raw.get('combo_options', {}),
            raw.get('combo_options', {})
        )
        # LLM context: override полностью если есть в домене
        llm_ctx = raw.get('llm_context') or base_raw.get('llm_context', {})
    else:
        entity_hints = raw.get('entity_hints', {})
        type_hints = raw.get('type_hints', {})
        field_name_map = raw.get('field_name_map', {})
        optional_classifiers = raw.get('optional_classifiers', [])
        alternative_classifiers = raw.get('alternative_classifiers', [])
        combo_options = raw.get('combo_options', {})
        llm_ctx = raw.get('llm_context', {})

    # Компилировать regex
    compiled_entities = _compile_hints(entity_hints)
    compiled_types = _compile_hints(type_hints)

    # combo_options: list of lists → list of tuples
    combo_tuples = {}
    for key, items in combo_options.items():
        combo_tuples[key] = [(item[0], item[1]) for item in items]

    # Подставить переменные в LLM промпты
    entity_list = ', '.join(entity_hints.keys())
    field_name_examples = ', '.join(sorted(set(field_name_map.values())))
    field_type_list = ', '.join(type_hints.keys())

    system_prompt = llm_ctx.get('system_prompt', '').format(
        entity_list=entity_list,
        field_name_examples=field_name_examples,
        field_type_list=field_type_list,
    )
    user_prompt_template = llm_ctx.get('user_prompt_template', '')

    return DomainConfig(
        domain_id=raw['domain_id'],
        display_name=raw['display_name'],
        entity_hints=compiled_entities,
        type_hints=compiled_types,
        field_name_map=field_name_map,
        optional_classifiers=optional_classifiers,
        alternative_classifiers=alternative_classifiers,
        combo_options=combo_tuples,
        llm_system_prompt=system_prompt,
        llm_user_prompt_template=user_prompt_template,
        llm_document_type=llm_ctx.get('document_type', 'документ'),
    )


def detect_domain(text_sample: str, domains_dir: str = None) -> DomainConfig:
    """Автоопределение домена по тексту документа.

    Сканирует все доменные конфиги (кроме _base*),
    считает совпадения entity_hints, выбирает лучший.
    """
    search_dir = Path(domains_dir) if domains_dir else DOMAINS_DIR
    best_domain = None
    best_score = 0
    text_lower = text_sample.lower()

    for json_file in search_dir.glob('*.json'):
        if json_file.stem.startswith('_'):
            continue
        try:
            domain = load_domain(str(json_file))
        except Exception:
            continue

        score = 0
        for pattern in domain.entity_hints.values():
            score += len(pattern.findall(text_lower))

        if score > best_score:
            best_score = score
            best_domain = domain

    if best_domain:
        return best_domain

    # Fallback: базовый юридический
    return load_domain('_base_legal_ru')


def list_domains(domains_dir: str = None) -> List[dict]:
    """Список доступных доменов"""
    search_dir = Path(domains_dir) if domains_dir else DOMAINS_DIR
    result = []
    for json_file in sorted(search_dir.glob('*.json')):
        try:
            raw = _load_raw(str(json_file))
            result.append({
                'id': raw['domain_id'],
                'name': raw['display_name'],
                'file': json_file.name,
            })
        except Exception:
            continue
    return result
