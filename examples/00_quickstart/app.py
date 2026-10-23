import marshmallow as ma
import uvicorn
from fastapi import FastAPI
from marshmallow import fields as mf
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

from fastapi_muck import FastAPIMuck
from fastapi_muck import FastAPIMuckApiView
from fastapi_muck.app_context import app_context

# Create a FastAPI app
app = FastAPI()
muck = FastAPIMuck()
muck.init_app(app)


# Init SQLAlchemy and set database to a local sqlite file.
class Base(DeclarativeBase):
    pass


SQLALCHEMY_DATABASE_URI = "sqlite:///todo_example.db"
engine = create_engine(SQLALCHEMY_DATABASE_URI)
db_session = scoped_session(sessionmaker(bind=engine))


# Create SQLAlchemy database models.
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


# Add Muck views to generate CRUD REST API.
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


if __name__ == "__main__":
    with app_context(app):
        Base.metadata.create_all(engine)
        muck.register_muck_views([TodoApiView])
    uvicorn.run(app)
