from langchain.schema import Document

documents = [
    Document(
        page_content=open("manifests/istio_postgres_se.yaml").read(),
        metadata={
            "source": "manifests/istio_postgres_se.yaml",
            "description": "Манифесты для интеграции Istio Service Mesh с PostgreSQL, c использованием Service Entry",
            "keywords": "istio, service mesh, postgresql, база данных, с service entry"
        }
    ),
    Document(
        page_content=open("manifests/istio_postgres.yaml").read(),
        metadata={
            "source": "manifests/istio_postgres.yaml",
            "description": "Манифесты для интеграции Istio Service Mesh с PostgreSQL, без использования Service Entry",
            "keywords": "istio, service mesh, postgresql, база данных, без service entry"
        }
    ),
    Document(
        page_content=open("manifests/istio_secman.yaml").read(),
        metadata={
            "source": "manifests/istio_secman.yaml",
            "description": "Манифесты для интеграции Istio Service Mesh с Secman",
            "keywords": "istio, service mesh, secman"
        }
    )
]

def load_documents() -> list[Document]:
    return documents
