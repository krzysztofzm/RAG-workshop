import asyncio
import uuid
from typing import List

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.retrievers import EnsembleRetriever
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from qdrant_client import QdrantClient

# Imports from our existing codebase
from swagger_processor import SwaggerParser
from database_service import DatabaseService
from local_llm_service import LocalLLMService # for helper methods

MY_APP_NAMESPACE = uuid.NAMESPACE_DNS

class SQLiteFTSRetriever(BaseRetriever):
    """Cusom Retriever for LangChain that performs keyword search on SQLite FTS5."""
    db_svc: DatabaseService
    limit: int = 5

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun = None
    ) -> List[Document]:
        # We use the existing search_keyword method from DatabaseService, which is asynchronous.
        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(self.db_svc.search_keyword(query, self.limit))
        
        docs = []
        for res in results:
            docs.append(Document(
                page_content=res.get('summary', '') or res.get('description', ''),
                metadata=res
            ))
        return docs

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun = None
    ) -> List[Document]:
        results = await self.db_svc.search_keyword(query, self.limit)
        return [Document(page_content=res.get('summary', '') or '', metadata=res) for res in results]

async def main():
    # 1. Inicjalization of LLM and Embeddings (LangChain)
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    llm_general = ChatOllama(model="llama3.2", temperature=0)
    llm_coder = ChatOllama(model="codellama", temperature=0.1)

    # Intialization of our existing services (Database and Swagger Parser)
    # (LocalLLMService only for DB is DataBaseService needs it)
    temp_llm_svc = LocalLLMService() 
    from vector_service import VectorService
    vector_svc = VectorService(temp_llm_svc)
    db_svc = DatabaseService("api_rag.db", vector_svc)
    parser = SwaggerParser(MY_APP_NAMESPACE)

    # 2. DB initialization
    await db_svc.initialize_database()
    
    # Qdrant Client for LangChain
    client = QdrantClient(path="./qdrant_db")
    vectorstore = QdrantVectorStore(
        client=client,
        collection_name="api_collection",
        embeddings=embeddings,
    )

    # 3. Import of data from swagger.json if database is empty
    if await db_svc.get_all_count() == 0:
        print("Importing documentation...")
        api_docs = parser.process_swagger('swagger.json')
        
        # Inserting documents into the database and vector store
        for doc in api_docs:
            await db_svc.insert_api_doc(doc)
        print(f"End! {len(api_docs)} elements indexed.")

    # 4. Hybrid Search configuration (Ensemble Retriever)
    # LangChain EnsembleRetriever uses RRF (Reciprocal Rank Fusion) by defalut
    qdrant_retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    sqlite_retriever = SQLiteFTSRetriever(db_svc=db_svc, limit=5)

    ensemble_retriever = EnsembleRetriever(
        retrievers=[qdrant_retriever, sqlite_retriever],
        weights=[0.5, 0.5]
    )

    # 5. klassifiing the Query (Router)
    QUERY = "Write a Robot Framework test case that adds a dog to the pet store and places an order for it."
    print(f"\nQUERYING: {QUERY}")

    classification_prompt = ChatPromptTemplate.from_template(
        "Analyze the user query. Is the user asking to write, create, or generate an automation test, "
        "a test case, or Robot Framework code? Answer only 'YES' or 'NO'.\nQuery: {query}"
    )
    
    classification_chain = classification_prompt | llm_general | StrOutputParser()
    is_test = "YES" in (await classification_chain.ainvoke({"query": QUERY})).upper()

    # 6. Retrieval & Generation
    context_docs = await ensemble_retriever.ainvoke(QUERY)
    
    # preparing a context block for the LLM - we are using 'content' from Qdrant metadata, 
    # which contains both technical details and descriptions. 
    # In SQLite FTS5 we have only summary and description, so we fallback to them if content is not available.
    context_text = "\n---\n".join([
        doc.metadata.get('content', doc.page_content) for doc in context_docs
    ])

    if is_test:
        print("\n[GENERATING ROBOT FRAMEWORK TEST CASE...]")
        test_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a QA Automation Expert. Use the provided API documentation to write a Robot Framework test case.
                Use 'RequestsLibrary'. Rules:
                1. Include 'Settings' (Library RequestsLibrary).
                2. Use Keywords: 'Create Session', 'POST On Session', etc.
                3. Return ONLY code.
                4. Use "https://petstore.swagger.io" as base URL."""),
            ("user", "Context:\n{context}\n\nUser Request: {query}")
        ])
        
        test_chain = test_prompt | llm_coder | StrOutputParser()
        result = await test_chain.ainvoke({"context": context_text, "query": QUERY})
    else:
        print("\n[ANSWERING QUERY...]")
        qa_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an API Expert. Answer based on context. Return only the answer."),
            ("user", "Context:\n{context}\n\nQuery: {query}")
        ])
        qa_chain = qa_prompt | llm_general | StrOutputParser()
        result = await qa_chain.ainvoke({"context": context_text, "query": QUERY})

    print("\nRESULT:\n")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())