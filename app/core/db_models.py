import uuid
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum, func
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)

    memberships = relationship("TenantMember", back_populates="user")


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)

    owner = relationship("User")
    members = relationship("TenantMember", back_populates="tenant")


class TenantMember(Base):
    __tablename__ = "tenant_members"

    id = Column(String, primary_key=True, default=_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False, default="member")  # owner, admin, member
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="members")
    user = relationship("User", back_populates="memberships")


class ScanRecord(Base):
    __tablename__ = "scan_records"

    id = Column(String, primary_key=True, default=_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    triggered_by = Column(String, ForeignKey("users.id"), nullable=False)
    repo_url = Column(String, nullable=False)
    branch = Column(String, default="main")
    repo_source = Column(String, default="github")
    bug_tracker_type = Column(String, nullable=True)
    bug_tracker_config_json = Column(Text, nullable=True)
    status = Column(String, default="pending")
    summary_json = Column(Text, nullable=True)
    issues_json = Column(Text, nullable=True)
    test_results_json = Column(Text, nullable=True)
    bugs_filed_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    user = relationship("User")


class ConnectorConfig(Base):
    __tablename__ = "connector_configs"

    id = Column(String, primary_key=True, default=_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    tracker_type = Column(String, nullable=False)
    credentials_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(String, ForeignKey("users.id"), nullable=False)

    tenant = relationship("Tenant")
    user = relationship("User")
