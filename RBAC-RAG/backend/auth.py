import os
import jwt
from jwt import PyJWKClient

SUPABASE_URL = os.environ["SUPABASE_URL"]

jwks_client = PyJWKClient(
    f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
)


def verify_supabase_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        print("JWT header:", header)

        signing_key = jwks_client.get_signing_key_from_jwt(token)
        print("Signing key found")

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            options={"verify_aud": False},
        )

        print("Payload:", payload)
        return payload

    except Exception as e:
        print("JWT verification error:", repr(e))
        raise