"""
SQLAlchemy ORM models for DocuFlow database schema.
These models are used by Alembic for migrations.
The application continues to use raw SQL via database.py for now.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, REAL, TIMESTAMP,
    ForeignKey, Date, VARCHAR, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class Organization(Base):
    """Multi-tenant organization table."""
    __tablename__ = 'organizations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    subscription_plan = Column(Text, default='trial')
    billing_email = Column(Text)
    status = Column(Text, default='active')
    org_metadata = Column('metadata', Text)  # 'metadata' is reserved, use 'org_metadata' attribute
    review_mode = Column(Text, default='review_all')
    confidence_threshold = Column(REAL, default=0.85)
    auto_upload_enabled = Column(Boolean, default=False)

    # Relationships
    users = relationship("User", back_populates="organization")
    batches = relationship("Batch", back_populates="organization")
    organization_settings = relationship("OrganizationSetting", back_populates="organization")
    usage_logs = relationship("UsageLog", back_populates="organization")
    subscription = relationship("Subscription", back_populates="organization", uselist=False)
    document_metadata = relationship("DocumentMetadata", back_populates="organization")
    field_corrections = relationship("FieldCorrection", back_populates="organization")


class User(Base):
    """User account with organization support."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    auth0_user_id = Column(VARCHAR(255), unique=True, nullable=False)
    email = Column(VARCHAR(255), unique=True, nullable=False)
    name = Column(VARCHAR(255))
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='SET NULL'))
    role = Column(VARCHAR(20), default='member')
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    last_login = Column(TIMESTAMP)

    # Relationships
    organization = relationship("Organization", back_populates="users")
    batches = relationship("Batch", back_populates="user")
    connector_configs = relationship("ConnectorConfig", back_populates="user")


class Batch(Base):
    """Batch processing table."""
    __tablename__ = 'batches'

    id = Column(VARCHAR(36), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='SET NULL'))
    status = Column(VARCHAR(20), nullable=False)
    total_files = Column(Integer, nullable=False)
    processed_files = Column(Integer, default=0)
    successful = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    results_json = Column(Text)
    processing_summary_json = Column(Text)
    download_url = Column(VARCHAR(500))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    completed_at = Column(TIMESTAMP)

    # Relationships
    user = relationship("User", back_populates="batches")
    organization = relationship("Organization", back_populates="batches")


class OrganizationSetting(Base):
    """Organization-level connector settings."""
    __tablename__ = 'organization_settings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    connector_type = Column(Text, nullable=False)
    config_encrypted = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    review_mode = Column(Text, default='review_all')
    confidence_threshold = Column(REAL, default=0.85)
    auto_upload_enabled = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow)
    created_by_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))

    # Relationships
    organization = relationship("Organization", back_populates="organization_settings")

    # Unique constraint
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class UsageLog(Base):
    """Usage tracking for billing."""
    __tablename__ = 'usage_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    action_type = Column(Text, nullable=False)
    document_count = Column(Integer, default=1)
    timestamp = Column(TIMESTAMP, default=datetime.utcnow)
    log_metadata = Column('metadata', Text)  # 'metadata' is reserved, use 'log_metadata' attribute
    billed = Column(Boolean, default=False)
    billing_period = Column(Text)

    # Relationships
    organization = relationship("Organization", back_populates="usage_logs")


class Subscription(Base):
    """Subscription and billing information."""
    __tablename__ = 'subscriptions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), unique=True, nullable=False)
    plan_type = Column(Text, default='per_document')
    price_per_document = Column(REAL, default=0.10)
    monthly_base_fee = Column(REAL)
    monthly_document_limit = Column(Integer)
    overage_price_per_document = Column(REAL)
    stripe_customer_id = Column(Text)
    stripe_subscription_id = Column(Text)
    billing_cycle_start = Column(Date)
    current_period_start = Column(Date)
    current_period_end = Column(Date)
    trial_end_date = Column(TIMESTAMP)
    status = Column(Text, default='active')
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="subscription")


class ConnectorConfig(Base):
    """Legacy connector configurations (user-level)."""
    __tablename__ = 'connector_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    connector_type = Column(VARCHAR(20), nullable=False)
    is_active = Column(Boolean, default=True)
    config_json = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow)
    last_used_at = Column(TIMESTAMP)

    # Relationships
    user = relationship("User", back_populates="connector_configs")
    field_mappings = relationship("FieldMapping", back_populates="connector_config")


class FieldMapping(Base):
    """Field mapping for connectors."""
    __tablename__ = 'field_mappings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    connector_config_id = Column(Integer, ForeignKey('connector_configs.id'), nullable=False)
    source_field = Column(VARCHAR(255), nullable=False)
    target_field = Column(VARCHAR(255), nullable=False)
    confidence_score = Column(REAL)
    is_manual_override = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    # Relationships
    connector_config = relationship("ConnectorConfig", back_populates="field_mappings")

    # Unique constraint
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class DocumentMetadata(Base):
    """Document metadata for review workflow."""
    __tablename__ = 'document_metadata'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    batch_id = Column(VARCHAR(36))
    filename = Column(Text, nullable=False)
    file_path = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    extracted_data = Column(Text)
    status = Column(Text, default='pending_review')
    confidence_score = Column(REAL)
    connector_type = Column(Text)
    connector_config_snapshot = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    processed_at = Column(TIMESTAMP, default=datetime.utcnow)
    reviewed_at = Column(TIMESTAMP)
    reviewed_by_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    approved_at = Column(TIMESTAMP)
    uploaded_at = Column(TIMESTAMP)
    uploaded_to_connector = Column(Boolean, default=False)
    error_message = Column(Text)

    # Relationships
    organization = relationship("Organization", back_populates="document_metadata")
    field_corrections = relationship("FieldCorrection", back_populates="document")


class FieldCorrection(Base):
    """Field corrections for AI learning."""
    __tablename__ = 'field_corrections'

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    document_id = Column(Integer, ForeignKey('document_metadata.id', ondelete='CASCADE'), nullable=False)
    field_name = Column(Text, nullable=False)
    original_value = Column(Text)
    corrected_value = Column(Text, nullable=False)
    original_confidence = Column(REAL)
    correction_method = Column(Text, default='manual')
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    created_by = Column(Text)

    # Relationships
    organization = relationship("Organization", back_populates="field_corrections")
    document = relationship("DocumentMetadata", back_populates="field_corrections")
