import marshmallow as ma
import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from marshmallow import fields as mf
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from fastapi_muck import FastAPIMuck
from fastapi_muck.app_context import app_context
from fastapi_muck.views import FastAPIMuckApiView

# Create a FastAPI app
app = FastAPI()
SECRET_KEY = "super-secret"
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
muck = FastAPIMuck()
muck.init_app(app)


# Init SQLAlchemy and set database to a local sqlite file.
class Base(DeclarativeBase):
    pass


SQLALCHEMY_DATABASE_URI = "sqlite:///todo_example.db"
engine = create_engine(SQLALCHEMY_DATABASE_URI)
db_session = scoped_session(sessionmaker(bind=engine))


# Create SQLAlchemy database models.
class UserModel(Base):
    """User model to use for authentication."""

    __tablename__ = "user_model"

    id = Column(Integer, primary_key=True, autoincrement=True)


class TodoModel(Base):
    """Simple model to track ToDo items."""

    __tablename__ = "todo_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String, nullable=False)


# Create Marshmallow schemas for serialization.
class TodoSchema(ma.Schema):
    """ToDo model schema that can be used for CRUD operations."""

    id = mf.Integer(required=True, dump_only=True)
    text = mf.String(required=True)


# Add a FastAPI router to organize authentication views.
auth_router = APIRouter(prefix="/auth")


# Load the authenticated user from the session and add login/logout endpoints.
def load_user(request: Request) -> UserModel:
    user_id = request.session.get("_user_id")
    user = db_session.get(UserModel, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401)
    return user


@auth_router.post("/login")
def login_view(request: Request) -> dict:
    """Dummy login view that creates a User and authenticates them."""
    user = UserModel()
    db_session.add(user)
    db_session.commit()
    request.session["_user_id"] = user.id
    return {}


@auth_router.post("/logout")
def logout_view(request: Request) -> dict:
    request.session.pop("_user_id", None)
    return {}


# Add Muck views to generate CRUD REST API.
class BaseApiView(FastAPIMuckApiView):
    """Base view to inherit from. Helpful for setting class variables shared with all API views such as "sqlalchemy_db"
    and "dependencies".
    """

    session = db_session
    dependencies = [Depends(load_user)]


class TodoApiView(BaseApiView):
    """ToDo API view that provides all RESTful CRUD operations."""

    api_name = "todos"
    Model = TodoModel
    ResponseSchema = TodoSchema
    CreateSchema = TodoSchema
    PatchSchema = TodoSchema
    UpdateSchema = TodoSchema
    searchable_columns = [TodoModel.text]


# Register auth router with the app.
app.include_router(auth_router)

if __name__ == "__main__":
    with app_context(app):
        Base.metadata.create_all(engine)
        muck.register_muck_views([TodoApiView])
    uvicorn.run(app)
