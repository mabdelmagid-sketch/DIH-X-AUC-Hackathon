"""
RAG (Retrieval Augmented Generation) Engine
"""
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from typing import Optional
from pathlib import Path
import json
from datetime import datetime

from ..config import settings


class RAGEngine:
    """Vector search and context retrieval for LLM"""

    def __init__(
        self,
        persist_path: Optional[Path] = None,
        embedding_model: Optional[str] = None
    ):
        self.persist_path = persist_path or settings.chroma_path
        self.embedding_model_name = embedding_model or settings.embedding_model

        # Initialize embedding model
        self.embedder = SentenceTransformer(self.embedding_model_name)

        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(
            path=str(self.persist_path),
            settings=ChromaSettings(anonymized_telemetry=False)
        )

        # Collections
        self.insights_collection = self.client.get_or_create_collection(
            name="insights",
            metadata={"description": "Daily insights and anomalies"}
        )

        self.rules_collection = self.client.get_or_create_collection(
            name="business_rules",
            metadata={"description": "Business rules and thresholds"}
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts"""
        embeddings = self.embedder.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def add_insight(
        self,
        insight_type: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> str:
        """Add an insight to the vector store"""
        doc_id = f"{insight_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        meta = {
            "type": insight_type,
            "created_at": datetime.now().isoformat(),
            **(metadata or {})
        }

        self.insights_collection.add(
            documents=[content],
            metadatas=[meta],
            ids=[doc_id],
            embeddings=self.embed([content])
        )

        return doc_id

    def add_business_rule(
        self,
        rule_name: str,
        description: str,
        rule_data: dict
    ) -> str:
        """Add a business rule to the vector store"""
        doc_id = f"rule_{rule_name}"

        content = f"{rule_name}: {description}\n\nDetails: {json.dumps(rule_data)}"

        meta = {
            "rule_name": rule_name,
            "rule_data": json.dumps(rule_data),
            "created_at": datetime.now().isoformat()
        }

        # Upsert (update if exists)
        self.rules_collection.upsert(
            documents=[content],
            metadatas=[meta],
            ids=[doc_id],
            embeddings=self.embed([content])
        )

        return doc_id

    def search_insights(
        self,
        query: str,
        n_results: int = 5,
        insight_type: Optional[str] = None
    ) -> list[dict]:
        """Search for relevant insights"""
        where_filter = {"type": insight_type} if insight_type else None

        results = self.insights_collection.query(
            query_embeddings=self.embed([query]),
            n_results=n_results,
            where=where_filter
        )

        return self._format_results(results)

    def search_rules(
        self,
        query: str,
        n_results: int = 3
    ) -> list[dict]:
        """Search for relevant business rules"""
        results = self.rules_collection.query(
            query_embeddings=self.embed([query]),
            n_results=n_results
        )

        return self._format_results(results)

    def get_context_for_query(
        self,
        query: str,
        include_insights: bool = True,
        include_rules: bool = True,
        max_items: int = 5
    ) -> str:
        """Get relevant context for an LLM query"""
        context_parts = []

        if include_rules:
            rules = self.search_rules(query, n_results=min(3, max_items))
            if rules:
                context_parts.append("**Relevant Business Rules:**")
                for rule in rules:
                    context_parts.append(f"- {rule['document']}")

        if include_insights:
            insights = self.search_insights(query, n_results=max_items)
            if insights:
                context_parts.append("\n**Recent Related Insights:**")
                for insight in insights:
                    context_parts.append(f"- [{insight['metadata'].get('type', 'insight')}] {insight['document'][:200]}...")

        return "\n".join(context_parts)

    def _format_results(self, results: dict) -> list[dict]:
        """Format ChromaDB results into a cleaner structure"""
        formatted = []

        if not results["documents"]:
            return formatted

        for i, doc in enumerate(results["documents"][0]):
            formatted.append({
                "document": doc,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "id": results["ids"][0][i] if results["ids"] else None,
                "distance": results["distances"][0][i] if results.get("distances") else None
            })

        return formatted

    def seed_default_rules(self):
        """Seed the database with default business rules"""
        default_rules = [
            {
                "name": "low_stock_threshold",
                "description": "Item is considered low stock when quantity falls below threshold",
                "data": {
                    "default_days_of_supply": 3,
                    "alert_level": "warning",
                    "action": "reorder"
                }
            },
            {
                "name": "expiry_alert_windows",
                "description": "Alert windows for expiring inventory",
                "data": {
                    "critical_days": 2,
                    "warning_days": 5,
                    "caution_days": 7,
                    "actions": {
                        "critical": "immediate_promotion_or_use",
                        "warning": "plan_promotion",
                        "caution": "monitor"
                    }
                }
            },
            {
                "name": "waste_thresholds",
                "description": "Acceptable waste levels by category",
                "data": {
                    "produce": 0.08,
                    "dairy": 0.05,
                    "meat": 0.03,
                    "prepared_food": 0.10,
                    "default": 0.05
                }
            },
            {
                "name": "promotion_rules",
                "description": "Rules for automatic promotion suggestions",
                "data": {
                    "min_margin_after_discount": 0.10,
                    "max_discount_percentage": 0.50,
                    "bundle_discount_limit": 0.30
                }
            },
            {
                "name": "forecast_accuracy",
                "description": "Acceptable forecast deviation thresholds",
                "data": {
                    "excellent": 0.10,
                    "good": 0.20,
                    "acceptable": 0.30,
                    "needs_review": 0.50
                }
            }
        ]

        for rule in default_rules:
            self.add_business_rule(
                rule_name=rule["name"],
                description=rule["description"],
                rule_data=rule["data"]
            )

        return len(default_rules)

    def clear_insights(self, older_than_days: int = 30):
        """Clear old insights to manage storage"""
        pass
