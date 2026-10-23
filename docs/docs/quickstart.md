# Quick Start

FastAPI-Muck provides standard REST APIs for resources in your FastAPI/SqlAlchemy application. This 
is accomplishing by creating subclasses of the FastAPIMuckApiView and configuring them by setting a series of class
variables.

The quick start guide will walk you through creating your first basic API. The subsequent chapters cover using the APIs and configuring advanced features.


## Define a base view
FastAPI-Muck works by subclassing the FastAPIMuckApiView and setting class variables on the concrete view classes. In almost 
all projects there will be a basic set of class variables shared by all FastAPIMuckApiView subclasses. The two most common 
settings to be shared across all views is the database session used for committing changes and a set of 
dependencies that should be applied to all views.

In this example a base class is defined with the app's database session and authentication dependency set.

Application importing an existing [SqlAlchemy](https://docs.sqlalchemy.org/en/20/orm/contextual.html) session setup:
```python
from fastapi import Depends
from fastapi_muck import FastAPIMuckApiView
from myapp.database import db_session 
from myapp.auth.dependencies import load_user


class BaseApiView(FastAPIMuckApiView):
    session = db_session
    dependencies = [Depends(load_user)]

```

Application creating the [SqlAlchemy](https://docs.sqlalchemy.org/en/20/orm/contextual.html) session directly:
```python
from fastapi import Depends
from fastapi_muck import FastAPIMuckApiView
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from myapp.auth.dependencies import load_user

engine = create_engine("sqlite:///todo_example.db")
db_session = scoped_session(sessionmaker(bind=engine))


class BaseApiView(FastAPIMuckApiView):
    session = db_session
    dependencies = [Depends(load_user)]
```

!!! note
    For the remainder of this guide we'll assume usage of the [SqlAlchemy](https://docs.sqlalchemy.org/en/20/orm/contextual.html) scoped session shown above.

## Create SQLAlchemy Model
FastAPI-Muck requires the use of SQLAlchemy's [declarative system](https://docs.sqlalchemy.org/en/20/orm/quickstart.html). If you are not using the declarative system, you will need to review those [docs](https://docs.sqlalchemy.org/en/20/orm/quickstart.html) and re-evaluate whether FastAPI-Muck is the right choice for your project. Explaining the full process of creating and registering a SQLAlchemy model in your FastAPI app is outside the scope of this guide. The example code below shows the model class we will be creating an API for in the rest of the guide.

```python
from sqlalchemy import Column, Integer, String

from myapp import Base

class Teacher(Base):
    __tablename__ = "teacher"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    years_teaching = Column(Integer)
```

## Create Request and Response Schemas
FastAPI-Muck requires configuring Marshmallow and/or Pydantic classes that will be used to validate the payload data for 
the Create, Update, Patch, and (optionally) Delete endpoints. Additionally, a schema must be supplied that will 
serialize the endpoint's resource in responses. In this example, a simple schema is defined that can be re-used for 
all validation and serialization. In this example you'll be defining [Marshmallow](https://marshmallow.readthedocs.io/en/stable/)
schemas. 

!!! tip
    In v0.2.0 and higher, Pydantic models can also be used as schemas. You can see an example app using Pydantic models
    [here](https://github.com/dtiesling/flask-muck/tree/main/examples/02_pydantic)

```python
from marshmallow import Schema, fields as mf

class TeacherSchema(Schema):
    id = mf.Integer(dump_only=True)
    name = mf.String(required=True)
    years_teaching = mf.Integer()
```

## Create Concrete FastAPIMuckApiView
Inherit from the project's base API view class and define the required class variables.

```python
class TeacherApiView(BaseApiView):
    api_name = "teachers" #(1)!
    Model = Teacher #(2)!
    ResponseSchema = TeacherSchema #(3)!
    CreateSchema = TeacherSchema #(4)!
    PatchSchema = TeacherSchema #(5)!
    UpdateSchema = TeacherSchema #(6)!
    searchable_columns = [Teacher.name] #(7)!
```

1. Name used as the URL endpoint in the REST API.
2. Model class that will be queried and updated by this API.
3. Marshmallow schema used to serialize Teachers returned by the API.
4. Marshmallow schema used to validate payload data sent to the Create endpoint.
5. Marshmallow schema used to validate payload data sent to the Patch endpoint.
6. Marshmallow schema used to validate payload data sent to the Update endpoint.
7. List of model columns that can be searched when listing Teachers using the API.

## Register the FastAPIMuckApiViews
There are two options for registering the CRUD views. FastAPIMuck can be initialized as a FastAPI extension or each 
FastAPIMuckApiView can be added to an existing FastAPI APIRouter. 

### Initialize FastAPIMuck extension.
The FastAPIMuck extension is the "batteries included" approach and handles registering all of your views to a single 
API url root. Optionally the extension generates an OpenAPI spec definition and host a Swagger UI page.

```python
from fastapi import FastAPI

from fastapi_muck import FastAPIMuck

app = FastAPI(
    MUCK_API_URL_PREFIX="/api/",
    MUCK_APIDOCS_ENABLED=True,
    MUCK_API_TITLE="School App API",
)
muck = FastAPIMuck(app)
muck.register_muck_views([TeacherApiView], app=app)
```

### OR

### Manually register FastAPIMuckApiViews
Manually registering each FastAPIMuckApiView is an escape hatch to allow greater flexibility to work with existing 
views in an app and other frameworks and extensions.

A class method is included that handles adding all necessary rules to the given APIRouter.

```python
from fastapi import APIRouter

from myapp import app

router = APIRouter(prefix="/api")
TeacherApiView.add_rules_to_router(router)
app.include_router(router)
```

## Success!

The following views are generated for a standard REST API:

| URL Path                    | Method | Description                                                                                                |
|-----------------------------|--------|------------------------------------------------------------------------------------------------------------|
| /api/teachers/              | GET    | List all teachers - querystring options available for sorting, filtering, searching, and pagination        |
| /api/teachers/              | POST   | Create a teacher                                                                                           |
| /api/teachers/<TEACHER_ID\> | GET    | Fetch a single teacher                                                                                     |
| /api/teachers/<TEACHER_ID\> | PUT    | Update a single teacher                                                                                    |
| /api/teachers/<TEACHER_ID\> | PATCH  | Patch a single teacher                                                                                     |
| /api/teachers/<TEACHER_ID\> | DELETE | Delete a single teacher                                                                                    |
| /apidocs/                   | GET    | Swagger UI browsable API documentation page (Only available if FastAPIMuck extension used to register views) |


