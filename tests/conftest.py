"""Фикстуры для тестов Draft Builder"""

import json
import zipfile
import tempfile
from pathlib import Path

import pytest
from lxml import etree


@pytest.fixture
def sample_config():
    """Минимальный валидный конфиг для template_builder"""
    return {
        "meta": {
            "source_file": "test.docx",
            "domain": "loan_agreement",
            "namespace": "urn:draftbuilder:template:v1",
            "total_paragraphs": 3,
            "total_placeholders": 2,
            "total_alternatives": 0,
            "total_optionals": 0,
        },
        "paragraphs": [
            {
                "idx": 0,
                "text": "ДОГОВОР ЗАЙМА",
                "style": "Heading1",
                "is_heading": True,
                "article_num": None,
                "item_num": None,
            },
            {
                "idx": 1,
                "text": "г. [●], дата [●] года",
                "style": None,
                "is_heading": False,
                "article_num": None,
                "item_num": None,
            },
            {
                "idx": 2,
                "text": "Обычный текст без плейсхолдеров.",
                "style": None,
                "is_heading": False,
                "article_num": None,
                "item_num": None,
            },
        ],
        "placeholders": [
            {
                "id": 0,
                "para_idx": 1,
                "char_pos": 3,
                "context": "г. [●], дата",
                "ai_comment": None,
                "field_type": "text",
                "entity": "agreement",
                "field_name": "city",
                "xml_path": "agreement/city",
                "confidence": 0.85,
                "classified_by": "llm",
                "needs_review": False,
            },
            {
                "id": 1,
                "para_idx": 1,
                "char_pos": 14,
                "context": "дата [●] года",
                "ai_comment": None,
                "field_type": "date",
                "entity": "agreement",
                "field_name": "date",
                "xml_path": "agreement/date",
                "confidence": 0.85,
                "classified_by": "llm",
                "needs_review": False,
            },
        ],
        "alternatives": [],
        "optionals": [],
        "xml_schema": {
            "agreement": {
                "city": {"type": "text", "count": 1},
                "date": {"type": "date", "count": 1},
            }
        },
        "combo_options": {},
    }


@pytest.fixture
def sample_docx(tmp_path):
    """Создать минимальный .docx с плейсхолдерами для тестирования парсера"""
    docx_path = tmp_path / "test.docx"

    document_xml = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>1. ПРЕДМЕТ ДОГОВОРА</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>Займодавец [●] предоставляет Заёмщику [●] сумму [●] рублей.</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>Дата [●] года [Комментарий ИИ: дата заключения договора]</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>Обычный параграф без плейсхолдеров.</w:t></w:r>
    </w:p>
  </w:body>
</w:document>"""

    rels_xml = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>"""

    content_types_xml = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

    with zipfile.ZipFile(docx_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('word/document.xml', document_xml)
        zf.writestr('_rels/.rels', rels_xml)
        zf.writestr('[Content_Types].xml', content_types_xml)

    return docx_path
