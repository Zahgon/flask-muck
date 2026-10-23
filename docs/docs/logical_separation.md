# Supporting Logical Data Separation (Multi-tenancy)

A common architecture in web applications is multi-tenancy through logical separation. `FastAPIMuckApiView` includes a method, `get_base_query_kwargs`, which can be overridden to generate a set of arguments passed to all queries. This method enables filtering of resources to those available to a user, preventing resource leakage between tenants.

The `get_base_query_kwargs` should return a dictionary of keyword arguments. These kwargs are applied to CRUD operations at the SqlAlchemy level. For example, the GET /<resource\>/ endpoint will generate the query `Model.query.filter_by(**get_base_query_kwargs()).all()` instead of `Model.query.all()`. The keyword arguments are also applied when creating or updating a model.

```python
from fastapi_muck import FastAPIMuckApiView
from myapp.auth.dependencies import load_user

class MyApiView(FastAPIMuckApiView):
    ...
    
    def get_base_query_kwargs(self):
        return {"organization_id": load_user(self.request).organization_id}#(1)!
```

1. Assumes the resource has an `organization_id` column and it will be filtered by the current user's organization ID.

## Example Usage

!!! note
    This example builds upon the [quickstart](quickstart.md) example. It will be more comprehensible if you have read through the [quickstart](quickstart.md).

Imagine a customer support platform where each user belongs to a single organization. Nearly all resources in the application are associated with an organization, and users should only access resources within their organization.

The SqlAlchemy models might look like this:

```python title="myapp/models.py"
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from myapp import Base

class Organization(Base):
    """Customer support organization containing users and support tickets."""
    __tablename__ = "organization"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    
class User(Base):
    """User responsible for responding to support tickets in their organization."""
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    organization_id = Column(ForeignKey(Organization.id))
    organization = relationship(Organization)

class SupportTicket(Base):
    """Support ticket submitted for an organization."""
    __tablename__ = "support_ticket"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_number = Column(Integer, nullable=False)
    organization_id = Column(ForeignKey(Organization.id))
    organization = relationship(Organization)

class NewsfeedItem(Base):
    """Newsfeed item with platform information (e.g., release notes), available to all users regardless of organization."""
    __tablename__ = "newsfeed_item"
    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String, nullable=False)
```

Since we have views that need to be filtered by organization and others that do not, two base classes will be created:

```python title="myapp/baseviews.py"
from fastapi import Depends
from fastapi_muck import FastAPIMuckApiView
from myapp import db_session
from myapp.auth.dependencies import load_user

class BaseApiView(FastAPIMuckApiView):
    session = db_session
    dependencies = [Depends(load_user)]#(1)!

class OrganizationResourceApiView(BaseApiView):
    def get_base_query_kwargs(self):
        return {"organization_id": load_user(self.request).organization_id}#(2)!
```

1. The `load_user` dependency enforces user authentication.
2. The `load_user` dependency provides access to the current user, allowing views to filter by the current organization.

Now, simply choose the appropriate base view class based on whether the resource should be filtered by the current user's organization:

```python title="views.py"
from myapp.baseviews import BaseApiView, OrganizationResourceApiView
from myapp.models import SupportTicket, NewsfeedItem

class SupportTicketsApiView(OrganizationResourceApiView):
    Model = SupportTicket
    ...#(1)!

class NewsfeedItemApiview(BaseApiView):
    Model = NewsfeedItem
    ...#(2)!
```

1. The remainder of the `SupportTicketsApiView` configuration goes here.
2. The remainder of the `NewsfeedItemApiview` configuration goes here.