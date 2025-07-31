"""
Google AI (Gemini) client for LLM operations and vector search.
Extracted and cleaned from gemini_client.py
"""

import os
from typing import List, Type, TypeVar, Dict, Any, Optional, Tuple
import instructor
import google.genai as genai
from google.genai.types import GenerateContentConfig
from pydantic import BaseModel
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from loguru import logger

T = TypeVar('T', bound=BaseModel)

class GeminiClient:
    """Client for Google AI (Gemini) operations including LLM and embeddings."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        """
        Initialize Gemini client.
        
        Args:
            api_key: Optional API key (defaults to env var)
            model: Model name to use
        """
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError('GOOGLE_API_KEY not provided or set in environment')
        
        self.model = model
        
        # Initialize Gemini client
        self.client = genai.Client(api_key=self.api_key)
        
        # Initialize instructor client for structured output
        self.instructor_client = instructor.from_genai(
            client=genai.Client(api_key=self.api_key),
            mode=instructor.Mode.GENAI_TOOLS
        )
        
        # Initialize embeddings client
        self.embedding_client = GoogleGenerativeAIEmbeddings(
            client=self.client,
            model="models/text-embedding-004"
        )
        
        logger.info(f"Initialized Gemini client with model: {model}")
    
    def generate_response(
        self, 
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Generate a text response from the LLM.
        
        Args:
            prompt: User prompt
            system_instruction: Optional system instruction
            temperature: Response randomness (0-1)
            max_tokens: Maximum response length
            
        Returns:
            Generated text response
        """
        try:
            config = GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_instruction
            )
            
            if max_tokens:
                config.max_output_tokens = max_tokens
            
            response = self.client.models.generate_content(
                model=self.model,
                config=config,
                contents=prompt
            )
            
            return response.text
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise
    
    def generate_structured_output(
        self,
        prompt: str,
        response_model: Type[T],
        system_instruction: Optional[str] = None
    ) -> T:
        """
        Generate structured output using a Pydantic model.
        
        Args:
            prompt: User prompt
            response_model: Pydantic model class for response structure
            system_instruction: Optional system instruction
            
        Returns:
            Instance of response_model with generated data
        """
        try:
            messages = []
            
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            
            messages.append({"role": "user", "content": prompt})
            
            return self.instructor_client.messages.create(
                messages=messages,
                model=self.model,
                response_model=response_model
            )
            
        except Exception as e:
            logger.error(f"Error generating structured output: {e}")
            raise
    
    def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Create embeddings for a list of texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        try:
            if not texts:
                return []
            
            # Batch process for efficiency
            embeddings = self.embedding_client.embed_documents(texts)
            logger.debug(f"Created embeddings for {len(texts)} texts")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Error creating embeddings: {e}")
            raise
    
    def create_embedding(self, text: str) -> List[float]:
        """
        Create embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        try:
            embedding = self.embedding_client.embed_query(text)
            return embedding
            
        except Exception as e:
            logger.error(f"Error creating embedding: {e}")
            raise
    
    def search_with_vectors(
        self,
        content_list: List[Dict[str, Any]],
        content_key: str,
        query: str,
        num_results: int = 10,
        metadata_fields: Optional[List[str]] = None
    ) -> List[Tuple[Document, float]]:
        """
        Perform vector similarity search on content.
        
        Args:
            content_list: List of content dictionaries
            content_key: Key in dict containing searchable text
            query: Search query
            num_results: Number of results to return
            metadata_fields: Additional fields to include in metadata
            
        Returns:
            List of (Document, score) tuples sorted by relevance
        """
        try:
            if not content_list:
                return []
            
            # Validate content key exists
            if not all(content_key in item for item in content_list):
                raise ValueError(f"Content key '{content_key}' not found in all items")
            
            # Create documents
            documents = []
            for item in content_list:
                # Get the searchable content
                page_content = str(item.get(content_key, ""))
                
                # Build metadata
                metadata = item.copy()
                
                # Filter metadata fields if specified
                if metadata_fields:
                    metadata = {k: v for k, v in metadata.items() if k in metadata_fields}
                
                documents.append(Document(
                    page_content=page_content,
                    metadata=metadata
                ))
            
            # Create vector store
            vector_store = Chroma.from_documents(
                documents=documents,
                embedding=self.embedding_client
            )
            
            # Perform search
            results = vector_store.similarity_search_with_score(
                query, 
                k=num_results
            )
            
            # Sort by score (lower is better for Chroma)
            results = sorted(results, key=lambda x: x[1])
            
            logger.info(f"Found {len(results)} results for query: '{query}'")
            
            # Clean up vector store
            vector_store.delete_collection()
            
            return results
            
        except Exception as e:
            logger.error(f"Error in vector search: {e}")
            raise
    
    def search_emails_with_vectors(
        self,
        emails: List[Dict[str, Any]],
        query: str,
        search_field: str = "body",
        num_results: int = 5
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Search emails using vector similarity.
        
        Args:
            emails: List of email dictionaries
            query: Search query
            search_field: Field to search ('body', 'subject', or 'all')
            num_results: Number of results
            
        Returns:
            List of (email_dict, score) tuples
        """
        try:
            # Prepare content for vector search
            if search_field == "all":
                # Combine subject and body for search
                search_content = []
                for email in emails:
                    combined = f"{email.get('subject', '')} {email.get('body', '')}"
                    email_copy = email.copy()
                    email_copy['_search_content'] = combined
                    search_content.append(email_copy)
                content_key = '_search_content'
            else:
                search_content = emails
                content_key = search_field
            
            # Perform vector search
            results = self.search_with_vectors(
                content_list=search_content,
                content_key=content_key,
                query=query,
                num_results=num_results,
                metadata_fields=['id', 'subject', 'senders', 'date']
            )
            
            # Convert back to email format
            email_results = []
            for doc, score in results:
                email_dict = doc.metadata
                # Remove temporary search content if added
                email_dict.pop('_search_content', None)
                email_results.append((email_dict, score))
            
            return email_results
            
        except Exception as e:
            logger.error(f"Error searching emails with vectors: {e}")
            return []
    
    def summarize_text(
        self,
        text: str,
        max_length: int = 150,
        style: str = "concise"
    ) -> str:
        """
        Summarize text for voice output.
        
        Args:
            text: Text to summarize
            max_length: Maximum summary length in words
            style: Summary style ('concise', 'detailed', 'bullet_points')
            
        Returns:
            Summarized text
        """
        try:
            style_instructions = {
                "concise": "Provide a brief, concise summary suitable for voice output.",
                "detailed": "Provide a comprehensive summary with key details.",
                "bullet_points": "Provide a summary as clear bullet points."
            }
            
            instruction = style_instructions.get(style, style_instructions["concise"])
            
            prompt = f"""
            {instruction}
            Maximum {max_length} words.
            Text to summarize:
            
            {text}
            """
            
            return self.generate_response(
                prompt=prompt,
                system_instruction="You are a helpful assistant that creates clear, voice-friendly summaries.",
                temperature=0.3
            )
            
        except Exception as e:
            logger.error(f"Error summarizing text: {e}")
            return text[:500] + "..."  # Fallback to truncation
    
    def generate_email_reply(
        self,
        original_email: str,
        instruction: str,
        tone: str = "professional"
    ) -> str:
        """
        Generate an email reply based on context.
        
        Args:
            original_email: The email to reply to
            instruction: User's instruction for the reply
            tone: Reply tone ('professional', 'friendly', 'formal', 'casual')
            
        Returns:
            Generated reply text
        """
        try:
            tone_instructions = {
                "professional": "professional and courteous",
                "friendly": "warm and friendly",
                "formal": "formal and respectful",
                "casual": "casual and conversational"
            }
            
            tone_desc = tone_instructions.get(tone, "professional and courteous")
            
            prompt = f"""
            Generate an email reply based on the following:
            
            Original Email:
            {original_email}
            
            User Instruction:
            {instruction}
            
            Write a {tone_desc} reply that addresses the user's instruction.
            Do not include subject line or email headers, just the body text.
            """
            
            return self.generate_response(
                prompt=prompt,
                system_instruction="You are an expert email writer who crafts clear, appropriate responses.",
                temperature=0.7
            )
            
        except Exception as e:
            logger.error(f"Error generating email reply: {e}")
            raise