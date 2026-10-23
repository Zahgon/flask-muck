import marshmallow as ma
import uvicorn
from fastapi import APIRouter, FastAPI
from marshmallow import fields as mf
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

from fastapi_muck import FastAPIMuckApiView, install_error_pages

app = FastAPI()
# Without the FastAPIMuck extension, give the app the error pages and url handling the generated views expect.
install_error_pages(app)


class Base(DeclarativeBase):
    pass


SQLALCHEMY_DATABASE_URI = "sqlite:///todo_example.db"
engine = create_engine(SQLALCHEMY_DATABASE_URI)
db_session = scoped_session(sessionmaker(bind=engine))


class TodoModel(Base):
    __tablename__ = "todo_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String, nullable=False)


class TodoSchema(ma.Schema):
    """ToDo model schema that can be used for CRUD operations."""

    id = mf.Integer(required=True, dump_only=True)
    text = mf.String(required=True)


class BaseApiView(FastAPIMuckApiView):
    """Base view to inherit from. Helpful for setting class variables shared with all API views such as "session"
    and "dependencies".
    """

    session = db_session


class TodoApiView(BaseApiView):
    """ToDo API view that provides all RESTful CRUD operations."""

    api_name = "todos"
    Model = TodoModel
    ResponseSchema = TodoSchema
    CreateSchema = TodoSchema
    PatchSchema = TodoSchema
    UpdateSchema = TodoSchema
    searchable_columns = [TodoModel.text]


# This is the existing api router where all other routes are registered.
api_router = APIRouter()

# Use add_rules_to_router classmethod on the FastAPIMuckApiView to add all the CRUD route rules to the existing router.
TodoApiView.add_rules_to_router(api_router)

app.include_router(api_router)

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    uvicorn.run(app)
