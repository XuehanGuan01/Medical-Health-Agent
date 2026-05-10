"""
检索接口 — Phase 3 Agent 调用
这里的embedding模型选用了初始化ChromaDB数据库时相同的：text-embedding-v4

用法:
    from rag.retriever import MedicalRetriever
    retriever = MedicalRetriever()
    docs = retriever.search("小孩发烧怎么办？", k=5)
    context = retriever.format_context(docs)
"""

from __future__ import annotations

import os

import chromadb
from langchain_community.embeddings import DashScopeEmbeddings


class MedicalRetriever:
    """华佗医疗 RAG 检索器"""

    def __init__(self, persist_dir: str = "rag/data/chroma"):
        if not os.path.exists(persist_dir):
            raise FileNotFoundError(
                f"ChromaDB 目录不存在: {persist_dir}\n"
                f"请先运行: python rag/build_vectordb.py"
            )

        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_collection("huatuo_medical_qa")
        self.embedder = DashScopeEmbeddings(model="text-embedding-v4")

    def search(self, query: str, k: int = 5) -> list[dict]:
        """检索 Top-K 相关医疗 QA 对"""
        embedding = self.embedder.embed_query(query)

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )

        return self._format_results(results)

    def _format_results(self, results: dict) -> list[dict]:
        docs = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i in range(len(ids)):
            docs.append({
                "id": ids[i],
                "content": documents[i],
                "question": (metadatas[i] or {}).get("question", ""),
                "source": (metadatas[i] or {}).get("source", ""),
                "score": round(1 - distances[i], 4),
            })

        return docs

    def format_context(self, docs: list[dict]) -> str:
        """将检索结果格式化为 LLM context"""
        parts = []
        for i, doc in enumerate(docs, 1):
            parts.append(
                f"[参考知识 {i}] (相关度: {doc['score']:.2f})\n{doc['content']}"
            )
        return "\n\n".join(parts)

    def count(self) -> int:
        return self.collection.count()
