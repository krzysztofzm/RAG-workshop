import asyncio
import uuid
from tabulate import tabulate

from local_llm_service import LocalLLMService
from vector_service import VectorService
from database_service import DatabaseService
from swagger_processor import SwaggerParser

# Static namespace for reproducible UUIDs
MY_APP_NAMESPACE = uuid.NAMESPACE_DNS 

def calculate_rrf(vector_results: list, keyword_results: list):
    """Reciprocal Rank Fusion algorithm for merging results from vector and keyword search."""
    result_map = {}
    for i, res in enumerate(vector_results):
        uid = str(res['uuid'])
        if uid not in result_map: result_map[uid] = res.copy()
        result_map[uid]['vector_rank'] = i + 1

    for i, res in enumerate(keyword_results):
        uid = str(res['uuid'])
        if uid not in result_map: result_map[uid] = res.copy()
        result_map[uid]['keyword_rank'] = i + 1

    final_results = []
    for item in result_map.values():
        # constant 60 is a standatd in RRF
        v_score = 1 / (60 + item.get('vector_rank', 999))
        k_score = 1 / (60 + item.get('keyword_rank', 999))
        item['score'] = v_score + k_score
        final_results.append(item)

    return sorted(final_results, key=lambda x: x['score'], reverse=True)

async def main():
    # 1. Service Initialization
    llm_svc = LocalLLMService()
    vector_svc = VectorService(llm_svc)
    db_svc = DatabaseService("api_rag.db", vector_svc)
    parser = SwaggerParser(MY_APP_NAMESPACE)
    
    try:
        # 2. Database Initialization
        await db_svc.initialize_database()

        # 3. Chceck is database empty and import data if needed
        if await db_svc.get_all_count() == 0:
            print("Importowanie dokumentacji ze swagger.json...")
            api_docs = parser.process_swagger('RAG\swagger.json')
            # api_docs = parser.process_swagger('C:\AI Playground\AI_Devs\zadania\hybrid_rag_local_api\swagger.json')
            
            for doc in api_docs:  #doc is a single dictionary representing one endpoint or model.
                # We are using a new method tailored to the API.
                await db_svc.insert_api_doc(doc)
            print(f"End! {len(api_docs)} elements indexed.")

        # 4. Exapmple Query
        # QUERY = "Write a Robot Framework test case that adds a dog to the pet store and places an order for it."
        QUERY = "How to add a dog?"
        print(f"\nQUERYING: {QUERY}")
        
        # Hybrid search
        vector_results = await vector_svc.perform_search("api_collection", QUERY, limit=5)
        keyword_results = await db_svc.search_keyword(QUERY, limit=5)
        
        final_results = calculate_rrf(vector_results, keyword_results)

        # 5. Result presentation
        table = []
        for r in final_results[:5]:
            # Displaying key technical information
            method = r.get('method', 'N/A')
            path = r.get('path', 'N/A')
            summary = (r.get('summary') or r.get('description') or "")[:60] + "..."
            table.append([method, path, summary, f"{r['score']:.4f}"])
            
        print("\n[TOP SEARCH RESULTS:]")
        print(tabulate(table, headers=["Method", "Path / Model", "Summary", "Score"]))

        # 6. Generating a test case or answering the question based on the top results
        context_block = "\n---\n".join([r['content'] for r in final_results[:3]])

        needs_test = await llm_svc.is_test_request(QUERY)

        if needs_test:
            print("\n[GENERATING ROBOT FRAMEWORK TEST CASE...]")
            test_code = await llm_svc.generate_test_case(context_block, QUERY)

            print("\nGENERATED CODE:\n")
            print(test_code)
        else:
            print("\n[ANSWER TO THE QUERY...]")
            answer = await llm_svc.generate_answer(context_block, QUERY)
            print("\nANSWER:")
            print(answer)

    finally:
        await vector_svc.close()

if __name__ == "__main__":
    asyncio.run(main())