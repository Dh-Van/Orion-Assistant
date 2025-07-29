import dotenv, os
from nylas import Client
from typing import Dict, List
from custom_types.message_types import Email
from clients.gemini_client import GeminiClient

dotenv.load_dotenv()

class NylasClient():
    def __init__(self, grant_id: str):
        API_KEY = os.getenv('NYLAS_API_KEY')
        API_URI = os.getenv('NYLAS_API_URI')
        self.grant_id = grant_id

        if not API_KEY or not API_URI: 
            raise ValueError('NYLAS_API_KEY or NYLAS_API_URI not set in environment.')

        self.nylas = Client(
            API_KEY,
            API_URI
        )        
        
        self.llm_client = GeminiClient()

    def read_emails(self, num_emails: int = 100, return_class=False):
        emails = []
        next_cursor = ""

        while len(emails) < num_emails:
            # Minor Fix: The API response object itself is not iterable, .data is.
            response = self.nylas.messages.list(
                identifier=self.grant_id,
                query_params={'limit': 100, 'page_token': next_cursor} # type: ignore
            )

            if not response.data: 
                break
            
            emails.extend([Email(email=msg) for msg in response.data])
            
            next_cursor = response.next_cursor
            if not next_cursor: 
                break
        if(return_class): return emails
        str_output = [str(email) for email in emails]
        return str_output

    
    def keyword_filter(self, email_list: List[Email]) -> List[Email]:
        """
        Filters out emails from senders matching negative keywords.
        """
        NEGATIVE_KEYWORDS = ['noreply', 'no-reply', 'mailinglist', 'support@']

        def is_unwanted(email: Email) -> bool:
            return any(
                # CORRECTED: Access the 'email' key from the sender dictionary before checking for keywords.
                any(keyword in sender_dict.get('email', '').lower() for keyword in NEGATIVE_KEYWORDS)
                for sender_dict in email.senders
            )

        return [email for email in email_list if not is_unwanted(email)]

    
    def search_emails_with_vector_db(self, query: str, query_key: str, num_emails_to_scan: int = 200, num_results: int = 5):
        """
        FIXED: This new method restores the original end-to-end functionality.
        It reads, filters, and then performs a vector search on emails.
        """
        print(f"Reading up to {num_emails_to_scan} emails...")
        all_emails = self.read_emails(num_emails=num_emails_to_scan, return_class=True)
        
        # print(f"Filtering {len(all_emails)} emails...")
        # filtered_emails = self.keyword_filter(all_emails)
        # print(f"Found {len(filtered_emails)} emails after filtering.")
        
        # if not filtered_emails:
        #     return []

        formatted_emails = []
        for email in all_emails:
            formatted_emails.append(email.get_dict()) # type: ignore

        # The llm_client's query_content expects a list of objects and the key to query on.
        return self.llm_client.query_content(
            content_list=formatted_emails, 
            content_key=query_key, 
            query=query, 
            num_results=num_results
        )

    def send_email(self, to: List[Dict[str, str]] | str, subject: str, body: str):
        """
        FIXED: Restores the ability to compose and send a NEW email, like the original `write_email`.
        'to' format: [{'name': 'Jane Doe', 'email': 'jane.doe@example.com'}]
        """
        if(isinstance(to, str)): to = [{'name': to, 'email': to}]
        print(f"Composing email to: {to[0]['email']}")
        draft_response = self.nylas.drafts.create(
            identifier=self.grant_id,
            request_body={
                "to": to, # type: ignore
                "subject": subject,
                "body": body
            }
        )
        
        draft_id = draft_response[0].id
        print(f"Sending draft with ID: {draft_id}")
        sent_message = self.nylas.drafts.send(identifier=self.grant_id, draft_id=draft_id)
        if(sent_message): return True
        return False