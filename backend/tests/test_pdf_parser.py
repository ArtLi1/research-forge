import pymupdf

from app.parsers.pdf import PdfParser


def test_pdf_parser_reads_text_pdf(tmp_path) -> None:
    path = tmp_path / "paper.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "System Model")
    page.insert_text((72, 100), "A UAV provides edge computing services.")
    document.save(path)
    document.close()

    parsed = PdfParser().parse(path)
    assert parsed.blocks
    assert any("UAV" in block.content for block in parsed.blocks)
