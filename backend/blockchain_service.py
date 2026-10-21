import hashlib
import json
import datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from backend.models import BlockchainBlockModel, ActivityLogModel, EvidenceItemModel, CaseModel

GENESIS_HASH = "0" * 64

def calculate_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def calculate_block_hash(index: int, prev_hash: str, timestamp: str, case_id: str, doc_type: str, data: Dict[str, Any]) -> str:
    raw_str = f"{index}:{prev_hash}:{timestamp}:{case_id}:{doc_type}:{json.dumps(data, sort_keys=True)}"
    return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

class BlockchainService:
    @staticmethod
    def ensure_genesis_block(db: Session):
        first_block = db.query(BlockchainBlockModel).filter(BlockchainBlockModel.block_index == 1).first()
        if not first_block:
            now_iso = datetime.datetime.utcnow().isoformat() + "Z"
            genesis_data = {"event": "GENESIS_BLOCK", "system": "ATLAS Forensics Engine", "protocol": "v2.0"}
            gen_hash = calculate_block_hash(1, GENESIS_HASH, now_iso, "SYSTEM_GENESIS", "SYSTEM_GENESIS", genesis_data)
            block = BlockchainBlockModel(
                block_index=1,
                case_id="SYSTEM_GENESIS",
                document_type="SYSTEM_GENESIS",
                hash=gen_hash,
                prev_hash=GENESIS_HASH,
                timestamp=now_iso,
                data=genesis_data,
                merkle_root=gen_hash
            )
            db.add(block)
            db.commit()

    @staticmethod
    def append_block(
        db: Session,
        case_id: str,
        document_type: str,
        data: Dict[str, Any]
    ) -> BlockchainBlockModel:
        BlockchainService.ensure_genesis_block(db)
        last_block = db.query(BlockchainBlockModel).order_by(BlockchainBlockModel.block_index.desc()).first()
        prev_hash = last_block.hash if last_block else GENESIS_HASH
        new_index = (last_block.block_index + 1) if last_block else 1
        now_iso = datetime.datetime.utcnow().isoformat() + "Z"
        
        block_hash = calculate_block_hash(new_index, prev_hash, now_iso, case_id, document_type, data)
        block = BlockchainBlockModel(
            block_index=new_index,
            case_id=case_id,
            document_type=document_type,
            hash=block_hash,
            prev_hash=prev_hash,
            timestamp=now_iso,
            data=data,
            merkle_root=block_hash
        )
        db.add(block)
        db.commit()
        db.refresh(block)
        return block

    @staticmethod
    def verify_chain(db: Session) -> Tuple[bool, str, int]:
        BlockchainService.ensure_genesis_block(db)
        blocks = db.query(BlockchainBlockModel).order_by(BlockchainBlockModel.block_index.asc()).all()
        if not blocks:
            return True, "Chain is empty", 0

        for i, block in enumerate(blocks):
            if i == 0:
                expected_prev = GENESIS_HASH
            else:
                expected_prev = blocks[i-1].hash

            if block.prev_hash != expected_prev:
                return False, f"Broken link at block {block.block_index}: prev_hash mismatch", len(blocks)

            calc_hash = calculate_block_hash(
                block.block_index,
                block.prev_hash,
                block.timestamp,
                block.case_id,
                block.document_type,
                block.data or {}
            )
            if calc_hash != block.hash:
                return False, f"Tamper detected at block {block.block_index}: hash payload mismatch", len(blocks)

        return True, "Chain integrity cryptographically verified. All Merkle roots intact.", len(blocks)

    @staticmethod
    def verify_case(db: Session, case_id: str) -> Dict[str, Any]:
        chain_valid, chain_msg, total_blocks = BlockchainService.verify_chain(db)
        case_blocks = db.query(BlockchainBlockModel).filter(BlockchainBlockModel.case_id == case_id).all()
        evidence_items = db.query(EvidenceItemModel).filter(EvidenceItemModel.case_id == case_id).all()

        if not chain_valid:
            return {
                "status": "TAMPER_DETECTED",
                "case_id": case_id,
                "valid": False,
                "message": chain_msg,
                "blocks_count": len(case_blocks),
                "evidence_count": len(evidence_items)
            }

        # Check evidence hashes match blocks
        evidence_sha_set = {e.sha256 for e in evidence_items}
        matched_blocks = 0
        for b in case_blocks:
            b_sha = (b.data or {}).get("sha256")
            if b_sha and b_sha in evidence_sha_set:
                matched_blocks += 1

        return {
            "status": "VERIFIED",
            "case_id": case_id,
            "valid": True,
            "message": f"Case {case_id} integrity verified across {len(case_blocks)} chain-of-custody blocks.",
            "blocks_count": len(case_blocks),
            "evidence_count": len(evidence_items),
            "matched_records": matched_blocks
        }

    @staticmethod
    def log_activity(
        db: Session,
        case_id: str,
        action_type: str,
        title: str,
        description: str,
        officer_name: str = "System",
        officer_badge: str = "SYS-001",
        status_type: str = "info",
        icon_type: str = "info"
    ) -> ActivityLogModel:
        now_dt = datetime.datetime.utcnow()
        now_iso = now_dt.isoformat() + "Z"
        formatted_date = now_dt.strftime("%d %b %Y, %H:%M")
        
        # Sequence number
        last_log = db.query(ActivityLogModel).filter(ActivityLogModel.case_id == case_id).order_by(ActivityLogModel.sequence_num.desc()).first()
        seq = (last_log.sequence_num + 1) if last_log else 1
        
        event_id = f"EVT-{case_id}-{seq}-{hashlib.md5(f'{now_iso}:{title}'.encode()).hexdigest()[:8]}"
        
        log_entry = ActivityLogModel(
            event_id=event_id,
            case_id=case_id,
            sequence_num=seq,
            action_type=action_type,
            title=title,
            description=description,
            officer_name=officer_name,
            officer_badge=officer_badge,
            timestamp=now_iso,
            formatted_date=formatted_date,
            status_type=status_type,
            icon_type=icon_type
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
