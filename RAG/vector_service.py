import uuid
from typing import List, Dict, Any
from qdrant_client import QdrantClient, models

class VectorService:
    def __init__(self, local_llm_service):
        # Qdrant runs in local mode using the qdrant_db folder.
        self.client = QdrantClient(path="./qdrant_db")
        self.llm = local_llm_service

    async def ensure_collection(self, name: str):
        collections = self.client.get_collections().collections
        if not any(c.name == name for c in collections):
            self.client.create_collection(
                collection_name=name,
                # 768-dimensional vector size for the nomic-embed-text model
                vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE)
            )

    async def add_points(self, collection_name: str, points: List[Dict]):
        await self.ensure_collection(collection_name)
        points_to_upsert = []
        for p in points:
            embedding = await self.llm.create_embedding(p['text'])
            points_to_upsert.append(models.PointStruct(
                id=p.get('id') or str(uuid.uuid4()),
                vector=embedding,
                payload={"text": p['text'], **p.get('metadata', {})}
            ))
        self.client.upsert(collection_name=collection_name, points=points_to_upsert)

    async def perform_search(self, collection_name: str, query: str, limit: int = 15):
        query_embedding = await self.llm.create_embedding(query)
        
        response = self.client.query_points(
            collection_name=collection_name,
            query=query_embedding,
            limit=limit,
            with_payload=True
        )

        return [{
            "uuid": res.id,
            "path": res.payload.get('path'),
            "method": res.payload.get('method'),
            "summary": res.payload.get('summary'),
            "description": res.payload.get('description'),
            "content": res.payload.get('content'),
            "score": res.score
        } for res in response.points]

    async def close(self):
        self.client = None