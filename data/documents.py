from langchain.schema import Document

documents = [
    Document(
        page_content=open("manifests/inbound_https_traffic.yaml").read(),
        metadata={
            "source": "manifests/inbound_https_traffic.yaml",
            "description": "Ввод в приклад HTTPS трафика из вне через ingress",
            "keywords": "istio, истио, service mesh, сервис меш, https, ввод, inbound, трафик"
        }
    ),
    Document(
        page_content=open("manifests/outbound_https_mtls.yaml").read(),
        metadata={
            "source": "manifests/outbound_https_mtls.yaml",
            "description": "Вывод HTTPS трафика из прикладного пода через egress и шифрование mtls",
            "keywords": "istio, истио, service mesh, сервис меш, https, вывод, outbound, mtls, трафик"
        }
    ),
    Document(
        page_content=open("manifests/outbound_kafka_tcp_with_ip.yaml").read(),
        metadata={
            "source": "manifests/outbound_kafka_tcp_with_ip.yaml",
            "description": "Подключение к кластеру kafka по протоколу TCP, с указанием реального ip адреса",
            "keywords": "istio, истио, service mesh, сервис меш, tcp, подключение, kafka, кафка, ip-адрес"
        }
    ),
    Document(
        page_content=open("manifests/outbound_kafka_tcp_without_ip.yaml").read(),
        metadata={
            "source": "manifests/outbound_kafka_tcp_without_ip.yaml",
            "description": "Подключение к кластеру kafka по протоколу TCP, без указания реального ip адреса",
            "keywords": "istio, истио, service mesh, сервис меш, tcp, подключение, kafka, кафка, без ip-адреса"
        }
    ),
    Document(
        page_content=open("manifests/outbound_kafka_through_kafka.yaml").read(),
        metadata={
            "source": "manifests/outbound_kafka_through_kafka.yaml",
            "description": "Подключение к кластеру kafka по протоколу KAFKA",
            "keywords": "istio, истио, service mesh, сервис меш, подключение, kafka, кафка, протокол kafka, протокол кафка"
        }
    ),
    Document(
        page_content=open("manifests/outbound_kafka_through_kafka.yaml").read(),
        metadata={
            "source": "manifests/outbound_kafka_through_kafka.yaml",
            "description": "Подключение к кластеру kafka по протоколу KAFKA",
            "keywords": "istio, истио, service mesh, сервис меш, подключение, kafka, кафка, протокол kafka, протокол кафка"
        }
    ),
    Document(
        page_content=open("manifests/postgres_with_ip.yaml").read(),
        metadata={
            "source": "manifests/postgres_with_ip.yaml",
            "description": "Подключение к базе данных (master и slave), с указанием реального ip адреса базы данных",
            "keywords": "istio, истио, service mesh, сервис меш, postgresql, база данных, с указанием ip-адреса"
        }
    ),
        Document(
        page_content=open("manifests/postgres_without_ip.yaml").read(),
        metadata={
            "source": "manifests/postgres_with_ip.yaml",
            "description": "Подключение к базе данных (master и slave), без указания реального ip адреса базы данных",
            "keywords": "istio, истио, service mesh, сервис меш, postgresql, база данных, без указания ip-адреса"
        }
    ),
    Document(
        page_content=open("manifests/secman_https_passthrough.yaml").read(),
        metadata={
            "source": "manifests/secman_https_passthrough.yaml",
            "description": "Интеграция Istio Service Mesh с Secman",
            "keywords": "istio, истио, service mesh, сервис меш, secman, секман"
        }
    )

    # Document(
    #     page_content=open("manifests/istio_postgres_se.yaml").read(),
    #     metadata={
    #         "source": "manifests/istio_postgres_se.yaml",
    #         "description": "Манифесты для интеграции Istio Service Mesh с PostgreSQL, c использованием Service Entry",
    #         "keywords": "istio, service mesh, postgresql, база данных, с service entry"
    #     }
    # ),
    # Document(
    #     page_content=open("manifests/istio_postgres.yaml").read(),
    #     metadata={
    #         "source": "manifests/istio_postgres.yaml",
    #         "description": "Манифесты для интеграции Istio Service Mesh с PostgreSQL, без использования Service Entry",
    #         "keywords": "istio, service mesh, postgresql, база данных, без service entry"
    #     }
    # ),
    # Document(
    #     page_content=open("manifests/istio_secman.yaml").read(),
    #     metadata={
    #         "source": "manifests/istio_secman.yaml",
    #         "description": "Манифесты для интеграции Istio Service Mesh с Secman",
    #         "keywords": "istio, service mesh, secman, секман"
    #     }
    # )
]

def load_documents() -> list[Document]:
    return documents
