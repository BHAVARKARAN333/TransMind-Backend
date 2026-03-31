import os
import firebase_admin
from firebase_admin import credentials, auth, firestore
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Initialize Firebase Admin SDK
cred_path = os.path.join(os.path.dirname(__file__), "firebase-service-account.json")

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Failed to initialize Firebase Admin SDK: {e}")
        # In case the file is missing or invalid, we will let it crash early
        # but we also don't want to prevent the app from starting up if they are debugging
        pass

db = firestore.client() if firebase_admin._apps else None
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verifies the Firebase ID token in the Authorization header."""
    token = credentials.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid'] # Return the user ID
    except Exception as e:
        print(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_db():
    return db
