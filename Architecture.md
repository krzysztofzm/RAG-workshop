1. Conceptual Block Diagram This diagram illustrates the high-level system structure, from the data source to the generative output.

```mermaid
graph TD
    subgraph Ingestion_Layer [Data Ingestion Layer]
        SW[swagger.json] --> SP[Swagger Parser]
        SP --> EX[Endpoint and Schema Extraction]
    end

    subgraph Storage_Layer [Dual Storage Layer]
        EX --> SQL[(SQLite FTS5)]
        EX --> QD[(Qdrant Vector DB)]
        SQL -- Keyword Search --o RS[Hybrid Search / RRF]
        QD -- Semantic Search --o RS
    end

    subgraph Orchestration_Layer [Orchestration & RAG Layer]
        RS --> RRF[Reciprocal Rank Fusion]
        RRF --> IA[Intent Analysis]
        IA --> CB[Context Builder]
    end

    subgraph Generative_Layer [Generation layer]
        CB --> LLM[Local LLM - codellama / llama3.2]
        LLM --> OUT[Robot Framework Code / Metadata]
    end

    style Ingestion_Layer fill:#ED4545,stroke:#333
    style Storage_Layer fill:#bbf,stroke:#333
    style Orchestration_Layer fill:#74b388,stroke:#333
    style Generative_Layer fill:#BCD65C,stroke:#333
```

2. Component Architecture Detailed relationships between classes within your Python code.

```mermaid
classDiagram
    class Main {
        +calculate_rrf()
        +main()
    }
    class SwaggerParser {
        +process_swagger(file_path)
    }
    class DatabaseService {
        -db_path: str
        +initialize_database()
        +insert_api_doc(doc)
        +search_keyword(query)
        +get_all_count()
    }
    class VectorService {
        -client: QdrantClient
        +ensure_collection()
        +add_points(points)
        +perform_search(query)
    }
    class LocalLLMService {
        -client: AsyncOpenAI
        +create_embedding(text)
        +is_test_request(query)
        +generate_test_case(context, query)
        +completion(messages)
    }

    Main --> SwaggerParser : uses
    Main --> DatabaseService : data management
    Main --> VectorService : semantic search
    Main --> LocalLLMService : classifies and generates
    DatabaseService ..> VectorService : data synchrinization
    VectorService --> LocalLLMService : asks for embedings (nomic)
```

3. Workflow (Data Flow) A sequence diagram illustrating the two main processes: Indexing and Querying (RAG).

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#ffffff',
    'primaryTextColor': '#000000',
    'primaryBorderColor': '#333333',
    'lineColor': '#333333',
    'secondaryColor': '#f4f4f4',
    'tertiaryColor': '#ffffff',
    'noteTextColor': '#000000',
    'noteBkgColor': '#fff5ad',
    'actorTextColor': '#000000',
    'actorLineColor': '#333333',
    'signalColor': '#333333',
    'signalTextColor': '#000000',
    'labelBoxBkgColor': '#ffffff',
    'labelBoxBorderColor': '#333333',
    'loopTextColor': '#000000',
    'sequenceNumberColor': '#ffffff'
  }
} }%%
sequenceDiagram
    autonumber
    
    rect rgb(245, 245, 245)
    Note over User, Qdrant: STEP 1: initialization and Seeding
    User->>Main: start
    Main->>SwaggerParser: process_swagger("swagger.json")
    SwaggerParser-->>Main: documents list (UUID, content, metadata)
    Main->>DatabaseService: insert_api_doc(doc)
    DatabaseService->>SQLite: saves to FTS5 (path, method, tags)
    DatabaseService->>VectorService: add_points(doc)
    VectorService->>LocalLLMService: create_embedding(text)
    LocalLLMService-->>VectorService: vector (768d - nomic)
    VectorService->>Qdrant: saving points (vector + payload)
    end

    rect rgb(235, 245, 255)
    Note over User, LocalLLMService: STEP 2 & 3: Retrieval and Generation
    User->>Main: Query: "How to add a dog?"
    Main->>VectorService: perform_search(query)
    VectorService-->>Main: vector results
    Main->>DatabaseService: search_keyword(query)
    DatabaseService-->>Main: FTS5 results
    Main->>Main: Algorythm RRF (Ranking)
    Main->>LocalLLMService: is_test_request(query)
    LocalLLMService-->>Main: YES
    Main->>LocalLLMService: generate_test_case(Top 3 Context, Query)
    LocalLLMService-->>Main: Robot Framework Code
    Main->>User: Displays results table + generated code
    end
```

4. Schemat Input/Output
Diagram wejść i wyjść systemu.

```mermaid
graph LR
    subgraph Inputs [WEJŚCIE]
        A[swagger.json] --> SYS
        B[User Query / NLP] --> SYS
    end

    subgraph SYS [SYSTEM HYBRID RAG]
        direction TB
        S1[Hybrid Search]
        S2[RRF Re-ranker]
        S3[LLM Reasoner]
    end

    subgraph Outputs [WYJŚCIE]
        SYS --> C[Tabela Metadanych: Metoda, Ścieżka, Score]
        SYS --> D[Kod Robot Framework: RequestsLibrary]
    end

    style SYS fill:#fff,stroke:#333,stroke-width:2px
    style Inputs fill:#eee
    style Outputs fill:#eee
```


Podsumowanie techniczne zawarte w diagramach:
Dual-Storage: Rozdzielenie wyszukiwania na SQLite (FTS5) dla słów kluczowych (np. dokładne nazwy endpointów) i Qdrant dla semantyki (kontekst "dodawania").
Model Embeddingów: Wykorzystanie modelu nomic-embed-text (wymiar 768) realizowane przez LocalLLMService.
Hybrid Search: Połączenie wyników za pomocą RRF (Reciprocal Rank Fusion), co zapewnia, że najbardziej trafne dokumenty z obu silników trafiają do kontekstu LLM.
Generacja: Specjalizacja modelu codellama w generowaniu skryptów dla Robot Framework przy użyciu biblioteki RequestsLibrary.