import datetime
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, JSON
from backend.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    badge_number = Column(String(100), unique=True, nullable=False, index=True)
    officer_name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    department = Column(String(150), default="CID Crime Branch")
    unit = Column(String(150), nullable=True)
    role = Column(String(50), default="investigator")  # officer, investigator, analyst, supervisor, admin
    clearance_level = Column(String(100), default="Level 2: Investigator")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class CaseModel(Base):
    __tablename__ = "cases"

    case_id = Column(String(100), primary_key=True, index=True)
    fir_number = Column(String(100), nullable=True, index=True)
    case_name = Column(String(255), nullable=False)
    status = Column(String(50), default="Under Investigation")
    lead_investigator = Column(String(150), default="Lead Investigator")
    uploaded_by = Column(String(100), nullable=True)
    severity = Column(String(50), default="High")
    crime_category = Column(String(100), default="General Investigation")
    primary_suspect = Column(String(150), nullable=True)
    victim = Column(String(150), nullable=True)
    date_filed = Column(String(50), nullable=True)
    summary = Column(Text, nullable=True)
    total_entities = Column(Integer, default=0)
    overlapping_cases = Column(JSON, default=list)
    evidences = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class CasePermission(Base):
    __tablename__ = "case_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    badge_number = Column(String(100), nullable=False, index=True)
    case_id = Column(String(100), nullable=False, index=True)
    permission_level = Column(String(50), default="write")  # read, write, admin
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class EvidenceItemModel(Base):
    __tablename__ = "evidence_items"

    evidence_id = Column(String(100), primary_key=True, index=True)
    case_id = Column(String(100), nullable=False, index=True)
    sha256 = Column(String(64), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    uploader = Column(String(150), default="Investigator")
    uploaded_at = Column(String(50), nullable=False)
    format = Column(String(50), default="pdf")
    size = Column(Integer, default=0)
    relative_path = Column(String(500), nullable=True)
    classification_override = Column(String(100), nullable=True)
    category = Column(String(100), default="General Investigation")
    status = Column(String(50), default="Queued")  # Queued, Processing, Complete, Reviewed, Failed
    job_id = Column(String(100), nullable=True)
    job_stage = Column(String(100), default="Initialized")
    job_progress = Column(Float, default=0.0)
    job_error = Column(Text, nullable=True)
    job_warnings = Column(JSON, default=list)
    job_classification = Column(String(100), nullable=True)
    mention_count = Column(Integer, default=0)
    claim_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    finished_at = Column(String(50), nullable=True)


class EvidenceSourceModel(Base):
    __tablename__ = "evidence_sources"

    id = Column(String(100), primary_key=True)
    evidence_id = Column(String(100), nullable=False, index=True)
    case_id = Column(String(100), nullable=False, index=True)
    unit_id = Column(String(100), nullable=True)
    unit_kind = Column(String(50), default="page")
    page = Column(Integer, nullable=True)
    row = Column(Integer, nullable=True)
    sheet = Column(String(100), nullable=True)
    text = Column(Text, nullable=True)
    bbox = Column(JSON, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class EvidenceMentionModel(Base):
    __tablename__ = "evidence_mentions"

    id = Column(String(100), primary_key=True)
    evidence_id = Column(String(100), nullable=False, index=True)
    case_id = Column(String(100), nullable=False, index=True)
    type = Column(String(100), nullable=False, index=True)  # Person, Phone, Vehicle, BankAccount, IMEI, Location, etc.
    raw_value = Column(Text, nullable=False)
    normalized_value = Column(Text, nullable=False, index=True)
    role = Column(String(100), nullable=True)
    identifier_trust = Column(String(50), default="strong")  # strong, confirmed, review_required
    quote = Column(Text, nullable=True)
    quote_status = Column(String(50), default="verified")
    page = Column(Integer, nullable=True)
    sheet = Column(String(100), nullable=True)
    row = Column(Integer, nullable=True)
    bbox = Column(JSON, nullable=True)
    ocr_scores = Column(JSON, nullable=True)
    confirmed_by = Column(String(100), nullable=True)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class EvidenceReviewModel(Base):
    __tablename__ = "evidence_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    evidence_id = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), default="mentions")
    target_id = Column(String(100), nullable=False)
    decision = Column(String(50), nullable=False)
    correction = Column(Text, nullable=True)
    reviewer = Column(String(150), default="Investigator")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class BlockchainBlockModel(Base):
    __tablename__ = "blockchain_ledger"

    block_index = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(100), nullable=False, index=True)
    document_type = Column(String(100), default="EVIDENCE_RECORD")
    hash = Column(String(64), nullable=False)
    prev_hash = Column(String(64), nullable=False)
    timestamp = Column(String(50), nullable=False)
    data = Column(JSON, default=dict)
    merkle_root = Column(String(64), nullable=True)


class ActivityLogModel(Base):
    __tablename__ = "activity_logs"

    event_id = Column(String(100), primary_key=True)
    case_id = Column(String(100), nullable=False, index=True)
    sequence_num = Column(Integer, default=1)
    action_type = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    officer_name = Column(String(150), default="System")
    officer_badge = Column(String(100), default="SYS-001")
    timestamp = Column(String(50), nullable=False)
    formatted_date = Column(String(100), nullable=True)
    status_type = Column(String(50), default="info")  # verified, error, warning, info
    icon_type = Column(String(50), default="info")


class CaseFindingModel(Base):
    __tablename__ = "case_findings"

    finding_id = Column(String(100), primary_key=True)
    case_id = Column(String(100), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    category = Column(String(100), default="General Note")
    content = Column(Text, nullable=False)
    officer_name = Column(String(150), nullable=True)
    officer_badge = Column(String(100), nullable=True)
    severity = Column(String(50), default="MEDIUM")
    attachments = Column(JSON, default=list)
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=True)


class InvestigationBoardModel(Base):
    __tablename__ = "investigation_boards"

    board_id = Column(String(100), primary_key=True)
    case_id = Column(String(100), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    creator_id = Column(String(100), nullable=True)
    creator_name = Column(String(150), nullable=True)
    creator_badge = Column(String(100), nullable=True)
    nodes = Column(JSON, default=list)
    edges = Column(JSON, default=list)
    notes = Column(JSON, default=list)
    viewport = Column(JSON, default=dict)
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=True)
