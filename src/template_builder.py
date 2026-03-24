#!/usr/bin/env python3
"""
Template Builder for Draft Builder
Генерирует .docx шаблон с Content Controls из JSON конфига

Вход: *_config.json (от document_analyzer.py)
Выход: *_Template.docx (готовый шаблон с CC + Custom XML Part)
"""

import json
import copy
import uuid
import zipfile
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from lxml import etree
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════
# OOXML NAMESPACES
# ═══════════════════════════════════════════════════════════════════════════

NAMESPACES = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
    'w14': 'http://schemas.microsoft.com/office/word/2010/wordml',
    'w15': 'http://schemas.microsoft.com/office/word/2012/wordml',
    'ct': 'http://schemas.openxmlformats.org/package/2006/content-types',
}

W = f"{{{NAMESPACES['w']}}}"

def qn(tag: str) -> str:
    """Qualified name: w:p -> {namespace}p"""
    if ':' in tag:
        prefix, local = tag.split(':')
        return f"{{{NAMESPACES[prefix]}}}{local}"
    return tag


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_NAMESPACE = "urn:draftbuilder:template:v1"

# Типы полей → CC type (OOXML маппинг, не зависит от домена)
FIELD_TYPE_MAP = {
    'text': 'plain_text',
    'name': 'plain_text',
    'address': 'plain_text',
    'account': 'plain_text',
    'date': 'date',
    'amount': 'plain_text',
    'rate': 'plain_text',
    'days': 'combo_box',
    'dropdown': 'dropdown',
    'representative': 'plain_text',
    'authority': 'plain_text',
    'email': 'plain_text',
}

# Fallback значения для combo_box (если не заданы в конфиге домена)
DEFAULT_DAYS_OPTIONS = [
    ("5 (пяти)", "5 (пяти)"),
    ("10 (десяти)", "10 (десяти)"),
    ("15 (пятнадцати)", "15 (пятнадцати)"),
    ("30 (тридцати)", "30 (тридцати)"),
]


# ═══════════════════════════════════════════════════════════════════════════
# ELEMENT BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def make_run(text: str, bold: bool = False, size: int = None) -> etree.Element:
    """Создать w:r элемент"""
    r = etree.Element(qn('w:r'))
    
    if bold or size:
        rpr = etree.SubElement(r, qn('w:rPr'))
        if bold:
            etree.SubElement(rpr, qn('w:b'))
        if size:
            sz = etree.SubElement(rpr, qn('w:sz'))
            sz.set(qn('w:val'), str(size))
            szCs = etree.SubElement(rpr, qn('w:szCs'))
            szCs.set(qn('w:val'), str(size))
    
    t = etree.SubElement(r, qn('w:t'))
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    t.text = text
    return r


def make_paragraph(text: str = None, style: str = None, 
                   alignment: str = None, bold: bool = False,
                   spacing_before: int = None, spacing_after: int = None,
                   keep_next: bool = False) -> etree.Element:
    """Создать w:p элемент"""
    p = etree.Element(qn('w:p'))
    ppr = etree.SubElement(p, qn('w:pPr'))
    
    if style:
        pstyle = etree.SubElement(ppr, qn('w:pStyle'))
        pstyle.set(qn('w:val'), style)
    
    if keep_next:
        etree.SubElement(ppr, qn('w:keepNext'))
    
    if spacing_before is not None or spacing_after is not None:
        spacing = etree.SubElement(ppr, qn('w:spacing'))
        if spacing_before is not None:
            spacing.set(qn('w:before'), str(spacing_before))
        if spacing_after is not None:
            spacing.set(qn('w:after'), str(spacing_after))
    
    if alignment:
        jc = etree.SubElement(ppr, qn('w:jc'))
        jc.set(qn('w:val'), alignment)
    
    if text:
        p.append(make_run(text, bold=bold))
    
    return p


def make_inline_sdt(
    tag: str,
    title: str = None,
    sdt_type: str = 'plain_text',
    default_value: str = '[●]',
    placeholder: str = None,
    xml_path: str = None,
    namespace: str = None,
    guid: str = None,
    dropdown_items: List[tuple] = None,
    bold: bool = False,
) -> etree.Element:
    """Создать inline SDT (Content Control)"""
    
    sdt = etree.Element(qn('w:sdt'))
    sdt_pr = etree.SubElement(sdt, qn('w:sdtPr'))
    
    # Run properties
    if bold:
        rpr = etree.SubElement(sdt_pr, qn('w:rPr'))
        etree.SubElement(rpr, qn('w:b'))
    
    # Alias (title)
    if title:
        alias = etree.SubElement(sdt_pr, qn('w:alias'))
        alias.set(qn('w:val'), title)
    
    # Tag
    tag_el = etree.SubElement(sdt_pr, qn('w:tag'))
    tag_el.set(qn('w:val'), tag)
    
    # Lock
    lock = etree.SubElement(sdt_pr, qn('w:lock'))
    lock.set(qn('w:val'), 'sdtLocked')
    
    # Data binding (XML mapping)
    if xml_path and namespace and guid:
        db = etree.SubElement(sdt_pr, qn('w:dataBinding'))
        db.set(qn('w:prefixMappings'), f"xmlns:la='{namespace}'")
        db.set(qn('w:xpath'), xml_path)
        db.set(qn('w:storeItemID'), guid)
    
    # Type-specific properties
    if sdt_type == 'plain_text':
        etree.SubElement(sdt_pr, qn('w:text'))
    elif sdt_type == 'date':
        date_el = etree.SubElement(sdt_pr, qn('w:date'))
        fmt = etree.SubElement(date_el, qn('w:dateFormat'))
        fmt.set(qn('w:val'), 'dd.MM.yyyy')
        lid = etree.SubElement(date_el, qn('w:lid'))
        lid.set(qn('w:val'), 'ru-RU')
        store = etree.SubElement(date_el, qn('w:storeMappedDataAs'))
        store.set(qn('w:val'), 'dateTime')
        cal = etree.SubElement(date_el, qn('w:calendar'))
        cal.set(qn('w:val'), 'gregorian')
    elif sdt_type == 'combo_box':
        cb = etree.SubElement(sdt_pr, qn('w:comboBox'))
        items = dropdown_items or DEFAULT_DAYS_OPTIONS
        for display, value in items:
            item = etree.SubElement(cb, qn('w:listItem'))
            item.set(qn('w:displayText'), display)
            item.set(qn('w:value'), value)
    elif sdt_type == 'dropdown':
        dd = etree.SubElement(sdt_pr, qn('w:dropDownList'))
        if dropdown_items:
            for display, value in dropdown_items:
                item = etree.SubElement(dd, qn('w:listItem'))
                item.set(qn('w:displayText'), display)
                item.set(qn('w:value'), value)
    
    # Content
    sdt_content = etree.SubElement(sdt, qn('w:sdtContent'))
    r = etree.SubElement(sdt_content, qn('w:r'))
    if bold:
        rpr = etree.SubElement(r, qn('w:rPr'))
        etree.SubElement(rpr, qn('w:b'))
    t = etree.SubElement(r, qn('w:t'))
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    t.text = default_value or placeholder or '[●]'
    
    return sdt


def make_block_sdt(
    tag: str,
    title: str = None,
    content_elements: List[etree.Element] = None,
    default_text: str = None,
) -> etree.Element:
    """Создать block-level SDT"""
    
    sdt = etree.Element(qn('w:sdt'))
    sdt_pr = etree.SubElement(sdt, qn('w:sdtPr'))
    
    if title:
        alias = etree.SubElement(sdt_pr, qn('w:alias'))
        alias.set(qn('w:val'), title)
    
    tag_el = etree.SubElement(sdt_pr, qn('w:tag'))
    tag_el.set(qn('w:val'), tag)
    
    lock = etree.SubElement(sdt_pr, qn('w:lock'))
    lock.set(qn('w:val'), 'sdtLocked')
    
    # Content
    sdt_content = etree.SubElement(sdt, qn('w:sdtContent'))
    
    if content_elements:
        for el in content_elements:
            sdt_content.append(el)
    elif default_text:
        sdt_content.append(make_paragraph(default_text))
    
    return sdt


# ═══════════════════════════════════════════════════════════════════════════
# CUSTOM XML PART
# ═══════════════════════════════════════════════════════════════════════════

def build_custom_xml(schema: Dict, namespace: str) -> str:
    """Построить Custom XML Part из схемы"""
    
    def add_elements(parent: etree.Element, data: Dict, ns: str):
        for key, value in data.items():
            if key.startswith('_'):
                continue
            
            el = etree.SubElement(parent, f"{{{ns}}}{key}")
            
            if isinstance(value, dict):
                if 'type' in value:
                    # Leaf node — оставить пустым
                    pass
                else:
                    # Nested structure
                    add_elements(el, value, ns)
    
    root = etree.Element(f"{{{namespace}}}document", nsmap={'la': namespace})
    add_elements(root, schema, namespace)
    
    xml_str = etree.tostring(root, pretty_print=True, encoding='UTF-8', xml_declaration=True)
    return xml_str.decode('utf-8')


def build_custom_xml_props(namespace: str, guid: str) -> str:
    """Построить itemProps для Custom XML Part"""
    ds_ns = "http://schemas.openxmlformats.org/officeDocument/2006/customXml"
    
    props = etree.Element(f"{{{ds_ns}}}datastoreItem", nsmap={None: ds_ns})
    props.set(f"{{{ds_ns}}}itemID", guid)
    
    schema_refs = etree.SubElement(props, f"{{{ds_ns}}}schemaRefs")
    schema_ref = etree.SubElement(schema_refs, f"{{{ds_ns}}}schemaRef")
    schema_ref.set(f"{{{ds_ns}}}uri", namespace)
    
    xml_str = etree.tostring(props, pretty_print=True, encoding='UTF-8', xml_declaration=True)
    return xml_str.decode('utf-8')


# ═══════════════════════════════════════════════════════════════════════════
# DOCUMENT BUILDER
# ═══════════════════════════════════════════════════════════════════════════

class TemplateBuilder:
    """Строит .docx шаблон из JSON конфига"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.meta = config['meta']
        self.paragraphs = config['paragraphs']
        self.placeholders = {p['id']: p for p in config['placeholders']}
        self.alternatives = config['alternatives']
        self.optionals = config['optionals']
        self.xml_schema = config['xml_schema']

        self.namespace = self.meta.get('namespace', DEFAULT_NAMESPACE)
        self.guid = f"{{{uuid.uuid4()}}}"

        # combo_options из конфига домена (записаны analyzer-ом)
        combo_raw = config.get('combo_options', {})
        self.combo_options = {}
        for key, items in combo_raw.items():
            self.combo_options[key] = [(item[0], item[1]) for item in items]
        
        # Маппинг para_idx -> list of placeholders
        self.ph_by_para = {}
        for ph in config['placeholders']:
            para_idx = ph['para_idx']
            if para_idx not in self.ph_by_para:
                self.ph_by_para[para_idx] = []
            self.ph_by_para[para_idx].append(ph)
        
        # Сортировать плейсхолдеры по позиции в параграфе (в обратном порядке для замены)
        for para_idx in self.ph_by_para:
            self.ph_by_para[para_idx].sort(key=lambda x: x['char_pos'], reverse=True)
        
        # Альтернативы и optionals по para_idx
        self.alt_by_para = {}
        for alt in self.alternatives:
            for i in range(alt['start_para'], alt['end_para'] + 1):
                self.alt_by_para[i] = alt
        
        self.opt_by_para = {}
        for opt in self.optionals:
            for i in range(opt['start_para'], opt['end_para'] + 1):
                self.opt_by_para[i] = opt
    
    def xpath(self, path: str) -> str:
        """Построить XPath для XML mapping"""
        parts = path.split('/')
        return '/la:document/' + '/la:'.join([''] + parts)[1:]
    
    def build_paragraph_with_cc(self, para_data: Dict) -> etree.Element:
        """Построить параграф с Content Controls вместо [●]"""
        
        para_idx = para_data['idx']
        text = para_data['text']
        
        # Создать параграф
        p = etree.Element(qn('w:p'))
        ppr = etree.SubElement(p, qn('w:pPr'))
        
        # Стиль
        if para_data.get('is_heading') or para_data.get('article_num'):
            etree.SubElement(ppr, qn('w:keepNext'))
            pstyle = etree.SubElement(ppr, qn('w:pStyle'))
            pstyle.set(qn('w:val'), 'Heading1')
        
        # Если нет плейсхолдеров — просто текст
        if para_idx not in self.ph_by_para:
            # Убрать AI комментарии
            text = self._strip_ai_comments(text)
            if text.strip():
                p.append(make_run(text))
            return p
        
        # Есть плейсхолдеры — разбить текст и вставить CC
        placeholders = self.ph_by_para[para_idx]
        
        # Убрать AI комментарии
        text = self._strip_ai_comments(text)
        
        # Найти позиции [●] в очищенном тексте
        import re
        ph_pattern = re.compile(r'\[●\]|\[___+\]')
        matches = list(ph_pattern.finditer(text))
        
        if not matches:
            # Плейсхолдеры были в AI комментариях
            if text.strip():
                p.append(make_run(text))
            return p
        
        # Построить контент
        last_end = 0
        ph_idx = 0
        
        for match in matches:
            # Текст до плейсхолдера
            if match.start() > last_end:
                p.append(make_run(text[last_end:match.start()]))
            
            # Найти соответствующий плейсхолдер из конфига
            if ph_idx < len(placeholders):
                ph = placeholders[-(ph_idx + 1)]  # Они в обратном порядке
                
                # Определить тип CC
                sdt_type = FIELD_TYPE_MAP.get(ph.get('field_type', 'text'), 'plain_text')
                
                # XML path
                xml_path = None
                if ph.get('xml_path'):
                    xml_path = self.xpath(ph['xml_path'])
                
                # Title
                title = ph.get('field_name', '') or ''
                if ph.get('entity'):
                    title = f"{ph['entity']}/{title}" if title else ph['entity']
                
                # combo_box items из доменного конфига
                combo_items = None
                if sdt_type == 'combo_box':
                    field_type = ph.get('field_type', '')
                    combo_items = self.combo_options.get(field_type)

                # Создать CC
                cc = make_inline_sdt(
                    tag=ph.get('xml_path') or f"field_{ph['id']}",
                    title=title,
                    sdt_type=sdt_type,
                    default_value='[●]',
                    xml_path=xml_path,
                    namespace=self.namespace if xml_path else None,
                    guid=self.guid if xml_path else None,
                    dropdown_items=combo_items,
                )
                p.append(cc)
                
                ph_idx += 1
            else:
                # Fallback — просто текст
                p.append(make_run(match.group()))
            
            last_end = match.end()
        
        # Текст после последнего плейсхолдера
        if last_end < len(text):
            p.append(make_run(text[last_end:]))
        
        return p
    
    def _strip_ai_comments(self, text: str) -> str:
        """Убрать [Комментарий ИИ: ...]"""
        import re
        return re.sub(r'\s*\[Комментарий ИИ:[^\]]*\]', '', text)
    
    def build_document(self) -> etree.Element:
        """Построить document.xml"""
        
        # Root
        doc = etree.Element(qn('w:document'), nsmap={
            'w': NAMESPACES['w'],
            'r': NAMESPACES['r'],
            'mc': NAMESPACES['mc'],
            'w14': NAMESPACES['w14'],
            'w15': NAMESPACES['w15'],
        })
        doc.set(qn('mc:Ignorable'), 'w14 w15')
        
        body = etree.SubElement(doc, qn('w:body'))
        
        # Track которые para уже обработаны (для alt/optional блоков)
        processed = set()
        
        # Группировать альтернативы
        alt_groups = {}
        for alt in self.alternatives:
            if alt['group_id'] not in alt_groups:
                alt_groups[alt['group_id']] = []
            alt_groups[alt['group_id']].append(alt)
        
        i = 0
        while i < len(self.paragraphs):
            para = self.paragraphs[i]
            
            if i in processed:
                i += 1
                continue
            
            # Проверить альтернативу
            if i in self.alt_by_para:
                alt = self.alt_by_para[i]
                
                # Найти все альтернативы в группе
                group = alt_groups.get(alt['group_id'], [alt])
                
                # Обработать каждую альтернативу
                for alt_item in group:
                    # Создать block SDT
                    content = []
                    for j in range(alt_item['start_para'], alt_item['end_para'] + 1):
                        if j < len(self.paragraphs):
                            content.append(self.build_paragraph_with_cc(self.paragraphs[j]))
                            processed.add(j)
                    
                    if content:
                        sdt = make_block_sdt(
                            tag=f"{alt_item['group_id']}:{alt_item['option_idx']}",
                            title=f"{alt_item['group_id']} вариант {alt_item['option_idx']}",
                            content_elements=content,
                        )
                        body.append(sdt)
                    
                    # Разделитель между альтернативами
                    if alt_item != group[-1]:
                        body.append(make_paragraph("/", alignment="center"))
                
                # Пропустить обработанные параграфы
                max_para = max(a['end_para'] for a in group)
                i = max_para + 1
                continue
            
            # Проверить optional
            if i in self.opt_by_para:
                opt = self.opt_by_para[i]
                
                # Создать block SDT
                content = []
                for j in range(opt['start_para'], opt['end_para'] + 1):
                    if j < len(self.paragraphs):
                        content.append(self.build_paragraph_with_cc(self.paragraphs[j]))
                        processed.add(j)
                
                if content:
                    sdt = make_block_sdt(
                        tag=opt['tag'],
                        title=opt['tag'],
                        content_elements=content,
                    )
                    body.append(sdt)
                
                i = opt['end_para'] + 1
                continue
            
            # Обычный параграф
            p = self.build_paragraph_with_cc(para)
            # Не добавлять пустые параграфы подряд
            if len(list(p)) > 1 or (p.text and p.text.strip()):  # Есть контент
                body.append(p)
            elif para['text'].strip():  # Есть текст в оригинале
                body.append(p)
            
            i += 1
        
        # Section properties
        sect_pr = etree.SubElement(body, qn('w:sectPr'))
        pg_sz = etree.SubElement(sect_pr, qn('w:pgSz'))
        pg_sz.set(qn('w:w'), '11906')
        pg_sz.set(qn('w:h'), '16838')
        pg_mar = etree.SubElement(sect_pr, qn('w:pgMar'))
        pg_mar.set(qn('w:top'), '1440')
        pg_mar.set(qn('w:right'), '1440')
        pg_mar.set(qn('w:bottom'), '1440')
        pg_mar.set(qn('w:left'), '1440')
        
        return doc
    
    def build(self, output_path: str):
        """Собрать .docx файл"""
        
        print(f"[BUILD] Creating template...")
        
        # Создать временную директорию
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Структура .docx
            os.makedirs(f"{tmpdir}/_rels")
            os.makedirs(f"{tmpdir}/word/_rels")
            os.makedirs(f"{tmpdir}/word/theme")
            os.makedirs(f"{tmpdir}/customXml/_rels")
            os.makedirs(f"{tmpdir}/docProps")
            
            # [Content_Types].xml
            self._write_content_types(tmpdir)
            
            # _rels/.rels
            self._write_root_rels(tmpdir)
            
            # word/document.xml
            doc = self.build_document()
            with open(f"{tmpdir}/word/document.xml", 'wb') as f:
                f.write(etree.tostring(doc, pretty_print=True, encoding='UTF-8', xml_declaration=True))
            
            # word/_rels/document.xml.rels
            self._write_doc_rels(tmpdir)
            
            # word/styles.xml
            self._write_styles(tmpdir)
            
            # word/settings.xml
            self._write_settings(tmpdir)
            
            # word/fontTable.xml
            self._write_font_table(tmpdir)
            
            # word/webSettings.xml
            self._write_web_settings(tmpdir)
            
            # word/theme/theme1.xml
            self._write_theme(tmpdir)
            
            # customXml/item1.xml
            xml_content = build_custom_xml(self.xml_schema, self.namespace)
            with open(f"{tmpdir}/customXml/item1.xml", 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            # customXml/itemProps1.xml
            props_content = build_custom_xml_props(self.namespace, self.guid)
            with open(f"{tmpdir}/customXml/itemProps1.xml", 'w', encoding='utf-8') as f:
                f.write(props_content)
            
            # customXml/_rels/item1.xml.rels
            self._write_custom_xml_rels(tmpdir)
            
            # docProps/core.xml
            self._write_core_props(tmpdir)
            
            # docProps/app.xml
            self._write_app_props(tmpdir)
            
            # Упаковать в .docx
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(tmpdir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arc_name = os.path.relpath(file_path, tmpdir)
                        zf.write(file_path, arc_name)
        
        print(f"[DONE] {output_path}")
    
    def _write_content_types(self, tmpdir: str):
        ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
        types = etree.Element(f"{{{ct_ns}}}Types", nsmap={None: ct_ns})
        
        # Defaults
        for ext, ct in [
            ('rels', 'application/vnd.openxmlformats-package.relationships+xml'),
            ('xml', 'application/xml'),
        ]:
            d = etree.SubElement(types, f"{{{ct_ns}}}Default")
            d.set('Extension', ext)
            d.set('ContentType', ct)
        
        # Overrides
        overrides = [
            ('/word/document.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'),
            ('/word/styles.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml'),
            ('/word/settings.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml'),
            ('/word/fontTable.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml'),
            ('/word/webSettings.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml'),
            ('/word/theme/theme1.xml', 'application/vnd.openxmlformats-officedocument.theme+xml'),
            ('/customXml/itemProps1.xml', 'application/vnd.openxmlformats-officedocument.customXmlProperties+xml'),
            ('/docProps/core.xml', 'application/vnd.openxmlformats-package.core-properties+xml'),
            ('/docProps/app.xml', 'application/vnd.openxmlformats-officedocument.extended-properties+xml'),
        ]
        
        for part, ct in overrides:
            o = etree.SubElement(types, f"{{{ct_ns}}}Override")
            o.set('PartName', part)
            o.set('ContentType', ct)
        
        with open(f"{tmpdir}/[Content_Types].xml", 'wb') as f:
            f.write(etree.tostring(types, pretty_print=True, encoding='UTF-8', xml_declaration=True))
    
    def _write_root_rels(self, tmpdir: str):
        rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        rels = etree.Element(f"{{{rels_ns}}}Relationships", nsmap={None: rels_ns})
        
        relationships = [
            ('rId1', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument', 'word/document.xml'),
            ('rId2', 'http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties', 'docProps/core.xml'),
            ('rId3', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties', 'docProps/app.xml'),
        ]
        
        for rid, rtype, target in relationships:
            rel = etree.SubElement(rels, f"{{{rels_ns}}}Relationship")
            rel.set('Id', rid)
            rel.set('Type', rtype)
            rel.set('Target', target)
        
        with open(f"{tmpdir}/_rels/.rels", 'wb') as f:
            f.write(etree.tostring(rels, pretty_print=True, encoding='UTF-8', xml_declaration=True))
    
    def _write_doc_rels(self, tmpdir: str):
        rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        rels = etree.Element(f"{{{rels_ns}}}Relationships", nsmap={None: rels_ns})
        
        relationships = [
            ('rId1', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml', '../customXml/item1.xml'),
            ('rId2', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles', 'styles.xml'),
            ('rId3', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings', 'settings.xml'),
            ('rId4', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable', 'fontTable.xml'),
            ('rId5', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/webSettings', 'webSettings.xml'),
            ('rId6', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme', 'theme/theme1.xml'),
        ]
        
        for rid, rtype, target in relationships:
            rel = etree.SubElement(rels, f"{{{rels_ns}}}Relationship")
            rel.set('Id', rid)
            rel.set('Type', rtype)
            rel.set('Target', target)
        
        with open(f"{tmpdir}/word/_rels/document.xml.rels", 'wb') as f:
            f.write(etree.tostring(rels, pretty_print=True, encoding='UTF-8', xml_declaration=True))
    
    def _write_custom_xml_rels(self, tmpdir: str):
        rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        rels = etree.Element(f"{{{rels_ns}}}Relationships", nsmap={None: rels_ns})
        
        rel = etree.SubElement(rels, f"{{{rels_ns}}}Relationship")
        rel.set('Id', 'rId1')
        rel.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXmlProps')
        rel.set('Target', 'itemProps1.xml')
        
        with open(f"{tmpdir}/customXml/_rels/item1.xml.rels", 'wb') as f:
            f.write(etree.tostring(rels, pretty_print=True, encoding='UTF-8', xml_declaration=True))
    
    def _write_styles(self, tmpdir: str):
        styles = etree.Element(qn('w:styles'), nsmap={'w': NAMESPACES['w']})
        
        # Default style
        doc_defaults = etree.SubElement(styles, qn('w:docDefaults'))
        rpr_default = etree.SubElement(doc_defaults, qn('w:rPrDefault'))
        rpr = etree.SubElement(rpr_default, qn('w:rPr'))
        rfonts = etree.SubElement(rpr, qn('w:rFonts'))
        rfonts.set(qn('w:ascii'), 'Times New Roman')
        rfonts.set(qn('w:hAnsi'), 'Times New Roman')
        sz = etree.SubElement(rpr, qn('w:sz'))
        sz.set(qn('w:val'), '24')
        
        # Normal style
        normal = etree.SubElement(styles, qn('w:style'))
        normal.set(qn('w:type'), 'paragraph')
        normal.set(qn('w:styleId'), 'Normal')
        normal.set(qn('w:default'), '1')
        name = etree.SubElement(normal, qn('w:name'))
        name.set(qn('w:val'), 'Normal')
        
        # Heading1
        h1 = etree.SubElement(styles, qn('w:style'))
        h1.set(qn('w:type'), 'paragraph')
        h1.set(qn('w:styleId'), 'Heading1')
        name = etree.SubElement(h1, qn('w:name'))
        name.set(qn('w:val'), 'Heading 1')
        based = etree.SubElement(h1, qn('w:basedOn'))
        based.set(qn('w:val'), 'Normal')
        rpr = etree.SubElement(h1, qn('w:rPr'))
        etree.SubElement(rpr, qn('w:b'))
        sz = etree.SubElement(rpr, qn('w:sz'))
        sz.set(qn('w:val'), '28')
        
        with open(f"{tmpdir}/word/styles.xml", 'wb') as f:
            f.write(etree.tostring(styles, pretty_print=True, encoding='UTF-8', xml_declaration=True))
    
    def _write_settings(self, tmpdir: str):
        settings = etree.Element(qn('w:settings'), nsmap={'w': NAMESPACES['w']})
        
        zoom = etree.SubElement(settings, qn('w:zoom'))
        zoom.set(qn('w:percent'), '100')
        
        with open(f"{tmpdir}/word/settings.xml", 'wb') as f:
            f.write(etree.tostring(settings, pretty_print=True, encoding='UTF-8', xml_declaration=True))
    
    def _write_font_table(self, tmpdir: str):
        fonts = etree.Element(qn('w:fonts'), nsmap={'w': NAMESPACES['w']})
        
        font = etree.SubElement(fonts, qn('w:font'))
        font.set(qn('w:name'), 'Times New Roman')
        
        with open(f"{tmpdir}/word/fontTable.xml", 'wb') as f:
            f.write(etree.tostring(fonts, pretty_print=True, encoding='UTF-8', xml_declaration=True))
    
    def _write_web_settings(self, tmpdir: str):
        ws = etree.Element(qn('w:webSettings'), nsmap={'w': NAMESPACES['w']})
        
        with open(f"{tmpdir}/word/webSettings.xml", 'wb') as f:
            f.write(etree.tostring(ws, pretty_print=True, encoding='UTF-8', xml_declaration=True))
    
    def _write_theme(self, tmpdir: str):
        a_ns = NAMESPACES['a']
        theme = etree.Element(f"{{{a_ns}}}theme", nsmap={'a': a_ns})
        theme.set('name', 'Office Theme')
        
        with open(f"{tmpdir}/word/theme/theme1.xml", 'wb') as f:
            f.write(etree.tostring(theme, pretty_print=True, encoding='UTF-8', xml_declaration=True))
    
    def _write_core_props(self, tmpdir: str):
        cp_ns = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
        dc_ns = "http://purl.org/dc/elements/1.1/"
        dcterms_ns = "http://purl.org/dc/terms/"
        
        props = etree.Element(f"{{{cp_ns}}}coreProperties", nsmap={
            'cp': cp_ns,
            'dc': dc_ns,
            'dcterms': dcterms_ns,
        })
        
        title = etree.SubElement(props, f"{{{dc_ns}}}title")
        title.text = "Draft Builder Template"
        
        creator = etree.SubElement(props, f"{{{dc_ns}}}creator")
        creator.text = "Document Analyzer"
        
        created = etree.SubElement(props, f"{{{dcterms_ns}}}created")
        created.set('{http://www.w3.org/2001/XMLSchema-instance}type', 'dcterms:W3CDTF')
        created.text = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
        
        with open(f"{tmpdir}/docProps/core.xml", 'wb') as f:
            f.write(etree.tostring(props, pretty_print=True, encoding='UTF-8', xml_declaration=True))
    
    def _write_app_props(self, tmpdir: str):
        ep_ns = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
        
        props = etree.Element(f"{{{ep_ns}}}Properties", nsmap={None: ep_ns})
        
        app = etree.SubElement(props, f"{{{ep_ns}}}Application")
        app.text = "Draft Builder"
        
        with open(f"{tmpdir}/docProps/app.xml", 'wb') as f:
            f.write(etree.tostring(props, pretty_print=True, encoding='UTF-8', xml_declaration=True))


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Template Builder for Draft Builder")
        print("")
        print("Usage: python template_builder.py <config.json> [output.docx]")
        print("")
        print("Input:  *_config.json from document_analyzer.py")
        print("Output: *_Template.docx with Content Controls")
        sys.exit(1)
    
    config_path = sys.argv[1]
    
    if not Path(config_path).exists():
        print(f"[ERROR] Config not found: {config_path}")
        sys.exit(1)
    
    # Output path
    if len(sys.argv) > 2:
        output_path = sys.argv[2]
    else:
        output_path = Path(config_path).stem.replace('_config', '') + '_Template.docx'
    
    # Load config
    print(f"[LOAD] {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    print(f"       {config['meta']['total_paragraphs']} paragraphs")
    print(f"       {config['meta']['total_placeholders']} placeholders")
    print(f"       {config['meta']['total_alternatives']} alternatives")
    print(f"       {config['meta']['total_optionals']} optionals")
    
    # Build
    builder = TemplateBuilder(config)
    builder.build(output_path)


if __name__ == '__main__':
    main()
