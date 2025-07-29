from nylas.models.messages import Message
from typing import List, Optional, Dict

class Email():
    id: str
    senders: List[Dict[str, str]]
    recipients: List[Dict[str, str]]
    subject: str
    body: str
    date: int

    def __init__(self, email: Optional[Message] = None, 
                 senders: Optional[List[Dict[str, str]]] = None, 
                 recipients: Optional[List[Dict[str, str]]] = None, 
                 subject: Optional[str] = None, 
                 body: Optional[str] = None, 
                 date: Optional[int] = None, 
                 msg_id: Optional[str] = None) -> None:
        
        # --- FIXED: Rewritten constructor for robustness ---
        
        # 1. Initialize all attributes to default values first.
        self.id = ""
        self.senders = []
        self.recipients = []
        self.subject = ""
        self.body = ""
        self.date = 0

        # 2. If a Nylas Message object is provided, populate from it.
        if email:
            self.id = email.id or ""
            if email.from_:
                self.senders = email.from_
            if email.to:
                self.recipients.extend(email.to)
            if email.cc:
                self.recipients.extend(email.cc)
            if email.bcc:
                self.recipients.extend(email.bcc)
            self.subject = email.subject or ""
            self.body = email.body or ""
            self.date = email.date or 0
        # 3. Otherwise, populate from any provided keyword arguments.
        else:
            if msg_id is not None: self.id = msg_id
            if senders is not None: self.senders = senders
            if recipients is not None: self.recipients = recipients
            if subject is not None: self.subject = subject
            if body is not None: self.body = body
            if date is not None: self.date = date
            
    def get_reply_recipients(self) -> List[Dict[str, str]]:
        """
        Returns the original senders, formatted to be used as recipients in a reply.
        """
        return self.senders

    def __str__(self) -> str:
        """Provides a more detailed string representation for easy debugging."""
        sender_emails = [s.get('email', 'N/A') for s in self.senders]
        recipient_emails = [r.get('email', 'N/A') for r in self.recipients]
        return f"ID: {self.id}\nFrom: {sender_emails}\nTo: {recipient_emails}\nSubject: {self.subject}"
    
    def get_dict(self):
        return {
            'id': self.id,
            'senders': self.senders[0]['email'],
            'recipients': self.recipients[0]['email'],
            'subject': self.subject,
            'body': self.body,
            'date': self.date
        }