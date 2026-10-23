import marshmallow as ma
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from marshmallow import fields as mf
from pydantic import BaseModel
from sqlalchemy import Column, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, relationship, scoped_session
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from fastapi_muck import FastAPIMuckCallback, FastAPIMuck, install_error_pages
from fastapi_muck.responses import MuckJSONResponse
from fastapi_muck.views import FastAPIMuckApiView

SECRET_KEY = "super-secret"
SQLALCHEMY_DATABASE_URI = "sqlite:///todo_example.db"


# Init SQLAlchemy and set database to a local sqlite file.
class Base(DeclarativeBase):
    pass


class Database:
    """Minimal stand-in for the ORM integration a Flask extension used to provide.

    FastAPI ships no ORM binding, so the engine and session are owned here. The
    session is scoped to a constant so the request-handling thread the test
    client spawns shares the session the test body writes through.
    """

    def __init__(self) -> None:
        self.engine = create_engine(
            SQLALCHEMY_DATABASE_URI, connect_args={"check_same_thread": False}
        )
        self.session = scoped_session(
            sessionmaker(bind=self.engine, expire_on_commit=False),
            scopefunc=lambda: None,
        )

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)


db = Database()
Base.query = db.session.query_property()


# Create SQLAlchemy database models.
class UserModel(Base):
    """User model to use for authentication."""

    __tablename__ = "user_model"
    id = Column(Integer, primary_key=True, autoincrement=True)


class FamilyModel(Base):
    __tablename__ = "family_model"
    id = Column(Integer, primary_key=True, autoincrement=True)
    surname = Column(String, nullable=False)


class GuardianModel(Base):
    __tablename__ = "guardian_model"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    age = Column(Integer, nullable=True)
    family_id = Column(Integer, ForeignKey(FamilyModel.id))
    family = relationship(FamilyModel)
    children: Mapped[list["ChildModel"]] = relationship()


class ChildModel(Base):
    __tablename__ = "child_model"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=True)
    family_id = Column(Integer, ForeignKey(FamilyModel.id))
    guardian_id = Column(Integer, ForeignKey(GuardianModel.id))
    guardian = relationship(GuardianModel, back_populates="children")
    toy: Mapped["ToyModel"] = relationship(uselist=False)


class ToyModel(Base):
    __tablename__ = "toy_model"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    family_id = Column(Integer, ForeignKey(FamilyModel.id))
    child_id = Column(Integer, ForeignKey(ChildModel.id))
    child = relationship(ChildModel, back_populates="toy")


class GuardianSchema(BaseModel):
    name: str


class ChildSchema(ma.Schema):
    name = mf.String(required=True)
    guardian_id = mf.Integer(required=True, load_only=True)


class GuardianDetailSchema(ma.Schema):
    name = mf.String(required=True)
    children = mf.Nested(ChildSchema, many=True)


class ToySchema(ma.Schema):
    name = mf.String(required=True)
    child_id = mf.Integer(required=True, load_only=True)


auth_router = APIRouter()


def load_user(request: Request) -> UserModel:
    user_id = request.session.get("_user_id")
    user = db.session.get(UserModel, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401)
    return user


def login_required(user: UserModel = Depends(load_user)) -> UserModel:
    return user


@auth_router.post("/login")
def login_view(request: Request) -> MuckJSONResponse:
    """Dummy login view that creates a User and authenticates them."""
    user = UserModel()
    db.session.add(user)
    db.session.commit()
    request.session["_user_id"] = user.id
    return MuckJSONResponse({}, 200, debug=request.app.debug)


@auth_router.post("/logout")
def logout_view(request: Request) -> MuckJSONResponse:
    request.session.pop("_user_id", None)
    return MuckJSONResponse({}, 200, debug=request.app.debug)


# Add Muck views to generate CRUD REST API.
class PreCallback(FastAPIMuckCallback):
    def execute(self) -> None:
        return


class PostCallback(FastAPIMuckCallback):
    def execute(self) -> None:
        return


class BaseApiView(FastAPIMuckApiView):
    """Base view to inherit from. Helpful for setting class variables shared with all API views such as "sqlalchemy_db"
    and "dependencies".
    """

    session = db.session
    dependencies = [Depends(login_required)]
    pre_create_callbacks = [PreCallback]
    pre_update_callbacks = [PreCallback]
    pre_patch_callbacks = [PreCallback]
    pre_delete_callbacks = [PreCallback]
    post_create_callbacks = [PostCallback]
    post_update_callbacks = [PostCallback]
    post_patch_callbacks = [PostCallback]
    post_delete_callbacks = [PostCallback]


class GuardianApiView(BaseApiView):
    api_name = "guardians"
    Model = GuardianModel
    ResponseSchema = GuardianSchema
    CreateSchema = GuardianSchema
    PatchSchema = GuardianSchema
    UpdateSchema = GuardianSchema
    DetailSchema = GuardianDetailSchema
    searchable_columns = [GuardianModel.name, GuardianModel.age]


class ChildApiView(BaseApiView):
    api_name = "children"
    Model = ChildModel
    ResponseSchema = ChildSchema
    CreateSchema = ChildSchema
    PatchSchema = ChildSchema
    UpdateSchema = ChildSchema
    parent = GuardianApiView
    searchable_columns = [ChildModel.name]


class ToyApiView(BaseApiView):
    api_name = "toy"
    Model = ToyModel
    ResponseSchema = ToySchema
    CreateSchema = ToySchema
    PatchSchema = ToySchema
    UpdateSchema = ToySchema
    parent = ChildApiView
    one_to_one_api = True


def create_app(use_extension: bool = True) -> FastAPI:
    app = FastAPI(debug=True)
    app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
    # The login route is registered on both branches. Flask-Login shipped a test
    # client that forged an authenticated session without one; the ASGI test
    # client has no such hook, so the session cookie has to be earned.
    app.include_router(auth_router)
    if use_extension:
        muck = FastAPIMuck(app)
        muck.register_muck_views(
            [GuardianApiView, ChildApiView, ToyApiView], app=app
        )
    else:
        # Without the extension there is nothing to install the error pages and
        # the slash redirect, which the original framework supplied to every app
        # whether or not the library was in use.
        install_error_pages(app)
        api_router = APIRouter()
        GuardianApiView.add_rules_to_router(api_router)
        ChildApiView.add_rules_to_router(api_router)
        ToyApiView.add_rules_to_router(api_router)
        app.include_router(api_router)
    return app
