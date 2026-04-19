import pytest
import sys
import os
from pathlib import Path

# Ensure we can import from the parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from mpesa_parser import parse
from state import TransactionType

def test_parse_csv_returns_correct_transaction_count():
    csv_data = """Receipt No,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance
SH123ABC,2024-04-18 14:30:00,JANE DOE,Completed,1500.00,,1500.00
SH456DEF,2024-04-18 15:00:00,NAIVAS,Completed,,2000.00,-500.00
"""
    txs = parse(csv_data, "csv")
    assert len(txs) == 2
    assert txs[0].mpesa_ref == "SH123ABC"
    assert txs[0].amount == 1500.0
    assert txs[1].transaction_type == TransactionType.B2C

def test_parse_pdf_text_extracts_amounts_correctly():
    pdf_text = """
    Random PDF Noise
    Receipt No. QH123XYZ
    Amount KES 5,400.50
    More Noise
    Receipt No. QH456PDQ
    Amount KES 1,000
    """
    txs = parse(pdf_text, "pdf_text")
    assert len(txs) == 2
    assert txs[0].mpesa_ref == "QH123XYZ"
    assert txs[0].amount == 5400.50
    assert txs[1].amount == 1000.0

def test_duplicate_receipts_are_deduplicated():
    csv_data = """Receipt No,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance
DUP123,2024-04-18 14:30:00,JANE DOE,Completed,1500.00,,1500.00
DUP123,2024-04-18 14:30:00,JANE DOE,Completed,1500.00,,1500.00
"""
    txs = parse(csv_data, "csv")
    assert len(txs) == 1

def test_malformed_lines_are_skipped_not_crashed():
    csv_data = """Receipt No,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance
OK123,2024-04-18 14:30:00,JANE DOE,Completed,1500.00,,1500.00
BAD,,,,,
"""
    txs = parse(csv_data, "csv")
    assert len(txs) == 1
    assert txs[0].mpesa_ref == "OK123"

def test_parse_sms_captures_correctly():
    sms = "Confirmed. NH123456 Sent to Safaricom Ksh1,500.00 on 18/4/24 at 2:30 PM."
    txs = parse(sms, "sms")
    assert len(txs) == 1
    assert txs[0].mpesa_ref == "NH123456"
    assert txs[0].amount == 1500.0
