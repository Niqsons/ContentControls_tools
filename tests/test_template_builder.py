"""Тесты генератора шаблонов — валидность OOXML"""

import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from template_builder import TemplateBuilder, qn, NAMESPACES

W_NS = NAMESPACES['w']


class TestTemplateBuilderOutput:
    """Тесты на валидность сгенерированного .docx"""

    def build(self, config, tmp_path):
        output = tmp_path / "output.docx"
        builder = TemplateBuilder(config)
        builder.build(str(output))
        return output

    def test_creates_valid_zip(self, sample_config, tmp_path):
        output = self.build(sample_config, tmp_path)
        assert output.exists()
        assert zipfile.is_zipfile(str(output))

    def test_contains_required_parts(self, sample_config, tmp_path):
        output = self.build(sample_config, tmp_path)
        with zipfile.ZipFile(str(output), 'r') as zf:
            names = zf.namelist()
            assert 'word/document.xml' in names
            assert 'word/styles.xml' in names
            assert 'word/settings.xml' in names
            assert '[Content_Types].xml' in names
            assert '_rels/.rels' in names
            assert 'customXml/item1.xml' in names
            assert 'customXml/itemProps1.xml' in names

    def test_document_xml_is_wellformed(self, sample_config, tmp_path):
        output = self.build(sample_config, tmp_path)
        with zipfile.ZipFile(str(output), 'r') as zf:
            with zf.open('word/document.xml') as f:
                doc = etree.parse(f)  # Должен парситься без ошибок
                root = doc.getroot()
                assert root.tag == f'{{{W_NS}}}document'

    def test_custom_xml_is_wellformed(self, sample_config, tmp_path):
        output = self.build(sample_config, tmp_path)
        with zipfile.ZipFile(str(output), 'r') as zf:
            with zf.open('customXml/item1.xml') as f:
                doc = etree.parse(f)
                root = doc.getroot()
                assert 'document' in root.tag

    def test_content_controls_present(self, sample_config, tmp_path):
        output = self.build(sample_config, tmp_path)
        with zipfile.ZipFile(str(output), 'r') as zf:
            with zf.open('word/document.xml') as f:
                doc = etree.parse(f)

        # Найти все SDT элементы
        sdts = list(doc.iter(f'{{{W_NS}}}sdt'))
        assert len(sdts) >= 2  # Как минимум 2 плейсхолдера

    def test_sdt_structure(self, sample_config, tmp_path):
        """Каждый SDT должен содержать sdtPr и sdtContent"""
        output = self.build(sample_config, tmp_path)
        with zipfile.ZipFile(str(output), 'r') as zf:
            with zf.open('word/document.xml') as f:
                doc = etree.parse(f)

        for sdt in doc.iter(f'{{{W_NS}}}sdt'):
            sdt_pr = sdt.find(f'{{{W_NS}}}sdtPr')
            sdt_content = sdt.find(f'{{{W_NS}}}sdtContent')
            assert sdt_pr is not None, "SDT missing sdtPr"
            assert sdt_content is not None, "SDT missing sdtContent"

    def test_data_binding_xpath_matches_custom_xml(self, sample_config, tmp_path):
        """dataBinding xpath должен ссылаться на существующий элемент в Custom XML"""
        output = self.build(sample_config, tmp_path)
        with zipfile.ZipFile(str(output), 'r') as zf:
            with zf.open('word/document.xml') as f:
                doc_tree = etree.parse(f)
            with zf.open('customXml/item1.xml') as f:
                xml_tree = etree.parse(f)

        xml_root = xml_tree.getroot()
        ns = sample_config['meta']['namespace']

        # Собрать все xpath из dataBinding
        for db in doc_tree.iter(f'{{{W_NS}}}dataBinding'):
            xpath = db.get(f'{{{W_NS}}}xpath')
            assert xpath is not None

            # Преобразовать xpath из la: формата в реальный namespace
            # /la:document/la:agreement/la:city → проверить что agreement/city есть в XML
            # Убрать /la:document/ и разбить по /
            path_str = xpath.replace('/la:document/', '')
            parts = [p.replace('la:', '') for p in path_str.split('/')]
            current = xml_root
            for part in parts:
                if not part:
                    continue
                child = current.find(f'{{{ns}}}{part}')
                assert child is not None, f"Custom XML missing element for xpath: {xpath}"
                current = child

    def test_unique_guid_per_build(self, sample_config, tmp_path):
        """Каждый билд должен генерировать уникальный GUID"""
        b1 = TemplateBuilder(sample_config)
        b2 = TemplateBuilder(sample_config)
        assert b1.guid != b2.guid

    def test_date_sdt_has_date_properties(self, sample_config, tmp_path):
        """SDT с типом date должен содержать w:date элемент"""
        output = self.build(sample_config, tmp_path)
        with zipfile.ZipFile(str(output), 'r') as zf:
            with zf.open('word/document.xml') as f:
                doc = etree.parse(f)

        date_sdts = []
        for sdt in doc.iter(f'{{{W_NS}}}sdt'):
            sdt_pr = sdt.find(f'{{{W_NS}}}sdtPr')
            if sdt_pr is not None and sdt_pr.find(f'{{{W_NS}}}date') is not None:
                date_sdts.append(sdt)

        # Конфиг содержит одно date-поле
        assert len(date_sdts) >= 1

        for sdt in date_sdts:
            sdt_pr = sdt.find(f'{{{W_NS}}}sdtPr')
            date_el = sdt_pr.find(f'{{{W_NS}}}date')
            fmt = date_el.find(f'{{{W_NS}}}dateFormat')
            assert fmt is not None
            assert fmt.get(f'{{{W_NS}}}val') is not None


class TestTemplateBuilderComboOptions:
    """Тесты на combo_options из доменного конфига"""

    def test_combo_options_from_config(self, sample_config, tmp_path):
        sample_config['combo_options'] = {
            'days': [
                ['5 дней', '5'],
                ['10 дней', '10'],
            ]
        }
        # Добавить placeholder с типом days
        sample_config['placeholders'].append({
            'id': 2,
            'para_idx': 2,
            'char_pos': 0,
            'context': 'срок [●] дней',
            'ai_comment': None,
            'field_type': 'days',
            'entity': 'loan',
            'field_name': 'deadline',
            'xml_path': 'loan/deadline',
            'confidence': 0.85,
            'classified_by': 'llm',
            'needs_review': False,
        })
        sample_config['paragraphs'][2]['text'] = 'Срок [●] дней'

        output = tmp_path / "output.docx"
        builder = TemplateBuilder(sample_config)
        builder.build(str(output))

        with zipfile.ZipFile(str(output), 'r') as zf:
            with zf.open('word/document.xml') as f:
                doc = etree.parse(f)

        # Найти comboBox SDT
        combo_found = False
        for sdt in doc.iter(f'{{{W_NS}}}sdt'):
            sdt_pr = sdt.find(f'{{{W_NS}}}sdtPr')
            cb = sdt_pr.find(f'{{{W_NS}}}comboBox') if sdt_pr is not None else None
            if cb is not None:
                combo_found = True
                items = cb.findall(f'{{{W_NS}}}listItem')
                assert len(items) == 2
                assert items[0].get(f'{{{W_NS}}}displayText') == '5 дней'

        assert combo_found, "No comboBox SDT found in output"
