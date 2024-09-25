import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

ADMIN_EMAIL = ""
ADMIN_PASSWORD = ""


def init_supabase():
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    supabase: Client = create_client(url, key)
    return supabase


def create_admin(supabase):
    response = supabase.auth.sign_in_with_password(
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    print(response)
    response = supabase.auth.sign_out()


def sign_myself_in(supabase):
    auth_response = supabase.auth.sign_in_with_password(
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    session = auth_response.session
    access_token = session.access_token
    refresh_token = session.refresh_token

    supabase.auth.set_session(access_token=access_token, refresh_token=refresh_token)
    print("myself signed in")
    return auth_response


def sign_out(supabase):
    supabase.auth.sign_out()


if __name__ == "__main__":
    supabase = init_supabase()
    session = sign_myself_in(supabase)
    user_id = session.user.id
    print(user_id)
