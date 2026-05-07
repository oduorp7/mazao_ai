import csv
import io
import re
from datetime import datetime, timezone
from typing import List, Optional

from apps.agent.state import RawTransaction, TransactionType
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

def detect_internal_transfer(name: str, tx_type: TransactionType) -> TransactionType:
    """
    T37: Detects if a transaction is an internal financing movement (M-Shwari, Fuliza, etc.)
    while preserving business charges/fees.
    """
    name_upper = name.upper()
    internal_keywords = [
        "M-SHWARI", "MSHWARI", "FULIZA", "OVERDRAFT", "OD LOAN", 
        "LOAN REPAYMENT", "GIVE TO", "WITHDRAW FROM", "DEPOSIT TO"
    ]
    is_internal = any(kw in name_upper for kw in internal_keywords)
    is_charge = any(kw in name_upper for kw in ["CHARGE", "FEE", "COST"])
    
    if is_internal and not is_charge:
        return TransactionType.INTERNAL_TRANSFER
    return tx_type

def parse(data: bytes | str, fmt: str) -> List[RawTransaction]:
    """
    Main entry point for parsing M-Pesa statements.
    Supported formats: csv, pdf_text, sms.
    """
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
    else:
        text = data

    log.info("parsing_statement", fmt=fmt, length=len(text))

    if fmt == "csv":
        txs = _parse_csv(text)
    elif fmt == "pdf_text":
        txs = _parse_pdf_text(text)
    elif fmt == "sms":
        txs = _parse_sms(text)
    else:
        log.warning("unsupported_format", fmt=fmt)
        return []

    # T37: Exclude internal financing movements from the pipeline to prevent
    # non-revenue drawdowns from inflating business income totals.
    filtered = [t for t in txs if t.transaction_type != TransactionType.INTERNAL_TRANSFER]
    deduped = _deduplicate(filtered)
    
    log.info("parsing_complete", count=len(deduped), excluded=len(txs)-len(filtered), fmt=fmt)
    return deduped

def _parse_csv(text: str) -> List[RawTransaction]:
    def get_any(row, keys, default=None):
        for k in keys:
            if row.get(k) is not None:
                return row[k]
        return default

    txs = []
    f = io.StringIO(text)
    reader = csv.DictReader(f)
    
    for row in reader:
        try:
            # MySafaricom CSV columns: Receipt No, Completion Time, Details, Transaction Status, Paid In, Withdrawn, Balance
            receipt = get_any(row, ["Receipt No", "Receipt No.", "Receipt", "Receipt Number"])
            status  = get_any(row, ["Transaction Status", "Status"])
            
            if not receipt or str(status).strip().lower() != "completed":
                continue
                
            paid_in_str = get_any(row, ["Paid In", "PaidIn", "Credit"], "0") or "0"
            withdrawn_str = get_any(row, ["Withdrawn", "Debit", "Paid Out"], "0") or "0"
            
            paid_in = float(paid_in_str.replace(",", ""))
            withdrawn = float(withdrawn_str.replace(",", ""))
            
            # Amount is either paid in or withdrawn
            amount = paid_in if paid_in > 0 else withdrawn
            tx_type = TransactionType.C2B if paid_in > 0 else TransactionType.B2C
            
            # T37: Internal Financing & Transfer Classification
            # Prevents loan drawdowns and internal movements from inflating revenue/expenses.
            # Charges (Fees) are preserved as business expenses even on internal movements.
            name = get_any(row, ["Details", "Description"], "UNKNOWN")
            tx_type = detect_internal_transfer(name, tx_type)

            # Format: 2024-04-18 14:30:00
            ts_str = get_any(row, ["Completion Time", "CompletionTime", "Date"])
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                ts = datetime.now(timezone.utc)
            
            txs.append(RawTransaction(
                mpesa_ref=receipt,
                amount=amount,
                phone="", 
                name=name,
                shortcode="",
                transaction_type=tx_type,
                timestamp=ts,
                raw_payload=row
            ))

        except (ValueError, TypeError, KeyError):
            continue
            
    return txs

def _parse_pdf_text(text: str) -> List[RawTransaction]:
    """Extractor for raw PDF-to-text dumps (FAANG-grade regex)."""
    txs = []
    
    # Receipt No. [REF] ... KES [AMOUNT]
    primary_pattern = re.compile(r"Receipt No\.\s*([A-Z0-9]+).*?KES\s*([\d,]+\.?\d*)", re.DOTALL | re.MULTILINE)
    
    # Fallback/Table pattern: [REF] [DATE] [DETAILS] [AMOUNT]
    fallback_pattern = re.compile(r"([A-Z]{2}\d+)\s+(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+(.+?)\s+([\d,]+\.?\d*)")

    # Match primary
    for match in primary_pattern.finditer(text):
        try:
            ref, amt_str = match.groups()
            txs.append(RawTransaction(
                mpesa_ref=ref,
                amount=float(amt_str.replace(",", "")),
                phone="",
                name="PDF_CAPTURE",
                shortcode="",
                transaction_type=TransactionType.UNKNOWN,
                timestamp=datetime.now(timezone.utc)
            ))
        except Exception:
            continue

    # Match fallbacks
    for match in fallback_pattern.finditer(text):
        try:
            ref, ts_str, name, amt_str = match.groups()
            txs.append(RawTransaction(
                mpesa_ref=ref,
                amount=float(amt_str.replace(",", "")),
                phone="",
                name=name.strip(),
                shortcode="",
                transaction_type=TransactionType.UNKNOWN,
                timestamp=datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            ))
        except Exception:
            continue
        
    return txs

def _parse_sms(text: str) -> List[RawTransaction]:
    """Captures M-Pesa confirmation SMS text."""
    pattern = re.compile(r"confirmed\.\s*([A-Z0-9]+).*?Ksh([\d,]+\.?\d*)", re.I | re.DOTALL)
    match = pattern.search(text)
    if match:
        try:
            ref, amt_str = match.groups()
            return [RawTransaction(
                mpesa_ref=ref,
                amount=float(amt_str.replace(",", "")),
                phone="",
                name="SMS_FORWARD",
                shortcode="",
                transaction_type=TransactionType.C2B,
                timestamp=datetime.now(timezone.utc)
            )]
        except Exception:
            pass
    return []

def _deduplicate(txs: List[RawTransaction]) -> List[RawTransaction]:
    # T37: Context-aware deduplication.
    # M-Pesa statements often use the same Receipt Number for the main transaction 
    # and the associated 'Pay Bill Charge'. We must preserve both.
    seen = set()
    unique = []
    for tx in txs:
        # Use (mpesa_ref, amount, name) as the unique key to preserve related charges
        key = (tx.mpesa_ref, tx.amount, tx.name)
        if key not in seen:
            seen.add(key)
            unique.append(tx)
    return unique
