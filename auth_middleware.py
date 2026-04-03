import os
import json
import firebase_admin
from firebase_admin import credentials, auth, firestore
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Initialize Firebase Admin SDK
# Priority: Environment variable (for cloud deployments) > local file (for development)
db = None

if not firebase_admin._apps:
    try:
        # Try environment variable first (for Render/Cloud deployments)
        firebase_creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        
        if firebase_creds_json:
            print("[FIREBASE] Loading credentials from FIREBASE_SERVICE_ACCOUNT env var...")
            cred_dict = json.loads(firebase_creds_json)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("[FIREBASE] ✓ Initialized from environment variable")
        else:
            # Fall back to local file (for local development)
            cred_path = os.path.join(os.path.dirname(__file__), "firebase-service-account.json")
            if os.path.exists(cred_path):
                print(f"[FIREBASE] Loading credentials from file: {cred_path}")
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                print("[FIREBASE] ✓ Initialized from local file")
            else:
                print("[FIREBASE] ⚠ No credentials found. Running in limited mode.")
                
    except Exception as e:
        print(f"[FIREBASE] ✗ Failed to initialize: {e}")

# Initialize Firestore client only if Firebase was initialized
if firebase_admin._apps:
    try:
        db = firestore.client()
        print("[FIREBASE] ✓ Firestore client ready")
    except Exception as e:
        print(f"[FIREBASE] ✗ Firestore client failed: {e}")

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
