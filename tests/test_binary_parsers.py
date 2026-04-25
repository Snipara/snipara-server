"""Tests for binary parser foundations."""

from __future__ import annotations

import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from src.rlm_engine import RLMEngine
from src.services.binary_parsers import (
    DocxDocumentParser,
    PdfDocumentParser,
    PptxDocumentParser,
    SvgDocumentParser,
    VsdxDocumentParser,
    build_svg_context,
    enrich_svg_content,
)
from src.services.indexer import DocumentIndexer

SVG_SAMPLE = """
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <title>Architecture Overview</title>
  <desc>Shows the API, worker, and database tiers.</desc>
  <text x="10" y="20">API</text>
  <text x="10" y="50">Worker</text>
  <text x="10" y="80">Database</text>
</svg>
""".strip()


def _make_pdf_bytes(text: str) -> bytes:
    body_stream = f"BT\n/F1 18 Tf\n72 96 Td\n({text}) Tj\nET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(body_stream.encode('utf-8'))} >>\nstream\n{body_stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    parts = ["%PDF-1.4\n"]
    offsets = [0]
    current = len(parts[0].encode("utf-8"))
    for index, obj in enumerate(objects, start=1):
        offsets.append(current)
        blob = f"{index} 0 obj\n{obj}\nendobj\n"
        parts.append(blob)
        current += len(blob.encode("utf-8"))

    xref_offset = current
    xref = ["xref\n0 6\n", "0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n")
    trailer = "trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n"
    eof = f"{xref_offset}\n%%EOF"
    return "".join(parts + xref + [trailer, eof]).encode("utf-8")


def _make_docx_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>Binary Guide</w:t></w:r>
    </w:p>
    <w:p><w:r><w:t>Keep project context clean.</w:t></w:r></w:p>
    <w:p>
      <w:pPr><w:numPr/></w:pPr>
      <w:r><w:t>Prefer explicit parser support.</w:t></w:r>
    </w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Owner</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Snipara</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>""",
        )
        archive.writestr(
            "docProps/core.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Binary Playbook</dc:title>
  <dc:creator>Ana</dc:creator>
</cp:coreProperties>""",
        )
    return buffer.getvalue()


def _make_pptx_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/notesSlides/notesSlide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>""",
        )
        archive.writestr(
            "ppt/slides/slide1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Launch Review</a:t></a:r></a:p>
          <a:p><a:r><a:t>Token budget by team</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>""",
        )
        archive.writestr(
            "ppt/notesSlides/notesSlide1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Note for presenters</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:notes>""",
        )
        archive.writestr(
            "docProps/core.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Quarterly Deck</dc:title>
  <dc:creator>Ana</dc:creator>
</cp:coreProperties>""",
        )
    return buffer.getvalue()


def _make_vsdx_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "docProps/core.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Campus Network</dc:title>
  <dc:creator>Ana</dc:creator>
</cp:coreProperties>""",
        )
        archive.writestr(
            "visio/pages/pages.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main">
  <Page ID="0" Name="Network Topology" NameU="Page-1"/>
</Pages>""",
        )
        archive.writestr(
            "visio/pages/page1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main">
  <Shapes>
    <Shape ID="1" NameU="Firewall" Name="Firewall" Type="Shape">
      <Cell N="PinX" V="1.0"/>
      <Cell N="PinY" V="2.0"/>
      <Text>Firewall</Text>
    </Shape>
    <Shape ID="2" NameU="Core Switch" Name="Core Switch" Type="Shape">
      <Cell N="PinX" V="4.0"/>
      <Cell N="PinY" V="2.0"/>
      <Text>Core Switch</Text>
    </Shape>
    <Shape ID="3" NameU="Dynamic connector" Name="Firewall uplink" Type="Shape">
      <Cell N="BeginX" V="1.5"/>
      <Cell N="EndX" V="3.5"/>
      <Text>Firewall uplink</Text>
    </Shape>
  </Shapes>
  <Connects>
    <Connect FromSheet="3" FromCell="BeginX" ToSheet="1" ToCell="Connections.X1"/>
    <Connect FromSheet="3" FromCell="EndX" ToSheet="2" ToCell="Connections.X1"/>
  </Connects>
</PageContents>""",
        )
    return buffer.getvalue()


def _base64_payload(raw: bytes) -> str:
    return f"base64:{base64.b64encode(raw).decode('ascii')}"


PDF_SAMPLE = _base64_payload(_make_pdf_bytes("Snipara Binary PDF"))
DOCX_SAMPLE = _base64_payload(_make_docx_bytes())
PPTX_SAMPLE = _base64_payload(_make_pptx_bytes())
VSDX_SAMPLE = _base64_payload(_make_vsdx_bytes())


def test_svg_parser_emits_markdown_like_sections():
    parser = SvgDocumentParser()

    result = parser.parse(content=SVG_SAMPLE, path="docs/architecture.svg")

    assert result.parser_name == "svg"
    assert result.metadata["viewBox"] == "0 0 100 100"
    assert result.metadata["schemaVersion"] == "snipara.svg-context.v1"
    assert result.metadata["bundleId"].startswith("svgctx_")
    assert len(result.metadata["sourceHash"]) == 64
    assert result.metadata["qualityStatus"] == "good"
    assert "# Architecture Overview" in result.content
    assert "Bundle ID: `svgctx_" in result.content
    assert "## Context Quality" in result.content
    assert "## Titles" in result.content
    assert "Architecture Overview" in result.content
    assert "## Text Labels" in result.content
    assert "Database" in result.content
    assert "## Diagram Elements" in result.content


def test_svg_context_builder_emits_manifest_and_enriched_svg():
    bundle = build_svg_context(content=SVG_SAMPLE, path="docs/architecture.svg")

    assert bundle.manifest["schemaVersion"] == "snipara.svg-context.v1"
    assert bundle.bundle_id == bundle.manifest["bundleId"]
    assert bundle.bundle_id.startswith("svgctx_")
    assert bundle.source_hash == bundle.manifest["sourceHash"]
    assert bundle.manifest["title"] == "Architecture Overview"
    assert bundle.manifest["content"]["textLabels"] == ["API", "Worker", "Database"]
    assert bundle.manifest["metadata"]["viewBox"] == "0 0 100 100"
    assert bundle.manifest["elements"][0]["label"] == "API"
    assert bundle.manifest["quality"]["status"] == "good"
    assert bundle.manifest["quality"]["score"] >= 0.75

    enriched = enrich_svg_content(content=SVG_SAMPLE, path="docs/architecture.svg")

    assert 'data-snipara-context="snipara.svg-context.v1"' in enriched
    assert f'data-snipara-bundle-id="{bundle.bundle_id}"' in enriched
    assert f'data-snipara-source-sha256="{bundle.source_hash}"' in enriched
    assert "<title>Architecture Overview</title>" in enriched


def test_svg_context_quality_flags_sparse_diagrams():
    sparse_svg = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L10 10"/></svg>'

    bundle = build_svg_context(content=sparse_svg, path="docs/sparse.svg")

    assert bundle.manifest["quality"]["status"] == "poor"
    assert bundle.manifest["quality"]["score"] < 0.55
    assert any("quality is low" in warning for warning in bundle.warnings)
    assert "Add a root <title>" in bundle.markdown


def test_pdf_parser_extracts_page_text():
    parser = PdfDocumentParser()

    result = parser.parse(content=PDF_SAMPLE, path="docs/manual.pdf")

    assert result.parser_name == "pdf"
    assert result.metadata["pageCount"] == 1
    assert "# PDF Document" in result.content
    assert "## Page 1" in result.content
    assert "Snipara Binary PDF" in result.content


def test_docx_parser_extracts_structure():
    parser = DocxDocumentParser()

    result = parser.parse(content=DOCX_SAMPLE, path="docs/playbook.docx")

    assert result.parser_name == "docx"
    assert result.metadata["title"] == "Binary Playbook"
    assert "# DOCX Document" in result.content
    assert "## Extracted Content" in result.content
    assert "# Binary Guide" in result.content
    assert "- Prefer explicit parser support." in result.content
    assert "| Owner | Snipara |" in result.content


def test_pptx_parser_extracts_slide_text_and_notes():
    parser = PptxDocumentParser()

    result = parser.parse(content=PPTX_SAMPLE, path="docs/review.pptx")

    assert result.parser_name == "pptx"
    assert result.metadata["slideCount"] == 1
    assert result.metadata["title"] == "Quarterly Deck"
    assert "# PPTX Deck" in result.content
    assert "## Slide 1: Launch Review" in result.content
    assert "- Token budget by team" in result.content
    assert "### Speaker Notes" in result.content
    assert "- Note for presenters" in result.content


def test_vsdx_parser_extracts_pages_shapes_and_connectors():
    parser = VsdxDocumentParser()

    result = parser.parse(content=VSDX_SAMPLE, path="diagrams/network.vsdx")

    assert result.parser_name == "vsdx"
    assert result.metadata["schemaVersion"] == "snipara.vsdx-context.v1"
    assert result.metadata["assetClass"] == "DIAGRAM"
    assert result.metadata["parser"] == {"name": "vsdx", "version": 1}
    assert result.metadata["pageCount"] == 1
    assert result.metadata["shapeCount"] == 3
    assert result.metadata["connectorCount"] == 1
    assert result.metadata["qualityStatus"] == "good"
    assert "# Campus Network" in result.content
    assert "### Page 1: Network Topology" in result.content
    assert "- Firewall (id=1" in result.content
    assert "- Core Switch (id=2" in result.content
    assert "Firewall -> Core Switch" in result.content


def test_document_indexer_accepts_supported_binary_formats():
    indexer = DocumentIndexer(AsyncMock())

    supported_docs = [
        SimpleNamespace(kind="BINARY", format="svg", path="docs/architecture.svg", content=SVG_SAMPLE),
        SimpleNamespace(kind="BINARY", format="pdf", path="docs/spec.pdf", content=PDF_SAMPLE),
        SimpleNamespace(kind="BINARY", format="docx", path="docs/spec.docx", content=DOCX_SAMPLE),
        SimpleNamespace(kind="BINARY", format="pptx", path="docs/spec.pptx", content=PPTX_SAMPLE),
        SimpleNamespace(kind="BINARY", format="vsdx", path="docs/network.vsdx", content=VSDX_SAMPLE),
    ]
    unsupported_doc = SimpleNamespace(
        kind="BINARY",
        format="png",
        path="docs/diagram.png",
        content="base64:AAAA",
    )

    for document in supported_docs:
        assert indexer._is_chunkable_document(document) is True
        assert indexer._get_indexable_content(document)

    assert indexer._is_chunkable_document(unsupported_doc) is False
    assert indexer._get_indexable_content(unsupported_doc) is None


@pytest.mark.asyncio
async def test_load_documents_indexes_supported_binary_docs(monkeypatch):
    fake_db = SimpleNamespace(
        project=SimpleNamespace(find_unique=AsyncMock(return_value=SimpleNamespace(slug="snipara"))),
        document=SimpleNamespace(
            find_many=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        path="docs/architecture.svg",
                        content=SVG_SAMPLE,
                        kind="BINARY",
                        format="svg",
                    ),
                    SimpleNamespace(
                        path="docs/playbook.docx",
                        content=DOCX_SAMPLE,
                        kind="BINARY",
                        format="docx",
                    ),
                    SimpleNamespace(
                        path="docs/review.pptx",
                        content=PPTX_SAMPLE,
                        kind="BINARY",
                        format="pptx",
                    ),
                    SimpleNamespace(
                        path="docs/network.vsdx",
                        content=VSDX_SAMPLE,
                        kind="BINARY",
                        format="vsdx",
                    ),
                ]
            )
        ),
    )
    monkeypatch.setattr("src.rlm_engine.get_db", AsyncMock(return_value=fake_db))

    engine = RLMEngine("proj-1")
    await engine.load_documents()

    assert engine.index is not None
    assert engine.index.files == [
        "docs/architecture.svg",
        "docs/playbook.docx",
        "docs/review.pptx",
        "docs/network.vsdx",
    ]
    joined = "\n".join(section.content for section in engine.index.sections)
    assert "Architecture Overview" in joined
    assert "Schema version: `snipara.svg-context.v1`" in joined
    assert "DOCX Document" in joined
    assert "PPTX Deck" in joined
    assert "Campus Network" in joined
    assert "Firewall -> Core Switch" in joined
    assert "Binary Guide" in joined
    assert "Launch Review" in joined
