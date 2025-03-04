import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Flask configuration
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')