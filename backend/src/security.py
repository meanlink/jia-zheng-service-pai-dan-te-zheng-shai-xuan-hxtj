import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .models import Role

SECRET = os.environ['JWT_SECRET']
bearer = HTTPBearer(auto_error=False)


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
    return f'{salt}:{digest.hex()}'


def verify_password(password, password_hash):
    return hmac.compare_digest(hash_password(password, password_hash.split(':')[0]), password_hash)


def issue_token(user):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {'sub': user['username'], 'role': user['role'], 'name': user['display_name'],
         'iat': now, 'exp': now + timedelta(hours=8), 'iss': 'home-service-dispatch'},
        SECRET, algorithm='HS256',
    )


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise HTTPException(401, '请先登录')
    try:
        payload = jwt.decode(credentials.credentials, SECRET, algorithms=['HS256'],
                             issuer='home-service-dispatch', options={'require': ['sub', 'iat', 'exp']})
        payload['role'] = Role(payload['role'])
        return payload
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(401, '登录已过期，请重新登录') from exc


def permits(*roles):
    def check(user=Depends(current_user)):
        if user['role'] not in roles:
            raise HTTPException(403, '当前角色没有此操作权限')
        return user
    return check
