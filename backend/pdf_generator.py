import fitz
from markdown_it import MarkdownIt

def generate_pdf(markdown_text: str) -> bytes:
    if not markdown_text or not markdown_text.strip():
        markdown_text = "No report content available."

    md = MarkdownIt()
    html_body = md.render(markdown_text)

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<style>
body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11pt; line-height: 1.6; color: #1e293b; }}
h1 {{ font-size: 18pt; color: #2563eb; margin-top: 20pt; margin-bottom: 10pt; }}
h2 {{ font-size: 14pt; color: #1d4ed8; margin-top: 16pt; margin-bottom: 8pt; }}
h3 {{ font-size: 12pt; color: #334155; margin-top: 12pt; margin-bottom: 6pt; }}
p {{ margin: 6pt 0; }}
ul {{ margin: 6pt 0; padding-left: 20pt; }}
li {{ margin: 3pt 0; }}
strong {{ color: #0f172a; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

    doc = fitz.open()
    story = fitz.Story(html_content)
    rect = fitz.Rect(50, 50, 550, 750)

    while True:
        page = doc.new_page()
        story.place(rect)
        story.draw()
        if story.eof():
            break

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
