import os, dotenv
import instructor
import google.genai as genai
from typing import List, Type, TypeVar, Dict, Any
from openai.types.chat import ChatCompletionMessageParam
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from pydantic import BaseModel
from google.genai.types import GenerateContentConfig

T = TypeVar('T', bound = BaseModel)
dotenv.load_dotenv()

class GeminiClient:
    def __init__(self):
        self.GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
        if not self.GOOGLE_API_KEY: raise ValueError('GOOGLE_API_KEY not set')

        self.MODEL = "gemini-2.0-flash"

        self.genai_client: genai.Client = genai.Client(api_key = self.GOOGLE_API_KEY)

        self.instructor_client = instructor.from_genai(
            client=genai.Client(api_key=self.GOOGLE_API_KEY),
            mode = instructor.Mode.GENAI_TOOLS
        )

        self.embedding_client = GoogleGenerativeAIEmbeddings(
            client=self.genai_client,
            model="models/text-embedding-004"
        )

    def generate_output(self, system_instruction: str, prompt: str):
        return self.genai_client.models.generate_content(
            model = self.MODEL,
            config = GenerateContentConfig(system_instruction=system_instruction),
            contents = prompt
        ).text

    def generate_structured_output(self, system_instruction: str, prompt: str, response_model: Type[T]):
        return self.instructor_client.messages.create(
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            model = self.MODEL,
            response_model = response_model
        )
    
    def get_vector_store(self, content_list, content_key: str):
        documents = []

        for content in content_list:
            metadata = content.copy()
            if(content_key not in metadata): raise ValueError(f'Content key {content_key} not in content_list item {metadata}')

            page_content = metadata.get(content_key)
            documents.append(Document(
                page_content=str(page_content),
                metadata=metadata
            ))

        return Chroma.from_documents(documents=documents, embedding=self.embedding_client)
    
    def query_content(self, content_list, content_key, query, num_results: int = 10):
        # print(content_list, content_key)
        vector_store = self.get_vector_store(content_list, content_key)
        output = vector_store.similarity_search_with_score(query, k=num_results)

        return sorted(output, key = lambda x: x[1])