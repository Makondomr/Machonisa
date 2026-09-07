import sqlite3
from pathlib import Path
from datetime import datetime
import uuid

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
UPLOAD_DIR = BASE_DIR / 'uploads'
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'lending_platform.db'


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS platform_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        cellphone TEXT,
        role TEXT NOT NULL DEFAULT 'Superuser',
        status TEXT NOT NULL DEFAULT 'Active',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS lenders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lender_code TEXT UNIQUE NOT NULL,
        business_name TEXT NOT NULL,
        registration_number TEXT,
        ncr_number TEXT,
        contact_person TEXT,
        registered_cellphone TEXT NOT NULL,
        email TEXT,
        address TEXT,
        province TEXT,
        bank_name TEXT,
        bank_account_name TEXT,
        bank_account_number TEXT,
        bank_branch_code TEXT,
        subscription_plan TEXT DEFAULT 'Basic',
        subscription_status TEXT DEFAULT 'Approved',
        created_by_superuser INTEGER,
        approved_by INTEGER,
        approved_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS lender_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lender_id INTEGER UNIQUE NOT NULL,
        min_loan_amount REAL NOT NULL DEFAULT 500,
        max_loan_amount REAL NOT NULL DEFAULT 5000,
        min_monthly_income REAL NOT NULL DEFAULT 0,
        min_employment_months INTEGER NOT NULL DEFAULT 0,
        employment_type TEXT NOT NULL DEFAULT 'Any',
        min_term_months INTEGER NOT NULL DEFAULT 1,
        max_term_months INTEGER NOT NULL DEFAULT 3,
        max_installment_percent REAL NOT NULL DEFAULT 30,
        provinces_served TEXT DEFAULT 'All',
        requires_id INTEGER NOT NULL DEFAULT 1,
        requires_payslip INTEGER NOT NULL DEFAULT 1,
        requires_bank_statement INTEGER NOT NULL DEFAULT 1,
        bank_statement_months INTEGER NOT NULL DEFAULT 3,
        requires_proof_address INTEGER NOT NULL DEFAULT 1,
        active INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY(lender_id) REFERENCES lenders(id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS borrowers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        borrower_number TEXT UNIQUE NOT NULL,
        first_name TEXT NOT NULL,
        surname TEXT NOT NULL,
        id_number TEXT NOT NULL,
        cellphone TEXT NOT NULL,
        email TEXT,
        residential_address TEXT,
        province TEXT,
        employment_status TEXT,
        employer_name TEXT,
        employment_months INTEGER NOT NULL DEFAULT 0,
        gross_income REAL NOT NULL DEFAULT 0,
        net_income REAL NOT NULL DEFAULT 0,
        salary_date INTEGER,
        bank_name TEXT,
        bank_account_holder TEXT,
        bank_account_number TEXT,
        bank_account_type TEXT,
        branch_code TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS loan_applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_number TEXT UNIQUE NOT NULL,
        borrower_id INTEGER NOT NULL,
        requested_amount REAL NOT NULL,
        requested_term INTEGER NOT NULL,
        loan_purpose TEXT,
        monthly_income REAL NOT NULL DEFAULT 0,
        monthly_expenses REAL NOT NULL DEFAULT 0,
        disposable_income REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'Submitted',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        submitted_at TEXT,
        FOREIGN KEY(borrower_id) REFERENCES borrowers(id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS application_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        borrower_id INTEGER NOT NULL,
        document_type TEXT NOT NULL,
        original_filename TEXT NOT NULL,
        file_path TEXT NOT NULL,
        verification_status TEXT NOT NULL DEFAULT 'Pending',
        uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(application_id) REFERENCES loan_applications(id),
        FOREIGN KEY(borrower_id) REFERENCES borrowers(id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS lender_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        lender_id INTEGER NOT NULL,
        match_score REAL NOT NULL DEFAULT 0,
        match_status TEXT NOT NULL DEFAULT 'Matched',
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(application_id, lender_id),
        FOREIGN KEY(application_id) REFERENCES loan_applications(id),
        FOREIGN KEY(lender_id) REFERENCES lenders(id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS loan_offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        lender_id INTEGER NOT NULL,
        approved_amount REAL NOT NULL,
        interest_amount REAL NOT NULL DEFAULT 0,
        initiation_fee REAL NOT NULL DEFAULT 0,
        service_fee REAL NOT NULL DEFAULT 0,
        total_repayment REAL NOT NULL,
        number_of_installments INTEGER NOT NULL DEFAULT 1,
        installment_amount REAL NOT NULL DEFAULT 0,
        first_payment_date TEXT,
        offer_status TEXT NOT NULL DEFAULT 'Pending',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(application_id) REFERENCES loan_applications(id),
        FOREIGN KEY(lender_id) REFERENCES lenders(id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_number TEXT UNIQUE NOT NULL,
        application_id INTEGER NOT NULL,
        offer_id INTEGER NOT NULL,
        borrower_id INTEGER NOT NULL,
        lender_id INTEGER NOT NULL,
        principal_amount REAL NOT NULL,
        total_repayment REAL NOT NULL,
        outstanding_balance REAL NOT NULL,
        start_date TEXT,
        loan_status TEXT NOT NULL DEFAULT 'Awaiting Mandate',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(application_id) REFERENCES loan_applications(id),
        FOREIGN KEY(offer_id) REFERENCES loan_offers(id),
        FOREIGN KEY(borrower_id) REFERENCES borrowers(id),
        FOREIGN KEY(lender_id) REFERENCES lenders(id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS payment_mandates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER NOT NULL UNIQUE,
        lender_id INTEGER NOT NULL,
        payment_provider TEXT,
        provider_reference TEXT,
        mandate_amount REAL,
        mandate_start_date TEXT,
        mandate_status TEXT NOT NULL DEFAULT 'Not Sent',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(loan_id) REFERENCES loans(id),
        FOREIGN KEY(lender_id) REFERENCES lenders(id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS repayment_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER NOT NULL,
        installment_number INTEGER NOT NULL,
        due_date TEXT NOT NULL,
        amount_due REAL NOT NULL,
        amount_paid REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'Pending',
        FOREIGN KEY(loan_id) REFERENCES loans(id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS payment_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER NOT NULL,
        repayment_schedule_id INTEGER,
        lender_id INTEGER NOT NULL,
        transaction_reference TEXT,
        amount REAL NOT NULL,
        provider_fee REAL NOT NULL DEFAULT 0,
        platform_fee REAL NOT NULL DEFAULT 0,
        transaction_status TEXT NOT NULL DEFAULT 'Pending',
        transaction_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(loan_id) REFERENCES loans(id),
        FOREIGN KEY(repayment_schedule_id) REFERENCES repayment_schedule(id),
        FOREIGN KEY(lender_id) REFERENCES lenders(id)
    )''')

    existing = cur.execute("SELECT id FROM platform_users WHERE role='Superuser' LIMIT 1").fetchone()
    if not existing:
        cur.execute("INSERT INTO platform_users(full_name, role, status) VALUES('Platform Administrator','Superuser','Active')")

    conn.commit()
    conn.close()


def generate_code(prefix, width=6):
    return f"{prefix}-{uuid.uuid4().hex[:width].upper()}"


def generate_lender_code():
    return generate_code('LND', 6)


def generate_borrower_number():
    return generate_code('BOR', 8)


def generate_application_number():
    return f"APP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def generate_loan_number():
    return f"LOAN-{datetime.now().strftime('%Y')}-{uuid.uuid4().hex[:6].upper()}"
