import os
from supabase import create_client, Client
from django.conf import settings

def get_supabase_client() -> Client:
    """
    Get a Supabase client instance using the configuration from settings.
    
    Returns:
        Client: A configured Supabase client instance
    """
    url: str = settings.SUPABASE_URL
    key: str = settings.SUPABASE_KEY
    return create_client(url, key)

# Create a singleton instance
supabase = get_supabase_client()
