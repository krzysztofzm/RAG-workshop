import aiosqlite
from vector_service import VectorService

class DatabaseService:
    def __init__(self, db_path: str, vector_service: VectorService):
        self.db_path = db_path
        self.vector_service = vector_service

    async def initialize_database(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Nowa tabela dopasowana do API
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
            
            # FTS5 zoptymalizowane pod wyszukiwanie techniczne
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

        # Dane zostały dodane do bazy, teraz przygotowujemy do wektora
        # Do wektora trafia zarówno metadane techniczne jak i opis
        vector_text = f"API {doc.get('method', '')} {doc.get('path', '')}: {doc.get('summary', '')}. {doc.get('content', '')}"
        await self.vector_service.add_points('api_collection', [{
            "id": doc['uuid'],
            "text": vector_text,
            "metadata": doc
        }])

    async def search_keyword(self, query: str, limit: int = 10):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            escaped_query = query.replace('"', '""')
            safe_query = f'"{escaped_query}"'
            
            # Pobieramy wszystkie kolumny z wirtualnej tabeli
            sql = "SELECT * FROM api_search WHERE api_search MATCH ? ORDER BY rank LIMIT ?"
            try:
                async with db.execute(sql, (safe_query, limit)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
            except Exception as e:
                print(f"Błąd FTS5: {e}")
                return []
    
    async def get_all_count(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT count(*) FROM api_docs") as cursor:
                res = await cursor.fetchone()
                return res[0]