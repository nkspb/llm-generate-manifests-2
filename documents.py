from langchain.schema import Document

def _load(path: str, description: str, keywords: str) -> Document:
    with open(path, encoding="utf-8") as f:
        yaml = f.read()

    return Document(
        page_content=f"{description}\n\n{yaml}",
        metadata={
            "source": path,
            "description": description,
            "keywords": keywords
        }
    )

documents = [
    _load(
        "manifests/inbound_https_traffic.yaml",
        "Ввод в приклад HTTPS трафика из вне через ingress",
        "istio, истио, service mesh, сервис меш, https, ввод, inbound, трафик"
    ),
    _load(
        "manifests/outbound_https_mtls.yaml",
        "Вывод HTTPS трафика из прикладного пода через egress и шифрование mtls",
        "istio, истио, service mesh, сервис меш, https, вывод, outbound, mtls, трафик"
    ),
    _load(
        "manifests/outbound_kafka_tcp_with_ip.yaml",
        "Подключение к кластеру kafka по протоколу TCP, с указанием реального ip адреса",
        "istio, истио, service mesh, сервис меш, tcp, подключение, kafka, кафка, ip-адрес"
    ),
    _load(
        "manifests/outbound_kafka_tcp_without_ip.yaml",
        "Подключение к кластеру kafka по протоколу TCP, без указания реального ip адреса",
        "istio, истио, service mesh, сервис меш, tcp, подключение, kafka, кафка, без ip-адреса"
    ),
    _load(
        "manifests/outbound_kafka_through_kafka.yaml",
        "Подключение к кластеру kafka по протоколу KAFKA",
        "istio, истио, service mesh, сервис меш, подключение, kafka, кафка, протокол kafka, протокол кафка"
    ),
    _load(
        "manifests/outbound_kafka_through_kafka.yaml",
        "Подключение к кластеру kafka по протоколу KAFKA",
        "istio, истио, service mesh, сервис меш, подключение, kafka, кафка, протокол kafka, протокол кафка"
    ),
    _load(
        "manifests/postgres_with_ip.yaml",
        "Подключение к базе данных postgres (master и slave), с указанием реального ip адреса базы данных",
        "istio, истио, service mesh, сервис меш, postgresql, база данных, с указанием ip-адреса"
    ),
    _load(
        "manifests/postgres_with_ip.yaml",
        "Подключение к базе данных postgres (master и slave), без указания реального ip адреса базы данных",
        "istio, истио, service mesh, сервис меш, postgresql, база данных, без указания ip-адреса"
    ),
    _load(
        "manifests/secman_https_passthrough.yaml",
        "Интеграция Istio Service Mesh с Secman",
        "istio, истио, service mesh, сервис меш, secman, секман"
    )
]

def load_documents() -> list[Document]:
    return documents
