"""Builds a default virtual enterprise from the PRD (§3, §5)."""
from __future__ import annotations

from .domain.enums import OrgUnit, SystemLayer
from .domain.organization import Enterprise
from .domain.systems import Metrics, System, SystemConfig
from .domain.users import VirtualUser


def _sys(sid, name, layer, org, stack, cpu, mem, lat, depends=None) -> System:
    base = Metrics(cpu_pct=cpu, mem_pct=mem, disk_pct=42.0, latency_ms=lat)
    return System(
        id=sid, name=name, layer=layer, org=org, stack=stack,
        depends_on=depends or [],
        baseline=base,
        config=SystemConfig(),
    )


def _users(system_id: str, org: OrgUnit, roles: list[tuple[str, str, int, float]]):
    out = []
    for i, (role, personality, priority, patience) in enumerate(roles, 1):
        out.append(VirtualUser(
            id=f"{system_id}-u{i}",
            name=f"{role} @ {system_id}",
            role=role,
            system_id=system_id,
            org=org,
            personality=personality,
            priority=priority,
            patience=patience,
        ))
    return out


def build_default_enterprise() -> Enterprise:
    """A compact but representative slice of the PRD's enterprise landscape."""
    ent = Enterprise(name="Virtual Petrochemical Co.")

    # --- Infrastructure / shared services -------------------------------
    ent.add_system(_sys("pg-core", "PostgreSQL (Core)", SystemLayer.DATABASE,
                        OrgUnit.IT, "PostgreSQL", 22, 40, 90))
    ent.add_system(_sys("eai", "EAI Bus", SystemLayer.INTEGRATION,
                        OrgUnit.IT, "EAI", 18, 35, 110))
    ent.add_system(_sys("lb", "Load Balancer", SystemLayer.INFRASTRUCTURE,
                        OrgUnit.IT, "ELB", 15, 25, 40))
    ent.add_system(_sys("iam", "IAM / SSO", SystemLayer.SECURITY,
                        OrgUnit.IT, "IAM+SSO", 16, 30, 70))
    ent.add_system(_sys("obs", "Prometheus/Grafana", SystemLayer.OBSERVABILITY,
                        OrgUnit.IT, "Prometheus", 20, 45, 90))

    # --- SAP ERP modules ------------------------------------------------
    sap = [
        ("sap-fi", "SAP FI", OrgUnit.MANAGEMENT),
        ("sap-co", "SAP CO", OrgUnit.MANAGEMENT),
        ("sap-mm", "SAP MM", OrgUnit.PURCHASING),
        ("sap-pm", "SAP PM", OrgUnit.MAINTENANCE),
        ("sap-sd", "SAP SD", OrgUnit.PRODUCTION),
    ]
    for sid, name, org in sap:
        ent.add_system(_sys(sid, name, SystemLayer.APPLICATION, org, "SAP UI5",
                           28, 55, 180, depends=["pg-core", "eai", "iam"]))

    # --- Business portals ----------------------------------------------
    ent.add_system(_sys("portal-purchase", "Purchase Portal", SystemLayer.APPLICATION,
                        OrgUnit.PURCHASING, "Spring Boot + Vue", 24, 50, 160,
                        depends=["pg-core", "eai", "iam"]))
    ent.add_system(_sys("portal-she", "SHE Portal", SystemLayer.APPLICATION,
                        OrgUnit.SHE, "ASP.NET + React", 22, 48, 150,
                        depends=["pg-core", "iam"]))
    ent.add_system(_sys("portal-ai", "AI Portal", SystemLayer.APPLICATION,
                        OrgUnit.DX, "FastAPI + React", 30, 60, 200,
                        depends=["pg-core", "eai", "iam"]))

    # --- Virtual users (~3 per business system) -------------------------
    ent.users.extend(_users("sap-pm", OrgUnit.MAINTENANCE, [
        ("Planner", "methodical", 3, 0.6),
        ("Maintenance Engineer", "impatient", 2, 0.25),
        ("Supervisor", "demanding", 1, 0.35),
    ]))
    ent.users.extend(_users("portal-purchase", OrgUnit.PURCHASING, [
        ("Buyer", "busy", 3, 0.4),
        ("Manager", "demanding", 2, 0.3),
        ("Approver", "cautious", 1, 0.5),
    ]))
    ent.users.extend(_users("sap-fi", OrgUnit.MANAGEMENT, [
        ("Accountant", "precise", 2, 0.4),
        ("Controller", "demanding", 1, 0.3),
        ("Auditor", "cautious", 3, 0.6),
    ]))
    ent.users.extend(_users("sap-mm", OrgUnit.PURCHASING, [
        ("Inventory Clerk", "busy", 4, 0.5),
        ("Procurement Lead", "demanding", 2, 0.3),
    ]))
    ent.users.extend(_users("portal-she", OrgUnit.SHE, [
        ("Safety Officer", "vigilant", 1, 0.3),
        ("Field Inspector", "busy", 3, 0.5),
    ]))
    ent.users.extend(_users("portal-ai", OrgUnit.DX, [
        ("Data Scientist", "curious", 3, 0.55),
        ("Ops Engineer", "impatient", 2, 0.3),
    ]))
    ent.users.extend(_users("sap-sd", OrgUnit.PRODUCTION, [
        ("Sales Ops", "busy", 3, 0.45),
        ("Plant Scheduler", "demanding", 2, 0.3),
    ]))
    return ent
