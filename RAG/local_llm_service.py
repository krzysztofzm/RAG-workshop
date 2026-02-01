import os
import tiktoken
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

class LocalLLMService:
    def __init__(self):
        # Ollama provides an OpenAI-compatible API on port 11434.
        self.client = AsyncOpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama" # Value required by the library, but ignored by Ollama.
        )
        self.tokenizers = {}

    def get_tokenizer(self, model_name: str = "gpt-4o"):
        if model_name not in self.tokenizers:
            try:
                self.tokenizers[model_name] = tiktoken.encoding_for_model(model_name)
            except:
                self.tokenizers[model_name] = tiktoken.get_encoding("cl100k_base")
        return self.tokenizers[model_name]

    async def create_embedding(self, text: str) -> List[float]:
        """Generates a local embedding using the Nomic model (768 dimensions)."""
        try:
            response = await self.client.embeddings.create(
                model="nomic-embed-text",
                input=text
            )
            return response.data[0].embedding  # We only return the embedding of the first element—why? We need to check what response.data contains.
        except Exception as e:
            print(f"Local embedding failure: {e}")
            raise

    async def completion(self, messages: List[Dict[str, str]], model: str = "llama3.2") -> Any:
        """Local text generation"""
        try:
            return await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0
            )
        except Exception as e:
            print(f"Local generation error: {e}")
            raise
    
    async def is_test_request(self, query: str) -> bool:
        """Checks if the user is requesting code or test generation."""
        prompt = f"""Analyze the user query. Is the user asking to write, create, or generate an automation test, 
        a test case, or Robot Framework code? Answer only 'YES' or 'NO'.
        
        Query: {query}
        Answer:"""
        
        resp = await self.completion([{"role": "user", "content": prompt}])
        answer = resp.choices[0].message.content.strip().upper()
        return "YES" in answer
    
    async def generate_test_case(self, context: str, query: str):
        system_prompt = """
        You are a QA Automation Expert. Use the provided API documentation to write a Robot Framework test case.
        Use 'RequestsLibrary'. 
        Follow these rules:
        1. Include the 'Settings' section with Library RequestsLibrary.
        2. Include 'Variables' section if needed.
        3. Write a clear 'Test Case'.
        4. Use keywords like 'Create Session', 'GET On Session', 'POST On Session', 'Status Should Be'.
        5. Return ONLY the code, no explanations.
        """
        
        user_prompt = f"""
        API Documentation Context:
        {context}
        
        User Request:
        {query}
        
        Robot Framework Code:
        """
        
        response = await self.client.chat.completions.create(
            model="codellama",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1 # Low temperature for stable code generation
        )
        return response.choices[0].message.content