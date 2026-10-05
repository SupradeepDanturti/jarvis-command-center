"""Fixed text-to-PDF renderer, loaded only by an enabled model worker."""
from html import escape
from io import BytesIO
from pathlib import Path
import re


def render_pdf(title, content):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    import reportlab

    fonts = Path('C:/Windows/Fonts')
    regular, bold = fonts / 'arial.ttf', fonts / 'arialbd.ttf'
    if not regular.is_file() or not bold.is_file():
        fonts = Path(reportlab.__file__).parent / 'fonts'
        regular, bold = fonts / 'Vera.ttf', fonts / 'VeraBd.ttf'
    pdfmetrics.registerFont(TTFont('Artifact', str(regular)))
    pdfmetrics.registerFont(TTFont('ArtifactBold', str(bold)))
    content = content.replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '-')
    title = title.replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '-')
    supported = pdfmetrics.getFont('Artifact').face.charWidths
    if any(ord(c) not in supported for c in title + content if not c.isspace()):
        raise ValueError('The PDF font cannot render one of the requested characters.')
    styles = {
        'body': ParagraphStyle('body', fontName='Artifact', fontSize=10.5, leading=16, spaceAfter=10, textColor=colors.HexColor('#263449')),
        'title': ParagraphStyle('title', fontName='ArtifactBold', fontSize=24, leading=30, spaceAfter=22, textColor=colors.HexColor('#123747'), keepWithNext=True),
        'heading': ParagraphStyle('heading', fontName='ArtifactBold', fontSize=15, leading=21, spaceBefore=14, spaceAfter=9, textColor=colors.HexColor('#123747'), keepWithNext=True),
        'cell': ParagraphStyle('cell', fontName='Artifact', fontSize=9, leading=13, textColor=colors.HexColor('#263449')),
    }
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=48, leftMargin=48, topMargin=48, bottomMargin=48,
                                 title=title, author='Jarvis Parallax')
    story = [Paragraph(escape(title), styles['title'])]
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            story.append(Spacer(1, 6))
        elif line.startswith('|') and line.endswith('|'):
            rows = []
            while index < len(lines) and lines[index].strip().startswith('|') and lines[index].strip().endswith('|'):
                cells = [cell.strip() for cell in lines[index].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', cell) for cell in cells):
                    rows.append(cells)
                index += 1
            if rows:
                width = max(map(len, rows))
                if width > 8 or len(rows) > 100:
                    raise ValueError('PDF table is too large.')
                data = [[Paragraph(escape(cell), styles['cell']) for cell in row + ['']*(width-len(row))] for row in rows]
                table = Table(data, colWidths=[document.width/width]*width, repeatRows=1, hAlign='LEFT')
                table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6eef1')),
                                          ('VALIGN',(0,0),(-1,-1),'TOP'), ('BOX',(0,0),(-1,-1),.4,colors.HexColor('#c8d4db')),
                                          ('INNERGRID',(0,0),(-1,-1),.3,colors.HexColor('#dce3e7')),
                                          ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
                                          ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
                story.extend([table, Spacer(1, 12)])
            continue
        elif line.startswith('#'):
            story.append(Paragraph(escape(line.lstrip('#').strip()), styles['heading']))
        else:
            bullet = line.startswith('- ')
            story.append(Paragraph(escape(line[2:] if bullet else line), styles['body'], bulletText='-' if bullet else None))
        index += 1

    def page(canvas, doc):
        if doc.page > 30:
            raise ValueError('PDF exceeds thirty pages.')
        canvas.setStrokeColor(colors.HexColor('#dce3e7'))
        canvas.line(48, 35, A4[0]-48, 35)
        canvas.setFont('Artifact', 8)
        canvas.setFillColor(colors.HexColor('#65758a'))
        canvas.drawString(48, 22, 'Jarvis Parallax')
        canvas.drawRightString(A4[0]-48, 22, str(doc.page))

    document.build(story, onFirstPage=page, onLaterPages=page)
    data = output.getvalue()
    if len(data) > 256000:
        raise ValueError('PDF exceeds the private artifact limit.')
    return data
