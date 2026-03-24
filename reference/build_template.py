#!/usr/bin/env python3
"""
Build a .docx loan agreement template with:
- Custom XML Part (data schema)
- Content Controls (SDT) with XML Mapping
- Alternative blocks, optional blocks, repeating sections
- Synchronized fields (multiple CC → one XML element)

Approach: python-docx for base document structure,
lxml for SDT/Custom XML injection at the OOXML level.
"""

import copy
import os
import shutil
import zipfile
from lxml import etree

from docx import Document
from docx.shared import Pt, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn, nsmap

# ─── Constants ────────────────────────────────────────────────────────────

OUTPUT_PATH = "/home/claude/Dogovor_Template.docx"
CUSTOM_XML_URI = "urn:draftbuilder:loan_agreement:v1"
CUSTOM_XML_GUID = "{12345678-1234-1234-1234-123456789ABC}"

# Word namespaces we'll need
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"  # Word 2013 for Repeating Section
DS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/customXml"

NSMAP_W = {"w": W_NS}
NSMAP_DS = {"ds": DS_NS}


# ─── Helper functions ─────────────────────────────────────────────────────

def make_element(tag, attrib=None, text=None, nsmap=None):
    """Create an lxml element with optional attributes and text."""
    el = etree.SubElement if False else etree.Element(qn(tag) if ":" in tag and "{" not in tag else tag, nsmap=nsmap)
    if attrib:
        for k, v in attrib.items():
            key = qn(k) if ":" in k and "{" not in k else k
            el.set(key, v)
    if text:
        el.text = text
    return el


def make_sdt_block(title, tag, placeholder=None, content_elements=None,
                   sdt_type="plain_text", dropdown_items=None,
                   default_value=None, xml_mapping_xpath=None):
    """
    Create a block-level SDT (Structured Document Tag / Content Control).
    
    sdt_type: 'plain_text', 'rich_text', 'date', 'dropdown', 'combo_box'
    content_elements: list of lxml elements to put inside sdtContent
    dropdown_items: list of (display, value) tuples for dropdown/combo
    xml_mapping_xpath: XPath for XML mapping to Custom XML Part
    """
    sdt = etree.Element(qn("w:sdt"))
    
    # ── sdtPr (properties) ──
    sdt_pr = etree.SubElement(sdt, qn("w:sdtPr"))
    
    # Alias (Title)
    alias_el = etree.SubElement(sdt_pr, qn("w:alias"))
    alias_el.set(qn("w:val"), title)
    
    # Tag
    tag_el = etree.SubElement(sdt_pr, qn("w:tag"))
    tag_el.set(qn("w:val"), tag)
    
    # Lock - prevent deletion of CC itself
    lock_el = etree.SubElement(sdt_pr, qn("w:lock"))
    lock_el.set(qn("w:val"), "sdtLocked")
    
    # Placeholder
    if placeholder:
        ph_el = etree.SubElement(sdt_pr, qn("w:placeholder"))
        doc_part = etree.SubElement(ph_el, qn("w:docPart"))
        doc_part.set(qn("w:val"), f"PH_{tag.replace('/', '_')}")
    
    # XML Mapping (dataBinding) — XSD order: before type-specific choice element
    if xml_mapping_xpath:
        db_el = etree.SubElement(sdt_pr, qn("w:dataBinding"))
        db_el.set(qn("w:prefixMappings"), f"xmlns:la='{CUSTOM_XML_URI}'")
        db_el.set(qn("w:xpath"), xml_mapping_xpath)
        db_el.set(qn("w:storeItemID"), CUSTOM_XML_GUID)
    
    # Type-specific properties (choice element — last in sdtPr per XSD)
    if sdt_type == "plain_text":
        etree.SubElement(sdt_pr, qn("w:text"))
    elif sdt_type == "date":
        date_el = etree.SubElement(sdt_pr, qn("w:date"))
        # fullDate omitted when empty - required format is xs:dateTime
        date_fmt = etree.SubElement(date_el, qn("w:dateFormat"))
        date_fmt.set(qn("w:val"), "dd.MM.yyyy")
        lang_el = etree.SubElement(date_el, qn("w:lid"))
        lang_el.set(qn("w:val"), "ru-RU")
        st_el = etree.SubElement(date_el, qn("w:storeMappedDataAs"))
        st_el.set(qn("w:val"), "dateTime")
        cal_el = etree.SubElement(date_el, qn("w:calendar"))
        cal_el.set(qn("w:val"), "gregorian")
    elif sdt_type == "dropdown":
        dd_el = etree.SubElement(sdt_pr, qn("w:dropDownList"))
        if dropdown_items:
            for display, value in dropdown_items:
                item = etree.SubElement(dd_el, qn("w:listItem"))
                item.set(qn("w:displayText"), display)
                item.set(qn("w:value"), value)
    elif sdt_type == "combo_box":
        cb_el = etree.SubElement(sdt_pr, qn("w:comboBox"))
        if dropdown_items:
            for display, value in dropdown_items:
                item = etree.SubElement(cb_el, qn("w:listItem"))
                item.set(qn("w:displayText"), display)
                item.set(qn("w:value"), value)
    # rich_text has no special element
    
    # ── sdtContent ──
    sdt_content = etree.SubElement(sdt, qn("w:sdtContent"))
    
    if content_elements:
        for el in content_elements:
            sdt_content.append(el)
    else:
        # Default: single paragraph with placeholder or default text
        p = etree.SubElement(sdt_content, qn("w:p"))
        r = etree.SubElement(p, qn("w:r"))
        t = etree.SubElement(r, qn("w:t"))
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = default_value or placeholder or "[●]"
    
    return sdt


def make_inline_sdt(title, tag, placeholder=None, sdt_type="plain_text",
                    dropdown_items=None, default_value=None,
                    xml_mapping_xpath=None, run_props=None):
    """
    Create an inline (run-level) SDT for use within a paragraph.
    Returns an sdt element that goes inside w:p alongside w:r elements.
    """
    sdt = etree.Element(qn("w:sdt"))
    
    # ── sdtPr ──
    sdt_pr = etree.SubElement(sdt, qn("w:sdtPr"))
    
    # Run properties inside sdtPr (formatting inheritance)
    if run_props:
        rpr = etree.SubElement(sdt_pr, qn("w:rPr"))
        for prop_el in run_props:
            rpr.append(copy.deepcopy(prop_el))
    
    alias_el = etree.SubElement(sdt_pr, qn("w:alias"))
    alias_el.set(qn("w:val"), title)
    
    tag_el = etree.SubElement(sdt_pr, qn("w:tag"))
    tag_el.set(qn("w:val"), tag)
    
    lock_el = etree.SubElement(sdt_pr, qn("w:lock"))
    lock_el.set(qn("w:val"), "sdtLocked")
    
    # XML Mapping (dataBinding) — XSD order: before type-specific choice element
    if xml_mapping_xpath:
        db_el = etree.SubElement(sdt_pr, qn("w:dataBinding"))
        db_el.set(qn("w:prefixMappings"), f"xmlns:la='{CUSTOM_XML_URI}'")
        db_el.set(qn("w:xpath"), xml_mapping_xpath)
        db_el.set(qn("w:storeItemID"), CUSTOM_XML_GUID)
    
    # Type-specific properties (choice element — last in sdtPr per XSD)
    if sdt_type == "plain_text":
        etree.SubElement(sdt_pr, qn("w:text"))
    elif sdt_type == "date":
        date_el = etree.SubElement(sdt_pr, qn("w:date"))
        # fullDate omitted when empty - required format is xs:dateTime
        date_fmt = etree.SubElement(date_el, qn("w:dateFormat"))
        date_fmt.set(qn("w:val"), "dd MMMM yyyy")
        lang_el = etree.SubElement(date_el, qn("w:lid"))
        lang_el.set(qn("w:val"), "ru-RU")
        st_el = etree.SubElement(date_el, qn("w:storeMappedDataAs"))
        st_el.set(qn("w:val"), "dateTime")
        cal_el = etree.SubElement(date_el, qn("w:calendar"))
        cal_el.set(qn("w:val"), "gregorian")
    elif sdt_type == "combo_box":
        cb_el = etree.SubElement(sdt_pr, qn("w:comboBox"))
        if dropdown_items:
            for display, value in dropdown_items:
                item = etree.SubElement(cb_el, qn("w:listItem"))
                item.set(qn("w:displayText"), display)
                item.set(qn("w:value"), value)
    elif sdt_type == "dropdown":
        dd_el = etree.SubElement(sdt_pr, qn("w:dropDownList"))
        if dropdown_items:
            for display, value in dropdown_items:
                item = etree.SubElement(dd_el, qn("w:listItem"))
                item.set(qn("w:displayText"), display)
                item.set(qn("w:value"), value)
    
    # ── sdtContent ──
    sdt_content = etree.SubElement(sdt, qn("w:sdtContent"))
    r = etree.SubElement(sdt_content, qn("w:r"))
    if run_props:
        rpr = etree.SubElement(r, qn("w:rPr"))
        for prop_el in run_props:
            rpr.append(copy.deepcopy(prop_el))
    t = etree.SubElement(r, qn("w:t"))
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = default_value or placeholder or "[●]"
    
    return sdt


def make_run(text, bold=False, size=None, font=None):
    """Create a w:r element with optional formatting."""
    r = etree.Element(qn("w:r"))
    if bold or size or font:
        rpr = etree.SubElement(r, qn("w:rPr"))
        if bold:
            etree.SubElement(rpr, qn("w:b"))
        if size:
            sz = etree.SubElement(rpr, qn("w:sz"))
            sz.set(qn("w:val"), str(size))  # half-points
            szCs = etree.SubElement(rpr, qn("w:szCs"))
            szCs.set(qn("w:val"), str(size))
        if font:
            rFonts = etree.SubElement(rpr, qn("w:rFonts"))
            rFonts.set(qn("w:ascii"), font)
            rFonts.set(qn("w:hAnsi"), font)
    t = etree.SubElement(r, qn("w:t"))
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    return r


def make_paragraph(runs=None, alignment=None, bold=False, size=None,
                   spacing_before=None, spacing_after=None, keep_next=False):
    """Create a w:p element. Element order per XSD: keepNext → spacing → jc."""
    p = etree.Element(qn("w:p"))
    ppr = etree.SubElement(p, qn("w:pPr"))
    
    # XSD order: pStyle, keepNext, ..., spacing, ind, ..., jc
    if keep_next:
        etree.SubElement(ppr, qn("w:keepNext"))
    
    if spacing_before is not None or spacing_after is not None:
        sp = etree.SubElement(ppr, qn("w:spacing"))
        if spacing_before is not None:
            sp.set(qn("w:before"), str(spacing_before))
        if spacing_after is not None:
            sp.set(qn("w:after"), str(spacing_after))
    
    if alignment:
        jc = etree.SubElement(ppr, qn("w:jc"))
        jc.set(qn("w:val"), alignment)
    
    if runs:
        for r in runs:
            p.append(r)
    
    return p


def make_separator_paragraph():
    """Create a separator line ──────"""
    p = make_paragraph(
        runs=[make_run("_" * 75, bold=True)],
        alignment="center"
    )
    return p


def make_repeating_section(title, tag, xml_mapping_xpath, items_content):
    """
    Create a Repeating Section Content Control (Word 2013+).
    
    This creates the outer w15:repeatingSection SDT that contains
    w15:repeatingSectionItem SDTs for each repeating item.
    
    items_content: list of lists of elements, one list per repeating item
    xml_mapping_xpath: XPath to the parent element containing repeating children
    """
    # Register w15 namespace
    nsmap_full = {
        "w": W_NS,
        "w15": W15_NS
    }
    
    # Outer SDT - Repeating Section container
    sdt = etree.Element(qn("w:sdt"))
    
    # sdtPr
    sdt_pr = etree.SubElement(sdt, qn("w:sdtPr"))
    
    alias_el = etree.SubElement(sdt_pr, qn("w:alias"))
    alias_el.set(qn("w:val"), title)
    
    tag_el = etree.SubElement(sdt_pr, qn("w:tag"))
    tag_el.set(qn("w:val"), tag)
    
    # XML Mapping to parent element (e.g., /la:loan_agreement/la:provision/la:tranches)
    if xml_mapping_xpath:
        db_el = etree.SubElement(sdt_pr, qn("w:dataBinding"))
        db_el.set(qn("w:prefixMappings"), f"xmlns:la='{CUSTOM_XML_URI}'")
        db_el.set(qn("w:xpath"), xml_mapping_xpath)
        db_el.set(qn("w:storeItemID"), CUSTOM_XML_GUID)
    
    # w15:repeatingSection - marks this as repeating section
    # Must use full namespace since lxml doesn't auto-register w15
    rep_section = etree.SubElement(sdt_pr, f"{{{W15_NS}}}repeatingSection")
    
    # sdtContent
    sdt_content = etree.SubElement(sdt, qn("w:sdtContent"))
    
    # Add each item as a RepeatingSectionItem
    for idx, item_elements in enumerate(items_content):
        item_sdt = make_repeating_section_item(f"{tag}_item_{idx+1}", item_elements)
        sdt_content.append(item_sdt)
    
    return sdt


def make_repeating_section_item(tag, content_elements):
    """
    Create a Repeating Section Item SDT.
    Each item in a repeating section is wrapped in this.
    """
    sdt = etree.Element(qn("w:sdt"))
    
    # sdtPr
    sdt_pr = etree.SubElement(sdt, qn("w:sdtPr"))
    
    tag_el = etree.SubElement(sdt_pr, qn("w:tag"))
    tag_el.set(qn("w:val"), tag)
    
    # w15:repeatingSectionItem - marks this as repeating section item
    rep_item = etree.SubElement(sdt_pr, f"{{{W15_NS}}}repeatingSectionItem")
    
    # sdtContent
    sdt_content = etree.SubElement(sdt, qn("w:sdtContent"))
    
    for el in content_elements:
        sdt_content.append(el)
    
    return sdt


def xpath_relative(parent_path, child_field):
    """
    Create XPath for a field inside a repeating item.
    For relative bindings in repeating sections, we use the child element name directly.
    """
    return f"la:{child_field}"


# ─── Custom XML Part ──────────────────────────────────────────────────────

CUSTOM_XML_DATA = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<la:loan_agreement xmlns:la="{uri}">
  <la:agreement>
    <la:date></la:date>
    <la:city>Москва</la:city>
    <la:has_appendices></la:has_appendices>
  </la:agreement>
  <la:lender>
    <la:name></la:name>
    <la:representative></la:representative>
    <la:authority_basis></la:authority_basis>
    <la:signatory_title></la:signatory_title>
    <la:signatory_name></la:signatory_name>
    <la:account>
      <la:currency>рублях</la:currency>
      <la:number></la:number>
      <la:bank_name></la:bank_name>
      <la:bik></la:bik>
      <la:corr_account></la:corr_account>
    </la:account>
    <la:notice>
      <la:address></la:address>
      <la:attention></la:attention>
    </la:notice>
    <la:dispute_email></la:dispute_email>
  </la:lender>
  <la:borrower>
    <la:name></la:name>
    <la:representative></la:representative>
    <la:authority_basis></la:authority_basis>
    <la:signatory_title></la:signatory_title>
    <la:signatory_name></la:signatory_name>
    <la:entity_type></la:entity_type>
    <la:account>
      <la:currency>рублях</la:currency>
      <la:number></la:number>
      <la:bank_name></la:bank_name>
      <la:bik></la:bik>
      <la:corr_account></la:corr_account>
    </la:account>
    <la:notice>
      <la:address></la:address>
      <la:attention></la:attention>
    </la:notice>
    <la:dispute_email></la:dispute_email>
  </la:borrower>
  <la:loan>
    <la:amount></la:amount>
    <la:maturity_date></la:maturity_date>
    <la:interest_bearing_clause></la:interest_bearing_clause>
    <la:penalty_rate></la:penalty_rate>
    <la:penalty_payment_days>5 (пяти)</la:penalty_payment_days>
  </la:loan>
  <la:purpose>
    <la:description></la:description>
    <la:report_days>10 (десяти)</la:report_days>
    <la:early_return_days>5 (пяти)</la:early_return_days>
  </la:purpose>
  <la:interest>
    <la:payment_frequency>ежемесячно</la:payment_frequency>
    <la:dividend>
      <la:security_type></la:security_type>
      <la:issuer_name></la:issuer_name>
      <la:security_count></la:security_count>
      <la:capital_percentage></la:capital_percentage>
      <la:issuer_name_genitive></la:issuer_name_genitive>
      <la:payment_days>10 (десяти)</la:payment_days>
    </la:dividend>
  </la:interest>
  <la:interest_payment>
    <la:day_of_month>5 (пятый)</la:day_of_month>
  </la:interest_payment>
  <la:provision>
    <la:single_deadline></la:single_deadline>
    <la:tranches>
      <la:tranche>
        <la:ordinal>первый</la:ordinal>
        <la:amount></la:amount>
        <la:deadline></la:deadline>
      </la:tranche>
      <la:tranche>
        <la:ordinal>второй</la:ordinal>
        <la:amount></la:amount>
        <la:deadline></la:deadline>
      </la:tranche>
      <la:tranche>
        <la:ordinal>третий</la:ordinal>
        <la:amount></la:amount>
        <la:deadline></la:deadline>
      </la:tranche>
      <la:tranche>
        <la:ordinal>четвертый</la:ordinal>
        <la:amount></la:amount>
        <la:deadline></la:deadline>
      </la:tranche>
    </la:tranches>
  </la:provision>
  <la:covenants>
    <la:transaction_threshold></la:transaction_threshold>
    <la:disposal_threshold></la:disposal_threshold>
    <la:litigation_threshold></la:litigation_threshold>
    <la:info_litigation_threshold></la:info_litigation_threshold>
  </la:covenants>
  <la:reporting>
    <la:financial_days>10 (десяти)</la:financial_days>
    <la:other_info_days>5 (пяти)</la:other_info_days>
    <la:event_notification_days>5 (пяти)</la:event_notification_days>
    <la:pre_event_days>10 (десяти)</la:pre_event_days>
    <la:post_event_days>2 (двух)</la:post_event_days>
  </la:reporting>
  <la:default_events>
    <la:early_return_days>5 (пяти)</la:early_return_days>
    <la:cure_period_days>30 (тридцать)</la:cure_period_days>
  </la:default_events>
  <la:representations>
    <la:financial_report_date></la:financial_report_date>
    <la:ordinary_business_since></la:ordinary_business_since>
  </la:representations>
</la:loan_agreement>
""".format(uri=CUSTOM_XML_URI)

CUSTOM_XML_PROPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<ds:datastoreItem ds:itemID="{guid}" xmlns:ds="{ds_ns}">
  <ds:schemaRefs>
    <ds:schemaRef ds:uri="{uri}"/>
  </ds:schemaRefs>
</ds:datastoreItem>
""".format(guid=CUSTOM_XML_GUID, ds_ns=DS_NS, uri=CUSTOM_XML_URI)


# ─── XPath helper ─────────────────────────────────────────────────────────

def xpath(path):
    """Convert a simple path like 'lender/name' to XPath for Custom XML Part."""
    parts = path.split("/")
    return "/la:loan_agreement/" + "/".join(f"la:{p}" for p in parts)


# ─── Build document body ──────────────────────────────────────────────────

def build_document_body():
    """
    Build all w:body content as lxml elements.
    Returns a list of block-level elements (paragraphs, SDTs, tables).
    """
    elements = []
    
    # ═══════════════════════════════════════════════════════════
    # ШАПКА (COVER)
    # ═══════════════════════════════════════════════════════════
    
    # «ДАТА [date] ГОДА»
    p_date = make_paragraph(alignment="center", bold=True, spacing_before=0, spacing_after=120)
    p_date.append(make_run("ДАТА ", bold=True, size=24))
    p_date.append(make_inline_sdt(
        title="Дата заключения договора",
        tag="agreement/date",
        placeholder="дд.мм.гггг",
        sdt_type="date",
        xml_mapping_xpath=xpath("agreement/date"),
        default_value="[●]",
        run_props=[etree.Element(qn("w:b"))]
    ))
    p_date.append(make_run(" ГОДА", bold=True, size=24))
    elements.append(p_date)
    
    # Separator
    elements.append(make_separator_paragraph())
    
    # «ДОГОВОР ЗАЙМА»
    elements.append(make_paragraph(
        runs=[make_run("ДОГОВОР ЗАЙМА", bold=True, size=28)],
        alignment="center", spacing_before=240, spacing_after=240
    ))
    
    elements.append(make_separator_paragraph())
    
    # «МЕЖДУ»
    elements.append(make_paragraph(
        runs=[make_run("МЕЖДУ", bold=True, size=24)],
        alignment="center", spacing_before=240, spacing_after=120
    ))
    
    # Займодавец name (cover) — synced
    p_lender_cover = make_paragraph(alignment="center", spacing_after=60)
    p_lender_cover.append(make_inline_sdt(
        title="Наименование Займодавца",
        tag="lender/name",
        placeholder="Наименование / ФИО Займодавца",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/name"),
        default_value="[●]",
        run_props=[etree.Element(qn("w:b"))]
    ))
    elements.append(p_lender_cover)
    
    elements.append(make_paragraph(
        runs=[make_run("в качестве Займодавца", bold=True)],
        alignment="center", spacing_after=120
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("И", bold=True, size=24)],
        alignment="center", spacing_before=120, spacing_after=120
    ))
    
    # Заёмщик name (cover) — synced
    p_borrower_cover = make_paragraph(alignment="center", spacing_after=60)
    p_borrower_cover.append(make_inline_sdt(
        title="Наименование Заёмщика",
        tag="borrower/name",
        placeholder="Наименование / ФИО Заёмщика",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/name"),
        default_value="[●]",
        run_props=[etree.Element(qn("w:b"))]
    ))
    elements.append(p_borrower_cover)
    
    elements.append(make_paragraph(
        runs=[make_run("в качестве Заемщика", bold=True)],
        alignment="center", spacing_after=120
    ))
    
    # City
    p_city = make_paragraph(alignment="center", spacing_before=240, spacing_after=480)
    p_city.append(make_run("ГОРОД ", bold=True, size=24))
    p_city.append(make_inline_sdt(
        title="Город заключения договора",
        tag="agreement/city",
        placeholder="Москва",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("agreement/city"),
        default_value="Москва",
        run_props=[etree.Element(qn("w:b"))]
    ))
    elements.append(p_city)
    
    # ═══════════════════════════════════════════════════════════
    # ПРЕАМБУЛА
    # ═══════════════════════════════════════════════════════════
    
    # «Настоящий договор займа ("Договор") заключен [date] года ("Дата Договора") в городе [city]»
    p_preamble = make_paragraph(spacing_before=360, spacing_after=240)
    p_preamble.append(make_run('Настоящий договор займа ("'))
    p_preamble.append(make_run("Договор", bold=True))
    p_preamble.append(make_run('") заключен '))
    p_preamble.append(make_inline_sdt(
        title="Дата заключения договора",
        tag="agreement/date",
        sdt_type="date",
        xml_mapping_xpath=xpath("agreement/date"),
        default_value="[●]"
    ))
    p_preamble.append(make_run(' года ("'))
    p_preamble.append(make_run("Дата Договора", bold=True))
    p_preamble.append(make_run('") в городе '))
    p_preamble.append(make_inline_sdt(
        title="Город заключения договора",
        tag="agreement/city",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("agreement/city"),
        default_value="Москва"
    ))
    elements.append(p_preamble)
    
    # «МЕЖДУ:»
    elements.append(make_paragraph(
        runs=[make_run("МЕЖДУ", bold=True), make_run(":")],
        spacing_before=120, spacing_after=120
    ))
    
    # (1) Займодавец
    p_lender = make_paragraph(spacing_after=120)
    p_lender.append(make_run("(1) "))
    p_lender.append(make_inline_sdt(
        title="Наименование Займодавца",
        tag="lender/name",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/name"),
        default_value="[●]"
    ))
    p_lender.append(make_run(', именуемым в дальнейшем "'))
    p_lender.append(make_run("Займодавец", bold=True))
    p_lender.append(make_run('", в лице '))
    p_lender.append(make_inline_sdt(
        title="Представитель Займодавца",
        tag="lender/representative",
        placeholder="ФИО и должность",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/representative"),
        default_value="[●]"
    ))
    p_lender.append(make_run(", действующего на основании "))
    p_lender.append(make_inline_sdt(
        title="Основание полномочий Займодавца",
        tag="lender/authority_basis",
        placeholder="устава / доверенности №...",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/authority_basis"),
        default_value="[●]"
    ))
    p_lender.append(make_run(", с одной стороны, и"))
    elements.append(p_lender)
    
    # (2) Заёмщик
    p_borrower = make_paragraph(spacing_after=120)
    p_borrower.append(make_run("(2) "))
    p_borrower.append(make_inline_sdt(
        title="Наименование Заёмщика",
        tag="borrower/name",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/name"),
        default_value="[●]"
    ))
    p_borrower.append(make_run(', именуемым в дальнейшем "'))
    p_borrower.append(make_run("Заемщик", bold=True))
    p_borrower.append(make_run('", в лице '))
    p_borrower.append(make_inline_sdt(
        title="Представитель Заёмщика",
        tag="borrower/representative",
        placeholder="ФИО и должность",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/representative"),
        default_value="[●]"
    ))
    p_borrower.append(make_run(", действующего на основании "))
    p_borrower.append(make_inline_sdt(
        title="Основание полномочий Заёмщика",
        tag="borrower/authority_basis",
        placeholder="устава / доверенности №...",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/authority_basis"),
        default_value="[●]"
    ))
    p_borrower.append(make_run(", с другой стороны,"))
    elements.append(p_borrower)
    
    # совместно именуемыми...
    elements.append(make_paragraph(
        runs=[
            make_run('совместно именуемыми "'),
            make_run("Стороны", bold=True),
            make_run('", а по отдельности — "'),
            make_run("Сторона", bold=True),
            make_run('".'),
        ],
        spacing_after=360
    ))
    
    # ═══════════════════════════════════════════════════════════
    # СТАТЬЯ 1. ОПРЕДЕЛЕНИЯ И ТОЛКОВАНИЕ
    # ═══════════════════════════════════════════════════════════
    
    elements.append(make_paragraph(
        runs=[make_run("1. ОПРЕДЕЛЕНИЯ И ТОЛКОВАНИЕ", bold=True, size=24)],
        spacing_before=360, spacing_after=240, keep_next=True
    ))
    
    # 1.1. Определения
    elements.append(make_paragraph(
        runs=[make_run("1.1. Определения", bold=True)],
        spacing_after=120, keep_next=True
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("В Договоре приведенные ниже термины, если не указано иное в тексте Договора, имеют следующие значения:")],
        spacing_after=120
    ))
    
    # --- Дата Договора ---
    elements.append(make_paragraph(
        runs=[
            make_run('"'),
            make_run("Дата Договора", bold=True),
            make_run('" имеет значение, указанное во вступительной части Договора;'),
        ],
        spacing_after=60
    ))
    
    # --- Дата Погашения ---
    p_maturity = make_paragraph(spacing_after=60)
    p_maturity.append(make_run('"'))
    p_maturity.append(make_run("Дата Погашения", bold=True))
    p_maturity.append(make_run('" означает '))
    p_maturity.append(make_inline_sdt(
        title="Дата Погашения",
        tag="loan/maturity_date",
        placeholder="дата / срок погашения",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("loan/maturity_date"),
        default_value="[●]"
    ))
    p_maturity.append(make_run(";"))
    elements.append(p_maturity)
    
    # --- Дата Уплаты Процентов (альтернативы) ---
    # alt:interest_payment_date:1 — ежемесячно
    p_int_date_1_content = make_paragraph(spacing_after=60)
    p_int_date_1_content.append(make_run('['))
    p_int_date_1_content.append(make_run('"'))
    p_int_date_1_content.append(make_run("Дата Уплаты Процентов", bold=True))
    p_int_date_1_content.append(make_run('" означает дату, наступающую на '))
    p_int_date_1_content.append(make_inline_sdt(
        title="День месяца для уплаты процентов",
        tag="interest_payment/day_of_month",
        placeholder="5 (пятый)",
        sdt_type="combo_box",
        dropdown_items=[
            ("1 (первый)", "1 (первый)"),
            ("5 (пятый)", "5 (пятый)"),
            ("10 (десятый)", "10 (десятый)"),
            ("15 (пятнадцатый)", "15 (пятнадцатый)"),
            ("последний", "последний"),
        ],
        xml_mapping_xpath=xpath("interest_payment/day_of_month"),
        default_value="5 (пятый)"
    ))
    p_int_date_1_content.append(make_run(" рабочий день месяца, следующего за месяцем, за который начисляются Проценты;]"))
    
    interest_date_alt1 = make_sdt_block(
        title="Дата Уплаты Процентов: ежемесячно",
        tag="alt:interest_payment_date:1",
        sdt_type="rich_text",
        content_elements=[p_int_date_1_content]
    )
    elements.append(interest_date_alt1)
    
    # Разделитель /
    elements.append(make_paragraph(runs=[make_run("/")], alignment="center", spacing_before=60, spacing_after=60))
    
    # alt:interest_payment_date:2 — на дату погашения
    p_int_date_2_content = make_paragraph(spacing_after=60)
    p_int_date_2_content.append(make_run('['))
    p_int_date_2_content.append(make_run('"'))
    p_int_date_2_content.append(make_run("Дата Уплаты Процентов", bold=True))
    p_int_date_2_content.append(make_run('" означает Дату Погашения;]'))
    
    interest_date_alt2 = make_sdt_block(
        title="Дата Уплаты Процентов: на дату погашения",
        tag="alt:interest_payment_date:2",
        sdt_type="rich_text",
        content_elements=[p_int_date_2_content]
    )
    elements.append(interest_date_alt2)
    
    # --- Заверения Заемщика ---
    elements.append(make_paragraph(
        runs=[
            make_run('"'),
            make_run("Заверения Заемщика", bold=True),
            make_run('" означает заверения об обстоятельствах, предоставленные Заемщиком Займодавцу в соответствии с пунктом 8.1;'),
        ],
        spacing_after=60
    ))
    
    # --- Заем ---
    elements.append(make_paragraph(
        runs=[
            make_run('"'),
            make_run("Заем", bold=True),
            make_run('" означает денежные средства, предоставленные Займодавцем Заемщику в виде займа по настоящему Договору;'),
        ],
        spacing_after=60
    ))
    
    # --- Проценты (optional) ---
    p_interest_def_content = make_paragraph(spacing_after=60)
    p_interest_def_content.append(make_run('['))
    p_interest_def_content.append(make_run('"'))
    p_interest_def_content.append(make_run("Проценты", bold=True))
    p_interest_def_content.append(make_run('" имеет значение, указанное в пункте 2.3;]'))
    
    interest_def_opt = make_sdt_block(
        title="Определение «Проценты»",
        tag="optional:interest_definition",
        sdt_type="rich_text",
        content_elements=[p_interest_def_content]
    )
    elements.append(interest_def_opt)
    
    # --- РАЦ (optional) ---
    p_rac_def_content = make_paragraph(spacing_after=60)
    p_rac_def_content.append(make_run('['))
    p_rac_def_content.append(make_run('"'))
    p_rac_def_content.append(make_run("РАЦ", bold=True))
    p_rac_def_content.append(make_run('" имеет значение, указанное в пункте 16.1;]'))
    
    rac_def_opt = make_sdt_block(
        title="Определение «РАЦ»",
        tag="optional:rac_definition",
        sdt_type="rich_text",
        content_elements=[p_rac_def_content]
    )
    elements.append(rac_def_opt)
    
    # --- Случай неисполнения ---
    elements.append(make_paragraph(
        runs=[
            make_run('"'),
            make_run("Случай неисполнения", bold=True),
            make_run('" означает любое событие или обстоятельство, указанное в статье 6;'),
        ],
        spacing_after=60
    ))
    
    # --- Счет Заемщика ---
    p_account_borrower = make_paragraph(spacing_after=60)
    p_account_borrower.append(make_run('"'))
    p_account_borrower.append(make_run("Счет Заемщика", bold=True))
    p_account_borrower.append(make_run('" означает расчетный счет Заемщика в '))
    p_account_borrower.append(make_inline_sdt(
        title="Валюта счёта Заёмщика",
        tag="borrower/account/currency",
        placeholder="рублях",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/account/currency"),
        default_value="рублях"
    ))
    p_account_borrower.append(make_run(" № "))
    p_account_borrower.append(make_inline_sdt(
        title="Номер счёта Заёмщика",
        tag="borrower/account/number",
        placeholder="номер счёта",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/account/number"),
        default_value="[●]"
    ))
    p_account_borrower.append(make_run(", открытый в "))
    p_account_borrower.append(make_inline_sdt(
        title="Банк Заёмщика",
        tag="borrower/account/bank_name",
        placeholder="наименование банка",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/account/bank_name"),
        default_value="[●]"
    ))
    p_account_borrower.append(make_run(" (БИК: "))
    p_account_borrower.append(make_inline_sdt(
        title="БИК банка Заёмщика",
        tag="borrower/account/bik",
        placeholder="БИК",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/account/bik"),
        default_value="[●]"
    ))
    p_account_borrower.append(make_run(", к/с "))
    p_account_borrower.append(make_inline_sdt(
        title="Корр. счёт банка Заёмщика",
        tag="borrower/account/corr_account",
        placeholder="корр. счёт",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/account/corr_account"),
        default_value="[●]"
    ))
    p_account_borrower.append(make_run(");"))
    elements.append(p_account_borrower)
    
    # --- Счет Займодавца ---
    p_account_lender = make_paragraph(spacing_after=60)
    p_account_lender.append(make_run('"'))
    p_account_lender.append(make_run("Счет Займодавца", bold=True))
    p_account_lender.append(make_run('" означает расчетный счет Займодавца в '))
    p_account_lender.append(make_inline_sdt(
        title="Валюта счёта Займодавца",
        tag="lender/account/currency",
        placeholder="рублях",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/account/currency"),
        default_value="рублях"
    ))
    p_account_lender.append(make_run(" № "))
    p_account_lender.append(make_inline_sdt(
        title="Номер счёта Займодавца",
        tag="lender/account/number",
        placeholder="номер счёта",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/account/number"),
        default_value="[●]"
    ))
    p_account_lender.append(make_run(", открытый в "))
    p_account_lender.append(make_inline_sdt(
        title="Банк Займодавца",
        tag="lender/account/bank_name",
        placeholder="наименование банка",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/account/bank_name"),
        default_value="[●]"
    ))
    p_account_lender.append(make_run(" (БИК: "))
    p_account_lender.append(make_inline_sdt(
        title="БИК банка Займодавца",
        tag="lender/account/bik",
        placeholder="БИК",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/account/bik"),
        default_value="[●]"
    ))
    p_account_lender.append(make_run(", к/с "))
    p_account_lender.append(make_inline_sdt(
        title="Корр. счёт банка Займодавца",
        tag="lender/account/corr_account",
        placeholder="корр. счёт",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/account/corr_account"),
        default_value="[●]"
    ))
    p_account_lender.append(make_run(");"))
    elements.append(p_account_lender)
    
    # --- Транш (optional) ---
    p_tranche_def_content = make_paragraph(spacing_after=60)
    p_tranche_def_content.append(make_run('['))
    p_tranche_def_content.append(make_run('"'))
    p_tranche_def_content.append(make_run("Транш", bold=True))
    p_tranche_def_content.append(make_run('" имеет значение, указанное в пункте 3.1.1;]'))
    
    tranche_def_opt = make_sdt_block(
        title="Определение «Транш»",
        tag="optional:tranche_definition",
        sdt_type="rich_text",
        content_elements=[p_tranche_def_content]
    )
    elements.append(tranche_def_opt)
    
    # 1.2. Толкование
    elements.append(make_paragraph(
        runs=[make_run("1.2. Толкование", bold=True)],
        spacing_before=180, spacing_after=120, keep_next=True
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("В Договоре, если иное прямо не следует из текста:")],
        spacing_after=60
    ))
    
    # 1.2.1
    elements.append(make_paragraph(
        runs=[make_run("1.2.1. ссылки на Договор или иной документ понимаются как ссылки на Договор или соответствующий иной документ с учетом периодически вносимых в них изменений;")],
        spacing_after=60
    ))
    
    # 1.2.2
    elements.append(make_paragraph(
        runs=[make_run('1.2.2. слово "лицо" может означать физическое лицо, юридическое лицо, организацию без прав юридического лица, государство или государственный орган;')],
        spacing_after=60
    ))
    
    # 1.2.3 (с optional:has_appendices)
    p_123 = make_paragraph(spacing_after=60)
    p_123.append(make_run("1.2.3. ссылка на "))
    p_123.append(make_inline_sdt(
        title="«преамбулу,» (если есть приложения)",
        tag="optional:has_appendices",
        sdt_type="rich_text",
        default_value="преамбулу, "
    ))
    p_123.append(make_run("статью, пункт "))
    p_123.append(make_inline_sdt(
        title="«или приложение» (если есть приложения)",
        tag="optional:has_appendices",
        sdt_type="rich_text",
        default_value="или приложение "
    ))
    p_123.append(make_run("является ссылкой на "))
    p_123.append(make_inline_sdt(
        title="«преамбулу,» (если есть приложения)",
        tag="optional:has_appendices",
        sdt_type="rich_text",
        default_value="преамбулу, "
    ))
    p_123.append(make_run("статью, пункт Договора "))
    p_123.append(make_inline_sdt(
        title="«или приложение к Договору» (если есть приложения)",
        tag="optional:has_appendices",
        sdt_type="rich_text",
        default_value="или приложение к Договору"
    ))
    p_123.append(make_run(", если иное прямо не следует из контекста;"))
    elements.append(p_123)
    
    # 1.2.4
    p_124 = make_paragraph(spacing_after=60)
    p_124.append(make_run("1.2.4. заголовки пунктов, статей "))
    p_124.append(make_inline_sdt(
        title="«и приложений» (если есть приложения)",
        tag="optional:has_appendices",
        sdt_type="rich_text",
        default_value="и приложений "
    ))
    p_124.append(make_run("используются только для удобства и не влияют на толкование Договора;"))
    elements.append(p_124)
    
    # 1.2.5
    elements.append(make_paragraph(
        runs=[make_run("1.2.5. слова в единственном числе включают множественное и наоборот;")],
        spacing_after=60
    ))
    
    # ═══════════════════════════════════════════════════════════
    # СТАТЬЯ 2. ПРЕДМЕТ ДОГОВОРА
    # ═══════════════════════════════════════════════════════════
    
    elements.append(make_paragraph(
        runs=[make_run("2. ПРЕДМЕТ ДОГОВОРА", bold=True, size=24)],
        spacing_before=360, spacing_after=240, keep_next=True
    ))
    
    # 2.1 Заём
    elements.append(make_paragraph(
        runs=[make_run("2.1. Заем", bold=True)],
        spacing_before=120, spacing_after=120, keep_next=True
    ))
    
    p_loan = make_paragraph(spacing_after=120)
    p_loan.append(make_run("При условии соблюдения Заемщиком положений настоящего Договора, Займодавец обязуется предоставить Заемщику Заем в размере "))
    p_loan.append(make_inline_sdt(
        title="Сумма Займа",
        tag="loan/amount",
        placeholder="сумма цифрами и прописью",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("loan/amount"),
        default_value="[●]"
    ))
    p_loan.append(make_run(" рублей, а Заемщик обязуется в течение срока действия Договора надлежащим образом исполнять предусмотренные Договором обязательства, включая обязательство возвратить Займодавцу сумму полученного от него Займа и выплатить "))
    # optional: interest_bearing_clause (inline) — «Проценты и»
    p_loan.append(make_inline_sdt(
        title="«Проценты и» (п. 2.1)",
        tag="optional:interest_bearing_clause",
        sdt_type="rich_text",
        default_value="Проценты и "
    ))
    p_loan.append(make_run("все иные суммы, предусмотренные настоящим Договором."))
    elements.append(p_loan)
    
    # ─── 2.2 Целевое назначение (optional block) ───
    purpose_block = make_sdt_block(
        title="Пункт 2.2 «Целевое назначение»",
        tag="optional:purpose",
        sdt_type="rich_text",
        content_elements=build_purpose_section()
    )
    elements.append(purpose_block)
    
    # ─── 2.3 Проценты (3 alternative blocks) ───
    elements.append(make_paragraph(
        runs=[make_run("2.3. Проценты", bold=True)],
        spacing_before=120, spacing_after=120, keep_next=True
    ))
    
    # Alt 1: беспроцентный
    alt1 = make_sdt_block(
        title="Проценты: беспроцентный заём",
        tag="alt:interest_type:1",
        sdt_type="rich_text",
        content_elements=[
            make_paragraph(
                runs=[make_run("Проценты на сумму Займа не начисляются.")],
                spacing_after=120
            )
        ]
    )
    elements.append(alt1)
    
    # Separator /
    elements.append(make_paragraph(
        runs=[make_run("/")],
        alignment="center", spacing_before=60, spacing_after=60
    ))
    
    # Alt 2: ключевая ставка
    alt2_content = []
    p_rate = make_paragraph(spacing_after=60)
    p_rate.append(make_run("За пользование суммой Займа по настоящему Договору с даты, следующей за датой зачисления на Счет Заемщика суммы соответствующего Транша (включительно) до Даты Погашения (включительно) Заемщику начисляются проценты в размере, равном ключевой ставке Банка России, установленной на дату выдачи соответствующего Транша, а в последующем установленной на каждую дату, начиная с которой изменяется ключевая ставка Банка России, годовых (\""))
    p_rate.append(make_run("Проценты", bold=True))
    p_rate.append(make_run("\"). Пересмотр размера процентной ставки по договору в связи с изменением ключевой ставки Банка России производится автоматически, то есть без дополнительного волеизъявления Сторон."))
    alt2_content.append(p_rate)
    
    p_freq = make_paragraph(spacing_after=120)
    p_freq.append(make_run("Заемщик обязуется "))
    p_freq.append(make_inline_sdt(
        title="Периодичность уплаты процентов (по умолч. «ежемесячно»)",
        tag="interest/payment_frequency",
        sdt_type="combo_box",
        dropdown_items=[("ежемесячно", "ежемесячно"), ("ежеквартально", "ежеквартально")],
        xml_mapping_xpath=xpath("interest/payment_frequency"),
        default_value="ежемесячно"
    ))
    p_freq.append(make_run(" уплачивать Займодавцу Проценты в каждую Дату Уплаты Процентов. При расчете Процентов количество дней в месяце и в году принимается равным календарному."))
    alt2_content.append(p_freq)
    
    alt2 = make_sdt_block(
        title="Проценты: ключевая ставка ЦБ",
        tag="alt:interest_type:2",
        sdt_type="rich_text",
        content_elements=alt2_content
    )
    elements.append(alt2)
    
    # Separator /
    elements.append(make_paragraph(
        runs=[make_run("/")],
        alignment="center", spacing_before=60, spacing_after=60
    ))
    
    # Alt 3: дивидендный
    alt3_content = []
    p_div = make_paragraph(spacing_after=60)
    p_div.append(make_run("На сумму Займа подлежат начислению проценты в размере, эквивалентном размеру дивидендов, объявленных на "))
    p_div.append(make_inline_sdt(
        title="Тип ценных бумаг",
        tag="interest/dividend/security_type",
        sdt_type="dropdown",
        dropdown_items=[("акции", "акции"), ("доли", "доли")],
        xml_mapping_xpath=xpath("interest/dividend/security_type"),
        default_value="акции"
    ))
    p_div.append(make_run(" "))
    p_div.append(make_inline_sdt(
        title="Наименование эмитента",
        tag="interest/dividend/issuer_name",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("interest/dividend/issuer_name"),
        placeholder="наименование ЮЛ",
        default_value="[●]"
    ))
    p_div.append(make_run(", в количестве "))
    p_div.append(make_inline_sdt(
        title="Количество ценных бумаг",
        tag="interest/dividend/security_count",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("interest/dividend/security_count"),
        placeholder="количество",
        default_value="[●]"
    ))
    p_div.append(make_run(" штук, составляющих на Дату Договора "))
    p_div.append(make_inline_sdt(
        title="% от уставного капитала",
        tag="interest/dividend/capital_percentage",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("interest/dividend/capital_percentage"),
        placeholder="процент",
        default_value="[●]"
    ))
    p_div.append(make_run("% от уставного капитала "))
    p_div.append(make_inline_sdt(
        title="Наименование эмитента (род. падеж)",
        tag="interest/dividend/issuer_name_genitive",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("interest/dividend/issuer_name_genitive"),
        placeholder="наименование ЮЛ в род. падеже",
        default_value="[●]"
    ))
    p_div.append(make_run(' ("'))
    p_div.append(make_run("Проценты", bold=True))
    p_div.append(make_run('").'))
    alt3_content.append(p_div)
    
    p_div_pay = make_paragraph(spacing_after=120)
    p_div_pay.append(make_run("Проценты, предусмотренные статьей 2.3, выплачиваются Заемщиком в течение "))
    p_div_pay.append(make_inline_sdt(
        title="Срок выплаты дивидендных процентов",
        tag="interest/dividend/payment_days",
        sdt_type="combo_box",
        dropdown_items=[("10 (десяти)", "10 (десяти)"), ("5 (пяти)", "5 (пяти)")],
        xml_mapping_xpath=xpath("interest/dividend/payment_days"),
        default_value="10 (десяти)"
    ))
    p_div_pay.append(make_run(" рабочих дней после окончания месяца, в котором были объявлены дивиденды."))
    alt3_content.append(p_div_pay)
    
    alt3 = make_sdt_block(
        title="Проценты: привязка к дивидендам",
        tag="alt:interest_type:3",
        sdt_type="rich_text",
        content_elements=alt3_content
    )
    elements.append(alt3)
    
    # ═══════════════════════════════════════════════════════════
    # СТАТЬЯ 3. ПОРЯДОК ПРЕДОСТАВЛЕНИЯ И ВОЗВРАТА ЗАЙМА
    # ═══════════════════════════════════════════════════════════
    
    elements.append(make_paragraph(
        runs=[make_run("3. ПОРЯДОК ПРЕДОСТАВЛЕНИЯ И ВОЗВРАТА ЗАЙМА", bold=True, size=24)],
        spacing_before=360, spacing_after=240, keep_next=True
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("3.1. Предоставление Займа", bold=True)],
        spacing_before=120, spacing_after=120, keep_next=True
    ))
    
    # ─── Alt: единовременно vs. траншами ───
    # Alt 1: единовременная выдача
    alt_prov1_content = []
    p_prov1 = make_paragraph(spacing_after=120)
    p_prov1.append(make_run("3.1.1. Займодавец обязуется предоставить Заемщику Заем путем перевода соответствующей суммы в рублях на Счет Заемщика не позднее "))
    p_prov1.append(make_inline_sdt(
        title="Срок предоставления Займа",
        tag="provision/single_deadline",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("provision/single_deadline"),
        placeholder="дата / описание срока",
        default_value="[●]"
    ))
    p_prov1.append(make_run("."))
    alt_prov1_content.append(p_prov1)
    
    elements.append(make_sdt_block(
        title="Предоставление: единовременно",
        tag="alt:loan_provision:1",
        sdt_type="rich_text",
        content_elements=alt_prov1_content
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("/")],
        alignment="center", spacing_before=60, spacing_after=60
    ))
    
    # Alt 2: траншами (с Repeating Section Content Control)
    alt_prov2_content = []
    alt_prov2_content.append(make_paragraph(
        runs=[make_run("3.1.1. Займодавец обязуется предоставить Заемщику Заем путем перевода соответствующей суммы в рублях на Счет Заемщика несколькими траншами (\""),
              make_run("Транш", bold=True),
              make_run("\") в следующем порядке:")],
        spacing_after=60
    ))
    
    # Build Repeating Section with 4 tranche items
    # Each item has: ordinal, amount, deadline with XML bindings
    tranche_items = []
    tranche_data = [
        ("первый", "i", 1),
        ("второй", "ii", 2),
        ("третий", "iii", 3),
        ("четвертый", "iv", 4)
    ]
    
    for ordinal, num, idx in tranche_data:
        # Create paragraph for this tranche
        p_tr = make_paragraph(spacing_after=40)
        p_tr.append(make_run(f"({num}) "))
        
        # Ordinal - mapped to la:tranche[idx]/la:ordinal
        p_tr.append(make_inline_sdt(
            title=f"Номер транша",
            tag=f"provision/tranches/tranche[{idx}]/ordinal",
            sdt_type="plain_text",
            xml_mapping_xpath=f"/la:loan_agreement/la:provision/la:tranches/la:tranche[{idx}]/la:ordinal",
            default_value=ordinal
        ))
        p_tr.append(make_run(" транш в размере "))
        
        # Amount - mapped to la:tranche[idx]/la:amount
        p_tr.append(make_inline_sdt(
            title=f"Сумма транша",
            tag=f"provision/tranches/tranche[{idx}]/amount",
            sdt_type="plain_text",
            xml_mapping_xpath=f"/la:loan_agreement/la:provision/la:tranches/la:tranche[{idx}]/la:amount",
            placeholder="сумма",
            default_value="[●]"
        ))
        p_tr.append(make_run(" рублей предоставляется не позднее "))
        
        # Deadline - mapped to la:tranche[idx]/la:deadline
        p_tr.append(make_inline_sdt(
            title=f"Срок транша",
            tag=f"provision/tranches/tranche[{idx}]/deadline",
            sdt_type="plain_text",
            xml_mapping_xpath=f"/la:loan_agreement/la:provision/la:tranches/la:tranche[{idx}]/la:deadline",
            placeholder="срок",
            default_value="[●]"
        ))
        p_tr.append(make_run(";" if idx < 4 else "."))
        
        # Each tranche paragraph becomes one repeating section item
        tranche_items.append([p_tr])
    
    # Create the Repeating Section SDT wrapping all tranche items
    repeating_section = make_repeating_section(
        title="Транши",
        tag="provision/tranches",
        xml_mapping_xpath="/la:loan_agreement/la:provision/la:tranches",
        items_content=tranche_items
    )
    alt_prov2_content.append(repeating_section)
    
    elements.append(make_sdt_block(
        title="Предоставление: траншами",
        tag="alt:loan_provision:2",
        sdt_type="rich_text",
        content_elements=alt_prov2_content
    ))
    
    # 3.1.2 — момент предоставления
    p_312 = make_paragraph(spacing_before=120, spacing_after=120)
    p_312.append(make_run("3.1.2. "))
    p_312.append(make_inline_sdt(
        title="«Сумма Займа» / «Каждый из траншей...»",
        tag="alt:loan_provision__p312_subject",
        sdt_type="dropdown",
        dropdown_items=[("Сумма Займа", "Сумма Займа"), ("Каждый из траншей, указанных в пункте 3.1.1 выше,", "Каждый из траншей")],
        default_value="Сумма Займа"
    ))
    p_312.append(make_run(" считается предоставленн"))
    p_312.append(make_inline_sdt(
        title="Окончание «-ым» / «-ой»",
        tag="provision__gender_suffix",
        sdt_type="dropdown",
        dropdown_items=[("ой", "ой"), ("ым", "ым")],
        default_value="ой"
    ))
    p_312.append(make_run(" с момента списания соответствующей суммы с корреспондентского счета банка Займодавца."))
    elements.append(p_312)
    
    # 3.2 Право на отказ
    elements.append(make_paragraph(
        runs=[make_run("3.2. Право на отказ от предоставления Займа", bold=True)],
        spacing_before=120, spacing_after=120, keep_next=True
    ))
    
    p_refusal = make_paragraph(spacing_after=60)
    p_refusal.append(make_run("Займодавец вправе отказаться от предоставления "))
    p_refusal.append(make_inline_sdt(
        title="«Займа» / «любого Транша»",
        tag="alt:loan_provision__refusal_object",
        sdt_type="dropdown",
        dropdown_items=[("Займа", "Займа"), ("любого Транша", "любого Транша")],
        default_value="Займа"
    ))
    p_refusal.append(make_run(" в следующих случаях:"))
    elements.append(p_refusal)
    
    for letter, text in [
        ("a", "при наличии или наступлении Случая неисполнения или если Займодавец обоснованно полагает, что какой-либо Случай неисполнения может наступить;"),
        ("b", "при наличии обстоятельств, которые, по мнению Займодавца, очевидно свидетельствуют о том, что Заем не будет возвращен Заемщиком в установленный Договором срок; или"),
        ("c", "в иных случаях, предусмотренных законодательством."),
    ]:
        elements.append(make_paragraph(
            runs=[make_run(f"({letter}) {text}")],
            spacing_after=40
        ))
    
    # 3.3 Последствия отказа
    elements.append(make_paragraph(
        runs=[make_run("3.3. Последствия отказа от предоставления Займа", bold=True)],
        spacing_before=120, spacing_after=60, keep_next=True
    ))
    elements.append(make_paragraph(
        runs=[make_run("В случае отказа Займодавца от предоставления Займа Стороны соглашаются, что Займодавец не несет какой-либо ответственности перед Заемщиком за такой отказ от предоставления Займа.")],
        spacing_after=120
    ))
    
    # 3.4 Возврат Займа
    elements.append(make_paragraph(
        runs=[make_run("3.4. Возврат Займа", bold=True)],
        spacing_before=120, spacing_after=120, keep_next=True
    ))
    
    # 3.4.1
    p_341 = make_paragraph(spacing_after=60)
    p_341.append(make_run("3.4.1. Заемщик обязуется вернуть сумму Займа "))
    p_341.append(make_inline_sdt(
        title="«и причитающиеся непогашенные Проценты» (п. 3.4.1)",
        tag="optional:interest_bearing_clause",
        sdt_type="rich_text",
        default_value="и причитающиеся непогашенные Проценты "
    ))
    p_341.append(make_run("в Дату Погашения путем перевода суммы Займа на Счет Займодавца."))
    elements.append(p_341)
    
    # 3.4.2
    elements.append(make_paragraph(
        runs=[make_run("3.4.2. Частичное погашение Заемщиком суммы Займа по Договору не допускается.")],
        spacing_after=60
    ))
    
    # 3.4.3
    p_343 = make_paragraph(spacing_after=60)
    p_343.append(make_run("3.4.3. Заемщик обязан возвратить сумму Займа "))
    p_343.append(make_inline_sdt(
        title="«и причитающиеся непогашенные Проценты» (п. 3.4.3, 1-е)",
        tag="optional:interest_bearing_clause",
        sdt_type="rich_text",
        default_value="и причитающиеся непогашенные Проценты "
    ))
    p_343.append(make_run("в рублях. Датой возврата суммы Займа "))
    p_343.append(make_inline_sdt(
        title="«и причитающихся непогашенных Процентов» (п. 3.4.3, 2-е)",
        tag="optional:interest_bearing_clause",
        sdt_type="rich_text",
        default_value="и причитающихся непогашенных Процентов "
    ))
    p_343.append(make_run("по Договору считается дата зачисления в полном объеме суммы Займа "))
    p_343.append(make_inline_sdt(
        title="«и причитающихся непогашенных Процентов» (п. 3.4.3, 3-е)",
        tag="optional:interest_bearing_clause",
        sdt_type="rich_text",
        default_value="и причитающихся непогашенных Процентов "
    ))
    p_343.append(make_run("на Счет Займодавца."))
    elements.append(p_343)
    
    # 3.4.4
    elements.append(make_paragraph(
        runs=[make_run("3.4.4. Заемщик вправе осуществлять досрочный возврат всего Займа или любой его части исключительно при условии получения предварительного письменного согласия Займодавца.")],
        spacing_after=120
    ))
    
    # 3.5 Неустойка
    elements.append(make_paragraph(
        runs=[make_run("3.5. Неустойка", bold=True)],
        spacing_before=120, spacing_after=60, keep_next=True
    ))
    
    p_penalty = make_paragraph(spacing_after=60)
    p_penalty.append(make_run("В случае, если Заемщик допустит просрочку исполнения каких-либо денежных обязательств в соответствии с Договором, Займодавец вправе потребовать уплаты Заемщиком неустойки в размере "))
    p_penalty.append(make_inline_sdt(
        title="Размер неустойки, %",
        tag="loan/penalty_rate",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("loan/penalty_rate"),
        placeholder="0,1",
        default_value="[●]"
    ))
    p_penalty.append(make_run("% от суммы соответствующего обязательства, которое не исполнено Заемщиком в срок, за каждый день просрочки. Заемщик обязуется выплатить неустойку в срок, установленный Займодавцем, который в любом случае должен составлять не менее "))
    p_penalty.append(make_inline_sdt(
        title="Срок уплаты неустойки (по умолч. «5 (пяти)»)",
        tag="loan/penalty_payment_days",
        sdt_type="combo_box",
        dropdown_items=[("5 (пяти)", "5 (пяти)"), ("10 (десяти)", "10 (десяти)")],
        xml_mapping_xpath=xpath("loan/penalty_payment_days"),
        default_value="5 (пяти)"
    ))
    p_penalty.append(make_run(" рабочих дней."))
    elements.append(p_penalty)
    
    # ═══════════════════════════════════════════════════════════
    # СТАТЬЯ 4. ОБЯЗАТЕЛЬСТВА ОБЩЕГО ХАРАКТЕРА
    # ═══════════════════════════════════════════════════════════
    
    elements.append(make_paragraph(
        runs=[make_run("4. ОБЯЗАТЕЛЬСТВА ОБЩЕГО ХАРАКТЕРА", bold=True, size=24)],
        spacing_before=360, spacing_after=240, keep_next=True
    ))
    
    # 4.1 Совершение сделок
    p_41 = make_paragraph(spacing_after=120)
    p_41.append(make_run("4.1. Совершение сделок. ", bold=True))
    p_41.append(make_run("Заемщик обязуется без предварительного письменного согласия Займодавца не совершать сделки или серии взаимосвязанных сделок на сумму свыше "))
    p_41.append(make_inline_sdt(
        title="Предельная сумма сделок (п. 4.1)",
        tag="covenants/transaction_threshold",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("covenants/transaction_threshold"),
        placeholder="сумма",
        default_value="[●]"
    ))
    p_41.append(make_run(" рублей."))
    elements.append(p_41)
    
    # 4.2 Отчуждение активов
    p_42 = make_paragraph(spacing_after=120)
    p_42.append(make_run("4.2. Отчуждение активов. ", bold=True))
    p_42.append(make_run("Заемщик обязуется без предварительного письменного согласия Займодавца не Отчуждать какие-либо активы на сумму более "))
    p_42.append(make_inline_sdt(
        title="Предельная сумма отчуждения (п. 4.2)",
        tag="covenants/disposal_threshold",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("covenants/disposal_threshold"),
        placeholder="сумма",
        default_value="[●]"
    ))
    p_42.append(make_run(" рублей."))
    elements.append(p_42)
    
    # 4.3–4.6 — static text
    for num, title_text, body_text in [
        ("4.3", "Обременение активов", "Заемщик обязуется без предварительного согласия Займодавца не создавать и не допускать существования какого-либо Обременения в отношении имущества Заемщика, за исключением Обременений в пользу Займодавца."),
        ("4.4", "Долговое финансирование", "Заемщик обязуется без предварительного согласия Займодавца не выступать в качестве займодавца в отношении какой-либо Финансовой задолженности."),
        ("4.5", "Запрет на предоставление поручительств", "Заемщик обязуется не выступать поручителем в отношении обязательств какого-либо лица без предварительного письменного согласия Займодавца."),
        ("4.6", "Налогообложение", "Заемщик обязуется своевременно платить Налоги."),
    ]:
        elements.append(make_paragraph(
            runs=[make_run(f"{num}. {title_text}. ", bold=True), make_run(body_text)],
            spacing_after=120
        ))
    
    # 4.7 Подготовка фин. отчётности (optional)
    elements.append(make_sdt_block(
        title="П. 4.7 «Подготовка фин. отчётности»",
        tag="optional:financial_reporting_covenant",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("4.7. Подготовка финансовой отчетности. ", bold=True),
                  make_run("Заемщик обязан обеспечить подготовку бухгалтерской (финансовой) отчетности Заемщика в соответствии с требованиями законодательства и применимыми стандартами бухгалтерского учета.")],
            spacing_after=120
        )]
    ))
    
    # 4.8 Судебные разбирательства
    p_48 = make_paragraph(spacing_after=120)
    p_48.append(make_run("4.8. Судебные разбирательства. ", bold=True))
    p_48.append(make_run("Заемщик обязуется без предварительного согласия Займодавца не признавать иск, не отказываться от иска и не заключать мировое соглашение в каком-либо гражданском разбирательстве, в котором Заемщик является стороной, третьим лицом или иным участвующим или привлеченным к делу лицом, если в результате указанных действий у Заемщика возникнут или могут возникнуть обязательства в размере, превышающем "))
    p_48.append(make_inline_sdt(
        title="Предельная сумма суд. разбирательств (п. 4.8)",
        tag="covenants/litigation_threshold",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("covenants/litigation_threshold"),
        placeholder="сумма",
        default_value="[●]"
    ))
    p_48.append(make_run(" рублей за исключением обязанности по компенсации убытков и (или) уплате неустойки, величина которых не утверждена судом или не отражена в мировом соглашении."))
    elements.append(p_48)
    
    # 4.9 Ограничения на распределение прибыли (optional)
    elements.append(make_sdt_block(
        title="П. 4.9 «Ограничения на распределение прибыли»",
        tag="optional:profit_distribution_restriction",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("4.9. Ограничения на распределение прибыли. ", bold=True),
                  make_run("Заемщик обязуется без предварительного согласия Займодавца не распределять прибыль участникам Заемщика.")],
            spacing_after=120
        )]
    ))
    
    # 4.10 Доступ (optional)
    elements.append(make_sdt_block(
        title="П. 4.10 «Доступ»",
        tag="optional:access_covenant",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("4.10. Доступ. ", bold=True),
                  make_run("По предварительному письменному запросу Займодавца Заемщик обязан в течение 10 (десяти) дней с даты такого запроса предоставить Займодавцу и (или) его аудиторам, консультантам или другим представителям доступ к помещениям, активам и первичным документам бухгалтерского и налогового учета Заемщика на бумажных и (или) электронных носителях.")],
            spacing_after=120
        )]
    ))
    
    # ═══════════════════════════════════════════════════════════
    # СТАТЬЯ 5. ОБЯЗАТЕЛЬСТВА ПО ПРЕДОСТАВЛЕНИЮ ИНФОРМАЦИИ
    # ═══════════════════════════════════════════════════════════
    
    elements.append(make_paragraph(
        runs=[make_run("5. ОБЯЗАТЕЛЬСТВА ПО ПРЕДОСТАВЛЕНИЮ ИНФОРМАЦИИ", bold=True, size=24)],
        spacing_before=360, spacing_after=240, keep_next=True
    ))
    
    # 5.1 Финансовая отчётность
    p_51 = make_paragraph(spacing_after=60)
    p_51.append(make_run("5.1. Финансовая отчетность. ", bold=True))
    p_51.append(make_run("По требованию Займодавца, Заемщик, в течение "))
    p_51.append(make_inline_sdt(
        title="Срок предоставления фин. отчётности (по умолч.)",
        tag="reporting/financial_days",
        sdt_type="combo_box",
        dropdown_items=[("10 (десяти)", "10 (десяти)"), ("5 (пяти)", "5 (пяти)"), ("15 (пятнадцати)", "15 (пятнадцати)")],
        xml_mapping_xpath=xpath("reporting/financial_days"),
        default_value="10 (десяти)"
    ))
    p_51.append(make_run(" рабочих дней с даты получения такого требования, обязан предоставлять Займодавцу следующую информацию в отношении Заемщика:"))
    elements.append(p_51)
    
    for letter, text in [
        ("a", "бухгалтерскую (финансовую) отчетность, в частности, годовую и полугодовую в составе и по формам, установленным законодательством Российской Федерации, с отметкой о способе отправления документа в подразделение ФНС России (для годовой отчетности), заверенную руководителем и печатью Заемщика;"),
        ("b", "расшифровки кредиторской и дебиторской задолженности с указанием наименований кредиторов, должников, суммы задолженности и дат возникновения задолженности, с указанием статуса данной задолженности (просроченная / текущая);"),
        ("c", "расшифровки краткосрочных и долгосрочных финансовых вложений с указанием видов, сумм вложений, наименований организаций и предприятий;"),
        ("d", "расшифровки задолженности по долгосрочным и краткосрочным кредитам и займам (включая вексельные и облигационные) с указанием кредиторов, суммы задолженности, срока кредитования, процентной ставки (доходности купона), графика погашения и уплаты процентов, суммы просроченных процентов;"),
        ("e", "расшифровки полученных обеспечений (с указанием от кого и в пользу кого получено) и выданных обеспечений (с указанием за кого и в пользу кого выдано, сроков исполнения обязательств);"),
        ("f", "расшифровки прочих доходов и прочих расходов; и"),
        ("g", "справку из подразделения ФНС России о состоянии расчетов с бюджетом или акт сверки расчетов с бюджетом."),
    ]:
        elements.append(make_paragraph(runs=[make_run(f"({letter}) {text}")], spacing_after=40))
    
    # 5.2 Информация: прочее
    p_52 = make_paragraph(spacing_before=120, spacing_after=60)
    p_52.append(make_run("5.2. Информация: прочее. ", bold=True))
    p_52.append(make_run("По требованию Займодавца, Заемщик, в течение "))
    p_52.append(make_inline_sdt(
        title="Срок предоставления прочей информации (по умолч.)",
        tag="reporting/other_info_days",
        sdt_type="combo_box",
        dropdown_items=[("5 (пяти)", "5 (пяти)"), ("10 (десяти)", "10 (десяти)")],
        xml_mapping_xpath=xpath("reporting/other_info_days"),
        default_value="5 (пяти)"
    ))
    p_52.append(make_run(" рабочих дней с даты получения такого требования, обязан предоставлять Займодавцу следующую информацию в отношении Заемщика:"))
    elements.append(p_52)
    
    for letter, text in [
        ("a", "действующий устав;"),
        ("b", "внутренние документы;"),
        ("c", "информацию о принятых органами управления Заемщика решениях (в том числе копии соответствующих решений и протоколов);"),
        ("d", "любую иную информацию и документы, имеющиеся у Заемщика, а также любые документы и информацию, которые могут быть получены Заемщиком, действующим разумно и добросовестно."),
    ]:
        elements.append(make_paragraph(runs=[make_run(f"({letter}) {text}")], spacing_after=40))
    
    # 5.3 Информация: события
    elements.append(make_paragraph(
        runs=[make_run("5.3. Информация: события. ", bold=True), make_run("Заемщик обязуется предоставлять Займодавцу:")],
        spacing_before=120, spacing_after=60
    ))
    
    p_53a = make_paragraph(spacing_after=60)
    p_53a.append(make_run("(a) не позднее "))
    p_53a.append(make_inline_sdt(
        title="Срок уведомления о суд. разбирательствах (по умолч.)",
        tag="reporting/event_notification_days",
        sdt_type="combo_box",
        dropdown_items=[("5 (пяти)", "5 (пяти)"), ("10 (десяти)", "10 (десяти)")],
        xml_mapping_xpath=xpath("reporting/event_notification_days"),
        default_value="5 (пяти)"
    ))
    p_53a.append(make_run(" рабочих дней с даты, когда ему становится об этом известно, — подробные сведения о любых судебных, третейских или административных разбирательствах в отношении Заемщика, в результате которых принято или существует высокая степень вероятности принятия решений, на сумму иска, превышающую "))
    p_53a.append(make_inline_sdt(
        title="Предельная сумма для уведомления (п. 5.3.a)",
        tag="covenants/info_litigation_threshold",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("covenants/info_litigation_threshold"),
        placeholder="сумма",
        default_value="[●]"
    ))
    p_53a.append(make_run(" рублей, либо иных решениях, которые могут существенным образом повлиять на условия ведения деятельности Заемщиком;"))
    elements.append(p_53a)
    
    p_53b = make_paragraph(spacing_after=120)
    p_53b.append(make_run("(b) информацию о любых сделках и (или) событиях, указанных в статье 4, в отношении которых требуется согласие Займодавца — не позднее "))
    p_53b.append(make_inline_sdt(
        title="Срок уведомления до события (по умолч.)",
        tag="reporting/pre_event_days",
        sdt_type="combo_box",
        dropdown_items=[("10 (десяти)", "10 (десяти)"), ("5 (пяти)", "5 (пяти)")],
        xml_mapping_xpath=xpath("reporting/pre_event_days"),
        default_value="10 (десяти)"
    ))
    p_53b.append(make_run(" рабочих дней до наступления соответствующего события или заключения сделки, а также информацию и документы о факте заключения таких сделок и (или) наступления таких событий — не позднее "))
    p_53b.append(make_inline_sdt(
        title="Срок уведомления после события (по умолч.)",
        tag="reporting/post_event_days",
        sdt_type="combo_box",
        dropdown_items=[("2 (двух)", "2 (двух)"), ("5 (пяти)", "5 (пяти)")],
        xml_mapping_xpath=xpath("reporting/post_event_days"),
        default_value="2 (двух)"
    ))
    p_53b.append(make_run(" рабочих дней после такого заключения или наступления."))
    elements.append(p_53b)
    
    # ═══════════════════════════════════════════════════════════
    # СТАТЬЯ 6. СЛУЧАИ НЕИСПОЛНЕНИЯ
    # ═══════════════════════════════════════════════════════════
    
    elements.append(make_paragraph(
        runs=[make_run("6. СЛУЧАИ НЕИСПОЛНЕНИЯ", bold=True, size=24)],
        spacing_before=360, spacing_after=120, keep_next=True
    ))
    
    p_6intro = make_paragraph(spacing_after=120)
    p_6intro.append(make_run("Каждый из случаев, событий или обстоятельств, описанных в настоящей статье 6 является Случаем неисполнения. При наступлении любого Случая неисполнения и в любой момент времени после наступления любого Случая неисполнения Займодавец имеет право, направив уведомление Заемщику, потребовать досрочного возврата Займа или любой его части, а Заемщик обязан исполнить такое требование в течение "))
    p_6intro.append(make_inline_sdt(
        title="Срок досрочного возврата при Случае неисполнения (по умолч.)",
        tag="default_events/early_return_days",
        sdt_type="combo_box",
        dropdown_items=[("5 (пяти)", "5 (пяти)"), ("10 (десяти)", "10 (десяти)")],
        xml_mapping_xpath=xpath("default_events/early_return_days"),
        default_value="5 (пяти)"
    ))
    p_6intro.append(make_run(" рабочих дней."))
    elements.append(p_6intro)
    
    for num, text in [
        ("6.1", "Нецелевое использование Займа. Нарушение Заемщиком обязанностей, предусмотренных пунктом 2.2 Договора."),
        ("6.2", "Нарушение порядка и сроков уплаты платежей по Договору. Неисполнение или ненадлежащее исполнение Заемщиком своих обязательств по уплате каких-либо платежей по Договору в порядке и сроки, предусмотренные Договором."),
        ("6.3", "Финансовая задолженность. Возникновение Финансовой задолженности, в отношении которой Заемщик является займодавцем, или ее изменение без предварительного письменного согласия Займодавца."),
    ]:
        elements.append(make_paragraph(
            runs=[make_run(f"{num}. ", bold=True), make_run(text)],
            spacing_after=60
        ))
    
    # 6.4 Процедуры несостоятельности
    elements.append(make_paragraph(
        runs=[make_run("6.4. ", bold=True), make_run("Процедуры несостоятельности. Совершение одного из следующих действий в отношении Заемщика:")],
        spacing_after=60
    ))
    
    # 6.4(a) — optional liquidation mention
    elements.append(make_sdt_block(
        title="П. 6.4 — ликвидация",
        tag="optional:insolvency_liquidation",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("(a) начало процедуры ликвидации или банкротства или назначение ликвидационной комиссии или аналогичного органа, или должностного лица;")],
            spacing_after=40
        )]
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("(b) предъявление в суд заявления о признании Заемщика банкротом, если компетентный суд в течение 30 (тридцати) дней с даты вынесения определения о принятии заявления не выносит определения об отказе во введении наблюдения и оставлении заявления без рассмотрения, прекращении производства по делу о банкротстве, определения о возвращении такого заявления, решения об отказе в признании банкротом либо иного аналогичного судебного акта;")],
        spacing_after=40
    ))
    
    # 6.4(c) — optional procedures
    elements.append(make_sdt_block(
        title="П. 6.4(c) — введение процедур банкротства",
        tag="optional:insolvency_procedures",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("(c) введение наблюдения, финансового оздоровления, внешнего управления или конкурсного производства;")],
            spacing_after=40
        )]
    ))
    
    # 6.4(d) — optional managers
    elements.append(make_sdt_block(
        title="П. 6.4(d) — назначение управляющих",
        tag="optional:insolvency_managers",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("(d) назначение временного управляющего, внешнего управляющего, административного управляющего, конкурсного управляющего или любого иного лица, выполняющего аналогичные функции;")],
            spacing_after=40
        )]
    ))
    
    for letter, text in [
        ("e", "созыв или объявление о намерении созыва собрания кредиторов с целью рассмотрения мирового соглашения;"),
        ("f", "инициирование любой иной процедуры банкротства, установленной Законом о банкротстве;"),
        ("g", "осуществление любых иных аналогичных процедур, предусмотренных законодательством о несостоятельности (банкротстве)."),
    ]:
        elements.append(make_paragraph(runs=[make_run(f"({letter}) {text}")], spacing_after=40))
    
    # 6.5, 6.6
    elements.append(make_paragraph(
        runs=[make_run("6.5. ", bold=True), make_run("Судебные и административные разбирательства. Начало каких-либо судебных, административных, арбитражных или третейских разбирательств в отношении Договора.")],
        spacing_after=60
    ))
    
    p_66 = make_paragraph(spacing_after=120)
    p_66.append(make_run("6.6. ", bold=True))
    p_66.append(make_run("Прочее. Нарушение Заемщиком обязанностей, указанных в пунктах 4.1–4.6, 4.8–4.9 и 5 (Обязательства по предоставлению информации), или недостоверность любого из Заверений Заемщика, если только любое такое нарушение обязанностей не будет устранено в срок "))
    p_66.append(make_inline_sdt(
        title="Срок устранения нарушения (по умолч.)",
        tag="default_events/cure_period_days",
        sdt_type="combo_box",
        dropdown_items=[("30 (тридцать)", "30 (тридцать)"), ("15 (пятнадцать)", "15 (пятнадцать)")],
        xml_mapping_xpath=xpath("default_events/cure_period_days"),
        default_value="30 (тридцать)"
    ))
    p_66.append(make_run(" дней с момента, когда оно произошло."))
    elements.append(p_66)
    
    # ═══════════════════════════════════════════════════════════
    # СТАТЬЯ 7. МЕХАНИЗМ ПЛАТЕЖЕЙ
    # ═══════════════════════════════════════════════════════════
    
    elements.append(make_paragraph(
        runs=[make_run("7. МЕХАНИЗМ ПЛАТЕЖЕЙ", bold=True, size=24)],
        spacing_before=360, spacing_after=120, keep_next=True
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("7.1. ", bold=True), make_run("Платежи Займодавцу. Если иное прямо не предусмотрено Договором, датой исполнения какого-либо обязательства Заемщика по совершению платежа в пользу Займодавца считается дата зачисления соответствующих сумм в полном объеме на Счет Займодавца.")],
        spacing_after=60
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("7.2. ", bold=True), make_run("Частичные платежи. Если Займодавец получает сумму, недостаточную для погашения в полном объеме всех сумм, подлежащих уплате Заемщиком по Договору на соответствующий момент, Займодавец обязан использовать такую сумму в счет погашения обязательств Заемщика в следующем порядке очередности:")],
        spacing_after=60
    ))
    
    for letter, text in [
        ("a", "во-первых, для компенсации Займодавцу расходов, возникших в связи с принудительным исполнением его требования к Заемщику;"),
        ("b", "во-вторых, для выплаты суммы непогашенного Займа;"),
        ("c", "в-третьих, для выплаты начисленной неустойки (если применимо); и"),
        ("d", "в-четвертых, для выплаты любых других сумм, причитающихся с Заемщика по условиям Договора."),
    ]:
        elements.append(make_paragraph(runs=[make_run(f"({letter}) {text}")], spacing_after=40))
    
    elements.append(make_paragraph(
        runs=[make_run("7.3. ", bold=True), make_run("Прекращение обязательств зачетом. Обязательства Заемщика из Договора могут быть прекращены посредством зачета встречных однородных требований исключительно при условии получения предварительного письменного согласия Займодавца.")],
        spacing_before=60, spacing_after=60
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("7.4. ", bold=True), make_run("Налоги. Заемщик обязуется совершать любые платежи по Договору без уменьшения таких платежей на суммы удержанных (или подлежащих удержанию) с таких сумм Налогов.")],
        spacing_after=120
    ))
    
    # ═══════════════════════════════════════════════════════════
    # СТАТЬЯ 8. ЗАВЕРЕНИЯ ОБ ОБСТОЯТЕЛЬСТВАХ
    # ═══════════════════════════════════════════════════════════
    
    elements.append(make_paragraph(
        runs=[make_run("8. ЗАВЕРЕНИЯ ОБ ОБСТОЯТЕЛЬСТВАХ", bold=True, size=24)],
        spacing_before=360, spacing_after=120, keep_next=True
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("8.1. Заемщик настоящим заверяет Займодавца (в соответствии со статьей 431.2 Гражданского кодекса), что:")],
        spacing_after=60
    ))
    
    # 8.1(a) — alt: ЮЛ / ФЛ
    elements.append(make_sdt_block(
        title="Заверение 8.1(a): Заёмщик — юрлицо",
        tag="alt:borrower_status_rep:1",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("(a) Заемщик является юридическим лицом, учрежденным в установленном порядке и действующим в соответствии с российским законодательством;")],
            spacing_after=40
        )]
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("/")],
        alignment="center", spacing_before=20, spacing_after=20
    ))
    
    elements.append(make_sdt_block(
        title="Заверение 8.1(a): Заёмщик — физлицо",
        tag="alt:borrower_status_rep:2",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("(a) Заемщик обладает полной дееспособностью, в отношении Заемщика не вынесено приказа об установлении опеки либо попечительства;")],
            spacing_after=40
        )]
    ))
    
    # 8.1(b)-(e) — static and optional
    elements.append(make_paragraph(
        runs=[make_run("(b) Заемщик обладает всеми правами и полномочиями по заключению и исполнению Договора;")],
        spacing_after=40
    ))
    elements.append(make_paragraph(
        runs=[make_run("(c) Договор надлежащим образом подписан Заемщиком и представляет собой законное, действительное и обладающее обязательной силой обязательство Заемщика, подлежащее принудительному исполнению в соответствии с требованиями применимого законодательства;")],
        spacing_after=40
    ))
    
    elements.append(make_sdt_block(
        title="Заверение 8.1(d): одобрения по внутренним документам",
        tag="optional:internal_approvals_rep",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("(d) Заемщик получил все необходимые одобрения на заключение и исполнение Договора в порядке, предусмотренном российским законодательством и его учредительными и иными внутренними документами;")],
            spacing_after=40
        )]
    ))
    
    elements.append(make_sdt_block(
        title="Заверение 8.1(e): непротиворечие внутренним документам",
        tag="optional:no_conflict_internal_rep",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("(e) заключение и исполнение Договора Заемщиком не противоречит договорам, иным финансовым инструментам и сделкам с участием Заемщика или обязывающим Заемщика, его учредительным и внутренним документам, а также не влечет нарушения применимого законодательства, актов государственных органов или судебных актов;")],
            spacing_after=40
        )]
    ))
    
    # 8.1(f)-(l) — all optional
    for letter, tag_suffix, text in [
        ("f", "signing_authority_rep", "на Дату Договора лица, действующие от имени Заемщика, обладают полномочиями на подписание Договора;"),
        ("g", "compliance_rep", "ведение деятельности Заемщика осуществляется без существенного нарушения применимого законодательства;"),
        ("h", "tax_rep", "Заемщик своевременно и в соответствии с законодательством составляет и подает налоговую отчетность и уплачивает все причитающиеся Налоги. Налоговая отчетность Заемщика является полной и достоверной, точно отражает все налоговые обязательства Заемщика. К Заемщику не предъявлены какие-либо налоговые претензии в любой форме, и ему неизвестно об обстоятельствах, которые могли бы повлечь предъявление таких претензий;"),
    ]:
        elements.append(make_sdt_block(
            title=f"Заверение 8.1({letter})",
            tag=f"optional:{tag_suffix}",
            sdt_type="rich_text",
            content_elements=[make_paragraph(
                runs=[make_run(f"({letter}) {text}")],
                spacing_after=40
            )]
        ))
    
    # 8.1(i) — with fillable date fields
    rep_i_content = []
    p_rep_i = make_paragraph(spacing_after=40)
    p_rep_i.append(make_run("(i) последняя финансовая отчетность Заемщика, составленная по состоянию на "))
    p_rep_i.append(make_inline_sdt(
        title="Дата последней фин. отчётности",
        tag="representations/financial_report_date",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("representations/financial_report_date"),
        placeholder="дата",
        default_value="[●]"
    ))
    p_rep_i.append(make_run(" года, является полной и достоверной, точно отражает финансовое состояние Заемщика. Заемщик не имеет каких-либо обязательств, как реальных, так и условных, которые не отражены в финансовой отчетности. С "))
    p_rep_i.append(make_inline_sdt(
        title="Дата начала обычной деятельности",
        tag="representations/ordinary_business_since",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("representations/ordinary_business_since"),
        placeholder="дата",
        default_value="[●]"
    ))
    p_rep_i.append(make_run(" года Заемщик вел обычную хозяйственную деятельность и не совершал каких-либо нестандартных операций;"))
    rep_i_content.append(p_rep_i)
    
    elements.append(make_sdt_block(
        title="Заверение 8.1(i): фин. отчётность",
        tag="optional:financial_statements_rep",
        sdt_type="rich_text",
        content_elements=rep_i_content
    ))
    
    for letter, tag_suffix, text in [
        ("j", "accounting_rep", "бухгалтерский, финансовый и налоговый учет, обязательные книги учета, первичные документы, счета, книги счетов и другие записи Заемщика, а также документы, составляющие управленческую отчетность Заемщика, являются актуальными на Дату Договора, находятся во владении или под контролем Заемщика, велись во всех существенных отношениях в соответствии с применимым законодательством и представляют полные и точные записи всей информации, которая должна в них отображаться и учитываться;"),
        ("k", "document_keeping_rep", "все предписанные применимым законодательством и обязательные документы Заемщика велись и ведутся в надлежащем порядке, содержат актуальную информацию, а также правдивые, полные и точные данные по всем необходимым в этом отношении вопросам;"),
        ("l", "no_liquidation_rep", "в отношении Заемщика не осуществляется процедура ликвидации или реорганизации, а также не принималось никаких решений о ликвидации или реорганизации;"),
    ]:
        elements.append(make_sdt_block(
            title=f"Заверение 8.1({letter})",
            tag=f"optional:{tag_suffix}",
            sdt_type="rich_text",
            content_elements=[make_paragraph(
                runs=[make_run(f"({letter}) {text}")],
                spacing_after=40
            )]
        ))
    
    # 8.1(m)-(p) — static
    for letter, text in [
        ("m", "в отношении Заемщика не осуществляется какой-либо процедуры или какого-либо действия в рамках Закона о банкротстве;"),
        ("n", "активы Заемщика не являются предметом какого-либо Обременения;"),
        ("o", "вся фактическая информация, предоставляемая Заемщиком или его участниками Займодавцу, его сотрудникам и консультантам, в связи с подписанием и заключением Договора, является достоверной и точной на дату предоставления;"),
        ("p", "у Заемщика отсутствуют займы, гарантии, поручительства, залоги, а также скрытые обязательства на Дату Договора, за исключением раскрытых и известных Займодавцу."),
    ]:
        elements.append(make_paragraph(runs=[make_run(f"({letter}) {text}")], spacing_after=40))
    
    # 8.2–8.5
    for num, text in [
        ("8.2", "Каждое Заверение Заемщика предоставляется Заемщиком и является достоверным на Дату Договора."),
        ("8.3", "Заемщик признает, что Займодавец заключает Договор, полностью полагаясь на Заверения Заемщика, каждое из которых имеет существенное значение для Займодавца, в том числе для заключения им Договора."),
        ("8.4", "Заемщик несет ответственность за несоответствие действительности предоставленных им заверений независимо от того, было ли ему известно о недостоверности соответствующих заверений."),
        ("8.5", "Каждое Заверение Заемщика толкуется как отдельное, независимое и не ограниченное другими Заверениями Заемщика."),
    ]:
        elements.append(make_paragraph(
            runs=[make_run(f"{num}. ", bold=True), make_run(text)],
            spacing_after=60
        ))
    
    # ═══════════════════════════════════════════════════════════
    # СТАТЬИ 9–19 (компактные, преимущественно статический текст)
    # ═══════════════════════════════════════════════════════════
    
    static_articles = [
        ("9. СРОК ДЕЙСТВИЯ И РАСТОРЖЕНИЕ", [
            "Договор вступает в силу в Дату Договора и действует до полного выполнения Сторонами своих обязательств по нему."
        ]),
        ("10. ИЗМЕНЕНИЯ", [
            "Все изменения и дополнения к Договору оформляются в письменном виде Сторонами или их уполномоченными представителями."
        ]),
        ("11. ПЕРЕМЕНА ЛИЦ И ОБРЕМЕНЕНИЯ", [
            "11.1. Заемщик не вправе без предварительного письменного согласия Займодавца уступать свои права и (или) передавать свои обязанности по Договору третьим лицам.",
            "11.2. Займодавец вправе без согласия Заемщика уступать свои права и (или) передавать свои обязанности по Договору третьим лицам. Заемщик настоящим предоставляет свое согласие на такую уступку и (или) передачу обязанностей Займодавца по Договору.",
        ]),
        ("12. ЧАСТИЧНАЯ НЕДЕЙСТВИТЕЛЬНОСТЬ", [
            "12.1. В случае если одно или несколько положений Договора по какой-либо причине окажутся недействительными, незаконными или не имеющими юридической силы в каком-либо отношении, это не должно повлиять на действительность, законность и юридическую силу остальных положений, содержащихся в Договоре. Стороны подтверждают, что в соответствии со статьей 180 Гражданского кодекса недействительность одного или нескольких положений Договора не влечет недействительности всего Договора.",
            "12.2. Стороны обязуются приложить все необходимые усилия для замены незаконного, недействительного или не имеющего обязательной силы положения Договора соответствующим законным, действительным и имеющим обязательную силу положением, действие которого будет, по возможности, максимально приближено к желаемому действию соответствующего незаконного, недействительного или не имеющего обязательной силы положения.",
        ]),
        ("15. ПРИМЕНИМОЕ ПРАВО", [
            "Настоящий Договор, а также права и обязанности Сторон, возникающие на основании настоящего Договора, регулируются законодательством Российской Федерации и подлежат толкованию в соответствии с ним.",
        ]),
        ("17. РАСХОДЫ", [
            "Если иное прямо не предусмотрено Договором, каждая Сторона самостоятельно несет все расходы, связанные с заключением Договора и его исполнением соответствующей Стороной.",
        ]),
        ("18. ЭКЗЕМПЛЯРЫ", [
            "Договор составлен в 2 (двух) экземплярах, имеющих одинаковую юридическую силу, по 1 (одному) экземпляру для каждой Стороны.",
        ]),
        ("19. ИНЫЕ ПОЛОЖЕНИЯ", [
            "Договор содержит весь объем соглашений между Сторонами в отношении предмета Договора, отменяет и заменяет все другие обязательства или представления, которые могли быть приняты или сделаны Сторонами, как в устной, так и в письменной форме, до заключения Договора.",
        ]),
    ]
    
    for title_text, paragraphs in static_articles:
        elements.append(make_paragraph(
            runs=[make_run(title_text, bold=True, size=24)],
            spacing_before=360, spacing_after=120, keep_next=True
        ))
        for para in paragraphs:
            elements.append(make_paragraph(
                runs=[make_run(para)],
                spacing_after=60
            ))
    
    # ─── Статья 13. КОНФИДЕНЦИАЛЬНОСТЬ (abbreviated) ───
    # Inserted between 12 and 15 in the flow above; putting it here since it has no CC
    # We'll add it inline in order
    
    # ─── Статья 14. УВЕДОМЛЕНИЯ (with CC for addresses) ───
    elements.append(make_paragraph(
        runs=[make_run("14. УВЕДОМЛЕНИЯ", bold=True, size=24)],
        spacing_before=360, spacing_after=120, keep_next=True
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("14.1. ", bold=True), make_run("Все уведомления и другие сообщения, направляемые в соответствии с Договором или в связи с ним другой Стороне, должны быть оформлены в письменном виде и будут считаться надлежащим образом направленными, если они направлены лично или международно-признанной курьерской службой (UPS, DHL, FedEx или аналогичной) по адресам, указанным в пункте 14.2.")],
        spacing_after=60
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("14.2. Адреса", bold=True)],
        spacing_before=60, spacing_after=60, keep_next=True
    ))
    
    # Lender notice
    elements.append(make_paragraph(
        runs=[make_run("Контактные данные Займодавца:", bold=True)],
        spacing_after=40
    ))
    p_ln_addr = make_paragraph(spacing_after=40)
    p_ln_addr.append(make_run("Адрес: "))
    p_ln_addr.append(make_inline_sdt(
        title="Адрес Займодавца для уведомлений",
        tag="lender/notice/address",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/notice/address"),
        placeholder="адрес",
        default_value="[●]"
    ))
    elements.append(p_ln_addr)
    
    p_ln_att = make_paragraph(spacing_after=60)
    p_ln_att.append(make_run("Вниманию: "))
    p_ln_att.append(make_inline_sdt(
        title="Получатель уведомлений Займодавца",
        tag="lender/notice/attention",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/notice/attention"),
        placeholder="ФИО / должность",
        default_value="[●]"
    ))
    elements.append(p_ln_att)
    
    # Borrower notice
    elements.append(make_paragraph(
        runs=[make_run("Контактные данные Заемщика:", bold=True)],
        spacing_after=40
    ))
    p_bn_addr = make_paragraph(spacing_after=40)
    p_bn_addr.append(make_run("Адрес: "))
    p_bn_addr.append(make_inline_sdt(
        title="Адрес Заёмщика для уведомлений",
        tag="borrower/notice/address",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/notice/address"),
        placeholder="адрес",
        default_value="[●]"
    ))
    elements.append(p_bn_addr)
    
    p_bn_att = make_paragraph(spacing_after=120)
    p_bn_att.append(make_run("Вниманию: "))
    p_bn_att.append(make_inline_sdt(
        title="Получатель уведомлений Заёмщика",
        tag="borrower/notice/attention",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/notice/attention"),
        placeholder="ФИО / должность",
        default_value="[●]"
    ))
    elements.append(p_bn_att)
    
    # ─── Статья 16. ПОРЯДОК РАЗРЕШЕНИЯ СПОРОВ (alt: РАЦ / гос.суд) ───
    elements.append(make_paragraph(
        runs=[make_run("16. ПОРЯДОК РАЗРЕШЕНИЯ СПОРОВ", bold=True, size=24)],
        spacing_before=360, spacing_after=120, keep_next=True
    ))
    
    # Alt 1: РАЦ
    rac_content = []
    rac_content.append(make_paragraph(
        runs=[make_run("16.1. Любой спор, разногласие или претензия, вытекающие из настоящего Договора или в связи с ними, в том числе касающиеся его исполнения, нарушения, прекращения или недействительности, которые не могут быть урегулированы Сторонами путем переговоров, разрешаются путем арбитража, администрируемого Российским арбитражным центром при автономной некоммерческой организации \"Российский институт современного арбитража\" (\""),
              make_run("РАЦ", bold=True),
              make_run("\") в соответствии с положениями Арбитражного регламента, действующим на дату подачи искового заявления. Место арбитража — город Москва, Российская Федерация. Язык арбитража — русский.")],
        spacing_after=60
    ))
    rac_content.append(make_paragraph(
        runs=[make_run("16.2. Состав арбитража — 3 арбитра, по одному назначает каждая сторона, председателя — РАЦ.")],
        spacing_after=60
    ))
    
    p_rac_email = make_paragraph(spacing_after=40)
    p_rac_email.append(make_run("16.3. Стороны соглашаются, что для целей направления письменных заявлений, сообщений и иных письменных документов будут использоваться следующие адреса электронной почты:"))
    rac_content.append(p_rac_email)
    
    p_rac_lender_email = make_paragraph(spacing_after=40)
    p_rac_lender_email.append(make_run("Займодавец: "))
    p_rac_lender_email.append(make_inline_sdt(
        title="Email Займодавца для арбитража",
        tag="lender/dispute_email",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/dispute_email"),
        placeholder="email@example.com",
        default_value="[●]"
    ))
    rac_content.append(p_rac_lender_email)
    
    p_rac_borrower_email = make_paragraph(spacing_after=60)
    p_rac_borrower_email.append(make_run("Заемщик: "))
    p_rac_borrower_email.append(make_inline_sdt(
        title="Email Заёмщика для арбитража",
        tag="borrower/dispute_email",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/dispute_email"),
        placeholder="email@example.com",
        default_value="[●]"
    ))
    rac_content.append(p_rac_borrower_email)
    
    for num, text in [
        ("16.4", "В случае изменения указанного выше адреса электронной почты Сторона обязуется незамедлительно сообщить о таком изменении другой Стороне, а в случае, если арбитраж уже начат, также РАЦ."),
        ("16.5", "Стороны принимают на себя обязанность добровольно исполнять арбитражное решение."),
        ("16.6", "Третьи лица вправе в любое время выразить согласие с обязательностью для них настоящего арбитражного соглашения в любом документе, направленном Сторонам настоящего Договора."),
        ("16.7", "Арбитражное решение является для Сторон окончательным."),
    ]:
        rac_content.append(make_paragraph(
            runs=[make_run(f"{num}. {text}")],
            spacing_after=40
        ))
    
    elements.append(make_sdt_block(
        title="Арбитраж: РАЦ",
        tag="alt:dispute_resolution:1",
        sdt_type="rich_text",
        content_elements=rac_content
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("/")],
        alignment="center", spacing_before=60, spacing_after=60
    ))
    
    # Alt 2: государственный суд
    elements.append(make_sdt_block(
        title="Арбитраж: государственный суд",
        tag="alt:dispute_resolution:2",
        sdt_type="rich_text",
        content_elements=[make_paragraph(
            runs=[make_run("16.1. Любой спор, разногласие или претензия, вытекающие из настоящего Договора или в связи с ними, в том числе касающиеся его исполнения, нарушения, прекращения или недействительности, которые не могут быть урегулированы Сторонами путем переговоров, подлежат разрешению в Арбитражном суде города Москвы.")],
            spacing_after=60
        )]
    ))
    
    # Досудебный порядок (always present)
    elements.append(make_paragraph(
        runs=[make_run("Для целей соблюдения досудебного порядка урегулирования спора, обязательного в соответствии с положениями Арбитражного процессуального кодекса Российской Федерации, Стороны определили, что срок для рассмотрения претензии одной Стороны другой Стороной и для принятия такой другой Стороной мер по досудебному урегулированию такой претензии (в совокупности) составляет 30 (тридцать) рабочих дней от даты направления соответствующей претензии.")],
        spacing_after=120
    ))
    
    # ═══════════════════════════════════════════════════════════
    # БЛОК ПОДПИСЕЙ (footer)
    # ═══════════════════════════════════════════════════════════
    
    elements.append(make_paragraph(
        runs=[make_run("ПОДПИСИ СТОРОН", bold=True, size=24)],
        alignment="center", spacing_before=480, spacing_after=240
    ))
    
    # Simple two-column layout for signatures
    p_sign_lender = make_paragraph(spacing_after=240)
    p_sign_lender.append(make_run("ЗАЙМОДАВЕЦ: ", bold=True))
    p_sign_lender.append(make_inline_sdt(
        title="Должность подписанта Займодавца",
        tag="lender/signatory_title",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/signatory_title"),
        placeholder="должность / основание полномочий",
        default_value="[●]"
    ))
    elements.append(p_sign_lender)
    
    p_sign_lender_name = make_paragraph(spacing_after=360)
    p_sign_lender_name.append(make_run("___________________________ "))
    p_sign_lender_name.append(make_inline_sdt(
        title="ФИО подписанта Займодавца",
        tag="lender/signatory_name",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("lender/signatory_name"),
        placeholder="Фамилия И.О.",
        default_value="[●]"
    ))
    elements.append(p_sign_lender_name)
    
    p_sign_borrower = make_paragraph(spacing_after=240)
    p_sign_borrower.append(make_run("ЗАЕМЩИК: ", bold=True))
    p_sign_borrower.append(make_inline_sdt(
        title="Должность подписанта Заёмщика",
        tag="borrower/signatory_title",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/signatory_title"),
        placeholder="должность / основание полномочий",
        default_value="[●]"
    ))
    elements.append(p_sign_borrower)
    
    p_sign_borrower_name = make_paragraph(spacing_after=120)
    p_sign_borrower_name.append(make_run("___________________________ "))
    p_sign_borrower_name.append(make_inline_sdt(
        title="ФИО подписанта Заёмщика",
        tag="borrower/signatory_name",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("borrower/signatory_name"),
        placeholder="Фамилия И.О.",
        default_value="[●]"
    ))
    elements.append(p_sign_borrower_name)
    
    return elements


def build_purpose_section():
    """Build content for the optional purpose (целевое назначение) block."""
    elements = []
    
    elements.append(make_paragraph(
        runs=[make_run("2.2. Целевое назначение", bold=True)],
        spacing_before=120, spacing_after=120, keep_next=True
    ))
    
    elements.append(make_paragraph(
        runs=[make_run("2.2.1. Настоящий Договор является договором займа с условием использования Заемщиком полученных средств на определенные цели (целевой заем).")],
        spacing_after=60
    ))
    
    p_purpose = make_paragraph(spacing_after=60)
    p_purpose.append(make_run("2.2.2. Заемщик обязуется использовать полученный Заем в полном объеме исключительно в следующих целях: "))
    p_purpose.append(make_inline_sdt(
        title="Цели использования Займа",
        tag="purpose/description",
        placeholder="описание целей",
        sdt_type="plain_text",
        xml_mapping_xpath=xpath("purpose/description"),
        default_value="[●]"
    ))
    p_purpose.append(make_run("."))
    elements.append(p_purpose)
    
    p_report = make_paragraph(spacing_after=60)
    p_report.append(make_run("2.2.3. По требованию Займодавца Заемщик обязуется в течение "))
    p_report.append(make_inline_sdt(
        title="Срок предоставления отчёта (по умолч. «10 (десяти)»)",
        tag="purpose/report_days",
        sdt_type="combo_box",
        dropdown_items=[("10 (десяти)", "10 (десяти)"), ("5 (пяти)", "5 (пяти)"), ("15 (пятнадцати)", "15 (пятнадцати)")],
        xml_mapping_xpath=xpath("purpose/report_days"),
        default_value="10 (десяти)"
    ))
    p_report.append(make_run(" дней с даты использования суммы Займа (полностью или в части) предоставлять письменный отчет Займодавцу с указанием целей такого использования и приложением подтверждающих целевое использование документов."))
    elements.append(p_report)
    
    p_return = make_paragraph(spacing_after=120)
    p_return.append(make_run("2.2.4. В случае нарушения Заемщиком обязанности, предусмотренной пунктом 2.2.3, Займодавец имеет право потребовать досрочного возврата суммы Займа, а Заемщик обязан исполнить такое требование в течение "))
    p_return.append(make_inline_sdt(
        title="Срок досрочного возврата (по умолч. «5 (пяти)»)",
        tag="purpose/early_return_days",
        sdt_type="combo_box",
        dropdown_items=[("5 (пяти)", "5 (пяти)"), ("10 (десяти)", "10 (десяти)")],
        xml_mapping_xpath=xpath("purpose/early_return_days"),
        default_value="5 (пяти)"
    ))
    p_return.append(make_run(" рабочих дней с даты получения соответствующего требования."))
    elements.append(p_return)
    
    return elements


# ─── Inject Custom XML and SDTs into .docx ────────────────────────────────

def inject_into_docx(docx_path, output_path, body_elements):
    """
    Take a base .docx, replace body content with our elements,
    and inject Custom XML Part.
    """
    # Work with a temp copy
    temp_dir = "/home/claude/docx_work"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    # Extract base docx
    extract_dir = os.path.join(temp_dir, "extracted")
    with zipfile.ZipFile(docx_path, 'r') as z:
        z.extractall(extract_dir)
    
    # ── 1. Replace document.xml body ──
    doc_xml_path = os.path.join(extract_dir, "word", "document.xml")
    tree = etree.parse(doc_xml_path)
    root = tree.getroot()
    
    # Find w:body
    body = root.find(qn("w:body"))
    
    # Preserve sectPr (page settings)
    sect_pr = body.find(qn("w:sectPr"))
    sect_pr_copy = copy.deepcopy(sect_pr) if sect_pr is not None else None
    
    # Clear body
    for child in list(body):
        body.remove(child)
    
    # Add our elements
    for el in body_elements:
        body.append(el)
    
    # Re-add sectPr
    if sect_pr_copy is not None:
        body.append(sect_pr_copy)
    
    # Write back
    tree.write(doc_xml_path, xml_declaration=True, encoding="UTF-8", standalone=True)
    
    # Post-process document.xml to add w15 namespace for Repeating Section
    with open(doc_xml_path, 'r', encoding='utf-8') as f:
        doc_content = f.read()
    
    # Add w15 namespace to root element
    if 'xmlns:w15=' not in doc_content:
        # Find the first > in w:document tag and insert before it
        import re
        doc_content = re.sub(
            r'(<w:document\s+[^>]*)(>)',
            r'\1 xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"\2',
            doc_content,
            count=1
        )
        # Also update mc:Ignorable to include w15
        if 'mc:Ignorable=' in doc_content:
            doc_content = re.sub(
                r'mc:Ignorable="([^"]*)"',
                r'mc:Ignorable="\1 w15"',
                doc_content,
                count=1
            )
        
        with open(doc_xml_path, 'w', encoding='utf-8') as f:
            f.write(doc_content)
    
    # ── 1b. Fix settings.xml — add missing zoom percent ──
    settings_path = os.path.join(extract_dir, "word", "settings.xml")
    if os.path.exists(settings_path):
        settings_tree = etree.parse(settings_path)
        settings_root = settings_tree.getroot()
        zoom_el = settings_root.find(qn("w:zoom"))
        if zoom_el is not None and qn("w:percent") not in zoom_el.attrib:
            zoom_el.set(qn("w:percent"), "100")
        settings_tree.write(settings_path, xml_declaration=True, encoding="UTF-8", standalone=True)
    
    # ── 2. Add Custom XML Part ──
    custom_xml_dir = os.path.join(extract_dir, "customXml")
    os.makedirs(custom_xml_dir, exist_ok=True)
    
    custom_xml_rels_dir = os.path.join(custom_xml_dir, "_rels")
    os.makedirs(custom_xml_rels_dir, exist_ok=True)
    
    # item1.xml — our data
    with open(os.path.join(custom_xml_dir, "item1.xml"), "w", encoding="utf-8") as f:
        f.write(CUSTOM_XML_DATA)
    
    # itemProps1.xml — properties
    with open(os.path.join(custom_xml_dir, "itemProps1.xml"), "w", encoding="utf-8") as f:
        f.write(CUSTOM_XML_PROPS)
    
    # _rels/item1.xml.rels
    rels_content = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXmlProps" Target="itemProps1.xml"/>
</Relationships>"""
    with open(os.path.join(custom_xml_rels_dir, "item1.xml.rels"), "w", encoding="utf-8") as f:
        f.write(rels_content)
    
    # ── 3. Update [Content_Types].xml ──
    ct_path = os.path.join(extract_dir, "[Content_Types].xml")
    ct_tree = etree.parse(ct_path)
    ct_root = ct_tree.getroot()
    ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    
    # item1.xml (Custom XML Data) inherits "application/xml" from Default Extension="xml"
    # Do NOT add Override for it — wrong ContentType breaks XML Mapping!
    
    # Only add Override for itemProps1.xml (Custom XML Properties) — needs special ContentType
    # Check if it already exists (avoid duplicates)
    existing_parts = {el.get("PartName") for el in ct_root}
    if "/customXml/itemProps1.xml" not in existing_parts:
        override_props = etree.SubElement(ct_root, f"{{{ct_ns}}}Override")
        override_props.set("PartName", "/customXml/itemProps1.xml")
        override_props.set("ContentType", "application/vnd.openxmlformats-officedocument.customXmlProperties+xml")
    
    ct_tree.write(ct_path, xml_declaration=True, encoding="UTF-8", standalone=True)
    
    # ── 4. Update .rels to reference Custom XML ──
    main_rels_path = os.path.join(extract_dir, "word", "_rels", "document.xml.rels")
    rels_tree = etree.parse(main_rels_path)
    rels_root = rels_tree.getroot()
    rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    
    # Check if customXml relationship already exists
    custom_xml_rel_exists = False
    for rel in rels_root:
        target = rel.get("Target", "")
        rel_type = rel.get("Type", "")
        if "customXml" in rel_type and "item1.xml" in target:
            custom_xml_rel_exists = True
            break
    
    # Only add if not exists
    if not custom_xml_rel_exists:
        # Find next rId
        existing_ids = [el.get("Id") for el in rels_root]
        max_id = max(int(rid.replace("rId", "")) for rid in existing_ids if rid and rid.startswith("rId"))
        new_rid = f"rId{max_id + 1}"
        
        new_rel = etree.SubElement(rels_root, f"{{{rels_ns}}}Relationship")
        new_rel.set("Id", new_rid)
        new_rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml")
        new_rel.set("Target", "../customXml/item1.xml")
    
    rels_tree.write(main_rels_path, xml_declaration=True, encoding="UTF-8", standalone=True)
    
    # ── 5. Repack into .docx ──
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for root_dir, dirs, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root_dir, file)
                arcname = os.path.relpath(file_path, extract_dir)
                zout.write(file_path, arcname)
    
    # Cleanup
    shutil.rmtree(temp_dir)
    
    print(f"Template written to: {output_path}")


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    # Step 1: Create base document with python-docx (for proper page setup)
    base_path = "/home/claude/base_template.docx"
    doc = Document()
    
    # Page setup (A4)
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(1.5)
    
    # Default font
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(12)
    
    # Add a dummy paragraph (will be replaced)
    doc.add_paragraph("PLACEHOLDER")
    
    doc.save(base_path)
    
    # Step 2: Build body elements
    body_elements = build_document_body()
    
    # Step 3: Inject into docx
    inject_into_docx(base_path, OUTPUT_PATH, body_elements)
    
    # Cleanup base
    os.remove(base_path)
    
    print(f"\nDone! Template with {len(body_elements)} body elements.")
    print(f"Contains: Custom XML Part, SDTs with XML Mapping")
    print(f"Covers: Cover page, Preamble, Art. 2 (Loan, Purpose, Interest), Signatures")


if __name__ == "__main__":
    main()
