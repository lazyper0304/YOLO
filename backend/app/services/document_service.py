"""Document service — manages document lifecycle: upload, process, delete."""

import asyncio
import logging
import os
import time
from pathlib import Path

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import async_session_factory
from app.core import decrypt_api_key
from app.models.knowledge_base import KnowledgeBase, KBDocument, KBChunk
from app.models.llm_config import LLMConfig
from app.models.ocr_config import OCRConfig
from app.services.chroma_service import ChromaService
from app.services.embedding_service import EmbeddingService
from app.services.document_parser import parse_document
from app.services.chunking_service import split_text
from app.services.image_parser import ImageParser
from app.services.llm_service import LLMService
from app.services.kb_progress import set_progress, delete_progress
from app.utils.file_utils import save_upload_file

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tiff'}
ALLOWED_TEXT_EXTENSIONS = {'.txt', '.md', '.pdf', '.docx'}
CHUNK_CUTOFF = 3


class DocumentService:
    """Handles document lifecycle: upload, parse, chunk, embed, store in ChromaDB."""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def process_document(self, doc_id: int) -> None:
        """Process a document: parse → chunk → embed → store.
        Supports both standalone and in-transaction usage.
        """
        if self.db is None:
            async with async_session_factory() as db:
                self.db = db
                try:
                    await self._do_process_document(doc_id)
                    await db.commit()
                except Exception as e:
                    logger.error(f"Document processing failed for doc {doc_id}: {e}", exc_info=True)
                    await db.rollback()
                    err_msg = str(e) or repr(e) or type(e).__name__
                    await self._save_failure_status(doc_id, err_msg[:500])
                    await delete_progress(doc_id)
                finally:
                    self.db = None
        else:
            try:
                await self._do_process_document(doc_id)
            except Exception as e:
                logger.error(f"Document processing failed for doc {doc_id}: {e}", exc_info=True)
                try:
                    doc = (await self.db.execute(select(KBDocument).where(KBDocument.id == doc_id))).scalar_one_or_none()
                    if doc:
                        doc.status = "failed"
                        doc.error_message = str(e)[:500]
                        await self.db.flush()
                except Exception:
                    pass
                await delete_progress(doc_id)
                raise

    async def _save_failure_status(self, doc_id: int, error_message: str) -> None:
        try:
            async with async_session_factory() as db:
                result = await db.execute(select(KBDocument).where(KBDocument.id == doc_id))
                doc = result.scalar_one_or_none()
                if doc:
                    doc.status = "failed"
                    doc.error_message = error_message
                    await db.commit()
        except Exception as e:
            logger.error(f"Failed to save document failure status: {e}")

    async def upload_document(
        self, user_id: int, kb_id: int, file_content: bytes, filename: str
    ) -> KBDocument:
        """Save uploaded file to disk and create a KBDocument record."""
        from app.utils.file_utils import save_upload_file
        file_path = await save_upload_file(file_content, filename, "documents", user_id)
        ext = Path(filename).suffix.lower() if filename else ".txt"

        doc = KBDocument(
            knowledge_base_id=kb_id,
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            file_type=ext,
            file_size=len(file_content),
            status="pending",
        )
        self.db.add(doc)
        await self.db.flush()

        # Update document count
        kb_result = await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        if kb:
            kb.document_count = (kb.document_count or 0) + 1
            await self.db.flush()
        return doc

    async def _do_process_document(self, doc_id: int) -> None:
        """Internal: process a document with an existing session."""
        result = await self.db.execute(select(KBDocument).where(KBDocument.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            return

        doc.status = "processing"
        await self.db.flush()
        await set_progress(doc.id, "parsing", 5, "开始解析文档...")

        if doc.file_type in ALLOWED_IMAGE_EXTENSIONS:
            # Try OCR first if an active config exists, fall back to multimodal LLM
            ocr_text = await self._try_ocr(doc)
            if ocr_text and ocr_text.strip():
                text = ocr_text
            else:
                text = await self._parse_image_document(doc)
        elif doc.file_type == ".pdf":
            text = parse_document(doc.file_path, doc.file_type)
            # Always try OCR for PDFs when active config exists
            ocr_text = await self._try_ocr(doc)
            if ocr_text and ocr_text.strip():
                text = ocr_text
            # If still no text, try parsing via multimodal LLM page by page
            if not text.strip():
                text = await self._parse_pdf_as_images(doc)
        else:
            text = parse_document(doc.file_path, doc.file_type)

        if not text.strip():
            doc.status = "completed"
            doc.error_message = "文档内容为空"
            await self.db.flush()
            await delete_progress(doc.id)
            return

        chunks = split_text(text)
        if not chunks:
            doc.status = "completed"
            doc.error_message = "文档分块结果为空"
            await self.db.flush()
            await delete_progress(doc.id)
            return

        texts = [c["content"] for c in chunks]
        await set_progress(
            doc.id, "embedding", 40,
            f"正在生成向量嵌入，共 {len(chunks)} 个文本块...",
            extra={"chunk_count": len(chunks)},
        )
        try:
            embedder = EmbeddingService()
            embeddings = await asyncio.wait_for(
                embedder.embed_texts(texts),
                timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise TimeoutError("嵌入API调用超时(120s)，请检查嵌入模型配置")

        await set_progress(doc.id, "chunking", 60, f"已生成 {len(embeddings)} 个向量...")

        import uuid
        chunk_records = []
        for i, c in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            chunk_records.append(KBChunk(
                document_id=doc.id,
                knowledge_base_id=doc.knowledge_base_id,
                chunk_index=c.get("chunk_index", i),
                content=c["content"],
                metadata_json={"filename": doc.filename},
                token_count=c.get("token_count", 0),
                chroma_id=chunk_id,
            ))
        self.db.add_all(chunk_records)
        await self.db.flush()

        chroma_ids = [c.chroma_id for c in chunk_records]
        metadatas = [
            {"document_id": doc.id, "filename": doc.filename, "chunk_index": c.chunk_index}
            for c in chunk_records
        ]
        await set_progress(doc.id, "storing", 75, "正在写入向量数据库...")
        try:
            chroma = ChromaService()
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    chroma.add_chunks,
                    doc.knowledge_base_id,
                    chroma_ids, texts, embeddings, metadatas,
                ),
                timeout=60,
            )
        except asyncio.TimeoutError:
            raise TimeoutError("向量数据库写入超时(60s)，请检查ChromaDB是否正常运行")

        doc.status = "completed"
        doc.chunk_count = len(chunks)
        await self.db.flush()

        kb_result = await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == doc.knowledge_base_id)
        )
        kb = kb_result.scalar_one_or_none()
        if kb:
            kb.chunk_count = (kb.chunk_count or 0) + len(chunks)
            await self.db.flush()

        await delete_progress(doc.id)

    async def _try_ocr(self, doc: KBDocument) -> str | None:
        """Try OCR on the document if an active OCR config exists."""
        try:
            ocr_result = await self.db.execute(
                select(OCRConfig).where(
                    OCRConfig.user_id == doc.user_id,
                    OCRConfig.is_active == True,
                )
            )
            ocr_config = ocr_result.scalar_one_or_none()
            if not ocr_config:
                return None

            from app.services.ocr_service import OCRService
            from app.core import decrypt_api_key
            ocr = OCRService()
            api_url = ocr_config.api_base_url
            api_key = decrypt_api_key(ocr_config.api_key) if ocr_config.api_key else None

            if doc.file_type in ALLOWED_IMAGE_EXTENSIONS or doc.file_type == ".pdf":
                # For images: send directly; for PDFs: convert pages to images
                if doc.file_type == ".pdf":
                    import fitz
                    pdf = fitz.open(doc.file_path)
                    texts = []
                    for page_num in range(len(pdf)):
                        page = pdf[page_num]
                        pix = page.get_pixmap(dpi=250)
                        img_bytes = pix.tobytes("png")
                        import tempfile
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                            tmp.write(img_bytes)
                            tmp_path = tmp.name
                        try:
                            page_text = await ocr.extract_text(tmp_path, api_base_url=api_url, api_key=api_key)
                            if page_text.strip():
                                texts.append(f"--- 第 {page_num + 1} 页 ---\n{page_text}")
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except Exception:
                                pass
                    pdf.close()
                    if not texts:
                        return None  # OCR returned nothing for all pages
                    return "\n\n".join(texts)
                else:
                    text = await ocr.extract_text(doc.file_path, api_base_url=api_url, api_key=api_key)
                    return text
        except Exception as e:
            logger.warning("OCR failed for doc %d: %s", doc.id, e)
        return None

    async def _parse_pdf_as_images(self, doc: KBDocument) -> str:
        """Parse a PDF by rendering each page as an image and using multimodal LLM."""
        try:
            import fitz
            pdf = fitz.open(doc.file_path)
        except Exception:
            return ""

        from app.services.llm_service import LLMService
        import base64

        result = await self.db.execute(
            select(LLMConfig).where(
                LLMConfig.user_id == doc.user_id,
                LLMConfig.is_active == True,
            )
        )
        llm_config = result.scalar_one_or_none()
        if llm_config is None:
            pdf.close()
            return ""

        try:
            api_key = decrypt_api_key(llm_config.api_key)
        except Exception:
            pdf.close()
            return ""

        llm_service = LLMService()
        pages_text = []
        max_pages = min(len(pdf), 30)  # Limit to 30 pages to avoid excessive LLM cost

        for i in range(max_pages):
            page = pdf[i]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            prompt = (
                "请提取这张图片中的全部文字内容，不要遗漏任何文字。"
                "如果图片中没有文字，请回复{\"summary\": \"(无文字)\"}。"
                "请以JSON格式返回: {\"summary\": \"提取到的完整文字\"}"
            )

            try:
                result = await llm_service.analyze_image(
                    api_base_url=llm_config.api_base_url,
                    api_key=api_key,
                    model_name=llm_config.model_name,
                    image_base64=img_b64,
                    provider=llm_config.provider,
                    prompt=prompt,
                )
                # analyze_image returns a dict; extract text from summary or detailed_analysis
                raw = (result.get("summary") or result.get("detailed_analysis") or "").strip()
                clean = raw.replace("(无文字)", "").replace('{"summary": "(无文字)"}', "").strip()
                if clean:
                    pages_text.append(f"--- 第 {i + 1} 页 ---\n{clean}")
            except Exception as e:
                logger.warning("LLM page parsing failed for page %d: %s", i + 1, e)

        pdf.close()
        return "\n\n".join(pages_text)

    async def _parse_image_document(self, doc: KBDocument) -> str:
        """Parse an image document via multimodal LLM."""
        result = await self.db.execute(
            select(LLMConfig).where(
                LLMConfig.user_id == doc.user_id,
                LLMConfig.is_active == True,
            )
        )
        llm_config = result.scalar_one_or_none()
        if llm_config is None:
            return "[图片] 未找到激活的LLM配置"

        try:
            api_key = decrypt_api_key(llm_config.api_key)
        except Exception:
            return "[图片] LLM配置密钥解密失败，请重新配置"

        llm_service = LLMService()
        from app.services.image_service import ImageService
        img_b64_result = ImageService().encode_image_base64(doc.file_path)
        if not img_b64_result:
            return "[图片] 无法读取图片"

        try:
            analysis = await llm_service.analyze_image(
                api_base_url=llm_config.api_base_url,
                api_key=api_key,
                model_name=llm_config.model_name,
                image_base64=img_b64_result,
                provider=llm_config.provider,
            )
            return analysis.get("summary", "") or analysis.get("detailed_analysis", "") or ""
        except Exception:
            return "[图片] 图片解析失败"

    async def delete_document(self, doc_id: int, user_id: int) -> None:
        """Delete a document and its chunks."""
        result = await self.db.execute(
            select(KBDocument).where(KBDocument.id == doc_id, KBDocument.user_id == user_id)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise ValueError("文档不存在")

        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except OSError:
                pass

        chunk_count = doc.chunk_count or 0

        await self.db.delete(doc)
        await self.db.flush()

        kb_result = await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == doc.knowledge_base_id)
        )
        kb = kb_result.scalar_one_or_none()
        if kb:
            kb.document_count = max(0, (kb.document_count or 0) - 1)
            kb.chunk_count = max(0, (kb.chunk_count or 0) - chunk_count)
            await self.db.flush()

    async def reprocess_document(self, doc_id: int, user_id: int) -> None:
        """Reset a document to pending for reprocessing."""
        result = await self.db.execute(
            select(KBDocument).where(KBDocument.id == doc_id, KBDocument.user_id == user_id)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise ValueError("文档不存在")

        # Delete existing chunks from ChromaDB
        chroma = ChromaService()
        try:
            chroma.delete_by_document(doc.knowledge_base_id, doc_id)
        except Exception as e:
            logger.warning("ChromaDB cleanup failed for doc %d: %s", doc_id, e)

        # Delete chunks from DB
        await self.db.execute(
            KBChunk.__table__.delete().where(KBChunk.document_id == doc_id)
        )

        # Decrement KB chunk_count
        kb_result = await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == doc.knowledge_base_id)
        )
        kb = kb_result.scalar_one_or_none()
        if kb:
            kb.chunk_count = max(0, (kb.chunk_count or 0) - (doc.chunk_count or 0))
        await self.db.flush()

        doc.status = "pending"
        doc.error_message = None
        doc.chunk_count = 0
        await self.db.flush()

    async def get_document_preview(self, doc_id: int) -> dict:
        """Get a native preview using the same document parser as processing."""
        result = await self.db.execute(select(KBDocument).where(KBDocument.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            raise ValueError("文档不存在")

        file_url = None
        if doc.file_path and os.path.exists(doc.file_path):
            from app.config import settings
            rel_path = Path(doc.file_path).as_posix()
            if "uploads" in rel_path:
                file_url = "/uploads/" + rel_path.split("uploads/", 1)[-1]
            else:
                file_url = "/uploads/" + Path(doc.file_path).name
            file_url = f"http://localhost:{settings.BACKEND_PORT}{file_url}"

        if doc.file_type in ALLOWED_IMAGE_EXTENSIONS:
            return {
                "doc_id": doc.id, "filename": doc.filename, "file_type": doc.file_type,
                "file_size": doc.file_size, "status": doc.status,
                "content_preview": "[图片] 图片文档已解析为文本描述并存储为片段",
                "file_url": file_url,
                "chunks": [],
            }

        content_preview = ""

        if doc.file_path and os.path.exists(doc.file_path):
            try:
                parsed = parse_document(doc.file_path, doc.file_type)
                if parsed and parsed.strip():
                    content_preview = parsed[:30000]
            except Exception:
                pass

        if not content_preview:
            chunk_result = await self.db.execute(
                select(KBChunk.content)
                .where(KBChunk.document_id == doc_id)
                .order_by(KBChunk.chunk_index)
            )
            chunk_contents = [row[0] for row in chunk_result.fetchall() if row[0]]
            if chunk_contents:
                content_preview = "\n\n".join(chunk_contents)[:30000]

        if not content_preview:
            content_preview = "(文档内容为空或无法解析)"

        return {
            "doc_id": doc.id, "filename": doc.filename, "file_type": doc.file_type,
            "file_size": doc.file_size, "status": doc.status,
            "content_preview": content_preview[:30000],
            "file_url": file_url,
            "chunks": [],
        }

    async def get_kb_stats(self, kb_id: int) -> dict:
        """Get knowledge base statistics from real DB counts."""
        result = await self.db.execute(
            select(func.count(KBDocument.id)).where(KBDocument.knowledge_base_id == kb_id)
        )
        doc_count = result.scalar() or 0
        chunk_result = await self.db.execute(
            select(func.coalesce(func.sum(KBDocument.chunk_count), 0))
            .where(KBDocument.knowledge_base_id == kb_id)
        )
        chunk_count = chunk_result.scalar() or 0
        return {"document_count": doc_count, "chunk_count": chunk_count}

    async def sync_kb_counts(self, kb_id: int) -> None:
        """Recalculate and sync KB document_count and chunk_count from real data."""
        stats = await self.get_kb_stats(kb_id)
        await self.db.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id)
            .values(
                document_count=stats["document_count"],
                chunk_count=stats["chunk_count"],
            )
        )
        await self.db.flush()

    async def _build_rag_context(self, kb_ids: list[int], query: str) -> str:
        """Build RAG context from knowledge bases (for collaborative analysis mode)."""
        from app.services.retrieval_service import RetrievalService
        retrieval = RetrievalService()
        try:
            results = await retrieval.search(kb_ids=kb_ids, query=query, top_k=3)
            if results:
                return retrieval.build_context(results, max_tokens=1000)
        except Exception:
            pass
        return ""

    async def reindex_knowledge_base(self, kb_id: int) -> None:
        """Re-index all documents in a knowledge base (re-embed all chunks)."""
        from app.services.kb_reindex import reindex_knowledge_base
        await reindex_knowledge_base(kb_id)
