import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

from fastapi_muck import FastAPIMuckApiView, FastAPIMuck
from fastapi_muck.app_context import app_context

app = FastAPI()
muck = FastAPIMuck()
muck.init_app(app)


class Base(DeclarativeBase):
    pass


SQLALCHEMY_DATABASE_URI = "sqlite:///todo_example.db"
engine = create_engine(SQLALCHEMY_DATABASE_URI)
db_session = scoped_session(sessionmaker(bind=engine))


class TodoModel(Base):
    __tablename__ = "todo_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String, nullable=False)


class TodoResponseSchema(BaseModel):
    id: int
    text: str


class TodoPayloadSchema(BaseModel):
    text: str


class TodoApiView(FastAPIMuckApiView):
    session = db_session
    api_name = "todos"
    Model = TodoModel
    ResponseSchema = TodoResponseSchema
    CreateSchema = TodoPayloadSchema
    PatchSchema = TodoPayloadSchema
    UpdateSchema = TodoPayloadSchema
    searchable_columns = [TodoModel.text]


if __name__ == "__main__":
    with app_context(app):
        Base.metadata.create_all(engine)
        muck.register_muck_views([TodoApiView])
    uvicorn.run(app)
