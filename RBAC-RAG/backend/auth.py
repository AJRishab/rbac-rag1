import os
import jwt
from jwt import PyJWKClient

SUPABASE_URL = os.environ["SUPABASE_URL"]

jwks_client = PyJWKClient(
    f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
)

def verify_supabase_token(token: str):
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256"],
        audience="authenticated",
    )

    return payload