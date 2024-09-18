import asyncio
import datetime

from tortoise import Tortoise
import certainty
from certainty.email import (
    send_monitor_deleted,
    send_monitor_error,
    send_monitor_expired,
    send_monitor_expiring,
    send_monitor_renewed,
)
from certainty.models import CertificateMonitor, MonitorState


async def create_certificate_monitor(domain: str, email: str, warning_days: int):
    return await CertificateMonitor.create(
        domain=domain, email=email, warning_days=warning_days
    )


async def get_certificate_monitor(monitor_id: int) -> CertificateMonitor:
    return await CertificateMonitor.get(uuid=monitor_id)


async def delete_certificate_monitor(
    monitor_id: int, send_notification: bool = True
) -> None:
    monitor = await CertificateMonitor.get(uuid=monitor_id)

    email, uuid, domain = monitor.email, monitor.uuid, monitor.domain

    await monitor.delete()

    if send_notification:
        # send_monitor_deleted(monitor.email, monitor.domain)
        certainty.q.enqueue(send_monitor_deleted, email, domain, uuid)


async def refresh_certificate_monitor(monitor_id: int) -> CertificateMonitor:
    monitor = await CertificateMonitor.get(uuid=monitor_id)

    print(f"Refreshing Monitor {monitor_id} ('{monitor.domain}')")

    if (monitor_detail := await get_certificate_detail(monitor.domain)) is not None:
        not_before_datetime = datetime.datetime.strptime(
            monitor_detail["notBefore"], "%b %d %H:%M:%S %Y %Z"
        )
        not_after_datetime = datetime.datetime.strptime(
            monitor_detail["notAfter"], "%b %d %H:%M:%S %Y %Z"
        )

        monitor = await CertificateMonitor.get(uuid=monitor_id)

        monitor.update_from_dict(
            {
                "serial": monitor_detail["serialNumber"],
                "not_before": not_before_datetime,
                "not_after": not_after_datetime,
                "checked_at": datetime.datetime.now(tz=datetime.timezone.utc),
            }
        )
    else:
        monitor.update_from_dict(
            {
                "serial": None,
                "not_before": None,
                "not_after": None,
                "checked_at": datetime.datetime.now(tz=datetime.timezone.utc),
            }
        )

    if (
        monitor.not_after is None
        or monitor.not_before is None
        or monitor.serial is None
    ):
        new_state = MonitorState.ERROR
    elif monitor.not_after < datetime.datetime.now(tz=datetime.timezone.utc):
        new_state = MonitorState.EXPIRED
    elif monitor.not_after < datetime.datetime.now(
        tz=datetime.timezone.utc
    ) + datetime.timedelta(days=monitor.warning_days):
        new_state = MonitorState.EXPIRING
    else:
        new_state = MonitorState.OK

    # State has changed
    if monitor.state != new_state:
        print(f"Monitor {monitor_id} ('{monitor.domain}') changed state to {new_state}")
        if new_state == MonitorState.ERROR:
            print("To Error")
            certainty.q.enqueue(
                send_monitor_error, monitor.email, monitor.domain, monitor.uuid
            )
        elif new_state == MonitorState.EXPIRED:
            print("To Expired")
            certainty.q.enqueue(
                send_monitor_expired,
                monitor.email,
                monitor.domain,
                monitor.uuid,
                monitor.not_after,
            )
        elif new_state == MonitorState.EXPIRING:
            print("To Expiring")
            certainty.q.enqueue(
                send_monitor_expiring,
                monitor.email,
                monitor.domain,
                monitor.uuid,
                monitor.not_after,
            )
        elif new_state == MonitorState.OK and monitor.state != MonitorState.UNKNOWN:
            print("To OK (from non-UNKNOWN state)")
            certainty.q.enqueue(
                send_monitor_renewed,
                monitor.email,
                monitor.domain,
                monitor.uuid,
                monitor.not_after,
            )

    monitor.state = new_state

    await monitor.save(
        update_fields=["serial", "not_before", "not_after", "checked_at", "state"]
    )

    return monitor


async def get_certificate_detail(domain: str) -> dict | None:
    try:
        _, writer = await asyncio.open_connection(domain, 443, ssl=True)
        peercert = writer.get_extra_info("peercert")
        writer.close()
        return peercert
    except Exception:
        return None


async def check_certificates() -> None:
    Tortoise.init_models(["certainty.models"], "models")

    await Tortoise.init(
        db_url="sqlite://db.sqlite3", modules={"models": ["certainty.models"]}
    )

    monitors = await CertificateMonitor.filter(
        enabled=True,
        checked_at__lt=datetime.datetime.now(tz=datetime.timezone.utc)
        - datetime.timedelta(seconds=10),
    )

    tasks = []
    for monitor in monitors:
        print(f"Running Monitor {monitor.uuid} ('{monitor.domain}')")
        tasks.append(refresh_certificate_monitor(monitor.uuid))

    await asyncio.gather(*tasks)


def check_certificates_sync() -> None:
    print("Triggering main certificate check job")
    asyncio.run(check_certificates())
    print("Certificate check job complete")
