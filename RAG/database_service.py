import aiosqlite
from vector_service import VectorService

class DatabaseService:
    def __init__(self, db_path: str, vector_service: VectorService):
        self.db_path = db_path
        self.vector_service = vector_service

    async def initialize_database(self):
        async with aiosqlite.connect(self.db_path) as db:
            # New Table Tailored to the API
            await db.execute("""
                CREATE TABLE IF NOT EXISTS api_docs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid TEXT NOT NULL UNIQUE,
                    path TEXT,           -- np. /pet/{petId}
                    method TEXT,         -- np. POST, GET
                    operation_id TEXT,   -- np. updatePet
                    summary TEXT,
                    description TEXT,
                    tags TEXT,           -- tagi po przecinku
                    content TEXT,        -- pełny tekst techniczny dla LLM
                    doc_type TEXT        -- 'endpoint' lub 'schema' (model danych)
                )
            """)
            
            # FTS5 optimized for technical search
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS api_search USING fts5(
                    uuid UNINDEXED,
                    path, method, operation_id, summary, description, tags,
                    tokenize='porter unicode61'
                )
            """)
            await db.commit()

    async def insert_api_doc(self, doc: dict):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO api_docs (uuid, path, method, operation_id, summary, description, tags, content, doc_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (doc['uuid'], doc.get('path'), doc.get('method'), doc.get('operation_id'), 
                  doc.get('summary'), doc.get('description'), doc.get('tags'), 
                  doc['content'], doc['doc_type']))
            
            await db.execute("""
                INSERT INTO api_search (uuid, path, method, operation_id, summary, description, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (doc['uuid'], doc.get('path'), doc.get('method'), doc.get('operation_id'), 
                  doc.get('summary'), doc.get('description'), doc.get('tags')))
            await db.commit()

        # Data has been added to the database; now we are preparing it for vectorization.
        # Both technical metadata and descriptions are sent to the vector store
        vector_text = f"API {doc.get('method', '')} {doc.get('path', '')}: {doc.get('summary', '')}. {doc.get('content', '')}"
        await self.vector_service.add_points('api_collection', [{
            "id": doc['uuid'],
            "text": vector_text,
            "metadata": doc
        }])

    async def search_keyword(self, query: str, limit: int = 5):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # 1. removing characterd that may destroy FTS5 query (we leave space, letters i digits)
            clean_query = "".join(c if c.isalnum() or c.isspace() else " " for c in query)
            
            # 2. combining the words with AND operator (all must appear, but in any order and column)
            words = clean_query.split()
            if not words: return []
            
            # creating a query string with AND operator between words for FTS5
            fts_query = " AND ".join(words)
            
            sql = "SELECT * FROM api_search WHERE api_search MATCH ? ORDER BY rank LIMIT ?"
            try:
                async with db.execute(sql, (fts_query, limit)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
            except Exception as e:
                print(f"Error in FTS5 search: {e}")
                return []
    
    async def get_all_count(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT count(*) FROM api_docs") as cursor:
                res = await cursor.fetchone()
                return res[0]