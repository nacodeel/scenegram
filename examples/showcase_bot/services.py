from __future__ import annotations

from dataclasses import dataclass

from scenegram import BroadcastReport, CrudDetailField, CrudListItem, CrudPage


@dataclass(slots=True)
class ProductRecord:
    id: str
    title: str
    price: str
    status: str
    description: str


PRODUCTS = [
    ProductRecord(
        id="starter",
        title="Starter Pack",
        price="9.90",
        status="draft",
        description="Небольшой пакет для первого бота.",
    ),
    ProductRecord(
        id="growth",
        title="Growth Pack",
        price="19.90",
        status="active",
        description="Модуль для каталога и клиентских сценариев.",
    ),
    ProductRecord(
        id="pro",
        title="Pro Pack",
        price="29.90",
        status="active",
        description="Набор reusable сцен для production-потока.",
    ),
    ProductRecord(
        id="enterprise",
        title="Enterprise Pack",
        price="49.90",
        status="archived",
        description="Шаблон для enterprise-flow с ролями и очередями.",
    ),
]


class ProductCrudAdapter:
    def __init__(self, items: list[ProductRecord]) -> None:
        self.items = items

    async def list_items(self, scene, page: int, per_page: int) -> CrudPage:
        total = len(self.items)
        pages = max(1, (total + per_page - 1) // per_page)
        page = min(max(page, 1), pages)
        start = (page - 1) * per_page
        end = start + per_page
        records = self.items[start:end]
        return CrudPage(
            items=[
                CrudListItem(
                    id=item.id,
                    title=item.title,
                    description=item.description,
                    badge=item.status,
                )
                for item in records
            ],
            page=page,
            pages=pages,
            total=total,
        )

    async def get_item(self, scene, item_id: str) -> ProductRecord:
        item = next((item for item in self.items if item.id == item_id), None)
        if item is None:
            raise LookupError(f"Product '{item_id}' was not found")
        return item

    async def get_item_title(self, scene, item: ProductRecord) -> str:
        return item.title

    async def get_item_fields(self, scene, item: ProductRecord) -> list[CrudDetailField]:
        return [
            CrudDetailField(label="ID", value=item.id),
            CrudDetailField(label="Price", value=item.price),
            CrudDetailField(label="Status", value=item.status),
            CrudDetailField(label="Description", value=item.description),
        ]

    async def delete_item(self, scene, item: ProductRecord) -> None:
        self.items[:] = [record for record in self.items if record.id != item.id]


class AudienceBroadcastAdapter:
    async def iter_recipients(self, scene):
        return [1001, 1002, 1003, 1004]

    async def send(self, scene, recipient_id: int, content: str) -> None:
        logger = await scene.services.require("audit_logger")
        await logger(f"broadcast.send recipient={recipient_id} content={content!r}")

    async def on_complete(self, scene, report: BroadcastReport) -> None:
        collector = await scene.services.require("broadcast_report_collector")
        await collector(report)


async def audit_logger(message: str) -> None:
    print(f"[showcase] {message}")


def build_service_container() -> dict[str, object]:
    reports: list[BroadcastReport] = []

    async def collect_report(report: BroadcastReport) -> None:
        reports.append(report)
        await audit_logger(
            f"broadcast.complete job={report.job_id} sent={report.sent} failed={report.failed}"
        )

    return {
        "audit_logger": audit_logger,
        "broadcast_report_collector": collect_report,
        "broadcast_reports": reports,
    }
