"""A small .docx writer: headings, paragraphs with **bold**, bulleted and numbered lists, and tables.

python-docx isn't in every sandbox, and a lesson plan needs little of Word, so this writes the XML parts
itself. The file opens in Word, Google Docs, and Pages, where the teacher can edit it like any document.
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
FONT = "Arial"


_CONTROL = re.compile(r"[\x00-\x08\x0c\x0e-\x1f]")  # not allowed in XML; \v (a pasted soft break) becomes a break


def _runs(text: str, bold: bool = False, italic: bool = False, color: str | None = None, size: float | None = None,
          markup: bool = True) -> str:
    """Runs for text with **bold** marked; markup=False for worksheet text, where ** is Python's power."""
    text = _CONTROL.sub("", text.replace("\v", "\n").replace("\r", ""))
    out = []
    for k, piece in enumerate(re.split(r"\*\*", text) if markup else [text]):
        if not piece:
            continue
        props = []
        if bold or (markup and k % 2 == 1):
            props.append("<w:b/>")
        if italic:
            props.append("<w:i/>")
        if color:
            props.append(f'<w:color w:val="{color}"/>')
        if size:
            props.append(f'<w:sz w:val="{int(size * 2)}"/>')
        rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
        lines = piece.split("\n")
        body = '<w:br/>'.join(f'<w:t xml:space="preserve">{escape(line)}</w:t>' for line in lines)
        out.append(f"<w:r>{rpr}{body}</w:r>")
    return "".join(out)


class Doc:
    def __init__(self, accent: str = "2453A6", tint: str = "E9EEF6"):
        self.accent, self.tint = accent, tint
        self.body: list[str] = []
        self.numbered_lists = 0

    def title(self, text: str) -> None:
        self.body.append(f'<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr>{_runs(text)}</w:p>')

    def heading(self, text: str, level: int = 1) -> None:
        self.body.append(f'<w:p><w:pPr><w:pStyle w:val="Heading{level}"/></w:pPr>{_runs(text)}</w:p>')

    def para(self, text: str, bold: bool = False, italic: bool = False, color: str | None = None,
             size: float | None = None, after: int | None = None, markup: bool = True) -> None:
        spacing = f'<w:pPr><w:spacing w:after="{after}"/></w:pPr>' if after is not None else ""
        self.body.append(f"<w:p>{spacing}{_runs(text, bold, italic, color, size, markup)}</w:p>")

    def labeled(self, label: str, text: str) -> None:
        """"Label: text", the label bold and the text as written (worksheet text: no markup)."""
        self.body.append(f"<w:p>{_runs(label + ': ', bold=True, markup=False)}{_runs(text, markup=False)}</w:p>")

    def bullets(self, items: list[str], markup: bool = True) -> None:
        for item in items:
            self.body.append('<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/>'
                             f'<w:numId w:val="1"/></w:numPr></w:pPr>{_runs(item, markup=markup)}</w:p>')

    def numbered(self, items: list[str]) -> None:
        self.numbered_lists += 1
        num = self.numbered_lists + 1  # numId 1 is the bullets
        for item in items:
            self.body.append('<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/>'
                             f'<w:numId w:val="{num}"/></w:numPr></w:pPr>{_runs(item)}</w:p>')

    def table(self, rows: list[list[str]], widths: list[float], header: bool = True) -> None:
        """widths in inches; the first row is the header."""
        twips = [int(w * 1440) for w in widths]
        grid = "".join(f'<w:gridCol w:w="{t}"/>' for t in twips)
        borders = "".join(f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="B8BEC6"/>'
                          for side in ("top", "left", "bottom", "right", "insideH", "insideV"))
        out = ['<w:tbl><w:tblPr><w:tblStyle w:val="LessonTable"/><w:tblW w:w="0" w:type="auto"/>'
               f'<w:tblBorders>{borders}</w:tblBorders>'
               '<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
               '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
               '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" '
               f'w:noHBand="0" w:noVBand="1"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>']
        for r, row in enumerate(rows):
            head = header and r == 0
            trpr = "<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>" if head else "<w:trPr><w:cantSplit/></w:trPr>"
            cells = []
            for text, t in zip(row, twips):
                shade = f'<w:shd w:val="clear" w:color="auto" w:fill="{self.tint}"/>' if head else ""
                paras = "".join(f"<w:p><w:pPr><w:spacing w:after=\"40\"/></w:pPr>{_runs(line, bold=head)}</w:p>"
                                for line in (text or "").split("\n\n"))
                cells.append(f'<w:tc><w:tcPr><w:tcW w:w="{t}" w:type="dxa"/>{shade}</w:tcPr>{paras}</w:tc>')
            out.append(f"<w:tr>{trpr}{''.join(cells)}</w:tr>")
        out.append("</w:tbl>")
        self.body.append("".join(out))
        self.body.append('<w:p><w:pPr><w:spacing w:after="0"/></w:pPr></w:p>')

    def page_break(self) -> None:
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def save(self, path: Path, title: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_W}><w:body>'
                    + "".join(self.body)
                    + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1080" w:right="1080" '
                      'w:bottom="1080" w:left="1080" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
                      "</w:body></w:document>")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", _CONTENT_TYPES)
            z.writestr("_rels/.rels", _RELS)
            z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
            z.writestr("word/document.xml", document)
            z.writestr("word/styles.xml", _styles(self.accent, self.tint))
            z.writestr("word/numbering.xml", _numbering(self.numbered_lists))
            z.writestr("docProps/core.xml", _core(title, now))
            z.writestr("docProps/app.xml", _APP)


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""

_APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Paper Loop</Application></Properties>"""


def _core(title: str, now: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{escape(title)}</dc:title><dc:creator>Paper Loop</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>')


def _styles(accent: str, tint: str) -> str:
    def para_style(sid, name, size, bold=False, color=None, before=0, after=120, extra="", based="Normal"):
        rpr = f'<w:sz w:val="{size * 2}"/>' + ("<w:b/>" if bold else "") + (f'<w:color w:val="{color}"/>' if color else "")
        return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="{based}"/>'
                f'<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="{before}" '
                f'w:after="{after}"/>{extra}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {_W}>'
            f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:eastAsia="{FONT}" '
            f'w:cs="{FONT}"/><w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="en-US"/></w:rPr></w:rPrDefault>'
            '<w:pPrDefault><w:pPr><w:spacing w:after="100" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
            '</w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/>'
            f'<w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:eastAsia="{FONT}" w:cs="{FONT}"/>'
            '<w:sz w:val="21"/></w:rPr></w:style>'
            + para_style("Title", "Title", 24, True, accent, 0, 60)
            + para_style("Heading1", "heading 1", 14, True, accent, 280, 100, '<w:outlineLvl w:val="0"/>')
            + para_style("Heading2", "heading 2", 12, True, None, 200, 80, '<w:outlineLvl w:val="1"/>')
            + '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/>'
              '<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="60"/><w:ind w:left="360"/>'
              '</w:pPr></w:style>'
            + '<w:style w:type="table" w:styleId="LessonTable"><w:name w:val="Lesson Table"/><w:tblPr>'
              '<w:tblBorders>'
              + "".join(f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="B8BEC6"/>'
                        for side in ("top", "left", "bottom", "right", "insideH", "insideV"))
              + '</w:tblBorders><w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
                '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>'
            + "</w:styles>")


def _numbering(numbered_lists: int) -> str:
    bullet = ('<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/><w:lvl w:ilvl="0">'
              '<w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/>'
              '<w:pPr><w:ind w:left="360" w:hanging="260"/></w:pPr><w:rPr><w:rFonts w:ascii="Arial" '
              'w:hAnsi="Arial"/></w:rPr></w:lvl></w:abstractNum>')
    decimal = ('<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="singleLevel"/><w:lvl w:ilvl="0">'
               '<w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:lvlJc w:val="left"/>'
               '<w:pPr><w:ind w:left="360" w:hanging="300"/></w:pPr></w:lvl></w:abstractNum>')
    nums = '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
    for k in range(numbered_lists):
        nums += (f'<w:num w:numId="{k + 2}"><w:abstractNumId w:val="1"/><w:lvlOverride w:ilvl="0">'
                 '<w:startOverride w:val="1"/></w:lvlOverride></w:num>')
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {_W}>{bullet}{decimal}{nums}</w:numbering>'
