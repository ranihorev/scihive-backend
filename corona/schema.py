import graphene
from graphene_sqlalchemy import SQLAlchemyConnectionField, SQLAlchemyObjectType
from .models import Paper as PaperModel, Author as AuthorModel


class PaperObject(SQLAlchemyObjectType):
    class Meta:
        model = PaperModel
        interfaces = (graphene.relay.Node,)


class AuthorObject(SQLAlchemyObjectType):
    class Meta:
        model = AuthorModel
        interfaces = (graphene.relay.Node,)


class Query(graphene.ObjectType):
    node = graphene.relay.Node.Field()
    paper = graphene.relay.Node.Field(PaperObject)
    all_papers = SQLAlchemyConnectionField(PaperObject)
    all_authors = SQLAlchemyConnectionField(AuthorObject)


schema = graphene.Schema(query=Query)