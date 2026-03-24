# XML Schema and Content Control Mapping v2

**Document:** Dogovor_Template.docx (Договор Займа)  
**Updated:** 2026-03-18  
**Total CC:** 121  
**Unique Tags:** 109

## Custom XML Part

**Namespace:** `urn:draftbuilder:loan_agreement:v1`  
**GUID:** `{12345678-1234-1234-1234-123456789ABC}`  
**Prefix:** `la`

## CC Summary

| Category | CC Count | Unique Tags |
|----------|----------|-------------|
| Data     | 79 | 75 |
| Alt      | 13 | 13 |
| Optional | 29 | 21 |

## Data CC by Section

### agreement

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `agreement/date` | DT | Дата заключения договора | ✓ | 2 |
| `agreement/city` | PT | Город заключения договора | ✓ | 2 |

### borrower

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `borrower/name` | PT | Наименование Заёмщика | ✓ | 2 |
| `borrower/representative` | PT | Представитель Заёмщика | ✓ | 1 |
| `borrower/authority_basis` | PT | Основание полномочий Заёмщика | ✓ | 1 |
| `borrower/account/currency` | PT | Валюта счёта Заёмщика | ✓ | 1 |
| `borrower/account/number` | PT | Номер счёта Заёмщика | ✓ | 1 |
| `borrower/account/bank_name` | PT | Банк Заёмщика | ✓ | 1 |
| `borrower/account/bik` | PT | БИК банка Заёмщика | ✓ | 1 |
| `borrower/account/corr_account` | PT | Корр. счёт банка Заёмщика | ✓ | 1 |
| `borrower/notice/address` | PT | Адрес Заёмщика для уведомлений | ✓ | 1 |
| `borrower/notice/attention` | PT | Получатель уведомлений Заёмщика | ✓ | 1 |
| `borrower/dispute_email` | PT | Email Заёмщика для арбитража | ✓ | 1 |
| `borrower/signatory_title` | PT | Должность подписанта Заёмщика | ✓ | 1 |
| `borrower/signatory_name` | PT | ФИО подписанта Заёмщика | ✓ | 1 |

### lender

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `lender/name` | PT | Наименование Займодавца | ✓ | 2 |
| `lender/representative` | PT | Представитель Займодавца | ✓ | 1 |
| `lender/authority_basis` | PT | Основание полномочий Займодавца | ✓ | 1 |
| `lender/account/currency` | PT | Валюта счёта Займодавца | ✓ | 1 |
| `lender/account/number` | PT | Номер счёта Займодавца | ✓ | 1 |
| `lender/account/bank_name` | PT | Банк Займодавца | ✓ | 1 |
| `lender/account/bik` | PT | БИК банка Займодавца | ✓ | 1 |
| `lender/account/corr_account` | PT | Корр. счёт банка Займодавца | ✓ | 1 |
| `lender/notice/address` | PT | Адрес Займодавца для уведомлений | ✓ | 1 |
| `lender/notice/attention` | PT | Получатель уведомлений Займодавца | ✓ | 1 |
| `lender/dispute_email` | PT | Email Займодавца для арбитража | ✓ | 1 |
| `lender/signatory_title` | PT | Должность подписанта Займодавца | ✓ | 1 |
| `lender/signatory_name` | PT | ФИО подписанта Займодавца | ✓ | 1 |

### loan

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `loan/maturity_date` | PT | Дата Погашения | ✓ | 1 |
| `loan/amount` | PT | Сумма Займа | ✓ | 1 |
| `loan/penalty_rate` | PT | Размер неустойки, % | ✓ | 1 |
| `loan/penalty_payment_days` | CB | Срок уплаты неустойки | ✓ | 1 |

### interest

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `interest/payment_frequency` | CB | Периодичность уплаты процентов | ✓ | 1 |
| `interest/dividend/security_type` | DD | Тип ценных бумаг | ✓ | 1 |
| `interest/dividend/issuer_name` | PT | Наименование эмитента | ✓ | 1 |
| `interest/dividend/security_count` | PT | Количество ценных бумаг | ✓ | 1 |
| `interest/dividend/capital_percentage` | PT | % от уставного капитала | ✓ | 1 |
| `interest/dividend/issuer_name_genitive` | PT | Наименование эмитента (род. падеж) | ✓ | 1 |
| `interest/dividend/payment_days` | CB | Срок выплаты дивидендных процентов | ✓ | 1 |

### interest_payment

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `interest_payment/day_of_month` | CB | День месяца для уплаты процентов | ✓ | 1 |

### purpose

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `purpose/description` | PT | Цели использования Займа | ✓ | 1 |
| `purpose/report_days` | CB | Срок предоставления отчёта | ✓ | 1 |
| `purpose/early_return_days` | CB | Срок досрочного возврата | ✓ | 1 |

### provision

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `provision/single_deadline` | PT | Срок предоставления Займа | ✓ | 1 |
| `provision/tranches` | RT | Транши (контейнер) | ✓ | 1 |
| `provision/tranches_item_N` | RT | RepeatingSectionItem | - | 4 |
| `provision/tranches/tranche[N]/ordinal` | PT | Номер транша | ✓ | 4 |
| `provision/tranches/tranche[N]/amount` | PT | Сумма транша | ✓ | 4 |
| `provision/tranches/tranche[N]/deadline` | PT | Срок транша | ✓ | 4 |

### covenants

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `covenants/transaction_threshold` | PT | Предельная сумма сделок (п. 4.1) | ✓ | 1 |
| `covenants/disposal_threshold` | PT | Предельная сумма отчуждения (п. 4.2) | ✓ | 1 |
| `covenants/litigation_threshold` | PT | Предельная сумма суд. разбирательств | ✓ | 1 |
| `covenants/info_litigation_threshold` | PT | Предельная сумма для уведомления | ✓ | 1 |

### reporting

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `reporting/financial_days` | CB | Срок предоставления фин. отчётности | ✓ | 1 |
| `reporting/other_info_days` | CB | Срок предоставления прочей информации | ✓ | 1 |
| `reporting/event_notification_days` | CB | Срок уведомления о суд. разбирательствах | ✓ | 1 |
| `reporting/pre_event_days` | CB | Срок уведомления до события | ✓ | 1 |
| `reporting/post_event_days` | CB | Срок уведомления после события | ✓ | 1 |

### default_events

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `default_events/early_return_days` | CB | Срок досрочного возврата при Случае неисполнения | ✓ | 1 |
| `default_events/cure_period_days` | CB | Срок устранения нарушения | ✓ | 1 |

### representations

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `representations/financial_report_date` | PT | Дата последней фин. отчётности | ✓ | 1 |
| `representations/ordinary_business_since` | PT | Дата начала обычной деятельности | ✓ | 1 |

### other (no XML binding)

| Tag | Type | Title | Binding | Count |
|-----|------|-------|---------|-------|
| `provision__gender_suffix` | DD | Окончание «-ым» / «-ой» | - | 1 |

---

## Alt Blocks (Alternatives)

Альтернативные блоки — выбирается один из вариантов.

| Tag | Title |
|-----|-------|
| `alt:interest_payment_date:1` | Дата Уплаты Процентов: ежемесячно |
| `alt:interest_payment_date:2` | Дата Уплаты Процентов: на дату погашения |
| `alt:interest_type:1` | Проценты: беспроцентный заём |
| `alt:interest_type:2` | Проценты: ключевая ставка ЦБ |
| `alt:interest_type:3` | Проценты: привязка к дивидендам |
| `alt:loan_provision:1` | Предоставление: единовременно |
| `alt:loan_provision:2` | Предоставление: траншами |
| `alt:loan_provision__p312_subject` | «Сумма Займа» / «Каждый из траншей...» |
| `alt:loan_provision__refusal_object` | «Займа» / «любого Транша» |
| `alt:borrower_status_rep:1` | Заверение 8.1(a): Заёмщик — юрлицо |
| `alt:borrower_status_rep:2` | Заверение 8.1(a): Заёмщик — физлицо |
| `alt:dispute_resolution:1` | Арбитраж: РАЦ |
| `alt:dispute_resolution:2` | Арбитраж: государственный суд |

---

## Optional Blocks

Необязательные блоки — могут быть удалены из документа.

| Tag | Title | Count |
|-----|-------|-------|
| `optional:interest_definition` | Определение «Проценты» | 1 |
| `optional:rac_definition` | Определение «РАЦ» | 1 |
| `optional:tranche_definition` | Определение «Транш» | 1 |
| `optional:has_appendices` | Вставки для приложений | 5 |
| `optional:interest_bearing_clause` | «Проценты и» (п. 2.1) | 5 |
| `optional:purpose` | Пункт 2.2 «Целевое назначение» | 1 |
| `optional:financial_reporting_covenant` | П. 4.7 «Подготовка фин. отчётности» | 1 |
| `optional:profit_distribution_restriction` | П. 4.9 «Ограничения на распределение прибыли» | 1 |
| `optional:access_covenant` | П. 4.10 «Доступ» | 1 |
| `optional:insolvency_liquidation` | П. 6.4 — ликвидация | 1 |
| `optional:insolvency_procedures` | П. 6.4(c) — введение процедур банкротства | 1 |
| `optional:insolvency_managers` | П. 6.4(d) — назначение управляющих | 1 |
| `optional:internal_approvals_rep` | Заверение 8.1(d) | 1 |
| `optional:no_conflict_internal_rep` | Заверение 8.1(e) | 1 |
| `optional:signing_authority_rep` | Заверение 8.1(f) | 1 |
| `optional:compliance_rep` | Заверение 8.1(g) | 1 |
| `optional:tax_rep` | Заверение 8.1(h) | 1 |
| `optional:financial_statements_rep` | Заверение 8.1(i) | 1 |
| `optional:accounting_rep` | Заверение 8.1(j) | 1 |
| `optional:document_keeping_rep` | Заверение 8.1(k) | 1 |
| `optional:no_liquidation_rep` | Заверение 8.1(l) | 1 |

---

## XML Part Structure

```xml
<la:loan_agreement xmlns:la="urn:draftbuilder:loan_agreement:v1">
  <la:agreement>
    <la:date/>
    <la:city>Москва</la:city>
    <la:has_appendices/>
  </la:agreement>
  <la:lender>
    <la:name/>
    <la:representative/>
    <la:authority_basis/>
    <la:signatory_title/>
    <la:signatory_name/>
    <la:account>
      <la:currency>рублях</la:currency>
      <la:number/>
      <la:bank_name/>
      <la:bik/>
      <la:corr_account/>
    </la:account>
    <la:notice>
      <la:address/>
      <la:attention/>
    </la:notice>
    <la:dispute_email/>
  </la:lender>
  <la:borrower>
    <la:name/>
    <la:representative/>
    <la:authority_basis/>
    <la:signatory_title/>
    <la:signatory_name/>
    <la:entity_type/>
    <la:account>
      <la:currency>рублях</la:currency>
      <la:number/>
      <la:bank_name/>
      <la:bik/>
      <la:corr_account/>
    </la:account>
    <la:notice>
      <la:address/>
      <la:attention/>
    </la:notice>
    <la:dispute_email/>
  </la:borrower>
  <la:loan>
    <la:amount/>
    <la:maturity_date/>
    <la:interest_bearing_clause/>
    <la:penalty_rate/>
    <la:penalty_payment_days>5 (пяти)</la:penalty_payment_days>
  </la:loan>
  <la:purpose>
    <la:description/>
    <la:report_days>10 (десяти)</la:report_days>
    <la:early_return_days>5 (пяти)</la:early_return_days>
  </la:purpose>
  <la:interest>
    <la:payment_frequency>ежемесячно</la:payment_frequency>
    <la:dividend>
      <la:security_type/>
      <la:issuer_name/>
      <la:security_count/>
      <la:capital_percentage/>
      <la:issuer_name_genitive/>
      <la:payment_days>10 (десяти)</la:payment_days>
    </la:dividend>
  </la:interest>
  <la:interest_payment>
    <la:day_of_month>5 (пятый)</la:day_of_month>
  </la:interest_payment>
  <la:provision>
    <la:single_deadline/>
    <la:tranches>
      <la:tranche>
        <la:ordinal>первый</la:ordinal>
        <la:amount/>
        <la:deadline/>
      </la:tranche>
      <!-- tranche 2, 3, 4 -->
    </la:tranches>
  </la:provision>
  <la:covenants>
    <la:transaction_threshold/>
    <la:disposal_threshold/>
    <la:litigation_threshold/>
    <la:info_litigation_threshold/>
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
    <la:financial_report_date/>
    <la:ordinary_business_since/>
  </la:representations>
</la:loan_agreement>
```

---

## Type Legend

| Abbr | Type | Description |
|------|------|-------------|
| PT | Plain Text | Простой текст |
| RT | Rich Text | Форматированный текст (может содержать вложенные CC) |
| DT | Date | Дата (с date picker) |
| CB | Combo Box | Выпадающий список с возможностью ввода |
| DD | Dropdown | Строгий выпадающий список |
