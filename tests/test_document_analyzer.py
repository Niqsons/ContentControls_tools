"""Тесты парсера документов (без LLM)"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from document_analyzer import (
    extract_paragraphs,
    find_placeholders,
    find_alternatives,
    find_optionals,
    classify_by_heuristics,
    build_xml_schema,
    Paragraph,
    Placeholder,
    PATTERNS,
)
from domain_config import load_domain


@pytest.fixture
def domain():
    return load_domain('loan_agreement')


class TestExtractParagraphs:
    def test_extracts_all_paragraphs(self, sample_docx):
        paras = extract_paragraphs(str(sample_docx))
        assert len(paras) == 4

    def test_detects_heading_style(self, sample_docx):
        paras = extract_paragraphs(str(sample_docx))
        assert paras[0].is_heading is True
        assert paras[0].style == 'Heading1'

    def test_extracts_text(self, sample_docx):
        paras = extract_paragraphs(str(sample_docx))
        assert 'Займодавец' in paras[1].text
        assert '[●]' in paras[1].text

    def test_detects_article_number(self, sample_docx):
        paras = extract_paragraphs(str(sample_docx))
        assert paras[0].article_num == '1'


class TestFindPlaceholders:
    def test_finds_all_placeholders(self, sample_docx):
        paras = extract_paragraphs(str(sample_docx))
        phs = find_placeholders(paras)
        assert len(phs) == 4  # 3 в параграфе 1 + 1 в параграфе 2

    def test_placeholder_has_context(self, sample_docx):
        paras = extract_paragraphs(str(sample_docx))
        phs = find_placeholders(paras)
        # Первый [●] — после "Займодавец "
        assert 'Займодавец' in phs[0].context_before

    def test_placeholder_extracts_ai_comment(self, sample_docx):
        paras = extract_paragraphs(str(sample_docx))
        phs = find_placeholders(paras)
        # Последний [●] — "Дата [●] года [Комментарий ИИ: ...]"
        date_ph = [p for p in phs if 'Дата' in p.context_before or 'дата' in p.context_before.lower()]
        assert len(date_ph) == 1
        assert date_ph[0].ai_comment is not None
        assert 'дата' in date_ph[0].ai_comment.lower()

    def test_placeholder_ids_sequential(self, sample_docx):
        paras = extract_paragraphs(str(sample_docx))
        phs = find_placeholders(paras)
        ids = [p.id for p in phs]
        assert ids == list(range(len(phs)))

    def test_placeholder_pattern_matches_bullet(self):
        assert PATTERNS['placeholder'].search('[●]') is not None
        assert PATTERNS['placeholder'].search('[_____]') is not None
        assert PATTERNS['placeholder'].search('[текст]') is None


class TestHeuristicClassification:
    def test_classifies_date_field(self, sample_docx, domain):
        paras = extract_paragraphs(str(sample_docx))
        phs = find_placeholders(paras)
        classify_by_heuristics(phs, paras, domain)

        date_phs = [p for p in phs if p.field_type == 'date']
        assert len(date_phs) >= 1

    def test_classifies_entity(self, sample_docx, domain):
        paras = extract_paragraphs(str(sample_docx))
        phs = find_placeholders(paras)
        classify_by_heuristics(phs, paras, domain)

        # Хотя бы один должен определить entity
        entities = [p.entity for p in phs if p.entity]
        assert len(entities) > 0

    def test_builds_xml_path(self, sample_docx, domain):
        paras = extract_paragraphs(str(sample_docx))
        phs = find_placeholders(paras)
        classify_by_heuristics(phs, paras, domain)

        with_path = [p for p in phs if p.xml_path]
        for p in with_path:
            assert '/' in p.xml_path
            assert p.entity in p.xml_path


class TestBuildXmlSchema:
    def test_schema_structure(self, sample_docx, domain):
        paras = extract_paragraphs(str(sample_docx))
        phs = find_placeholders(paras)
        classify_by_heuristics(phs, paras, domain)
        schema = build_xml_schema(phs)

        # Схема должна быть непустой если есть классифицированные поля
        classified = [p for p in phs if p.entity and p.field_name]
        if classified:
            assert len(schema) > 0

    def test_schema_leaf_has_type(self):
        """Leaf-ноды схемы должны иметь 'type' и 'count'"""
        ph = Placeholder(
            id=0, para_idx=0, char_pos=0,
            context_before='', context_after='',
            field_type='date', entity='agreement',
            field_name='date', xml_path='agreement/date',
        )
        schema = build_xml_schema([ph])
        assert 'agreement' in schema
        assert 'date' in schema['agreement']
        assert schema['agreement']['date']['type'] == 'date'
        assert schema['agreement']['date']['count'] == 1
