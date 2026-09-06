"""Local document ingestion and structure-aware chunking.

The stage-2 pipeline receives bytes from an already-authorized operator.  It
never dereferences ``source_uri`` and never performs network I/O.  Raw bytes
are parsed in memory, while the database stores only provenance, hashes,
status, and immutable chunks.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import re
import zipfile
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from serviceops.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    new_id,
    utcnow,
)
from serviceops.shared.errors import ConflictError, DomainError, NotFoundError

PARSER_VERSION = "document-parsers-v1"
CHUNKING_VERSION = "structure-chunks-v1"
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_CHUNK_CHARS = 1200
ALLOWED_SOURCE_SCHEMES = frozenset({"file", "fixture", "kb", "upload"})
SUPPORTED_EXTENSIONS = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
}


class KnowledgePipelineError(DomainError):
    """A safe, user-facing ingestion failure without document contents."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(code, message, status_code)


@dataclass(frozen=True)
class ParsedBlock:
    text: str
    kind: str
    title_path: tuple[str, ...]
    page_number: int | None
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    media_type: str
    content_hash: str
    byte_size: int
    parser_version: str
    page_count: int
    blocks: tuple[ParsedBlock, ...]


@dataclass(frozen=True)
class ChunkDraft:
    index: int
    content: str
    content_hash: str
    block_type: str
    title_path: tuple[str, ...]
    page_number: int | None
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class IngestResult:
    document: KnowledgeDocument
    duplicate: bool
    retried: bool


_HEADING_PATTERN = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_CLAUSE_PATTERN = re.compile(
    r"^\s*(?:第\s*[一二三四五六七八九十百\d.]+\s*[章节条]|\d+(?:\.\d+)*[、.)])\s*.+"
)
_LIST_PATTERN = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)、]\s+).+")
_TABLE_PATTERN = re.compile(r"^\s*\|.+\|\s*$")


def _safe_source_uri(source_uri: str) -> tuple[str, str]:
    value = source_uri.strip()
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if not value or not scheme or scheme not in ALLOWED_SOURCE_SCHEMES:
        raise KnowledgePipelineError(
            "KNOWLEDGE_EXTERNAL_SOURCE_FORBIDDEN",
            "来源 URI 只能指向受控本地来源，系统不会访问外部地址",
        )
    if not parsed.netloc and not parsed.path:
        raise KnowledgePipelineError("KNOWLEDGE_SOURCE_INVALID", "来源 URI 缺少资源标识")
    return value, scheme


def _filename_metadata(filename: str) -> tuple[str, str]:
    safe_name = Path(filename.strip()).name
    extension = Path(safe_name).suffix.lower()
    if not safe_name or extension not in SUPPORTED_EXTENSIONS:
        raise KnowledgePipelineError(
            "DOCUMENT_TYPE_UNSUPPORTED",
            "只支持 Markdown、TXT、PDF 和 DOCX 文件",
        )
    return safe_name, SUPPORTED_EXTENSIONS[extension]


def _line_records(text: str) -> list[tuple[str, int, int]]:
    records: list[tuple[str, int, int]] = []
    offset = 0
    for raw in text.splitlines(keepends=True):
        end = offset + len(raw)
        records.append((raw.rstrip("\r\n"), offset, end))
        offset = end
    if text and (not records or offset < len(text)):
        records.append((text[offset:], offset, len(text)))
    return records


def _block_text(lines: list[str]) -> str:
    return "\n".join(line.strip() for line in lines).strip()


def _parse_text_blocks(
    text: str,
    *,
    page_number: int | None = None,
    offset_base: int = 0,
) -> tuple[ParsedBlock, ...]:
    records = _line_records(text)
    blocks: list[ParsedBlock] = []
    title_stack: list[tuple[int, str]] = []
    current_kind: str | None = None
    current_lines: list[str] = []
    current_start = 0
    current_end = 0
    current_title_path: tuple[str, ...] = ()

    def flush() -> None:
        nonlocal current_kind, current_lines, current_start, current_end
        if current_kind is not None:
            value = _block_text(current_lines)
            if value:
                blocks.append(
                    ParsedBlock(
                        text=value,
                        kind=current_kind,
                        title_path=current_title_path,
                        page_number=page_number,
                        start_offset=offset_base + current_start,
                        end_offset=offset_base + current_end,
                    )
                )
        current_kind = None
        current_lines = []

    for line, start, end in records:
        stripped = line.strip()
        if not stripped:
            flush()
            continue

        heading = _HEADING_PATTERN.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            heading_text = heading.group(2).strip()
            title_stack = [item for item in title_stack if item[0] < level]
            title_stack.append((level, heading_text))
            title_path = tuple(item[1] for item in title_stack)
            blocks.append(
                ParsedBlock(
                    text=heading_text,
                    kind="heading",
                    title_path=title_path,
                    page_number=page_number,
                    start_offset=offset_base + start,
                    end_offset=offset_base + end,
                )
            )
            continue

        kind = "paragraph"
        title_path = tuple(item[1] for item in title_stack)
        if _TABLE_PATTERN.match(line):
            kind = "table"
        elif _LIST_PATTERN.match(line):
            kind = "list"
        elif _CLAUSE_PATTERN.match(line):
            kind = "clause"
            title_path = (*title_path, stripped)

        if current_kind != kind:
            flush()
            current_kind = kind
            current_start = start
            current_title_path = title_path
        current_lines.append(line)
        current_end = end
    flush()
    return tuple(blocks)


def _parse_plain_text(text: str, *, filename: str, media_type: str, content_hash: str, size: int) -> ParsedDocument:
    blocks = _parse_text_blocks(text)
    if not blocks:
        raise KnowledgePipelineError("DOCUMENT_EMPTY", "文档没有可用的非空文本")
    return ParsedDocument(
        filename=filename,
        media_type=media_type,
        content_hash=content_hash,
        byte_size=size,
        parser_version=PARSER_VERSION,
        page_count=1,
        blocks=blocks,
    )


def _pdf_unescape(value: str) -> str:
    value = re.sub(
        r"\\([0-7]{1,3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )
    return (
        value.replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
        .replace(r"\(", "(")
        .replace(r"\)", ")")
        .replace(r"\\", "\\")
    )


def _fallback_pdf_text(data: bytes) -> str:
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data:
        raise KnowledgePipelineError("DOCUMENT_PARSE_FAILED", "PDF 文件结构无效")
    if b"/Encrypt" in data:
        raise KnowledgePipelineError("DOCUMENT_ENCRYPTED", "加密 PDF 不允许进入知识流水线")
    text_parts: list[str] = []
    for stream_match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        payload = stream_match.group(1)
        object_prefix = data[max(0, stream_match.start() - 240) : stream_match.start()]
        if b"/FlateDecode" in object_prefix:
            try:
                payload = zlib.decompress(payload)
            except zlib.error as exc:
                raise KnowledgePipelineError("DOCUMENT_PARSE_FAILED", "PDF 压缩流无法解析") from exc
        decoded = payload.decode("latin-1", errors="ignore")
        strings = re.findall(r"\(((?:\\.|[^\\)])*)\)\s*(?:Tj|TJ|['\"])", decoded)
        text_parts.extend(_pdf_unescape(item) for item in strings)
    return "\n".join(part for part in text_parts if part.strip())


def _parse_pdf(data: bytes, *, filename: str, media_type: str, content_hash: str) -> ParsedDocument:
    try:
        from pypdf import PdfReader
    except ImportError:
        text = _fallback_pdf_text(data)
        if not text.strip():
            raise KnowledgePipelineError(
                "DOCUMENT_EMPTY", "PDF 没有可提取的非空文本"
            ) from None
        blocks = _parse_text_blocks(text, page_number=1)
        return ParsedDocument(
            filename=filename,
            media_type=media_type,
            content_hash=content_hash,
            byte_size=len(data),
            parser_version=PARSER_VERSION,
            page_count=1,
            blocks=blocks,
        )
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise KnowledgePipelineError("DOCUMENT_ENCRYPTED", "加密 PDF 不允许进入知识流水线")
        pages = list(reader.pages)
    except KnowledgePipelineError:
        raise
    except Exception as exc:
        raise KnowledgePipelineError("DOCUMENT_PARSE_FAILED", "PDF 文件无法解析") from exc
    if not pages:
        raise KnowledgePipelineError("DOCUMENT_EMPTY", "PDF 没有页面")
    blocks: list[ParsedBlock] = []
    page_count = len(pages)
    for page_index, page in enumerate(pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            raise KnowledgePipelineError("DOCUMENT_PARSE_FAILED", "PDF 页面无法解析") from exc
        blocks.extend(_parse_text_blocks(page_text, page_number=page_index))
    if not blocks:
        raise KnowledgePipelineError("DOCUMENT_EMPTY", "PDF 没有可提取的非空文本")
    return ParsedDocument(
        filename=filename,
        media_type=media_type,
        content_hash=content_hash,
        byte_size=len(data),
        parser_version=PARSER_VERSION,
        page_count=page_count,
        blocks=tuple(blocks),
    )


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_docx(data: bytes, *, filename: str, media_type: str, content_hash: str) -> ParsedDocument:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if any(info.flag_bits & 0x1 for info in archive.infolist()):
                raise KnowledgePipelineError("DOCUMENT_ENCRYPTED", "加密 DOCX 不允许进入知识流水线")
            xml_data = archive.read("word/document.xml")
    except KnowledgePipelineError:
        raise
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        raise KnowledgePipelineError("DOCUMENT_PARSE_FAILED", "DOCX 文件结构无效") from exc
    try:
        root = ElementTree.fromstring(xml_data)
    except ElementTree.ParseError as exc:
        raise KnowledgePipelineError("DOCUMENT_PARSE_FAILED", "DOCX XML 无法解析") from exc

    body = next((element for element in root.iter() if _xml_local_name(element.tag) == "body"), None)
    if body is None:
        raise KnowledgePipelineError("DOCUMENT_EMPTY", "DOCX 没有正文")
    lines: list[str] = []
    for child in list(body):
        kind = _xml_local_name(child.tag)
        if kind == "p":
            text = "".join(
                element.text or ""
                for element in child.iter()
                if _xml_local_name(element.tag) == "t"
            ).strip()
            if not text:
                continue
            style = next(
                (
                    element.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")
                    for element in child.iter()
                    if _xml_local_name(element.tag) == "pStyle"
                ),
                "",
            )
            heading_match = re.search(r"(\d+)$", style)
            if style.lower().startswith("heading"):
                level = int(heading_match.group(1)) if heading_match else 1
                lines.append(f"{'#' * max(1, min(6, level))} {text}")
            else:
                lines.append(text)
        elif kind == "tbl":
            for row in (item for item in child if _xml_local_name(item.tag) == "tr"):
                cells = []
                for cell in (item for item in row if _xml_local_name(item.tag) == "tc"):
                    cell_text = " ".join(
                        element.text or ""
                        for element in cell.iter()
                        if _xml_local_name(element.tag) == "t"
                    ).strip()
                    cells.append(cell_text)
                if any(cells):
                    lines.append("|" + "|".join(cells) + "|")
    text = "\n".join(lines)
    if not text.strip():
        raise KnowledgePipelineError("DOCUMENT_EMPTY", "DOCX 没有可用的非空文本")
    blocks = _parse_text_blocks(text)
    return ParsedDocument(
        filename=filename,
        media_type=media_type,
        content_hash=content_hash,
        byte_size=len(data),
        parser_version=PARSER_VERSION,
        page_count=1,
        blocks=blocks,
    )


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    """Parse one supported document into a provenance-rich block stream."""

    safe_name, media_type = _filename_metadata(filename)
    if not isinstance(data, bytes):
        raise KnowledgePipelineError("DOCUMENT_BYTES_INVALID", "文档内容必须是二进制数据")
    if not data:
        raise KnowledgePipelineError("DOCUMENT_EMPTY", "文档内容为空")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise KnowledgePipelineError("DOCUMENT_TOO_LARGE", "文档超过 5 MiB 大小限制")
    content_hash = hashlib.sha256(data).hexdigest()
    extension = Path(safe_name).suffix.lower()
    try:
        if extension in {".md", ".markdown", ".txt"}:
            text = data.decode("utf-8-sig")
            return _parse_plain_text(
                text,
                filename=safe_name,
                media_type=media_type,
                content_hash=content_hash,
                size=len(data),
            )
        if extension == ".pdf":
            return _parse_pdf(
                data,
                filename=safe_name,
                media_type=media_type,
                content_hash=content_hash,
            )
        return _parse_docx(
            data,
            filename=safe_name,
            media_type=media_type,
            content_hash=content_hash,
        )
    except UnicodeDecodeError as exc:
        raise KnowledgePipelineError("DOCUMENT_ENCODING_INVALID", "文本文件必须使用 UTF-8 编码") from exc
    except KnowledgePipelineError:
        raise
    except Exception as exc:
        raise KnowledgePipelineError("DOCUMENT_PARSE_FAILED", "文档无法解析") from exc


def decode_base64_document(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise KnowledgePipelineError("DOCUMENT_ENCODING_INVALID", "文档内容不是有效的 Base64") from exc


def _split_long_block(block: ParsedBlock) -> list[ParsedBlock]:
    pieces: list[ParsedBlock] = []
    cursor = 0
    while cursor < len(block.text):
        limit = min(len(block.text), cursor + MAX_CHUNK_CHARS)
        if limit < len(block.text):
            boundary = block.text.rfind(" ", cursor, limit)
            if boundary > cursor + MAX_CHUNK_CHARS // 2:
                limit = boundary
        piece = block.text[cursor:limit].strip()
        if piece:
            pieces.append(
                ParsedBlock(
                    text=piece,
                    kind=block.kind,
                    title_path=block.title_path,
                    page_number=block.page_number,
                    start_offset=block.start_offset + cursor,
                    end_offset=block.start_offset + limit,
                )
            )
        cursor = limit
    return pieces


def chunk_blocks(blocks: Sequence[ParsedBlock]) -> tuple[ChunkDraft, ...]:
    """Group structural blocks without crossing a configured size boundary."""

    chunks: list[ChunkDraft] = []
    current: list[ParsedBlock] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        content = "\n".join(item.text for item in current).strip()
        if content:
            first, last = current[0], current[-1]
            chunks.append(
                ChunkDraft(
                    index=len(chunks),
                    content=content,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    block_type=(current[0].kind if len({item.kind for item in current}) == 1 else "section"),
                    title_path=last.title_path or first.title_path,
                    page_number=first.page_number,
                    start_offset=min(item.start_offset for item in current),
                    end_offset=max(item.end_offset for item in current),
                )
            )
        current = []

    for block in blocks:
        candidates = _split_long_block(block) if len(block.text) > MAX_CHUNK_CHARS else [block]
        for candidate in candidates:
            if candidate.kind == "heading" and current:
                flush()
            projected = len("\n".join(item.text for item in (*current, candidate)).strip())
            if current and projected > MAX_CHUNK_CHARS:
                flush()
            current.append(candidate)
            if candidate.kind in {"list", "table"}:
                flush()
    flush()
    return tuple(chunks)


def _document_error(document: KnowledgeDocument, error: KnowledgePipelineError) -> None:
    document.status = "FAILED"
    document.error_code = error.code
    document.error_message = error.message[:240]
    document.updated_at = utcnow()


def ingest_document(
    db: Session,
    *,
    filename: str,
    source_uri: str,
    data: bytes,
    idempotency_key: str | None = None,
    owner: str = "knowledge-operations",
) -> IngestResult:
    """Ingest bytes idempotently and persist only parsed, traceable chunks."""

    safe_uri, source_type = _safe_source_uri(source_uri)
    safe_name, media_type = _filename_metadata(filename)
    if not isinstance(data, bytes) or not data:
        raise KnowledgePipelineError("DOCUMENT_EMPTY", "文档内容为空")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise KnowledgePipelineError("DOCUMENT_TOO_LARGE", "文档超过 5 MiB 大小限制")
    content_hash = hashlib.sha256(data).hexdigest()
    key = idempotency_key.strip() if idempotency_key else None

    existing_by_key = (
        db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.idempotency_key == key))
        if key
        else None
    )
    if existing_by_key:
        if existing_by_key.source_uri != safe_uri or existing_by_key.content_hash != content_hash:
            raise ConflictError("KNOWLEDGE_IDEMPOTENCY_CONFLICT", "幂等键已经绑定到其他文档")
        if existing_by_key.status != "FAILED":
            return IngestResult(existing_by_key, duplicate=True, retried=False)
        db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == existing_by_key.id))
        existing_by_key.status = "PARSING"
        existing_by_key.error_code = None
        existing_by_key.error_message = None
        existing_by_key.chunk_count = 0
        existing_by_key.updated_at = utcnow()
        document = existing_by_key
        retried = True
    else:
        duplicate = db.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.content_hash == content_hash)
        )
        if duplicate:
            return IngestResult(duplicate, duplicate=True, retried=False)
        source = db.scalar(select(KnowledgeSource).where(KnowledgeSource.source_uri == safe_uri))
        if source is None:
            source = KnowledgeSource(source_uri=safe_uri, source_type=source_type, owner=owner)
            db.add(source)
            db.flush()
        supersedes = db.scalar(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.source_uri == safe_uri)
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(1)
        )
        document = KnowledgeDocument(
            source_id=source.id,
            source_uri=safe_uri,
            filename=safe_name,
            media_type=media_type,
            content_hash=content_hash,
            byte_size=len(data),
            parser_version=PARSER_VERSION,
            chunking_version=CHUNKING_VERSION,
            status="PARSING",
            idempotency_key=key,
            supersedes_document_id=supersedes.id if supersedes else None,
        )
        db.add(document)
        db.flush()
        retried = False

    try:
        parsed = parse_document(safe_name, data)
        drafts = chunk_blocks(parsed.blocks)
        if not drafts:
            raise KnowledgePipelineError("DOCUMENT_EMPTY", "文档没有可用切块")
        document.status = "PARSED"
        document.page_count = parsed.page_count
        document.block_count = len(parsed.blocks)
        document.chunk_count = len(drafts)
        document.parser_version = parsed.parser_version
        document.chunking_version = CHUNKING_VERSION
        document.error_code = None
        document.error_message = None
        document.updated_at = utcnow()
        db.add_all(
            [
                KnowledgeChunk(
                    id=new_id(),
                    document_id=document.id,
                    chunk_index=draft.index,
                    content=draft.content,
                    content_hash=draft.content_hash,
                    block_type=draft.block_type,
                    title_path=list(draft.title_path),
                    page_number=draft.page_number,
                    start_offset=draft.start_offset,
                    end_offset=draft.end_offset,
                    source_uri=safe_uri,
                )
                for draft in drafts
            ]
        )
        db.commit()
        db.refresh(document)
        return IngestResult(document, duplicate=False, retried=retried)
    except KnowledgePipelineError as error:
        _document_error(document, error)
        db.commit()
        raise
    except Exception:
        db.rollback()
        raise


def get_document(db: Session, document_id: str) -> KnowledgeDocument:
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise NotFoundError("知识文档不存在")
    return document


def list_documents(db: Session) -> list[KnowledgeDocument]:
    return list(
        db.scalars(
            select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
        )
    )


def list_document_chunks(db: Session, document_id: str) -> list[KnowledgeChunk]:
    get_document(db, document_id)
    return list(
        db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        )
    )
