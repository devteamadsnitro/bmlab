from sqlmodel import Session, select

from .database import engine
from .models import Asset, Ticket, User
from .security import encrypt_password


def seed() -> None:
    with Session(engine) as session:
        if session.exec(select(User)).first():
            return

        moda = User(
            username="cliente001",
            password_encrypted=encrypt_password("1234"),
            name="Moda Trends SL",
            initials="MT",
            structure="Estructura A",
        )
        supl = User(
            username="cliente002",
            password_encrypted=encrypt_password("abc99"),
            name="Suplementos Plus",
            initials="SP",
            structure="Estructura B",
        )
        admin = User(
            username="admin",
            password_encrypted=encrypt_password("admin123"),
            name="Administrador",
            initials="AD",
            is_admin=True,
        )
        session.add_all([moda, supl, admin])
        session.commit()
        session.refresh(moda)
        session.refresh(supl)

        session.add_all(
            [
                Asset(external_id="BM-001", label="Business Manager principal", type="bm", icon="ti-building-store", owner_id=moda.id),
                Asset(external_id="PF-001", label="Perfil · Juan García", type="profile", icon="ti-user-circle", owner_id=moda.id),
                Asset(external_id="PF-002", label="Perfil · Ana Ruiz", type="profile", icon="ti-user-circle", owner_id=moda.id),
                Asset(external_id="PF-003", label="Perfil · Carlos López", type="profile", icon="ti-user-circle", owner_id=moda.id),
                Asset(external_id="FP-001", label="Fan Page · Moda Trends", type="page", icon="ti-brand-facebook", owner_id=moda.id),
                Asset(external_id="BM-002", label="Business Manager principal", type="bm", icon="ti-building-store", owner_id=supl.id),
                Asset(external_id="PF-004", label="Perfil · María Torres", type="profile", icon="ti-user-circle", owner_id=supl.id),
                Asset(external_id="PF-005", label="Perfil · Luis Sánchez", type="profile", icon="ti-user-circle", owner_id=supl.id),
                Asset(external_id="FP-002", label="Fan Page · Suplementos Plus", type="page", icon="ti-brand-facebook", owner_id=supl.id),
            ]
        )
        session.commit()

        session.add_all(
            [
                Ticket(code="INC-0029", client_name=moda.name, asset_external_id="PF-002", asset_label="Perfil · Ana Ruiz", asset_type="profile", status="done", user_id=moda.id),
                Ticket(code="INC-0030", client_name=supl.name, asset_external_id="FP-002", asset_label="Fan Page · Suplementos Plus", asset_type="page", status="progress", user_id=supl.id),
                Ticket(code="INC-0031", client_name=moda.name, asset_external_id="BM-001", asset_label="Business Manager principal", asset_type="bm", status="open", user_id=moda.id),
            ]
        )
        session.commit()
