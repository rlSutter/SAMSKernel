#!/usr/bin/env python3
"""guide_pdf.py - build docs/PROGRAMMERS-GUIDE.pdf from docs/PROGRAMMERS-GUIDE.md.

    python3 tools/guide_pdf.py

Needs pandoc, wkhtmltopdf, and the Python packages pypdf and reportlab (page
numbers, bookmarks, document properties are added afterwards: the unpatched
wkhtmltopdf has neither footers nor an outline).  Links to the other documents
become plain text, since the PDF travels alone.
"""
import io, os, re, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = '''
body { font-family: "DejaVu Serif", serif; font-size: 10.5pt; line-height: 1.42; color: #1a1a1a; }
h1 { font-family: "DejaVu Sans", sans-serif; font-size: 20pt; margin: 1.4em 0 .5em; padding-bottom: .15em; border-bottom: 2px solid #23498a; page-break-after: avoid; }
h1.title { border: none; font-size: 30pt; margin-top: 3.2in; }
h2 { font-family: "DejaVu Sans", sans-serif; font-size: 14pt; margin: 1.4em 0 .4em; color: #23498a; page-break-after: avoid; }
h3 { font-family: "DejaVu Sans", sans-serif; font-size: 11.5pt; margin: 1.2em 0 .3em; page-break-after: avoid; }
p.subtitle { font-family: "DejaVu Sans", sans-serif; font-size: 14pt; color: #555; margin: 0 0 .3in; }
p.meta { font-family: "DejaVu Sans", sans-serif; font-size: 10pt; color: #555; }
code, pre { font-family: "DejaVu Sans Mono", monospace; font-size: 8.6pt; }
code { background: #f0f2f6; padding: 0 2px; border-radius: 2px; }
pre { background: #f5f6f9; border: 1px solid #d5d9e2; border-left: 3px solid #23498a; padding: 7px 9px; white-space: pre-wrap; word-wrap: break-word; page-break-inside: avoid; line-height: 1.3; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: .7em 0; font-size: 9.4pt; }
tr { page-break-inside: avoid; }
th { background: #23498a; color: #fff; text-align: left; font-family: "DejaVu Sans", sans-serif; font-size: 9pt; }
th, td { border: 1px solid #c8cdd8; padding: 4px 6px; vertical-align: top; }
tr:nth-child(even) td { background: #f7f8fb; }
td code { font-size: 8.4pt; white-space: nowrap; }
nav#TOC { page-break-after: always; }
nav#TOC ul { list-style: none; padding-left: 1.2em; }
nav#TOC > ul { padding-left: 0; }
nav#TOC a { color: #1a1a1a; text-decoration: none; }
nav#TOC > ul > li { margin-top: .5em; font-family: "DejaVu Sans", sans-serif; font-weight: bold; }
nav#TOC > ul > li > ul > li { font-weight: normal; font-family: "DejaVu Serif", serif; font-size: 9.5pt; }
'''
HEAD = '''<h1 class="title">Lantern Kernel</h1>
<p class="subtitle">The programmer's guide: writing TI-99/4A applications in assembly</p>
<p class="meta">Version %s &middot; %s<br>For a TI-99/4A with an F18A video card and a SAMS memory card<br>MIT License, &copy; 2026 Rebecca Sutter</p>
'''

def main():
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    ver = open(os.path.join(ROOT, 'VERSION')).read().strip()
    date = '28 October 2026'
    md = open(os.path.join(ROOT, 'docs', 'PROGRAMMERS-GUIDE.md'), encoding='utf-8').read()
    md = re.sub(r'\[([^\]]+)\]\((?:[A-Z\-]+\.md)\)', r'\1', md)
    md = md.replace("# Lantern Kernel: the programmer's guide", '', 1)
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, 'g.md'), 'w', encoding='utf-8').write(md)
    open(os.path.join(tmp, 's.css'), 'w').write(CSS)
    open(os.path.join(tmp, 'h.html'), 'w').write(HEAD % (ver, date))
    subprocess.check_call(['pandoc', 'g.md', '-f', 'gfm', '-t', 'html5', '-s', '--toc', '--toc-depth=2', '--metadata',
                           "pagetitle=Lantern Kernel: the programmer's guide", '-c', 's.css', '-B', 'h.html', '-o', 'g.html'], cwd=tmp)
    h = open(os.path.join(tmp, 'g.html'), encoding='utf-8').read()
    h = re.sub(r'<header id="title-block-header">.*?</header>', '', h, flags=re.S)
    h = h.replace('<nav id="TOC" role="doc-toc">', '<nav id="TOC" role="doc-toc"><h1 style="page-break-before:always;margin-top:0">Contents</h1>')
    open(os.path.join(tmp, 'g.html'), 'w', encoding='utf-8').write(h)
    subprocess.call(['wkhtmltopdf', '--quiet', '--enable-local-file-access', '--disable-smart-shrinking', '--zoom', '1.55',
                     '--page-size', 'Letter', '--margin-top', '18mm', '--margin-bottom', '20mm', '--margin-left', '18mm',
                     '--margin-right', '18mm', 'g.html', 'raw.pdf'], cwd=tmp, stderr=subprocess.DEVNULL)
    src = PdfReader(os.path.join(tmp, 'raw.pdf'))
    texts = [re.sub(r'\s+', ' ', p.extract_text() or '') for p in src.pages]
    w = PdfWriter()
    for i, p in enumerate(src.pages):
        if i:
            buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=letter)
            c.setFont('Helvetica', 8); c.setFillGray(0.4)
            c.drawCentredString(306, 28, "Lantern Kernel programmer's guide  -  %d" % (i + 1)); c.save(); buf.seek(0)
            p.merge_page(PdfReader(buf).pages[0])
        w.add_page(p)
    w.add_outline_item('Title', 0); w.add_outline_item('Contents', 1)
    cur, parent, miss = 2, None, 0
    for line in md.split('\n'):
        m = re.match(r'^(#{2,3}) (.+?)\s*$', line)
        if not m: continue
        key = re.sub(r'\s+', ' ', m.group(2).replace('`', ''))
        pg = next((i for i in range(cur, len(texts)) if key in texts[i]), None)
        if pg is None: miss += 1; continue
        cur = pg
        if len(m.group(1)) == 2: parent = w.add_outline_item(m.group(2).replace('`', ''), pg)
        else: w.add_outline_item(m.group(2).replace('`', ''), pg, parent=parent)
    w.add_metadata({'/Title': "Lantern Kernel: the programmer's guide", '/Author': 'Rebecca Sutter',
                    '/Subject': 'Writing TI-99/4A applications in TMS9900 assembly on the Lantern Kernel, version ' + ver})
    w.page_mode = '/UseOutlines'
    out = os.path.join(ROOT, 'docs', 'PROGRAMMERS-GUIDE.pdf')
    w.write(out)
    print('wrote %s: %d pages, %d headings not found for bookmarks' % (out, len(src.pages), miss))

if __name__ == '__main__':
    main()
