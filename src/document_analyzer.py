#!/usr/bin/env python3
"""
Document Analyzer for Draft Builder
Гибридный парсер: алгоритм + LLM

Выход: template_config.json для template_builder.py
"""

import re
import json
import zipfile
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from lxml import etree

from domain_config import DomainConfig, load_domain, detect_domain, list_domains
from llm_provider import get_provider, parse_llm_json

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS (domain-agnostic markup patterns)
# ═══════════════════════════════════════════════════════════════════════════

W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

PATTERNS = {
    'placeholder': re.compile(r'\[●\]|\[___+\]'),
    'ai_comment': re.compile(r'\[Комментарий ИИ:\s*([^\]]+)\]'),
    'optional_block_start': re.compile(r'^\[(?!Комментарий)(.{10,})$'),
    'optional_block_end': re.compile(r'^(.+)\]$'),
    'alternative_sep': re.compile(r'^/$'),
    'article_heading': re.compile(r'^(\d+)\.\s*([А-ЯЁA-Z\s]+)$'),
    'numbered_item': re.compile(r'^(\d+\.\d+\.?\d*\.?)\s*(.*)'),
}


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Paragraph:
    """Параграф документа"""
    idx: int
    text: str
    style: Optional[str] = None
    is_heading: bool = False
    is_list_item: bool = False
    list_level: int = 0
    article_num: Optional[str] = None
    item_num: Optional[str] = None


@dataclass
class Placeholder:
    """Плейсхолдер в документе"""
    id: int
    para_idx: int
    char_pos: int
    context_before: str
    context_after: str
    ai_comment: Optional[str] = None

    # Классификация
    field_type: str = 'text'
    entity: Optional[str] = None
    field_name: Optional[str] = None
    xml_path: Optional[str] = None

    # Метаданные
    confidence: float = 0.0
    classified_by: str = 'none'  # 'heuristic', 'llm', 'manual'
    needs_review: bool = True

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'para_idx': self.para_idx,
            'char_pos': self.char_pos,
            'context': self.context_before[-40:] + '[●]' + self.context_after[:40],
            'ai_comment': self.ai_comment,
            'field_type': self.field_type,
            'entity': self.entity,
            'field_name': self.field_name,
            'xml_path': self.xml_path,
            'confidence': round(self.confidence, 2),
            'classified_by': self.classified_by,
            'needs_review': self.needs_review,
        }


@dataclass
class Alternative:
    """Альтернативный блок"""
    group_id: str
    option_idx: int
    start_para: int
    end_para: int
    text_preview: str
    placeholders: List[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OptionalBlock:
    """Необязательный блок"""
    tag: str
    start_para: int
    end_para: int
    text_preview: str
    placeholders: List[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocumentStructure:
    """Полная структура документа"""
    source_file: str
    paragraphs: List[Paragraph]
    placeholders: List[Placeholder]
    alternatives: List[Alternative]
    optionals: List[OptionalBlock]

    # Метаданные
    domain_id: str = ''
    namespace: str = "urn:draftbuilder:template:v1"
    xml_schema: Dict[str, Any] = field(default_factory=dict)
    combo_options: Dict[str, list] = field(default_factory=dict)

    def to_config(self) -> dict:
        """Экспорт в JSON конфиг для builder"""
        return {
            'meta': {
                'source_file': self.source_file,
                'domain': self.domain_id,
                'namespace': self.namespace,
                'total_paragraphs': len(self.paragraphs),
                'total_placeholders': len(self.placeholders),
                'total_alternatives': len(self.alternatives),
                'total_optionals': len(self.optionals),
            },
            'paragraphs': [
                {
                    'idx': p.idx,
                    'text': p.text,
                    'style': p.style,
                    'is_heading': p.is_heading,
                    'article_num': p.article_num,
                    'item_num': p.item_num,
                }
                for p in self.paragraphs
            ],
            'placeholders': [p.to_dict() for p in self.placeholders],
            'alternatives': [a.to_dict() for a in self.alternatives],
            'optionals': [o.to_dict() for o in self.optionals],
            'xml_schema': self.xml_schema,
            'combo_options': self.combo_options,
        }


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: DOCUMENT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def extract_paragraphs(docx_path: str) -> List[Paragraph]:
    """Извлечь параграфы из .docx"""
    paragraphs = []

    with zipfile.ZipFile(docx_path, 'r') as zf:
        with zf.open('word/document.xml') as f:
            doc = etree.parse(f)

    for p_idx, p in enumerate(doc.iter(f'{W_NS}p')):
        texts = []
        for t in p.iter(f'{W_NS}t'):
            if t.text:
                texts.append(t.text)
        full_text = ''.join(texts)

        ppr = p.find(f'{W_NS}pPr')
        style = None
        num_id = None
        ilvl = 0

        if ppr is not None:
            pstyle = ppr.find(f'{W_NS}pStyle')
            if pstyle is not None:
                style = pstyle.get(f'{W_NS}val')

            num_pr = ppr.find(f'{W_NS}numPr')
            if num_pr is not None:
                ilvl_el = num_pr.find(f'{W_NS}ilvl')
                if ilvl_el is not None:
                    ilvl = int(ilvl_el.get(f'{W_NS}val', 0))
                num_id_el = num_pr.find(f'{W_NS}numId')
                if num_id_el is not None:
                    num_id = num_id_el.get(f'{W_NS}val')

        para = Paragraph(
            idx=p_idx,
            text=full_text,
            style=style,
            is_heading=style and 'Heading' in style,
            is_list_item=num_id is not None,
            list_level=ilvl,
        )

        if full_text:
            article_match = PATTERNS['article_heading'].match(full_text.strip())
            if article_match:
                para.article_num = article_match.group(1)
                para.is_heading = True

            item_match = PATTERNS['numbered_item'].match(full_text.strip())
            if item_match:
                para.item_num = item_match.group(1).rstrip('.')

        paragraphs.append(para)

    return paragraphs


def find_placeholders(paragraphs: List[Paragraph]) -> List[Placeholder]:
    """Найти все плейсхолдеры"""
    placeholders = []
    ph_id = 0

    for para in paragraphs:
        text = para.text
        if not text:
            continue

        for match in PATTERNS['placeholder'].finditer(text):
            ctx_start = max(0, match.start() - 80)
            ctx_end = min(len(text), match.end() + 80)

            ai_comment = None
            ai_match = PATTERNS['ai_comment'].search(text[match.end():match.end()+400])
            if ai_match:
                ai_comment = ai_match.group(1).strip()

            ph = Placeholder(
                id=ph_id,
                para_idx=para.idx,
                char_pos=match.start(),
                context_before=text[ctx_start:match.start()],
                context_after=text[match.end():ctx_end],
                ai_comment=ai_comment,
            )

            placeholders.append(ph)
            ph_id += 1

    return placeholders


def find_alternatives(paragraphs: List[Paragraph], domain: DomainConfig) -> List[Alternative]:
    """Найти альтернативные блоки"""
    alternatives = []

    sep_indices = []
    for para in paragraphs:
        if PATTERNS['alternative_sep'].match(para.text.strip()):
            sep_indices.append(para.idx)

    if not sep_indices:
        return alternatives

    # Группировать последовательные альтернативы
    groups = []
    current_group = [sep_indices[0]]

    for i in range(1, len(sep_indices)):
        if sep_indices[i] - sep_indices[i-1] < 20:
            current_group.append(sep_indices[i])
        else:
            groups.append(current_group)
            current_group = [sep_indices[i]]
    groups.append(current_group)

    alt_counter = {}

    for group in groups:
        first_sep = group[0]
        context_para = paragraphs[first_sep - 1] if first_sep > 0 else None
        context_text = context_para.text.lower() if context_para else ''

        # Классификация по доменному конфигу
        group_id = _classify_alternative_group(context_text, domain, first_sep)

        if group_id not in alt_counter:
            alt_counter[group_id] = 0

        # Первая альтернатива (до первого /)
        start = max(0, group[0] - 5)
        for i in range(group[0] - 1, max(0, group[0] - 10), -1):
            if paragraphs[i].is_heading or not paragraphs[i].text.strip():
                start = i + 1
                break

        alt_counter[group_id] += 1
        alternatives.append(Alternative(
            group_id=f'alt:{group_id}',
            option_idx=alt_counter[group_id],
            start_para=start,
            end_para=group[0] - 1,
            text_preview=paragraphs[start].text[:60] if start < len(paragraphs) else '',
        ))

        # Альтернативы между разделителями и после последнего
        for i, sep_idx in enumerate(group):
            alt_counter[group_id] += 1

            end_idx = group[i + 1] - 1 if i + 1 < len(group) else min(sep_idx + 5, len(paragraphs) - 1)

            for j in range(sep_idx + 1, min(sep_idx + 10, len(paragraphs))):
                if paragraphs[j].is_heading or PATTERNS['alternative_sep'].match(paragraphs[j].text.strip()):
                    end_idx = j - 1
                    break

            alternatives.append(Alternative(
                group_id=f'alt:{group_id}',
                option_idx=alt_counter[group_id],
                start_para=sep_idx + 1,
                end_para=end_idx,
                text_preview=paragraphs[sep_idx + 1].text[:60] if sep_idx + 1 < len(paragraphs) else '',
            ))

    return alternatives


def _classify_alternative_group(context_text: str, domain: DomainConfig, fallback_idx: int) -> str:
    """Определить group_id альтернативного блока по доменным классификаторам"""
    for classifier in domain.alternative_classifiers:
        keywords = classifier['keywords']
        if all(kw in context_text for kw in keywords):
            return classifier['group_id']
    return f'alternative_{fallback_idx}'


def find_optionals(paragraphs: List[Paragraph], domain: DomainConfig) -> List[OptionalBlock]:
    """Найти optional блоки"""
    optionals = []

    i = 0
    while i < len(paragraphs):
        text = paragraphs[i].text.strip()

        if text.startswith('[Комментарий'):
            i += 1
            continue

        if text.startswith('[') and not text.endswith(']'):
            start = i
            j = i + 1
            while j < len(paragraphs):
                if paragraphs[j].text.strip().endswith(']'):
                    break
                j += 1

            if j < len(paragraphs):
                full_text = ' '.join(paragraphs[k].text for k in range(start, j + 1)).lower()
                tag = _classify_optional_tag(full_text, domain)

                optionals.append(OptionalBlock(
                    tag=tag,
                    start_para=start,
                    end_para=j,
                    text_preview=paragraphs[start].text[:60],
                ))
                i = j + 1
                continue

        elif text.startswith('[') and text.endswith(']') and len(text) > 30:
            if 'Комментарий' not in text:
                tag = _classify_optional_tag(text.lower(), domain)
                optionals.append(OptionalBlock(
                    tag=tag,
                    start_para=i,
                    end_para=i,
                    text_preview=text[:60],
                ))

        i += 1

    return optionals


def _classify_optional_tag(text: str, domain: DomainConfig) -> str:
    """Определить тег для optional блока по доменным классификаторам"""
    text = text.lower()
    for classifier in domain.optional_classifiers:
        keywords = classifier['keywords']
        if all(kw in text for kw in keywords):
            return classifier['tag']
    return 'optional:block'


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: HEURISTIC CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_by_heuristics(placeholders: List[Placeholder], paragraphs: List[Paragraph],
                           domain: DomainConfig):
    """Классифицировать плейсхолдеры по эвристикам (доменным)"""

    for ph in placeholders:
        context = (ph.context_before + ' ' + ph.context_after).lower()
        ai_hint = (ph.ai_comment or '').lower()
        combined = context + ' ' + ai_hint

        # Определить тип поля
        field_type = 'text'
        confidence = 0.3

        for ftype, pattern in domain.type_hints.items():
            if pattern.search(combined):
                field_type = ftype
                confidence = 0.6
                break

        # Уточнить по AI комментарию
        if ai_hint:
            confidence += 0.2
            for rus_name, eng_name in domain.field_name_map.items():
                if rus_name in ai_hint:
                    ph.field_name = eng_name
                    confidence += 0.1
                    break

        # Определить сущность
        entity = None
        for ent, pattern in domain.entity_hints.items():
            if pattern.search(combined):
                entity = ent
                confidence += 0.1
                break

        ph.field_type = field_type
        ph.entity = entity
        ph.confidence = min(confidence, 1.0)
        ph.classified_by = 'heuristic'
        ph.needs_review = confidence < 0.7

        if ph.entity and ph.field_name:
            ph.xml_path = f"{ph.entity}/{ph.field_name}"


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: LLM CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_with_llm(placeholders: List[Placeholder], domain: DomainConfig,
                      batch_size: int = 8):
    """Классифицировать неоднозначные плейсхолдеры через LLM"""

    uncertain = [ph for ph in placeholders if ph.confidence < 0.7]

    if not uncertain:
        print("[INFO] All placeholders classified with high confidence")
        return

    provider = get_provider()
    print(f"[INFO] Sending {len(uncertain)} placeholders to LLM ({provider.info()})...")

    system_prompt = domain.llm_system_prompt
    user_template = domain.llm_user_prompt_template

    for i in range(0, len(uncertain), batch_size):
        batch = uncertain[i:i+batch_size]

        fields_desc = []
        for idx, ph in enumerate(batch):
            fields_desc.append({
                'id': idx,
                'context': ph.context_before[-50:] + ' [●] ' + ph.context_after[:50],
                'ai_comment': ph.ai_comment,
                'current_entity': ph.entity,
                'current_field': ph.field_name,
            })

        prompt = user_template.format(
            document_type=domain.llm_document_type,
            fields_json=json.dumps(fields_desc, ensure_ascii=False, indent=2),
        )

        response = provider.generate(prompt, system_prompt)

        if not response:
            # LLM не ответил — пометить на ревью
            for ph in batch:
                ph.needs_review = True
            print(f"[WARN] Batch {i//batch_size + 1}: LLM returned empty response")
            continue

        classifications = parse_llm_json(response)

        if classifications is None:
            # Невалидный ответ — пометить на ревью
            for ph in batch:
                ph.needs_review = True
            print(f"[WARN] Batch {i//batch_size + 1}: invalid LLM response")
            continue

        for item in classifications:
            idx = item.get('id')
            if idx is not None and idx < len(batch):
                ph = batch[idx]

                if item.get('entity'):
                    ph.entity = item['entity']
                if item.get('field_name'):
                    ph.field_name = item['field_name']
                if item.get('field_type'):
                    ph.field_type = item['field_type']

                ph.confidence = 0.85
                ph.classified_by = 'llm'
                ph.needs_review = False

                if ph.entity and ph.field_name:
                    ph.xml_path = f"{ph.entity}/{ph.field_name}"

        print(f"[INFO] Batch {i//batch_size + 1}/{(len(uncertain)-1)//batch_size + 1} done")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: BUILD XML SCHEMA
# ═══════════════════════════════════════════════════════════════════════════

def build_xml_schema(placeholders: List[Placeholder]) -> Dict[str, Any]:
    """Построить XML схему"""
    schema = {}

    for ph in placeholders:
        if not ph.entity or not ph.field_name:
            continue

        path_parts = ph.xml_path.split('/') if ph.xml_path else [ph.entity, ph.field_name]

        current = schema
        for part in path_parts[:-1]:
            if part not in current:
                current[part] = {'_children': {}}
            if '_children' not in current[part]:
                current[part]['_children'] = {}
            current = current[part]['_children']

        field_key = path_parts[-1]
        if field_key not in current:
            current[field_key] = {
                'type': ph.field_type,
                'occurrences': 1,
            }
        else:
            current[field_key]['occurrences'] += 1

    def simplify(node):
        result = {}
        for key, val in node.items():
            if isinstance(val, dict):
                if '_children' in val and val['_children']:
                    result[key] = simplify(val['_children'])
                elif 'type' in val:
                    result[key] = {'type': val['type'], 'count': val.get('occurrences', 1)}
                else:
                    result[key] = simplify(val)
            else:
                result[key] = val
        return result

    return simplify(schema)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def analyze_document(docx_path: str, use_llm: bool = True,
                     domain_name: str = None) -> DocumentStructure:
    """Полный анализ документа"""

    print(f"[INFO] Analyzing: {docx_path}")

    # Step 1: Extract
    print("[STEP 1] Extracting document structure...")
    paragraphs = extract_paragraphs(docx_path)
    print(f"         {len(paragraphs)} paragraphs")

    # Определить домен
    if domain_name:
        domain = load_domain(domain_name)
        print(f"[DOMAIN] {domain.display_name} (explicit)")
    else:
        text_sample = ' '.join(p.text for p in paragraphs[:50] if p.text)
        domain = detect_domain(text_sample)
        print(f"[DOMAIN] {domain.display_name} (auto-detected)")

    placeholders = find_placeholders(paragraphs)
    print(f"         {len(placeholders)} placeholders")

    alternatives = find_alternatives(paragraphs, domain)
    print(f"         {len(alternatives)} alternative blocks")

    optionals = find_optionals(paragraphs, domain)
    print(f"         {len(optionals)} optional blocks")

    # Step 2: Heuristic classification
    print("[STEP 2] Heuristic classification...")
    classify_by_heuristics(placeholders, paragraphs, domain)

    high_conf = len([p for p in placeholders if p.confidence >= 0.7])
    print(f"         {high_conf}/{len(placeholders)} high confidence")

    # Step 3: LLM classification
    if use_llm:
        print("[STEP 3] LLM classification...")
        classify_with_llm(placeholders, domain)
    else:
        print("[STEP 3] Skipped (--no-llm)")

    # Step 4: Build schema
    print("[STEP 4] Building XML schema...")
    xml_schema = build_xml_schema(placeholders)

    # Link placeholders to alternatives/optionals
    for alt in alternatives:
        for ph in placeholders:
            if alt.start_para <= ph.para_idx <= alt.end_para:
                alt.placeholders.append(ph.id)

    for opt in optionals:
        for ph in placeholders:
            if opt.start_para <= ph.para_idx <= opt.end_para:
                opt.placeholders.append(ph.id)

    # combo_options из домена → в конфиг для builder
    combo_options = {k: [list(item) for item in v] for k, v in domain.combo_options.items()}

    structure = DocumentStructure(
        source_file=docx_path,
        paragraphs=paragraphs,
        placeholders=placeholders,
        alternatives=alternatives,
        optionals=optionals,
        domain_id=domain.domain_id,
        xml_schema=xml_schema,
        combo_options=combo_options,
    )

    print("[DONE] Analysis complete")
    return structure


def main():
    import sys

    # --list-domains
    if '--list-domains' in sys.argv:
        print("Available domains:")
        for d in list_domains():
            print(f"  {d['id']:20} {d['name']}")
        sys.exit(0)

    if len(sys.argv) < 2:
        provider = get_provider()
        print("Document Analyzer for Draft Builder")
        print("")
        print("Usage: python document_analyzer.py <document.docx> [options]")
        print("")
        print("Options:")
        print("  --no-llm              Skip LLM classification")
        print("  --domain <name>       Use specific domain (default: auto-detect)")
        print("  --list-domains        List available domain configs")
        print("")
        print("Environment variables:")
        print("  DRAFTBUILDER_LLM_PROVIDER  ollama | openrouter (default: ollama)")
        print("  DRAFTBUILDER_LLM_MODEL     Model name (default: qwen3:32b)")
        print("  DRAFTBUILDER_LLM_URL       API endpoint")
        print("  DRAFTBUILDER_LLM_API_KEY   API key (for openrouter)")
        print("")
        print(f"LLM: {provider.info()}")
        sys.exit(1)

    docx_path = sys.argv[1]
    use_llm = '--no-llm' not in sys.argv

    # Parse --domain
    domain_name = None
    if '--domain' in sys.argv:
        idx = sys.argv.index('--domain')
        if idx + 1 < len(sys.argv):
            domain_name = sys.argv[idx + 1]

    if not Path(docx_path).exists():
        print(f"[ERROR] File not found: {docx_path}")
        sys.exit(1)

    # Analyze
    structure = analyze_document(docx_path, use_llm=use_llm, domain_name=domain_name)

    # Export config
    config = structure.to_config()
    config_path = Path(docx_path).stem + '_config.json'

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\n[OUTPUT] {config_path}")

    # Summary
    print(f"\n{'='*50}")
    print("SUMMARY")
    print(f"{'='*50}")

    type_counts = {}
    for ph in structure.placeholders:
        type_counts[ph.field_type] = type_counts.get(ph.field_type, 0) + 1

    print("\nBy type:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:12} {c}")

    entity_counts = {}
    for ph in structure.placeholders:
        e = ph.entity or 'unclassified'
        entity_counts[e] = entity_counts.get(e, 0) + 1

    print("\nBy entity:")
    for e, c in sorted(entity_counts.items(), key=lambda x: -x[1]):
        print(f"  {e:15} {c}")

    needs_review = [ph for ph in structure.placeholders if ph.needs_review]
    if needs_review:
        print(f"\n[!] {len(needs_review)} placeholders need manual review")
        print("    Edit the JSON config before running template_builder.py")


if __name__ == '__main__':
    main()
