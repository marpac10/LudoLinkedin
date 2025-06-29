from supabase import create_client

SUPABASE_URL = "https://kfyihmqughvjgdioyunu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtmeWlobXF1Z2h2amdkaW95dW51Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTA4ODM2MzMsImV4cCI6MjA2NjQ1OTYzM30.QB-bdTWKchIJPQNQ119zx5Smc20YbUoArtFgWadeGqs"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
