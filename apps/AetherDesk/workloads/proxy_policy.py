"""Política de destino do futuro proxy: IP fixado pelo broker, sem URL do cliente."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from .service import WorkloadError


@dataclass(frozen=True)
class ProxyRoute:
    owner_id: str
    workload_id: str
    hostname: str
    port: int
    container_ip: str
    network_cidr: str


def authorize_route(route: ProxyRoute, *, owner_id: str, workload_id: str,
                    host_header: str, current_container_ip: str) -> tuple[str, int]:
    if owner_id != route.owner_id or workload_id != route.workload_id or host_header != route.hostname:
        raise WorkloadError('PROXY_DENIED')
    if type(route.port) is not int or not 1 <= route.port <= 65535:
        raise WorkloadError('PROXY_DENIED')
    try:
        network = ipaddress.ip_network(route.network_cidr, strict=True)
        pinned = ipaddress.ip_address(route.container_ip)
        current = ipaddress.ip_address(current_container_ip)
    except ValueError as exc:
        raise WorkloadError('PROXY_DENIED') from exc
    if (network.version != 4 or not network.is_private or pinned != current or
            pinned not in network or pinned in (network.network_address, network.broadcast_address) or
            pinned.is_loopback or pinned.is_link_local or pinned.is_multicast or pinned.is_unspecified or
            pinned == network.network_address + 1):
        raise WorkloadError('PROXY_DENIED')
    return str(pinned), route.port
