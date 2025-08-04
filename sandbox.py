import dotenv, os

dotenv.load_dotenv('.credentials.env')
creds = os.getenv('GOOGLE_CREDENTIALS')
print(creds)