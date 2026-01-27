import asyncio
import uuid
from tabulate import tabulate

from local_llm_service import LocalLLMService
from vector_service import VectorService
from RAG.database_service import DatabaseService
from swagger_processor import SwaggerParser

# Stały namespace dla powtarzalnych UUID
MY_APP_NAMESPACE = uuid.NAMESPACE_DNS 

def calculate_rrf(vector_results: list, keyword_results: list):
    """Algorytm Reciprocal Rank Fusion dla łączenia wyników"""
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
        # Stała 60 jest standardem w RRF
        v_score = 1 / (60 + item.get('vector_rank', 999))
        k_score = 1 / (60 + item.get('keyword_rank', 999))
        item['score'] = v_score + k_score
        final_results.append(item)

    return sorted(final_results, key=lambda x: x['score'], reverse=True)

async def main():
    # 1. Inicjalizacja usług
    llm_svc = LocalLLMService()
    vector_svc = VectorService(llm_svc)
    db_svc = DatabaseService("api_rag.db", vector_svc)
    parser = SwaggerParser(MY_APP_NAMESPACE)
    
    try:
        # 2. Setup bazy danych
        await db_svc.initialize_database()

        # 3. Sprawdzenie czy baza wymaga zasilenia (seeding)
        if await db_svc.get_all_count() == 0:
            print("Importowanie dokumentacji ze swagger.json...")
            api_docs = parser.process_swagger('swagger.json')
            # api_docs = parser.process_swagger('C:\AI Playground\AI_Devs\zadania\hybrid_rag_local_api\swagger.json')
            
            for doc in api_docs:  #doc to jeden słownik reprezentujący jeden endpoint lub model
                # Używamy nowej metody dostosowanej do API
                await db_svc.insert_api_doc(doc)
            print(f"Zakończono! Zaindeksowano {len(api_docs)} elementów.")

        # 4. Przykładowe zapytanie
        QUERY = "Write a Robot Framework test case that adds a dog to the pet store and places an order for it."
        # QUERY = "How to find pets by tags?"
        print(f"\nSZUKAM: {QUERY}")
        
        # Wyszukiwanie hybrydowe
        vector_results = await vector_svc.perform_search("api_collection", QUERY, limit=5)
        keyword_results = await db_svc.search_keyword(QUERY, limit=5)
        
        final_results = calculate_rrf(vector_results, keyword_results)

        # 5. Prezentacja wyników
        table = []
        for r in final_results[:5]:
            # Wyświetlamy najważniejsze informacje techniczne
            method = r.get('method', 'N/A')
            path = r.get('path', 'N/A')
            summary = (r.get('summary') or r.get('description') or "")[:60] + "..."
            table.append([method, path, summary, f"{r['score']:.4f}"])
            
        print(tabulate(table, headers=["Metoda", "Ścieżka / Model", "Podsumowanie", "Score"]))

        # 6. Generowanie test case'u na podstawie najlepszych wyników
        needs_test = await llm_svc.is_test_request(QUERY)

        if needs_test:
            print("\n[GENEROWANIE TESTU ROBOT FRAMEWORK...]")
            context_block = "\n---\n".join([r['content'] for r in final_results[:3]])

            test_code = await llm_svc.generate_test_case(context_block, QUERY)

            print("\nWYGENEROWANY KOD:")
            print("---------------------------------------")
            print(test_code)
            print("---------------------------------------")

    finally:
        await vector_svc.close()

if __name__ == "__main__":
    asyncio.run(main())