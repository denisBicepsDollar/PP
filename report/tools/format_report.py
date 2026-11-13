#!/usr/bin/env python3
"""Приводит отчёт по практике ПП.02.01 к оформлению эталонов.

Использование:
    python format_report.py ИСХОДНЫЙ.docx РЕЗУЛЬТАТ.docx [--pages pages.json]

Что делает скрипт:
  * лист А4, поля основной части 25/10/15/30 мм, номер страницы внизу по центру;
  * Times New Roman 14 пт, интервал 1,5, абзацный отступ 1,25 см, выравнивание
    по ширине, без интервалов между абзацами;
  * заголовки разделов/подразделов — стили «Заголовок 1–3», каждый раздел
    с новой страницы;
  * титульный лист, содержание с точками-заполнителями, приложения
    («Приложение А» справа, «Продолжение приложения А»), листинги;
  * аттестационный лист и дневник практики (бланки) в конце документа.

Текст отчёта не меняется — только оформление и состав служебных листов.
"""
import copy
import json
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Mm, Pt, RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph

FONT = "Times New Roman"
MONO = "Courier New"
L, C, R, J = (WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER,
              WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.JUSTIFY)
TEXT_W = Mm(175)          # 210 − 25 − 10
FORM_W = Mm(176)          # 210 − 20 − 14

DATE_START, DATE_END = "«03» 11.2026 г.", "«16» 11.2026 г."
DEF_START, DEF_END = "«13» 03.2027", "«21» 03.2027"


# ───────────────────────── низкоуровневые помощники ─────────────────────────

def set_run_font(run, size=14, bold=None, italic=None, name=FONT, underline=None):
    rpr = run._r.get_or_add_rPr()
    for tag in ("w:rFonts", "w:sz", "w:szCs", "w:color", "w:lang"):
        for el in rpr.findall(qn(tag)):
            rpr.remove(el)
    run.font.name = name
    rf = rpr.find(qn("w:rFonts"))
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(a), name)
    run.font.size = Pt(size)
    szcs = OxmlElement("w:szCs")
    szcs.set(qn("w:val"), str(int(size * 2)))
    rpr.find(qn("w:sz")).addnext(szcs)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if underline is not None:
        run.font.underline = underline


def fmt(p, align=J, first=0.0, left=0.0, spacing=1.5, before=0, after=0,
        keep_next=False, page_break=False, hanging=None):
    ppr = p._p.get_or_add_pPr()
    for tag in ("w:spacing", "w:ind", "w:jc", "w:pageBreakBefore", "w:keepNext",
                "w:contextualSpacing"):
        for el in ppr.findall(qn(tag)):
            ppr.remove(el)
    pf = p.paragraph_format
    pf.alignment = align
    pf.left_indent = Cm(left)
    pf.right_indent = Cm(0)
    pf.first_line_indent = Cm(-hanging) if hanging else Cm(first)
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = spacing
    if keep_next:
        pf.keep_with_next = True
    if page_break:
        pf.page_break_before = True
    pf.widow_control = True
    return p


def add_field(p, instr, cached="1", size=14, bold=None):
    def r(child):
        run = p.add_run()
        set_run_font(run, size, bold)
        run._r.append(child)
        return run
    b = OxmlElement("w:fldChar"); b.set(qn("w:fldCharType"), "begin")
    i = OxmlElement("w:instrText"); i.set(qn("xml:space"), "preserve"); i.text = instr
    s = OxmlElement("w:fldChar"); s.set(qn("w:fldCharType"), "separate")
    e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), "end")
    r(b); r(i); r(s)
    t = p.add_run(str(cached)); set_run_font(t, size, bold)
    r(e)


_bm_id = [100]


def add_bookmark(p, name):
    _bm_id[0] += 1
    s = OxmlElement("w:bookmarkStart")
    s.set(qn("w:id"), str(_bm_id[0])); s.set(qn("w:name"), name)
    e = OxmlElement("w:bookmarkEnd"); e.set(qn("w:id"), str(_bm_id[0]))
    ppr = p._p.find(qn("w:pPr"))
    idx = list(p._p).index(ppr) + 1 if ppr is not None else 0
    p._p.insert(idx, s)
    p._p.append(e)


def set_cell_margins(table, lr=0.1, tb=0.0):
    tblPr = table._tbl.tblPr
    for el in tblPr.findall(qn("w:tblCellMar")):
        tblPr.remove(el)
    mar = OxmlElement("w:tblCellMar")
    for side, v in (("top", tb), ("left", lr), ("bottom", tb), ("right", lr)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(int(v * 567))); el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblPr.append(mar)


def set_table_widths(table, widths_mm):
    """Фиксированная раскладка с заданными ширинами столбцов (мм)."""
    tbl = table._tbl
    tblPr = tbl.tblPr
    for tag in ("w:tblW", "w:tblLayout", "w:jc", "w:tblInd"):
        for el in tblPr.findall(qn(tag)):
            tblPr.remove(el)
    tw = OxmlElement("w:tblW")
    tw.set(qn("w:w"), str(int(sum(widths_mm) * 56.7))); tw.set(qn("w:type"), "dxa")
    tblPr.append(tw)
    lay = OxmlElement("w:tblLayout"); lay.set(qn("w:type"), "fixed"); tblPr.append(lay)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    grid = tbl.tblGrid
    for g in list(grid):
        grid.remove(g)
    for w in widths_mm:
        g = OxmlElement("w:gridCol"); g.set(qn("w:w"), str(int(w * 56.7))); grid.append(g)
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if i < len(widths_mm):
                cell.width = Mm(widths_mm[i])


def no_borders(table):
    tblPr = table._tbl.tblPr
    for el in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(el)
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}"); el.set(qn("w:val"), "nil"); b.append(el)
    tblPr.append(b)


# ───────────────────────────── построитель ──────────────────────────────────

class Builder:
    def __init__(self, src):
        self.doc = Document(src)
        self.body = self.doc.element.body
        self.final_sect = self.body.find(qn("w:sectPr"))
        self.old = [el for el in self.body if el is not self.final_sect]
        for el in self.old:
            self.body.remove(el)
        self.setup_styles()

    # -- стили --------------------------------------------------------------
    def setup_styles(self):
        st = self.doc.styles
        normal = st["Normal"]
        rpr = normal.element.get_or_add_rPr()
        for el in list(rpr):
            rpr.remove(el)
        normal.font.name = FONT
        rf = rpr.find(qn("w:rFonts"))
        for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rf.set(qn(a), FONT)
        normal.font.size = Pt(14)
        lang = OxmlElement("w:lang")
        lang.set(qn("w:val"), "ru-RU"); lang.set(qn("w:eastAsia"), "ru-RU")
        rpr.append(lang)
        pf = normal.paragraph_format
        pf.space_before = Pt(0); pf.space_after = Pt(0)
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE; pf.line_spacing = 1.5

        for lvl in (1, 2, 3):
            h = st[f"Heading {lvl}"]
            rpr = h.element.get_or_add_rPr()
            for el in list(rpr):
                rpr.remove(el)
            h.font.name = FONT
            rf = rpr.find(qn("w:rFonts"))
            for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                rf.set(qn(a), FONT)
            h.font.size = Pt(14); h.font.bold = True
            h.font.color.rgb = RGBColor(0, 0, 0)
            ppr = h.element.get_or_add_pPr()
            for tag in ("w:spacing", "w:ind", "w:jc", "w:pageBreakBefore"):
                for el in ppr.findall(qn(tag)):
                    ppr.remove(el)
            pf = h.paragraph_format
            pf.space_before = Pt(0); pf.space_after = Pt(0)
            pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE; pf.line_spacing = 1.5
            pf.first_line_indent = Cm(1.25); pf.left_indent = Cm(0)
            pf.alignment = L
            pf.keep_with_next = True; pf.keep_together = True
            pf.page_break_before = (lvl == 1)

    # -- добавление элементов -------------------------------------------------
    def keep(self, el):
        """Вернуть в тело существующий элемент исходного документа."""
        self.final_sect.addprevious(el)
        return el

    def P(self, text="", size=14, bold=None, italic=None, underline=None, style=None, **kw):
        p = self.doc.add_paragraph(style=style)
        if text:
            run = p.add_run(text)
            set_run_font(run, size, bold, italic, underline=underline)
        elif size != 14:
            # размер пустой строки задаётся знаком абзаца
            rpr = OxmlElement("w:rPr"); sz = OxmlElement("w:sz")
            sz.set(qn("w:val"), str(int(size * 2))); rpr.append(sz)
            p._p.get_or_add_pPr().append(rpr)
        kw.setdefault("align", L)
        fmt(p, **kw)
        return p

    def runs(self, parts, **kw):
        """Абзац из нескольких фрагментов: (текст, {size,bold,italic,underline})."""
        p = self.doc.add_paragraph()
        for text, o in parts:
            run = p.add_run(text)
            set_run_font(run, o.get("size", 14), o.get("bold"), o.get("italic"),
                         underline=o.get("underline"))
        kw.setdefault("align", L)
        fmt(p, **kw)
        return p

    def tabs(self, p, *stops):
        for pos, al, lead in stops:
            p.paragraph_format.tab_stops.add_tab_stop(Mm(pos), al, lead)
        return p

    def table(self, rows, cols):
        t = self.doc.add_table(rows=rows, cols=cols)
        t.style = "Table Grid"
        return t

    def cell(self, cell, text, size=12, bold=None, italic=None, align=L, spacing=1.0,
             valign=None):
        p = cell.paragraphs[0]
        for r in list(p.runs):
            r._r.getparent().remove(r._r)
        if text:
            set_run_font(p.add_run(text), size, bold, italic)
        fmt(p, align=align, spacing=spacing)
        if valign:
            cell.vertical_alignment = valign
        return p

    def section_break(self, **margins):
        """Закрыть текущий раздел (свойства задаются позже через doc.sections)."""
        self.doc.add_section(WD_SECTION.NEW_PAGE)

    # -- переоформление существующих абзацев ----------------------------------
    def restyle_runs(self, p, size=14, name=FONT, bold=None):
        for r in p.runs:
            b = r.bold if bold is None else bold
            i = r.italic
            set_run_font(r, size, name=name)
            r.bold = b if b else None
            r.italic = i if i else None

    def scale_images(self, p, max_w, max_h):
        for ext in p._p.iter(qn("wp:extent")):
            cx, cy = int(ext.get("cx")), int(ext.get("cy"))
            k = min(max_w / cx, max_h / cy, 1.0) if max_w < cx or max_h < cy else 1.0
            if max_w and k == 1.0 and cx != max_w and getattr(self, "_force_w", False):
                k = min(max_w / cx, max_h / cy)
            if k != 1.0:
                nx, ny = int(cx * k), int(cy * k)
                ext.set("cx", str(nx)); ext.set("cy", str(ny))
                for a in p._p.iter(qn("a:ext")):
                    if a.get("cx") == str(cx):
                        a.set("cx", str(nx)); a.set("cy", str(ny))


# ───────────────────────────── служебные листы ──────────────────────────────

def ministry_line(b, size=12, **kw):
    p = b.P("МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ РОССИЙСКОЙ ФЕДЕРАЦИИ",
            size=size, bold=True, align=C, spacing=1.0, **kw)
    # строка шире полосы набора — как в эталоне, слегка выходит на поля
    p.paragraph_format.left_indent = Mm(-4)
    p.paragraph_format.right_indent = Mm(-4)
    return p


def university_header(b, size=12):
    ministry_line(b, size)
    b.P("Брянский филиал федерального государственного бюджетного образовательного",
        size=size, align=C, spacing=1.0)
    b.P("учреждения высшего образования", size=size, align=C, spacing=1.0)
    b.P("«Российский экономический университет им. Г.В. Плеханова»",
        size=size, align=C, spacing=1.0)


def title_page(b):
    S = dict(spacing=1.0)
    cap = dict(size=7, bold=True, spacing=1.0)
    university_header(b)
    b.P(**S); b.P(**S)
    b.P("Отчет", size=16, bold=True, align=C, **S)
    b.P(size=11, **S)
    b.P("по производственной практике", size=11, bold=True, align=C, **S)
    b.P("ПП.02.01 Производственная практика (по профилю специальности)",
        size=12, bold=True, align=C, underline=True, **S)
    b.P("(наименование производственной практики)", align=C, **cap)
    b.P(size=11, **S)
    b.runs([("Специальность ", dict(size=11, bold=True)),
            ("09.02.07 Информационные системы и программирование", dict(size=11, bold=True, underline=True)),
            ("_______________________", dict(size=11, bold=True))], **S)
    b.P("(наименование специальности)", align=C, **cap)

    def sign_row(left, right):
        p = b.P(f"{left}\t{right}", size=12, **S)
        b.tabs(p, (75, WD_TAB_ALIGNMENT.LEFT, WD_TAB_LEADER.SPACES))
        p = b.P("\t(подпись)\t(фамилия, имя, отчество)", **cap)
        b.tabs(p, (30, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES),
               (112, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES))

    def date_row(left=""):
        p = b.P(f"{left}\t«16» ноября 2026 года", size=12, **S)
        b.tabs(p, (100, WD_TAB_ALIGNMENT.LEFT, WD_TAB_LEADER.SPACES))

    sign_row("Студент __________________", "__________________________________________")
    b.P(size=12, **S)
    b.P("Группы _______", size=12, **S)
    b.P(size=12, **S)
    b.P("Руководитель практики от организации", size=12, **S)
    b.P("_____________________________________________________________________________", size=12, **S)
    b.P("(должность)", align=C, **cap)
    sign_row("___________________________", "__________________________________________")
    b.P(size=12, **S)
    date_row("МП")
    b.P(size=12, **S); b.P(size=12, **S)
    b.P("Руководитель практики от", size=12, **S)
    b.P("Брянского филиала РЭУ им. Г.В. Плеханова", size=12, **S)
    b.P(size=12, **S)
    sign_row("___________________________", "____________________________")
    b.P(size=12, **S)
    date_row()
    for _ in range(14):
        b.P(size=12, **S)
    b.P("Брянск, 2026 год", size=12, align=C, **S)


def attestation_sheet(b):
    S = dict(spacing=1.0)
    cap = dict(size=7, bold=True, spacing=1.0)
    university_header(b, size=11)
    b.P("АТТЕСТАЦИОННЫЙ ЛИСТ", bold=True, align=C, **S)
    b.P("(характеристика профессиональной деятельности обучающегося во время практики)",
        size=11, bold=True, align=C, **S)
    b.P("_____________________________________________________________________________", size=12, **S)
    b.P("(фамилия, имя, отчество)", align=C, **cap)
    b.P(size=6, **S)
    b.P("Обучающийся на ___ курсе", size=11, **S)
    b.P("по специальности СПО 09.02.07 Информационные системы и программирование   Группа ______",
        size=11, **S)
    b.P("(код и наименование специальности)", align=C, **cap)
    b.P(size=6, **S)
    b.P("успешно прошел (ла) производственную практику", size=12, **S)
    b.P("ПП.02.01 Производственная практика (по профилю специальности)", size=12, underline=True, **S)
    b.P("(индекс и наименование практики)", **cap)
    b.P(size=6, **S)
    b.P(f"в объеме 108 часов с {DATE_START} по {DATE_END}, {DEF_START} по {DEF_END}", size=12, **S)
    b.P("1. Виды и объём работ, выполненные обучающимся во время практики", size=11, left=0.4, **S)

    rows = [
        ("Раздел 1. Анализ структуры базы практики (организации)", "3"),
        ("Раздел 2. Предпроектное исследование и анализ задачи.", "6"),
        ("Раздел 3. Процесс разработки технического задания.", "12"),
        ("Раздел 4. Процесс разработки программного обеспечения в соответствии с техническим заданием", "18"),
        ("Раздел 5. Процесс применения инструментальных средств разработки ПО.", "12"),
        ("Раздел 6. Процесс разработки интерфейса пользователя ПО в соответствии с техническим заданием", "30"),
        ("Раздел 7. Процесс тестирования и отладки", "12"),
        ("Раздел 8. Инспектирование компонент программного обеспечения на предмет соответствия стандартам кодирования.", "6"),
        ("Раздел 9. Осуществление технического сопровождения ПО", "6"),
        ("Сбор и систематизация материала для отчета. Подготовка доклада и презентации для защиты отчета", "3"),
    ]
    t = b.table(len(rows) + 2, 2)
    b.cell(t.cell(0, 0), "Виды работ", size=10, align=C)
    b.cell(t.cell(0, 1), "Объём выполненных работ (часов)", size=10, align=C)
    for i, (name, hours) in enumerate(rows, 1):
        b.cell(t.cell(i, 0), name, size=11)
        b.cell(t.cell(i, 1), hours, size=10, align=C, valign=WD_CELL_VERTICAL_ALIGNMENT.CENTER)
    b.cell(t.cell(len(rows) + 1, 0), "Итого часов", size=10, italic=True)
    b.cell(t.cell(len(rows) + 1, 1), "108", size=10, bold=True, align=C)
    set_table_widths(t, [112, 58])
    set_cell_margins(t, 0.15)

    b.P(size=6, **S)
    b.P("2. Качество выполнения работ в соответствии с требованиями программы практики:", size=11, **S)
    p = b.P("\t_______________\t(______________________________)", size=11, **S)
    b.tabs(p, (62, WD_TAB_ALIGNMENT.LEFT, WD_TAB_LEADER.SPACES), (100, WD_TAB_ALIGNMENT.LEFT, WD_TAB_LEADER.SPACES))
    p = b.P("\t(оценка)\t(прописью)", **cap)
    b.tabs(p, (78, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES), (130, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES))
    b.P(size=6, **S)
    b.P("3. База прохождения практики", size=11, **S)
    line = "_____________________________________________"

    def row3(a, bb, c=line):
        p = b.P(f"{a}\t{bb}\t{c}", size=11, **S)
        b.tabs(p, (50, WD_TAB_ALIGNMENT.LEFT, WD_TAB_LEADER.SPACES), (75, WD_TAB_ALIGNMENT.LEFT, WD_TAB_LEADER.SPACES))

    row3("Предприятие (организация):", "Наименование")
    row3("", ""); row3("", "")
    row3("Руководитель практики от", "", "")
    row3("предприятия (организации)", "Должность")
    row3("", "ФИО")
    row3("МП", "Подпись")
    b.P(size=6, **S)
    row3("Руководитель практики", "Должность")
    row3("от Брянского филиала", "ФИО")
    row3("РЭУ им. Г.В. Плеханова", "Подпись")
    p = b.P("Итоговая оценка по практике\t_______________  (__________________)", size=11, **S)
    b.tabs(p, (62, WD_TAB_ALIGNMENT.LEFT, WD_TAB_LEADER.SPACES))
    p = b.P("\t(оценка)\t(прописью)", **cap)
    b.tabs(p, (78, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES), (112, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES))
    b.P("Дата «16» 11.2026 г., «21» 03.2027 г.", size=11, before=4, **S)


def diary_title(b):
    S = dict(spacing=1.0)
    ministry_line(b, 12, page_break=True)
    b.P("Брянский филиал федерального государственного бюджетного образовательного", size=12, align=C, **S)
    b.P("учреждения высшего образования", size=12, align=C, **S)
    b.P("«Российский экономический университет им. Г.В. Плеханова»", size=12, align=C, **S)
    for _ in range(4):
        b.P(**S)
    b.P("Дневник", bold=True, align=C, **S)
    b.P("производственной практики", bold=True, underline=True, align=C, **S)
    b.P("(указать вид практики)", size=8, align=C, **S)
    for _ in range(3):
        b.P(**S)
    b.P("ПП.02.01 Производственная практика (по профилю специальности)", underline=True, align=C, **S)
    b.P("(наименование практики)", size=8, align=C, **S)
    b.P(**S)
    for parts in (
        [("Обучающийся ____ курса", {})],
        [("Специальности 09.02.07 ", {}), ("Информационные системы и программирование", {"underline": True})],
        [("Группа _____", {})],
        [("Фамилия ______________________________", {})],
        [("Имя __________________________________", {})],
        [("Отчество ______________________________", {})],
    ):
        b.runs([(t, dict(bold=True, **o)) for t, o in parts], **S)
        b.P(**S)
    b.P(**S); b.P(**S)
    b.P("Период проведения практики", bold=True, **S)
    b.P(f"с {DATE_START} по {DATE_END}", bold=True, **S)
    b.P(f"с {DEF_START} по {DEF_END} г.", bold=True, **S)


def base_info(b):
    S = dict(spacing=1.0)
    b.P(page_break=True, **S)
    b.P("СВЕДЕНИЯ О БАЗЕ ПРАКТИКИ", bold=True, align=C, **S)
    b.P(**S)
    b.P("Руководитель практики от структурного предприятия СПО:", bold=True, italic=True, underline=True, **S)
    b.P(**S)
    b.runs([("Ф.И.О.: ", {}), ("Луцкова Татьяна Николаевна", {"underline": True})], **S)
    b.P("(Фамилия, Имя, Отчество (полностью)", size=8, left=2.2, **S)
    b.P(**S)
    b.runs([("Должность: ", {}), ("преподаватель", {"underline": True})], **S)
    b.P(**S)
    b.P("Руководитель практики от предприятия:", bold=True, italic=True, underline=True, **S)
    b.P(**S)
    b.P("Ф.И.О.: __________________________________________________________", **S)
    b.P("(Фамилия, Имя и Отчество (полностью) руководителя практики по месту прохождения практики)",
        size=8, align=C, **S)
    b.P(**S)
    b.P("Должность: ____________________________________________________", **S)
    b.P(**S)
    b.P("Базовое предприятие (название организации)", bold=True, italic=True, underline=True, **S)
    b.P("______________________________________________________________", **S)
    b.P("______________________________________________________________", **S)
    b.P("Адрес предприятия (организации) ______________________________", **S)
    b.P("______________________________________________________________", **S)
    b.P(**S)
    b.P("Период прохождения практики:", **S)
    b.P(f"с {DATE_START} по {DATE_END}", bold=True, **S)
    b.P(f"с {DEF_START} по {DEF_END} г.", bold=True, **S)


OK_LIST = [
    ("ОК 1.", "Выбирать способы решения задач профессиональной деятельности, применительно к различным контекстам"),
    ("ОК 2.", "Использовать современные средства поиска, анализа и интерпретации информации и информационные технологии для выполнения задач профессиональной деятельности"),
    ("ОК 3.", "Планировать и реализовывать собственное профессиональное и личностное развитие, предпринимательскую деятельность в профессиональной сфере, использовать знания по финансовой грамотности в различных жизненных ситуациях"),
    ("ОК 4.", "Эффективно взаимодействовать и работать в коллективе и команде"),
    ("ОК 5.", "Осуществлять устную и письменную коммуникацию на государственном языке Российской Федерации с учетом особенностей социального и культурного контекста"),
    ("ОК 6.", "Проявлять гражданско-патриотическую позицию, демонстрировать осознанное поведение на основе традиционных общечеловеческих ценностей, в том числе с учетом гармонизации межнациональных и межрелигиозных отношений, применять стандарты антикоррупционного поведения"),
    ("ОК 7.", "Содействовать сохранению окружающей среды, ресурсосбережению, применять знания об изменении климата, принципы бережливого производства, эффективно действовать в чрезвычайных ситуациях"),
    ("ОК 8.", "Использовать средства физической культуры для сохранения и укрепления здоровья в процессе профессиональной деятельности и поддержание необходимого уровня физической подготовленности"),
    ("ОК 9.", "Пользоваться профессиональной документацией на государственном и иностранном языках"),
]
PK_LIST = [
    ("ПК 2.1", "Разрабатывать требования к программным модулям на основе анализа проектной и технической документации на предмет взаимодействия компонент."),
    ("ПК 2.2", "Выполнять интеграцию модулей в программное обеспечение."),
    ("ПК 2.3", "Выполнять отладку программного модуля с использованием специализированных программных средств."),
    ("ПК 2.4", "Осуществлять разработку тестовых наборов и тестовых сценариев для программного обеспечения."),
    ("ПК 2.5", "Производить инспектирование компонент программного обеспечения на предмет соответствия стандартам кодирования."),
]


def goals(b):
    S = dict(spacing=1.15)
    b.P("ЦЕЛИ И ЗАДАЧИ ПРАКТИКИ", bold=True, align=C, page_break=True, after=6, **S)
    b.P("Практика имеет целью комплексное освоение обучающимися по специальности 09.02.07 "
        "Информационные системы и программирование профессиональных и общих компетенций в рамках "
        "профессионального модуля ПМ.02 Осуществление интеграции программных модулей.",
        align=J, first=1.25, after=6, **S)
    b.P("Задачи практики:", first=1.25, after=4, **S)
    for t in ("закрепление теоретических знаний, полученных в процессе обучения,",
              "приобретение первичных профессиональных умений и навыков:"):
        b.P("–\t" + t, align=J, left=1.27, hanging=0.63, **S)
    for t in ("определение доступных источников информации;",
              "сбор материала по теоретическим вопросам индивидуального задания;",
              "выполнение практических заданий по виду профессиональной деятельности;",
              "представление результатов работы в виде отчета и его устной презентации."):
        b.P("•\t" + t, align=J, left=3.27, hanging=0.63, spacing=1.0)
    b.P(**S)
    b.P("ТРЕБОВАНИЯ К РЕЗУЛЬТАТАМ ОСВОЕНИЯ ОСНОВНОЙ ПРОФЕССИОНАЛЬНОЙ ОБРАЗОВАТЕЛЬНОЙ ПРОГРАММЫ",
        bold=True, align=C, after=8, spacing=1.0)
    b.P("Прохождение практики приводит к формированию следующих компетенций:", after=4, spacing=1.0)

    def comp_table(title, head, items):
        b.P(title, size=12, left=0.3, spacing=1.0, keep_next=True)
        t = b.table(len(items) + 1, 2)
        b.cell(t.cell(0, 0), "Код", bold=True)
        b.cell(t.cell(0, 1), head, bold=True)
        for i, (code, text) in enumerate(items, 1):
            b.cell(t.cell(i, 0), code, align=C)
            b.cell(t.cell(i, 1), text, align=J)
        set_table_widths(t, [20, 150])
        set_cell_margins(t, 0.12)

    comp_table("Перечень общих компетенций", "Наименование общих компетенций", OK_LIST)
    b.P(size=12, spacing=1.0)
    comp_table("Перечень профессиональных компетенций",
               "Наименование видов деятельности и профессиональных компетенций", PK_LIST)
    b.P(spacing=1.0)

    b.P("СОДЕРЖАНИЕ ЗАДАНИЯ НА ПРАКТИКУ", align=C, keep_next=True, **S)

    def num(t):
        b.P(t, align=J, left=1.27, hanging=0.63, **S)

    def dash(t, left=1.27):
        b.P("–\t" + t, align=J, left=left, hanging=0.63, **S)

    num("1.\tОзнакомиться со структурой предприятия и производства (основными видами деятельности);")
    num("2.\tИзучить:")
    dash("программные продукты, используемые и/или разрабатываемые на данном предприятии;")
    dash("их технические характеристики, разнообразие ассортимента и назначение программного обеспечения;")
    dash("этапы разработки и внедрения программного продукта на данном предприятии и специфика написания сопроводительной документации;")
    dash("инструментальные среды разработки и сопровождения программных средств;")
    dash("особенности использования вычислительной техники и автоматизированных систем на предприятии.")
    num("3.\tПровести анализ состояния информационной системы на предприятии.")
    num("4.\tОхарактеризовать программное обеспечение, с которым придётся работать в момент прохождения практики.")
    num("5.\tУчаствовать в написании программных продуктов для предприятия:")
    dash("разработка требований к программному продукту;", 2.5)
    dash("разработка программного продукта с использованием инструментального средства;", 2.5)
    dash("разработка интерфейса пользователя, разработка форм для ввода, просмотра и редактирования данных;", 2.5)
    dash("участие в проведении работ по тестированию и отладке программного продукта.", 2.5)
    num("6.\tПроизвести инспектирование компонент программного обеспечения на предмет соответствия стандартам кодирования.")
    num("7.\tВести дневник практики.")
    num("8.\tПо окончании практики сдать отчёт, в котором отразить вопросы, изученные в ходе прохождения практики.")
    b.P(**S)
    S1 = dict(spacing=1.0, left=6.0, keep_next=True)
    b.P("«03» 11.2026 год", **S1)
    b.P("«13» 03.2027 год", **S1)
    b.P(**S1)
    b.P("Руководитель практики", **S1)
    b.P("от организации ______________________", **S1)
    p = b.P("М.П.\t(подпись)", spacing=1.0, keep_next=True)
    b.tabs(p, (125, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES))
    b.P("Ознакомлен:", **S1)
    b.P("обучающийся ______________________", **S1)
    p = b.P("\t(подпись)", spacing=1.0)
    b.tabs(p, (125, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES))


def safety(b):
    S = dict(spacing=1.0, bold=True)
    b.P("ИНСТРУКТАЖ ПО ТЕХНИКЕ БЕЗОПАСНОСТИ", align=C, page_break=True, after=10, **S)
    b.P("Провёл инструктаж по охране труда, технике безопасности и производственной санитарии",
        align=J, first=1.25, **S)
    b.P("______________________________________________________________", **S)
    b.P("(Фамилия, имя, отчество, должность проводившего инструктаж)", size=10, bold=True, italic=True,
        align=C, spacing=1.0, after=6)
    b.P("Вид инструктаж: (заполнять только тот вид инструктажа, который проводится)", align=J, after=18, **S)
    b.P("ВВОДНЫЙ ИНСТРУКТАЖ", after=4, **S)
    b.P("Подпись____________________Дата 03.11.2026", after=4, **S)
    b.P("ПЕРВИЧНЫЙ ИНСТРУКТАЖ НА РАБОЧЕМ МЕСТЕ", after=4, **S)
    b.P("Подпись____________________Дата 03.11.2026", after=18, **S)
    for _ in range(2):
        b.P("ПОВТОРНЫЙ ИНСТРУКТАЖ, СВЯЗАННЫЙ С ПЕРЕМЕНОЙ РАБОЧЕГО МЕСТА", after=6, **S)
        b.P("Подпись____________________Дата ____________________", after=18, **S)
    b.P("Инструктаж получил (а)", after=12, **S)
    b.P("______________________________________________________________", **S)
    b.P("(Фамилия, имя, отчество получившего инструктаж)", size=10, italic=True, align=C, spacing=1.0, after=24)
    b.P("Подпись____________________Дата 03.11.2026", after=8, **S)
    b.P("Подпись____________________Дата 03.11.2026", after=8, **S)
    b.P("Подпись____________________Дата_______________", after=8, **S)
    b.P("Подпись____________________Дата_______________", after=8, **S)


def diary_table(b, tbl_el):
    b.P(size=2, spacing=1.0, page_break=True)
    b.keep(tbl_el)
    t = Table(tbl_el, b.doc)
    VC = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for ri, row in enumerate(t.rows):
        trPr = row._tr.get_or_add_trPr()
        for el in trPr.findall(qn("w:trHeight")):
            trPr.remove(el)
        h = OxmlElement("w:trHeight")
        h.set(qn("w:val"), str(int(17 * 56.7))); h.set(qn("w:hRule"), "atLeast")
        trPr.append(h)
        cant = OxmlElement("w:cantSplit"); trPr.append(cant)
        for ci, cell in enumerate(row.cells):
            cell.vertical_alignment = VC
            for p in cell.paragraphs:
                b.restyle_runs(p, 12, bold=False)
                fmt(p, align=C if (ri == 0 or ci == 0) else L, spacing=1.0)
    set_table_widths(t, [27, 114, 32])
    set_cell_margins(t, 0.15)


def characteristic(b):
    S = dict(spacing=1.0)
    line = "______________________________________________________________"
    b.runs([("Характеристика", {"bold": True}),
            (" обучающегося (с указанием степени его профессиональной подготовки, качества выполняемой "
             "работы, трудовой дисциплины и недостатков, если они имели место)", {})],
           align=J, page_break=True, **S)
    b.P(**S)
    b.P("За время практики обучающимся была выполнена следующая работа (перечислить):", align=J, **S)
    for _ in range(5):
        b.P(line, spacing=1.5)
    b.P(**S); b.P(**S)
    b.P("При прохождении практики обучающийся ____________________________", **S)
    p = b.P("\t(Фамилия, инициалы)", size=8, **S)
    b.tabs(p, (125, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES))
    b.P("зарекомендовал себя __________________________________________", spacing=1.5)
    b.P(line, spacing=1.5)
    b.P(line, spacing=1.5)
    b.P(**S)
    b.P("Примечание: дать характеристику профессиональным знаниям, умениям и навыкам обучающегося, "
        "степени его ответственности, дисциплинированности, исполнительности, адаптированности в "
        "коллективе, стремлению к саморазвитию, совершенствованию в профессиональной деятельности.",
        align=J, **S)
    b.P(**S)
    b.P("Оценка работы обучающегося за практику ___________  (_____________)", **S)
    p = b.P("\tоценка цифрой\t(оценка прописью)", size=8, **S)
    b.tabs(p, (112, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES), (145, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES))
    b.P(**S); b.P(**S)
    b.P("Руководитель практики от", bold=True, italic=True, **S)
    b.runs([("предприятия", {"bold": True, "italic": True}),
            (" ________________  /_____________________/", {})], **S)
    p = b.P("\tподпись\t(Расшифровка подписи)", size=8, **S)
    b.tabs(p, (50, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES), (100, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES))


def conclusion_form(b):
    S = dict(spacing=1.0)
    b.P("Заключение руководителя практики от Брянского филиала РЭУ им. Г.В. Плеханова и оценка "
        "результатов практики", page_break=True, after=10, **S)
    for _ in range(15):
        b.P("_____________________________________________________________________________", size=12, **S)
    b.P(size=12, **S)
    b.P("Итоговая оценка по практике", size=12, **S)
    b.P("_____________________________________________________________________________", size=12, **S)
    b.P("Руководитель практики", before=4, **S)
    b.P("от Брянского филиала", **S)
    b.runs([("РЭУ им. Г.В. Плеханова ___________              ", {}), ("Т.Н. Луцкова", {"underline": True})], **S)
    p = b.P("\t(подпись)\t(расшифровка подписи)", size=9, bold=True, italic=True, **S)
    b.tabs(p, (72, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES), (118, WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES))


# ───────────────────────────── основная часть ───────────────────────────────

RE_H1 = re.compile(r"^(\d)\s+\S")
RE_H2 = re.compile(r"^(\d)\.(\d)\s+\S")
RE_H3 = re.compile(r"^(\d)\.(\d)\.(\d)\s+\S")
STRUCT = ("Введение", "Заключение", "Список использованных источников")


def build(src, dst, pages=None, only=None):
    """pages — {закладка: номер страницы}; only — собрать один блок (для расчёта страниц)."""
    pages = pages or {}
    b = Builder(src)
    doc = b.doc
    old = b.old
    is_p = lambda el: el.tag == qn("w:p")
    text = lambda el: Paragraph(el, doc).text.strip() if is_p(el) else ""

    # --- разбор исходника -----------------------------------------------------
    diary_tbl = next(el for el in old if el.tag == qn("w:tbl"))
    i_intro = max(i for i, el in enumerate(old) if text(el) == "Введение")
    content = old[i_intro:]

    # блоки: каждый начинается с новой страницы
    blocks, cur = [], None
    toc = []          # (уровень, текст, закладка)
    mode = "body"
    n_h = [0]

    def new_block(name):
        nonlocal cur
        cur = {"name": name, "els": []}
        blocks.append(cur)

    items = []        # (kind, element)
    prev_kind = None
    for el in content:
        t = text(el)
        if not is_p(el):
            items.append(("table", el)); continue
        has_img = el.find(".//" + qn("w:drawing")) is not None
        if t in STRUCT:
            mode = "sources" if t.startswith("Список") else "body"
            items.append(("struct", el))
        elif re.match(r"^Приложение [А-Я]$", t):
            mode = "appA" if t.endswith("А") else "appB"
            items.append(("app", el))
        elif mode in ("appA", "appB") and items[-1][0] == "app":
            items.append(("apptitle", el))
        elif has_img:
            items.append(("slide" if mode == "appA" else "figure", el))
        elif mode == "appA":
            if t.startswith("Слайд"):
                items.append(("slidecap", el))
        elif mode == "appB":
            if re.match(r"^Листинг [А-Я]\.\d", t):
                items.append(("listcap", el))
            elif el.find(".//" + qn("w:rFonts")) is not None and \
                    "Consolas" in (el.find(".//" + qn("w:rFonts")).get(qn("w:ascii")) or ""):
                items.append(("code", el))
            elif t:
                items.append(("text", el))
        elif not t:
            continue                                   # пустые абзацы-разделители
        elif t.startswith("Рисунок ") and items and items[-1][0] == "figure":
            items.append(("figcap", el))
        elif t.startswith("Таблица ") and "–" in t[:14]:
            items.append(("tabcap", el))
        elif mode == "sources":
            items.append(("source", el))
        elif RE_H3.match(t) and Paragraph(el, doc).runs[0].bold:
            items.append(("h3", el))
        elif RE_H2.match(t) and Paragraph(el, doc).runs[0].bold:
            items.append(("h2", el))
        elif RE_H1.match(t) and Paragraph(el, doc).runs[0].bold:
            items.append(("h1", el))
        else:
            items.append(("text", el))

    for kind, el in items:
        if kind in ("struct", "h1", "app"):
            new_block(text(el))
        cur["els"].append((kind, el))

    if only not in (None, "title", "forms", "forms2"):
        b.P("(служебная страница для расчёта нумерации)")
    # --- 1. титульный лист ----------------------------------------------------
    if only is None or only == "title":
        title_page(b)
    if only is None:
        b.section_break()

    # --- 2. содержание --------------------------------------------------------
    toc_entries = []
    for blk in blocks:
        for kind, el in blk["els"]:
            if kind in ("struct", "h1", "h2"):
                n_h[0] += 1
                toc_entries.append((kind, text(el), f"_Toc{n_h[0]:03d}", el))
    bm_of = {id(el): bm for _, _, bm, el in toc_entries}

    if only is None or only == "toc":
        p = b.P("Содержание", bold=True, align=C, page_break=only is not None)
        for kind, t, bm, _ in toc_entries:
            top = kind != "h2"
            p = b.P(t + "\t", bold=top or None, left=0 if top else 0.5, spacing=1.0)
            b.tabs(p, (175, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS))
            p.add_run(str(pages.get(bm, "0")))
        b.P("Приложения", bold=True, spacing=1.0)

    # --- 3. основная часть и приложения ----------------------------------------
    slide_no = 0
    for blk in blocks:
        if only is not None and only != blk["name"]:
            continue
        for kind, el in blk["els"]:
            if is_p(el):
                p = Paragraph(el, doc)
                ppr = el.find(qn("w:pPr"))
                if ppr is not None:
                    for tag in ("w:pStyle", "w:rPr", "w:keepNext", "w:keepLines", "w:tabs"):
                        for x in ppr.findall(qn(tag)):
                            ppr.remove(x)
                for x in list(el.iter(qn("w:lastRenderedPageBreak"))):
                    x.getparent().remove(x)

            if kind == "struct":
                b.keep(el); p.style = doc.styles["Heading 1"]
                b.restyle_runs(p, bold=True)
                fmt(p, align=C, page_break=True, keep_next=True)
                add_bookmark(p, bm_of[id(el)])
            elif kind in ("h1", "h2", "h3"):
                b.keep(el); p.style = doc.styles[f"Heading {kind[1]}"]
                b.restyle_runs(p, bold=True)
                fmt(p, align=L, first=1.25, page_break=(kind == "h1"), keep_next=True)
                if kind != "h3":
                    add_bookmark(p, bm_of[id(el)])
            elif kind == "text":
                b.keep(el); b.restyle_runs(p)
                fmt(p, align=J, first=1.25)
            elif kind == "source":
                b.keep(el); b.restyle_runs(p)
                is_item = bool(re.match(r"^\d+\.", p.text.strip()))
                fmt(p, align=L if is_item else J, first=1.25)
            elif kind == "figure":
                b.keep(el); b.scale_images(p, Mm(165), Mm(115))
                fmt(p, align=C, keep_next=True, spacing=1.0)
            elif kind == "figcap":
                b.keep(el); b.restyle_runs(p)
                fmt(p, align=C)
            elif kind == "tabcap":
                b.keep(el); b.restyle_runs(p)
                fmt(p, align=L, keep_next=True)
            elif kind == "table":
                b.keep(el)
                t = Table(el, doc)
                grid = [int(g.get(qn("w:w"))) for g in el.tblGrid]
                k = 175.0 / sum(grid)
                for ri, row in enumerate(t.rows):
                    trPr = row._tr.get_or_add_trPr()
                    if trPr.find(qn("w:cantSplit")) is None:
                        trPr.append(OxmlElement("w:cantSplit"))
                    if ri == 0 and trPr.find(qn("w:tblHeader")) is None:
                        trPr.append(OxmlElement("w:tblHeader"))
                    for cell in row.cells:
                        for cp in cell.paragraphs:
                            was_center = cp.paragraph_format.alignment == C
                            b.restyle_runs(cp, 12, bold=(ri == 0))
                            fmt(cp, align=C if (ri == 0 or was_center) else L, spacing=1.0)
                        if ri == 0:
                            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                set_table_widths(t, [g * k for g in grid])
                set_cell_margins(t, 0.15)
            elif kind == "app":
                b.keep(el); b.restyle_runs(p, bold=True)
                fmt(p, align=R, page_break=True, keep_next=True)
            elif kind == "apptitle":
                b.keep(el); b.restyle_runs(p, bold=True)
                fmt(p, align=R, keep_next=True)
            elif kind == "slide":
                slide_no += 1
                if slide_no > 1 and slide_no % 2 == 1:
                    b.P("Продолжение приложения А", align=R, page_break=True, keep_next=True)
                b.keep(el)
                b._force_w = True
                b.scale_images(p, Mm(172), Mm(98))
                b._force_w = False
                fmt(p, align=C, keep_next=True, spacing=1.0)
            elif kind == "slidecap":
                b.keep(el); b.restyle_runs(p)
                fmt(p, align=C)
            elif kind == "listcap":
                b.P(size=10, spacing=1.0)
                b.keep(el); b.restyle_runs(p)
                fmt(p, align=L, spacing=1.0, keep_next=True)
            elif kind == "code":
                b.keep(el); b.restyle_runs(p, 10, name=MONO)
                fmt(p, align=L, spacing=1.0)

    # --- 4. аттестационный лист и дневник --------------------------------------
    if only in (None, "forms", "forms2"):
        if only is None:
            b.section_break()
        if only != "forms2":
            attestation_sheet(b)
            diary_title(b)
            base_info(b)
            goals(b)
        safety(b)
        diary_table(b, diary_tbl)
        characteristic(b)
        conclusion_form(b)

    # --- параметры разделов ------------------------------------------------------
    def geometry(s, left, right, top, bottom):
        s.page_width, s.page_height = Mm(210), Mm(297)
        s.left_margin, s.right_margin = Mm(left), Mm(right)
        s.top_margin, s.bottom_margin = Mm(top), Mm(bottom)
        s.header_distance, s.footer_distance = Mm(10), Mm(11)

    def page_footer(s):
        s.footer.is_linked_to_previous = False
        ft = s.footer
        for p in list(ft.paragraphs)[1:]:
            p._p.getparent().remove(p._p)
        p = ft.paragraphs[0]
        for ch in list(p._p):
            if ch.tag != qn("w:pPr"):
                p._p.remove(ch)
        fmt(p, align=C, spacing=1.0)
        add_field(p, "PAGE", "2", size=12)

    def empty_footer(s):
        ref = s._sectPr.find(qn("w:footerReference"))
        if ref is not None:
            s._sectPr.remove(ref)
        s.footer.is_linked_to_previous = False
        for p in s.footer.paragraphs:
            for ch in list(p._p):
                if ch.tag != qn("w:pPr"):
                    p._p.remove(ch)

    secs = doc.sections
    if only is None:
        geometry(secs[0], 20, 14, 20, 20)
        geometry(secs[1], 25, 10, 15, 30)
        geometry(secs[2], 20, 14, 20, 20)
        # нижние колонтитулы: сначала основной (со сквозным номером), затем пустые
        ref = secs[0]._sectPr.find(qn("w:footerReference"))
        if ref is not None:
            secs[1]._sectPr.insert(0, ref)          # исходный колонтитул — основной части
        page_footer(secs[1])
        empty_footer(secs[2])
        for s in secs:
            for el in s._sectPr.findall(qn("w:titlePg")):
                s._sectPr.remove(el)
    elif only in ("title", "forms", "forms2"):
        geometry(secs[0], 20, 14, 20, 20)
    else:
        geometry(secs[0], 25, 10, 15, 30)

    doc.core_properties.author = ""
    doc.core_properties.title = "Отчет по производственной практике ПП.02.01"
    doc.save(dst)
    return [blk["name"] for blk in blocks], [(k, t, bm) for k, t, bm, _ in toc_entries]


if __name__ == "__main__":
    args = sys.argv[1:]
    pages = {}
    if "--pages" in args:
        i = args.index("--pages")
        pages = json.load(open(args[i + 1], encoding="utf-8"))
        del args[i:i + 2]
    build(args[0], args[1], pages)
    print("saved", args[1])
