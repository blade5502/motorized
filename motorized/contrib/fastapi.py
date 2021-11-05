from fastapi import status, Query
from fastapi.routing import APIRouter
from fastapi.exceptions import HTTPException

from pydantic import BaseModel
from pydantic.types import NonNegativeInt
from motorized import QuerySet, Document
from motorized.types import InputObjectId
from typing import Type, Literal, Any, List, Optional


Action = Literal["create", "list", "delete", "patch", "put", "retrive"]


class RestApiView:
    queryset: QuerySet
    actions = [
        ('create', '', 'POST', status.HTTP_201_CREATED),
        ('list', '', 'GET', status.HTTP_200_OK),
        ('retrieve', '/{id}', 'GET', status.HTTP_200_OK),
        ('delete', '/{id}', 'DELETE', status.HTTP_204_NO_CONTENT),
        ('patch', '/{id}', 'PATCH', status.HTTP_200_OK),
        ('put', '/{id}', 'PATCH', status.HTTP_200_OK),
    ]

    @property
    def model(self) -> Type[Document]:
        return self.queryset.model

    @property
    def read_model(self) -> BaseModel:
        return self.model

    def register(self, router: APIRouter) -> None:
        for action, path, method, status_code in self.actions:
            if not self.is_implemented(action):
                continue
            router.add_api_route(
                path=path,
                endpoint=getattr(self, action),
                response_model=self.get_response_model(action),
                methods=[method],
                status_code=status_code,
            )

    def get_response_model(self, action: Action) -> Type[BaseModel]:
        try:
            return getattr(self, action).__annotations__['return']
        except KeyError:
            if action == 'list':
                return List[self.model]
            if action == 'delete':
                return None
            return self.model

    def is_implemented(self, action: Action) -> bool:
        try:
            return callable(getattr(self, action))
        except AttributeError:
            return False



class GenericApiView(RestApiView):
    def __init__(self):
        updater = self.model.get_updater_model()
        self.create.__annotations__.update({
            'payload': updater,
            'return': self.read_model
        })
        self.patch.__annotations__.update({
            'payload': updater,
            'return': self.read_model
        })
        self.list.__annotations__.update({
            'order_by': Optional[List[self.model.get_public_ordering_fields()]],
            'return': List[self.read_model]
        })
        self.retrieve.__annotations__.update({
            'return': Optional[self.read_model]
        })
        self.patch.__annotations__.update({
            'payload': updater,
            'return': self.read_model
        })

    async def create(self, payload):
        instance = self.model(**payload.dict())
        return await instance.commit()

    async def list(
        self,
        order_by = Query(None),
        skip: Optional[NonNegativeInt] = Query(None),
        limit: Optional[NonNegativeInt] = Query(10, maximum=50)
    ):
        return await self.queryset.order_by(order_by).skip(skip).limit(limit).all()

    async def retrieve(self, id: InputObjectId):
        try:
            return await self.queryset.get(_id=id)
        except self.model.DocumentNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    async def delete(self, id: InputObjectId):
        await self.queryset.filter(_id=id).delete()

    async def patch(self, id: InputObjectId, payload):
        try:
            instance = await self.queryset.get(_id=id)
            instance.deep_update(payload.dict(exclude_unset=True))
            await instance.save()
            return instance
        except self.model.DocumentNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
