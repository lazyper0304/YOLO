"""Entity extraction service — builds knowledge graph using jieba + embedding clustering."""

import json
import logging
from collections import Counter

import jieba

from sqlalchemy import select, delete
from app.core.database import async_session_factory
from app.models.knowledge_base import KBEntity, KBRelation, KnowledgeBase
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


def _extract_keywords(text: str, top_n: int = 30) -> list[tuple[str, float]]:
    """Extract keywords using jieba TF-IDF + TextRank.

    Returns list of (keyword, weight) tuples sorted by relevance.
    """
    import jieba.analyse

    tfidf = jieba.analyse.extract_tags(text, topK=top_n * 2, withWeight=True)
    textrank = jieba.analyse.textrank(text, topK=top_n * 2, withWeight=True)

    merged: dict[str, float] = {}
    for kw, w in tfidf:
        merged[kw] = merged.get(kw, 0) + w * 1.2
    for kw, w in textrank:
        merged[kw] = merged.get(kw, 0) + w

    filtered = [(k, v) for k, v in merged.items()
                if len(k) >= 2 and not k.isdigit() and not all(c in '0123456789.-+%' for c in k)]

    filtered.sort(key=lambda x: x[1], reverse=True)
    return filtered[:top_n]


async def _cluster_keywords(
    keywords: list[tuple[str, float]],
    embedder: EmbeddingService,
    similarity_threshold: float = 0.78,
) -> list[list[str]]:
    """Cluster similar keywords using embedding cosine similarity."""
    if len(keywords) <= 1:
        return [[kw] for kw, _ in keywords]

    kw_texts = [kw for kw, _ in keywords]
    try:
        embeddings = await embedder.embed_texts(kw_texts)
    except Exception:
        logger.warning("Embedding failed, skipping clustering")
        return [[kw] for kw in kw_texts]

    clusters: list[list[str]] = []
    used: set[int] = set()

    for i in range(len(kw_texts)):
        if i in used:
            continue
        cluster = [kw_texts[i]]
        used.add(i)
        for j in range(i + 1, len(kw_texts)):
            if j in used:
                continue
            sim = sum(a * b for a, b in zip(embeddings[i], embeddings[j]))
            if sim >= similarity_threshold:
                cluster.append(kw_texts[j])
                used.add(j)
        clusters.append(cluster)

    return clusters


def _guess_entity_type(keywords: list[str]) -> str:
    """Guess entity type from keyword patterns."""
    combined = ' '.join(keywords).lower()
    tech = {'系统', '模型', '算法', '数据', '网络', '接口', 'api', '代码', '框架', '引擎',
            'ai', 'gpu', 'cpu', '检测', '识别', '训练', '推理', '参数', '函数', '模块',
            '神经网络', '深度学习', '机器学习', '部署', '服务', '配置', '数据库', '缓存', '日志'}
    person = {'用户', '管理员', '人员', '学生', '老师', '客户', '负责人', '操作员'}
    org = {'公司', '部门', '团队', '组织', '机构', '学校', '实验室', '平台', '项目', '小组'}
    event = {'过程', '流程', '步骤', '阶段', '实验', '测试', '评估', '验证', '分析', '开发',
             '设计', '实现', '优化', '迭代', '部署'}

    if any(p in combined for p in tech): return 'technology'
    if any(p in combined for p in person): return 'person'
    if any(p in combined for p in org): return 'organization'
    if any(p in combined for p in event): return 'event'
    return 'concept'


async def extract_entities_for_kb(kb_id: int) -> dict:
    """Extract entities and relations using jieba + embedding clustering.

    Returns: {"entities_added": int, "relations_added": int}
    """
    async with async_session_factory() as db:
        from app.models.knowledge_base import KBChunk

        chunks_result = await db.execute(
            select(KBChunk.content).where(
                KBChunk.knowledge_base_id == kb_id
            ).order_by(KBChunk.chunk_index).limit(30)
        )
        chunks = chunks_result.scalars().all()

        if not chunks:
            return {"entities_added": 0, "relations_added": 0}

        # Extract per-chunk keywords
        per_chunk_kw: list[set[str]] = []
        for c in chunks:
            kws = _extract_keywords(c, top_n=8)
            per_chunk_kw.append({kw for kw, _ in kws})

        # Global keywords from combined text
        combined = "\n".join(chunks)
        global_kws = _extract_keywords(combined, top_n=25)

        # Cluster similar keywords
        embedder = EmbeddingService()
        clusters = await _cluster_keywords(global_kws, embedder)

        # Build entity data
        entity_data: list[dict] = []
        for cl in clusters:
            name = max(cl, key=len)
            entity_data.append({
                "name": name,
                "type": _guess_entity_type(cl),
                "description": f"含: {', '.join(cl[:4])}",
                "aliases": cl,
            })

        # Build co-occurrence relations
        co_count: Counter = Counter()
        for chunk_kws in per_chunk_kw:
            present: list[int] = []
            for ei, ed in enumerate(entity_data):
                if any(alias in chunk_kws for alias in ed["aliases"]):
                    present.append(ei)
            for a in range(len(present)):
                for b in range(a + 1, len(present)):
                    pair = (min(present[a], present[b]), max(present[a], present[b]))
                    co_count[pair] += 1

        # Persist
        await db.execute(delete(KBRelation).where(KBRelation.knowledge_base_id == kb_id))
        await db.execute(delete(KBEntity).where(KBEntity.knowledge_base_id == kb_id))
        await db.flush()

        eids: list[int] = []
        for ed in entity_data:
            ent = KBEntity(
                knowledge_base_id=kb_id,
                name=ed["name"], entity_type=ed["type"],
                description=ed["description"],
                metadata_json={"aliases": ed["aliases"]},
            )
            db.add(ent)
            await db.flush()
            eids.append(ent.id)

        rel_count = 0
        for (a, b), count in co_count.items():
            if count >= 3 and a < len(eids) and b < len(eids):
                db.add(KBRelation(
                    knowledge_base_id=kb_id,
                    source_id=eids[a], target_id=eids[b],
                    relation_type="关联",
                ))
                rel_count += 1

        await db.commit()
        return {"entities_added": len(eids), "relations_added": rel_count}


async def get_kb_graph(kb_id: int) -> dict:
    """Get knowledge graph data for visualization."""
    async with async_session_factory() as db:
        entities = (await db.execute(
            select(KBEntity).where(KBEntity.knowledge_base_id == kb_id)
        )).scalars().all()
        relations = (await db.execute(
            select(KBRelation).where(KBRelation.knowledge_base_id == kb_id)
        )).scalars().all()
        return {
            "nodes": [{"id": e.id, "name": e.name, "type": e.entity_type, "description": e.description} for e in entities],
            "edges": [{"source": r.source_id, "target": r.target_id, "type": r.relation_type} for r in relations],
        }
