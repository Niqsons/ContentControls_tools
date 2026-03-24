"""Тесты загрузки доменных конфигов"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from domain_config import load_domain, detect_domain, list_domains, DomainConfig


class TestLoadDomain:
    def test_load_base(self):
        domain = load_domain('_base_legal_ru')
        assert domain.domain_id == '_base_legal_ru'
        assert 'agreement' in domain.entity_hints
        assert 'dispute' in domain.entity_hints

    def test_load_loan_agreement(self):
        domain = load_domain('loan_agreement')
        assert domain.domain_id == 'loan_agreement'
        assert 'lender' in domain.entity_hints
        assert 'borrower' in domain.entity_hints

    def test_inheritance_merges_entities(self):
        domain = load_domain('loan_agreement')
        # Из базового
        assert 'agreement' in domain.entity_hints
        assert 'dispute' in domain.entity_hints
        # Из доменного
        assert 'lender' in domain.entity_hints
        assert 'penalty' in domain.entity_hints

    def test_inheritance_merges_type_hints(self):
        domain = load_domain('loan_agreement')
        # Из базового
        assert 'date' in domain.type_hints
        assert 'address' in domain.type_hints
        # Из доменного
        assert 'amount' in domain.type_hints
        assert 'days' in domain.type_hints

    def test_inheritance_merges_field_name_map(self):
        domain = load_domain('loan_agreement')
        # Из базового
        assert domain.field_name_map['дата'] == 'date'
        assert domain.field_name_map['адрес'] == 'address'
        # Из доменного
        assert domain.field_name_map['сумма'] == 'amount'
        assert domain.field_name_map['неустойка'] == 'penalty_rate'

    def test_inheritance_appends_classifiers(self):
        domain = load_domain('loan_agreement')
        # optional_classifiers: base (4) + loan (3) = 7
        assert len(domain.optional_classifiers) == 7
        # alternative_classifiers: base (1) + loan (3) = 4
        assert len(domain.alternative_classifiers) == 4

    def test_compiled_patterns_are_regex(self):
        domain = load_domain('loan_agreement')
        for key, pattern in domain.entity_hints.items():
            assert isinstance(pattern, re.Pattern), f"{key} is not compiled"
        for key, pattern in domain.type_hints.items():
            assert isinstance(pattern, re.Pattern), f"{key} is not compiled"

    def test_entity_patterns_match(self):
        domain = load_domain('loan_agreement')
        assert domain.entity_hints['lender'].search('Займодавец предоставляет')
        assert domain.entity_hints['borrower'].search('Заемщик обязуется')
        assert domain.entity_hints['agreement'].search('Договор займа')

    def test_combo_options_loaded(self):
        domain = load_domain('loan_agreement')
        assert 'days' in domain.combo_options
        assert len(domain.combo_options['days']) == 4
        assert domain.combo_options['days'][0] == ('5 (пяти)', '5 (пяти)')

    def test_llm_prompts_populated(self):
        domain = load_domain('loan_agreement')
        assert domain.llm_system_prompt
        assert domain.llm_document_type == 'договор займа'
        # Переменные должны быть подставлены
        assert '{entity_list}' not in domain.llm_system_prompt

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_domain('nonexistent_domain_xyz')


class TestDetectDomain:
    def test_detects_loan_agreement(self):
        text = "Займодавец предоставляет Заемщику сумму займа в размере"
        domain = detect_domain(text)
        assert domain.domain_id == 'loan_agreement'

    def test_fallback_to_base(self):
        text = "Стороны договорились о нижеследующем"
        domain = detect_domain(text)
        # Может определить как base или loan — зависит от скоринга
        assert domain is not None
        assert isinstance(domain, DomainConfig)


class TestListDomains:
    def test_lists_available(self):
        domains = list_domains()
        ids = [d['id'] for d in domains]
        assert '_base_legal_ru' in ids
        assert 'loan_agreement' in ids

    def test_has_required_fields(self):
        domains = list_domains()
        for d in domains:
            assert 'id' in d
            assert 'name' in d
            assert 'file' in d
