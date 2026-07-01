from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import create_access_token, get_password_hash, verify_password

router = APIRouter()

# тестовая БД пользователей (in-memory)
fake_users_db = {}


class UserCreate(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


@router.post("/register")
def register(user: UserCreate):
    if user.username in fake_users_db:
        raise HTTPException(status_code=400, detail="User already registered")
    role = "manager"
    if user.username == "chief":
        role = "chief"
    elif user.username == "analyst":
        role = "analyst"

    fake_users_db[user.username] = {
        "username": user.username,
        "hashed_password": get_password_hash(user.password),
        "role": role,
    }
    return {"msg": "User created successfully"}


@router.post("/login")
def login(user: UserLogin):
    db_user = fake_users_db.get(user.username)
    if not db_user or not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    role = db_user.get("role", "manager")
    access_token = create_access_token(data={"sub": user.username, "role": role})
    return {"access_token": access_token, "token_type": "bearer"}
