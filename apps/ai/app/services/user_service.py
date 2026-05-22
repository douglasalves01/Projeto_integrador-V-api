"""User lookup helpers."""

from sqlalchemy.orm import Session

from app.core.exceptions import UserNotFoundError
from app.models.schemas_db import User


def get_user_or_raise(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise UserNotFoundError(user_id)
    return user
