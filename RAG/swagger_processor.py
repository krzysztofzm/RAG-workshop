import json
import uuid
from typing import List, Dict, Any

class SwaggerParser:
    def __init__(self, namespace: uuid.UUID):
        self.namespace = namespace

    def process_swagger(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Konwertuje plik swagger.json na płaską listę dokumentów 
        gotowych do zapisu w bazie SQL i wektorowej.
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            swag = json.load(f)
        
        docs = []
        base_path = swag.get('basePath', '')

        # 1. Parsowanie Endpointów (Paths)
        paths = swag.get('paths', {}) #pobieramy slownik z endpointami
        for path, methods in paths.items():
            for method, info in methods.items():
                full_path = f"{base_path}{path}"
                op_id = info.get('operationId', 'n/a')
                tags = ",".join(info.get('tags', []))
                
                # Formatowanie parametrów do tekstu
                params = info.get('parameters', [])
                params_desc = "\n".join([  #comprehension list tworzący opis/string parametrów
                    f"- {p.get('name')} ({p.get('in')}): {p.get('description', '')} "
                    f"[type: {p.get('type', 'any')}]" 
                    for p in params
                ])
                
                # Budowanie czytelnego bloku wiedzy dla RAG
                content = f"API ENDPOINT: {method.upper()} {full_path}\n"
                content += f"Operation ID: {op_id}\n"
                content += f"Summary: {info.get('summary', '')}\n"
                content += f"Description: {info.get('description', '')}\n"
                if params_desc:
                    content += f"Parameters:\n{params_desc}"

                docs.append({
                    "uuid": str(uuid.uuid5(self.namespace, f"path_{method}_{full_path}")),
                    "path": full_path,
                    "method": method.upper(),
                    "operation_id": op_id,
                    "summary": info.get('summary'),
                    "description": info.get('description'),
                    "tags": tags,
                    "content": content,
                    "doc_type": "endpoint"
                })

        # 2. Parsowanie Definicji (Models/Definitions)
        definitions = swag.get('definitions', {})
        for model_name, details in definitions.items():
            props = details.get('properties', {})
            props_desc = "\n".join([
                f"- {name}: {p.get('type', 'object')} ({p.get('description', 'no description')})" 
                for name, p in props.items()
            ])
            
            content = f"DATA MODEL / SCHEMA: {model_name}\n"
            content += f"Description: {details.get('description', 'Model defining ' + model_name)}\n"
            content += f"Properties:\n{props_desc}"

            docs.append({
                "uuid": str(uuid.uuid5(self.namespace, f"model_{model_name}")),
                "path": f"Model: {model_name}",
                "method": "SCHEMA",
                "operation_id": model_name,
                "summary": f"Data structure for {model_name}",
                "description": details.get('description', ''),
                "tags": "definitions",
                "content": content,
                "doc_type": "schema"
            })
            
        return docs