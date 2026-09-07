import streamlit as st
from datetime import date, timedelta, datetime
import uuid

from database import (
    init_db,
    get_connection,
    UPLOAD_DIR,
    generate_lender_code,
    generate_borrower_number,
    generate_application_number,
    generate_loan_number,
)

st.set_page_config(page_title='Loan Marketplace', page_icon='💰', layout='wide', initial_sidebar_state='expanded')

st.markdown('''
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] {font-family:'Inter',sans-serif;}
.stApp {background:radial-gradient(circle at top left,rgba(59,130,246,.10),transparent 34%),radial-gradient(circle at top right,rgba(16,185,129,.08),transparent 30%),#f7f9fc;}
.block-container {max-width:1220px;padding-top:2rem;padding-bottom:4rem;}
h1,h2,h3 {letter-spacing:-.03em;color:#0f172a;}
p,label,.stMarkdown {color:#334155;}
[data-testid="stSidebar"] {background:linear-gradient(180deg,#0f172a 0%,#172554 100%);border-right:1px solid rgba(255,255,255,.08);}
[data-testid="stSidebar"] * {color:#f8fafc !important;}
.hero {background:linear-gradient(135deg,#0f172a 0%,#172554 52%,#0f766e 130%);padding:3.2rem 3rem;border-radius:28px;color:white;box-shadow:0 24px 60px rgba(15,23,42,.18);margin-bottom:1.6rem;position:relative;overflow:hidden;}
.hero:after {content:'';position:absolute;width:220px;height:220px;border-radius:50%;background:rgba(255,255,255,.07);right:-60px;top:-70px;}
.hero-badge {display:inline-block;padding:.42rem .8rem;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.18);border-radius:999px;font-size:.82rem;font-weight:700;margin-bottom:1rem;}
.hero h1 {color:#fff;font-size:clamp(2.2rem,5vw,4rem);line-height:1.02;margin:0 0 .9rem 0;max-width:780px;}
.hero p {color:#dbeafe;font-size:1.08rem;max-width:760px;margin:0;}
.feature-card {background:rgba(255,255,255,.90);border:1px solid #e2e8f0;border-radius:18px;padding:1.15rem 1.25rem;box-shadow:0 8px 30px rgba(15,23,42,.05);min-height:118px;}
.feature-card strong {color:#0f172a;font-size:1rem;}
div[data-testid="stForm"] {background:rgba(255,255,255,.94);border:1px solid #e2e8f0;padding:1.5rem;border-radius:20px;box-shadow:0 12px 35px rgba(15,23,42,.06);}
div[data-testid="stMetric"] {background:white;border:1px solid #e2e8f0;border-radius:16px;padding:1rem 1.1rem;box-shadow:0 8px 25px rgba(15,23,42,.045);}
div.stButton>button,div.stFormSubmitButton>button {border:0!important;border-radius:12px!important;min-height:46px;font-weight:700!important;box-shadow:0 7px 18px rgba(15,23,42,.10);transition:transform .15s ease,box-shadow .15s ease;}
div.stButton>button:hover,div.stFormSubmitButton>button:hover {transform:translateY(-1px);box-shadow:0 10px 24px rgba(15,23,42,.15);}
div[data-testid="stTextInput"] input,div[data-testid="stNumberInput"] input,div[data-baseweb="select"]>div,textarea {border-radius:11px!important;}
hr {border-color:#e2e8f0!important;}
#MainMenu {visibility:hidden;} footer {visibility:hidden;} header {background:transparent;}
</style>
''', unsafe_allow_html=True)

init_db()


def money(value):
    return f"R{float(value or 0):,.2f}"


def normalise_cell(cell):
    return str(cell or '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '').strip()


def save_uploaded_file(uploaded_file, application_number, document_type):
    app_dir = UPLOAD_DIR / application_number
    app_dir.mkdir(parents=True, exist_ok=True)
    safe_name = uploaded_file.name.replace('/', '_').replace('\\', '_')
    filename = f"{document_type.replace(' ', '_')}_{uuid.uuid4().hex[:6]}_{safe_name}"
    file_path = app_dir / filename
    with open(file_path, 'wb') as f:
        f.write(uploaded_file.getbuffer())
    return str(file_path)


def get_superuser():
    conn = get_connection()
    row = conn.execute("SELECT * FROM platform_users WHERE role='Superuser' AND status='Active' ORDER BY id LIMIT 1").fetchone()
    conn.close()
    return row


def get_lender_by_access(lender_code, cellphone):
    conn = get_connection()
    lender = conn.execute('''
        SELECT * FROM lenders
        WHERE UPPER(lender_code)=UPPER(?)
          AND registered_cellphone=?
          AND subscription_status='Approved'
        LIMIT 1
    ''', (lender_code.strip(), normalise_cell(cellphone))).fetchone()
    conn.close()
    return lender


def get_application_by_access(application_number, cellphone):
    conn = get_connection()
    row = conn.execute('''
        SELECT a.*, b.first_name, b.surname, b.cellphone, b.email, b.province
        FROM loan_applications a
        JOIN borrowers b ON b.id=a.borrower_id
        WHERE UPPER(a.application_number)=UPPER(?) AND b.cellphone=?
        LIMIT 1
    ''', (application_number.strip(), normalise_cell(cellphone))).fetchone()
    conn.close()
    return row


def run_matching(application_id):
    conn = get_connection()
    application = conn.execute('''
        SELECT a.*, b.employment_status, b.employment_months, b.net_income, b.province
        FROM loan_applications a
        JOIN borrowers b ON b.id=a.borrower_id
        WHERE a.id=?
    ''', (application_id,)).fetchone()

    lenders = conn.execute('''
        SELECT l.*, r.*
        FROM lenders l
        JOIN lender_rules r ON r.lender_id=l.id
        WHERE l.subscription_status='Approved' AND r.active=1
    ''').fetchall()

    conn.execute('DELETE FROM lender_matches WHERE application_id=?', (application_id,))

    for lender in lenders:
        reasons = []
        score = 100.0

        if application['requested_amount'] < lender['min_loan_amount']:
            reasons.append(f"Amount below minimum {money(lender['min_loan_amount'])}")
            score -= 30
        if application['requested_amount'] > lender['max_loan_amount']:
            reasons.append(f"Amount exceeds maximum {money(lender['max_loan_amount'])}")
            score -= 30
        if application['net_income'] < lender['min_monthly_income']:
            reasons.append(f"Income below minimum {money(lender['min_monthly_income'])}")
            score -= 30
        if application['employment_months'] < lender['min_employment_months']:
            reasons.append(f"Employment history below {lender['min_employment_months']} months")
            score -= 20
        if application['requested_term'] < lender['min_term_months']:
            reasons.append('Requested term below lender minimum')
            score -= 10
        if application['requested_term'] > lender['max_term_months']:
            reasons.append('Requested term exceeds lender maximum')
            score -= 10
        if lender['employment_type'] != 'Any' and application['employment_status'] != lender['employment_type']:
            reasons.append(f"Requires employment type: {lender['employment_type']}")
            score -= 20

        provinces = (lender['provinces_served'] or 'All').strip()
        if provinces.lower() != 'all':
            allowed = [p.strip().lower() for p in provinces.split(',') if p.strip()]
            if (application['province'] or '').strip().lower() not in allowed:
                reasons.append('Borrower province outside lender service area')
                score -= 20

        status = 'Matched' if not reasons else 'Not Eligible'
        reason = 'Meets lender criteria' if not reasons else '; '.join(reasons)

        conn.execute('''
            INSERT INTO lender_matches(application_id,lender_id,match_score,match_status,reason)
            VALUES(?,?,?,?,?)
        ''', (application_id, lender['id'], max(score, 0), status, reason))

    conn.execute("UPDATE loan_applications SET status='Matching Complete' WHERE id=?", (application_id,))
    conn.commit()
    conn.close()


def clear_portal():
    for key in ['portal', 'lender_id', 'tracked_application_id']:
        st.session_state.pop(key, None)
    st.rerun()


if 'portal' not in st.session_state:
    st.session_state.portal = None


# ============================================================
# HOME
# ============================================================
if st.session_state.portal is None:
    st.markdown('''
    <div class="hero">
        <div class="hero-badge">SMART LENDING MARKETPLACE</div>
        <h1>One application. More lending possibilities.</h1>
        <p>Apply once, upload your supporting documents, and let the platform match your request with participating lenders whose lending rules align with your application.</p>
    </div>
    ''', unsafe_allow_html=True)

    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown('<div class="feature-card">⚡ <strong>Fast application</strong><br><span>No borrower account to create. Enter your details and submit.</span></div>', unsafe_allow_html=True)
    with f2:
        st.markdown('<div class="feature-card">🎯 <strong>Rule-based matching</strong><br><span>Your request is checked against active lender criteria.</span></div>', unsafe_allow_html=True)
    with f3:
        st.markdown('<div class="feature-card">🔎 <strong>Simple tracking</strong><br><span>Use your application number and cellphone to check progress.</span></div>', unsafe_allow_html=True)

    st.markdown('### What would you like to do?')

    c1, c2 = st.columns(2)
    with c1:
        if st.button('💰 APPLY FOR A LOAN', type='primary', use_container_width=True):
            st.session_state.portal = 'apply'
            st.rerun()
    with c2:
        if st.button('🔎 CHECK MY APPLICATION', use_container_width=True):
            st.session_state.portal = 'track'
            st.rerun()

    c3, c4 = st.columns(2)
    with c3:
        if st.button('🏦 LENDER ACCESS', use_container_width=True):
            st.session_state.portal = 'lender'
            st.rerun()
    with c4:
        if st.button('⚙️ SUPERUSER', use_container_width=True):
            st.session_state.portal = 'superuser'
            st.rerun()
    st.stop()


# ============================================================
# APPLY
# ============================================================
if st.session_state.portal == 'apply':
    st.title('Apply for a Loan')
    if st.button('← Back to Home'):
        clear_portal()

    with st.form('loan_application_form'):
        st.subheader('1. Personal Details')
        c1, c2 = st.columns(2)
        first_name = c1.text_input('First Name *')
        surname = c2.text_input('Surname *')
        id_number = st.text_input('SA ID / Passport Number *')
        cellphone = st.text_input('Cellphone *')
        email = st.text_input('Email')
        residential_address = st.text_area('Residential Address')
        province = st.selectbox('Province', ['Gauteng','Limpopo','Mpumalanga','North West','Free State','KwaZulu-Natal','Eastern Cape','Western Cape','Northern Cape'])

        st.subheader('2. Employment & Income')
        employment_status = st.selectbox('Employment Type', ['Permanent','Contract','Self Employed','Unemployed'])
        employer_name = st.text_input('Employer')
        employment_months = st.number_input('Months Employed', min_value=0, value=0)
        a, b = st.columns(2)
        gross_income = a.number_input('Gross Monthly Income', min_value=0.0, value=0.0)
        net_income = b.number_input('Net Monthly Income', min_value=0.0, value=0.0)
        salary_date = st.number_input('Salary Day', min_value=1, max_value=31, value=25)

        st.subheader('3. Monthly Expenses')
        rent = st.number_input('Rent / Bond', min_value=0.0, value=0.0)
        food = st.number_input('Food', min_value=0.0, value=0.0)
        transport = st.number_input('Transport', min_value=0.0, value=0.0)
        insurance = st.number_input('Insurance', min_value=0.0, value=0.0)
        existing_loans = st.number_input('Existing Loan Repayments', min_value=0.0, value=0.0)
        other_expenses = st.number_input('Other Expenses', min_value=0.0, value=0.0)

        st.subheader('4. What Do You Need?')
        requested_amount = st.number_input('Loan Amount', min_value=100.0, value=1000.0)
        requested_term = st.number_input('Preferred Repayment Term (Months)', min_value=1, max_value=36, value=1)
        loan_purpose = st.text_area('Purpose of Loan')

        st.subheader('5. Banking Details')
        bank_name = st.text_input('Bank')
        bank_account_holder = st.text_input('Account Holder')
        bank_account_number = st.text_input('Account Number')
        bank_account_type = st.selectbox('Account Type', ['Cheque / Current','Savings'])
        branch_code = st.text_input('Branch Code')

        st.subheader('6. Supporting Documents')
        id_document = st.file_uploader('ID / Passport *', type=['pdf','png','jpg','jpeg'])
        payslip = st.file_uploader('Latest Payslip *', type=['pdf','png','jpg','jpeg'])
        bank_statement_1 = st.file_uploader('Bank Statement - Month 1 *', type=['pdf'])
        bank_statement_2 = st.file_uploader('Bank Statement - Month 2 *', type=['pdf'])
        bank_statement_3 = st.file_uploader('Bank Statement - Month 3 *', type=['pdf'])
        proof_of_address = st.file_uploader('Proof of Address *', type=['pdf','png','jpg','jpeg'])

        st.subheader('7. Consents')
        consent_credit = st.checkbox('I consent to a credit and affordability assessment.')
        consent_privacy = st.checkbox('I consent to the processing of my information for this application.')
        submit_application = st.form_submit_button('Submit Loan Application', type='primary')

    if submit_application:
        if not all([first_name.strip(), surname.strip(), id_number.strip(), cellphone.strip()]):
            st.error('Complete all required personal details.')
            st.stop()

        required_docs = [id_document,payslip,bank_statement_1,bank_statement_2,bank_statement_3,proof_of_address]
        if not all(required_docs):
            st.error('Upload ID, payslip, all 3 bank statements and proof of address.')
            st.stop()
        if not consent_credit or not consent_privacy:
            st.error('Both consents are required.')
            st.stop()

        total_expenses = rent + food + transport + insurance + existing_loans + other_expenses
        disposable_income = net_income - total_expenses
        application_number = generate_application_number()
        borrower_number = generate_borrower_number()

        conn = get_connection()
        try:
            cur = conn.execute('''
                INSERT INTO borrowers(
                    borrower_number,first_name,surname,id_number,cellphone,email,
                    residential_address,province,employment_status,employer_name,
                    employment_months,gross_income,net_income,salary_date,bank_name,
                    bank_account_holder,bank_account_number,bank_account_type,branch_code
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                borrower_number, first_name, surname, id_number.strip(), normalise_cell(cellphone), email,
                residential_address, province, employment_status, employer_name, employment_months,
                gross_income, net_income, salary_date, bank_name, bank_account_holder,
                bank_account_number, bank_account_type, branch_code
            ))
            borrower_id = cur.lastrowid

            cur = conn.execute('''
                INSERT INTO loan_applications(
                    application_number,borrower_id,requested_amount,requested_term,loan_purpose,
                    monthly_income,monthly_expenses,disposable_income,status,submitted_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ''', (
                application_number, borrower_id, requested_amount, requested_term, loan_purpose,
                net_income, total_expenses, disposable_income, 'Submitted',
                datetime.now().isoformat(timespec='seconds')
            ))
            application_id = cur.lastrowid

            docs = [
                ('ID / Passport', id_document),
                ('Payslip', payslip),
                ('Bank Statement - Month 1', bank_statement_1),
                ('Bank Statement - Month 2', bank_statement_2),
                ('Bank Statement - Month 3', bank_statement_3),
                ('Proof of Address', proof_of_address),
            ]
            for doc_type, uploaded_file in docs:
                file_path = save_uploaded_file(uploaded_file, application_number, doc_type)
                conn.execute('''
                    INSERT INTO application_documents(
                        application_id,borrower_id,document_type,original_filename,file_path,verification_status
                    ) VALUES(?,?,?,?,?,'Pending')
                ''', (application_id, borrower_id, doc_type, uploaded_file.name, file_path))

            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            st.error(f'Application could not be saved: {e}')
            st.stop()
        conn.close()

        run_matching(application_id)
        conn = get_connection()
        matching_count = conn.execute("SELECT COUNT(*) AS total FROM lender_matches WHERE application_id=? AND match_status='Matched'", (application_id,)).fetchone()['total']
        conn.close()

        st.success('Application submitted successfully.')
        st.markdown(f"### Your Application Number: `{application_number}`")
        st.write('Keep this number. Use it with your cellphone number to check offers and loan status.')
        if matching_count:
            st.info(f'Your application currently aligns with {matching_count} lender(s). Matching does not mean approval.')
        else:
            st.warning('No approved lender currently matches your request.')


# ============================================================
# TRACK APPLICATION
# ============================================================
elif st.session_state.portal == 'track':
    st.title('Check My Application')
    if st.button('← Back to Home'):
        clear_portal()

    if 'tracked_application_id' not in st.session_state:
        with st.form('tracking_form'):
            application_number = st.text_input('Application Number')
            cellphone = st.text_input('Cellphone Number')
            check = st.form_submit_button('Check Application', type='primary')
        if check:
            application = get_application_by_access(application_number, cellphone)
            if not application:
                st.error('Application number and cellphone do not match.')
                st.stop()
            st.session_state.tracked_application_id = application['id']
            st.rerun()
        st.stop()

    application_id = st.session_state.tracked_application_id
    conn = get_connection()
    application = conn.execute('''
        SELECT a.*, b.first_name, b.surname, b.cellphone
        FROM loan_applications a JOIN borrowers b ON b.id=a.borrower_id WHERE a.id=?
    ''', (application_id,)).fetchone()
    offers = conn.execute('''
        SELECT o.*, l.business_name
        FROM loan_offers o JOIN lenders l ON l.id=o.lender_id
        WHERE o.application_id=? ORDER BY o.id DESC
    ''', (application_id,)).fetchall()
    loan = conn.execute('''
        SELECT ln.*, l.business_name, pm.mandate_status
        FROM loans ln JOIN lenders l ON l.id=ln.lender_id
        LEFT JOIN payment_mandates pm ON pm.loan_id=ln.id
        WHERE ln.application_id=? LIMIT 1
    ''', (application_id,)).fetchone()
    conn.close()

    st.subheader(f"{application['application_number']} — {application['first_name']} {application['surname']}")
    a,b,c,d = st.columns(4)
    a.metric('Requested', money(application['requested_amount']))
    b.metric('Term', f"{application['requested_term']} months")
    c.metric('Disposable Income', money(application['disposable_income']))
    d.metric('Status', application['status'])

    st.write('### Loan Offers')
    pending = [o for o in offers if o['offer_status']=='Pending']
    if not pending:
        st.info('No pending offers yet.')

    for offer in pending:
        with st.container(border=True):
            st.subheader(offer['business_name'])
            x,y,z = st.columns(3)
            x.metric('Approved Amount', money(offer['approved_amount']))
            y.metric('Total Repayment', money(offer['total_repayment']))
            z.metric('Instalment', money(offer['installment_amount']))
            st.write(f"{offer['number_of_installments']} instalment(s)")
            st.write(f"First payment date: {offer['first_payment_date']}")

            if st.button('Accept This Offer', key=f"accept_{offer['id']}", type='primary'):
                conn = get_connection()
                exists = conn.execute('SELECT id FROM loans WHERE application_id=?', (application_id,)).fetchone()
                if exists:
                    conn.close()
                    st.warning('A loan already exists for this application.')
                    st.stop()

                loan_number = generate_loan_number()
                cur = conn.execute('''
                    INSERT INTO loans(
                        loan_number,application_id,offer_id,borrower_id,lender_id,
                        principal_amount,total_repayment,outstanding_balance,loan_status
                    ) VALUES(?,?,?,?,?,?,?,?,'Awaiting Mandate')
                ''', (
                    loan_number, application_id, offer['id'], application['borrower_id'], offer['lender_id'],
                    offer['approved_amount'], offer['total_repayment'], offer['total_repayment']
                ))
                loan_id = cur.lastrowid

                first_date = datetime.strptime(offer['first_payment_date'], '%Y-%m-%d').date()
                for n in range(1, offer['number_of_installments'] + 1):
                    due = first_date + timedelta(days=30 * (n-1))
                    conn.execute('''
                        INSERT INTO repayment_schedule(loan_id,installment_number,due_date,amount_due,status)
                        VALUES(?,?,?,?,'Pending')
                    ''', (loan_id, n, due.isoformat(), offer['installment_amount']))

                conn.execute('''
                    INSERT INTO payment_mandates(loan_id,lender_id,mandate_amount,mandate_start_date,mandate_status)
                    VALUES(?,?,?,?,'Not Sent')
                ''', (loan_id, offer['lender_id'], offer['installment_amount'], offer['first_payment_date']))
                conn.execute("UPDATE loan_offers SET offer_status='Accepted' WHERE id=?", (offer['id'],))
                conn.execute("UPDATE loan_offers SET offer_status='Rejected' WHERE application_id=? AND id!=? AND offer_status='Pending'", (application_id, offer['id']))
                conn.execute("UPDATE loan_applications SET status='Accepted' WHERE id=?", (application_id,))
                conn.commit()
                conn.close()
                st.success(f'Offer accepted. Loan created: {loan_number}')
                st.rerun()

    st.write('### Loan Status')
    if loan:
        a,b,c = st.columns(3)
        a.metric('Lender', loan['business_name'])
        b.metric('Outstanding', money(loan['outstanding_balance']))
        c.metric('Status', loan['loan_status'])
        st.write(f"Mandate status: **{loan['mandate_status']}**")
    else:
        st.info('No loan has been created yet.')

    if st.button('Check Another Application'):
        st.session_state.pop('tracked_application_id', None)
        st.rerun()


# ============================================================
# LENDER
# ============================================================
elif st.session_state.portal == 'lender':
    if 'lender_id' not in st.session_state:
        st.title('🏦 Lender Access')
        st.write('Enter the Lender Code and the cellphone registered by the Superuser.')
        with st.form('lender_access'):
            lender_code = st.text_input('Lender Code')
            cellphone = st.text_input('Registered Cellphone')
            access = st.form_submit_button('Access Lender Portal', type='primary')
        if access:
            lender = get_lender_by_access(lender_code, cellphone)
            if lender:
                st.session_state.lender_id = lender['id']
                st.rerun()
            else:
                st.error('Lender Code and cellphone do not match an approved lender.')
        if st.button('← Back to Home'):
            clear_portal()
        st.stop()

    lender_id = st.session_state.lender_id
    conn = get_connection()
    lender = conn.execute('SELECT * FROM lenders WHERE id=?', (lender_id,)).fetchone()
    conn.close()

    st.sidebar.title(lender['business_name'])
    page = st.sidebar.radio('Navigation', ['Dashboard','Lending Rules','Matched Applications','My Offers','My Loans','Repayments'])
    if st.sidebar.button('Exit Lender Portal'):
        clear_portal()

    if page == 'Dashboard':
        st.title(f"{lender['business_name']} Dashboard")
        conn = get_connection()
        matches = conn.execute("SELECT COUNT(*) AS total FROM lender_matches WHERE lender_id=? AND match_status IN ('Matched','Offered')", (lender_id,)).fetchone()['total']
        offers = conn.execute("SELECT COUNT(*) AS total FROM loan_offers WHERE lender_id=? AND offer_status='Pending'", (lender_id,)).fetchone()['total']
        loans = conn.execute('SELECT COUNT(*) AS total FROM loans WHERE lender_id=?', (lender_id,)).fetchone()['total']
        outstanding = conn.execute("SELECT COALESCE(SUM(outstanding_balance),0) AS total FROM loans WHERE lender_id=? AND loan_status!='Paid Up'", (lender_id,)).fetchone()['total']
        conn.close()
        a,b,c,d = st.columns(4)
        a.metric('Matched Applications', matches)
        b.metric('Pending Offers', offers)
        c.metric('Loans', loans)
        d.metric('Outstanding Book', money(outstanding))

    elif page == 'Lending Rules':
        st.title('My Lending Rules')
        conn = get_connection()
        rules = conn.execute('SELECT * FROM lender_rules WHERE lender_id=?', (lender_id,)).fetchone()
        conn.close()
        with st.form('rules'):
            a,b = st.columns(2)
            min_loan = a.number_input('Minimum Loan Amount', min_value=0.0, value=float(rules['min_loan_amount']))
            max_loan = b.number_input('Maximum Loan Amount', min_value=0.0, value=float(rules['max_loan_amount']))
            min_income = st.number_input('Minimum Net Monthly Income', min_value=0.0, value=float(rules['min_monthly_income']))
            min_emp = st.number_input('Minimum Months Employed', min_value=0, value=int(rules['min_employment_months']))
            employment_options = ['Any','Permanent','Contract','Self Employed']
            emp = st.selectbox('Employment Requirement', employment_options, index=employment_options.index(rules['employment_type'] if rules['employment_type'] in employment_options else 'Any'))
            c,d = st.columns(2)
            min_term = c.number_input('Minimum Term (Months)', min_value=1, value=int(rules['min_term_months']))
            max_term = d.number_input('Maximum Term (Months)', min_value=1, value=int(rules['max_term_months']))
            provinces = st.text_input('Provinces Served', value=rules['provinces_served'] or 'All')
            save = st.form_submit_button('Save Lending Rules')
        if save:
            if min_loan > max_loan or min_term > max_term:
                st.error('Check minimum and maximum values.')
            else:
                conn = get_connection()
                conn.execute('''UPDATE lender_rules SET min_loan_amount=?,max_loan_amount=?,min_monthly_income=?,min_employment_months=?,employment_type=?,min_term_months=?,max_term_months=?,provinces_served=? WHERE lender_id=?''',
                             (min_loan,max_loan,min_income,min_emp,emp,min_term,max_term,provinces,lender_id))
                conn.commit(); conn.close()
                st.success('Lending rules saved.')

    elif page == 'Matched Applications':
        st.title('Matched Applications')
        conn = get_connection()
        matches = conn.execute('''
            SELECT m.application_id,m.reason,a.application_number,a.requested_amount,a.requested_term,a.loan_purpose,a.disposable_income,
                   b.first_name,b.surname,b.cellphone,b.employment_status,b.employer_name,b.employment_months,b.net_income,b.province
            FROM lender_matches m
            JOIN loan_applications a ON a.id=m.application_id
            JOIN borrowers b ON b.id=a.borrower_id
            WHERE m.lender_id=? AND m.match_status IN ('Matched','Offered')
            ORDER BY m.id DESC
        ''', (lender_id,)).fetchall()
        conn.close()
        if not matches:
            st.info('No matched applications.')
        for match in matches:
            with st.expander(f"{match['application_number']} — {match['first_name']} {match['surname']} — {money(match['requested_amount'])}"):
                a,b,c,d = st.columns(4)
                a.metric('Requested', money(match['requested_amount']))
                b.metric('Term', f"{match['requested_term']} months")
                c.metric('Net Income', money(match['net_income']))
                d.metric('Disposable Income', money(match['disposable_income']))
                st.write(f"Cellphone: **{match['cellphone']}**")
                st.write(f"Employment: **{match['employment_status']}**")
                st.write(f"Months employed: **{match['employment_months']}**")
                st.write(f"Employer: **{match['employer_name'] or '-'}**")
                st.write(f"Province: **{match['province']}**")
                st.write(f"Purpose: {match['loan_purpose'] or '-'}")

                conn = get_connection()
                docs = conn.execute('SELECT document_type,original_filename,verification_status FROM application_documents WHERE application_id=? ORDER BY id', (match['application_id'],)).fetchall()
                existing_offer = conn.execute("SELECT id FROM loan_offers WHERE application_id=? AND lender_id=? AND offer_status IN ('Pending','Accepted')", (match['application_id'], lender_id)).fetchone()
                conn.close()
                st.write('**Uploaded Documents**')
                for doc in docs:
                    st.write(f"- {doc['document_type']}: {doc['original_filename']} ({doc['verification_status']})")

                if not existing_offer:
                    with st.form(f"offer_{match['application_id']}"):
                        approved_amount = st.number_input('Approved Amount', min_value=0.0, value=float(match['requested_amount']))
                        interest = st.number_input('Interest Amount', min_value=0.0, value=0.0)
                        initiation = st.number_input('Initiation Fee', min_value=0.0, value=0.0)
                        service = st.number_input('Service Fee', min_value=0.0, value=0.0)
                        installments = st.number_input('Number of Instalments', min_value=1, value=int(match['requested_term']))
                        first_payment = st.date_input('First Payment Date', value=date.today()+timedelta(days=30))
                        submit_offer = st.form_submit_button('Make Offer')
                    if submit_offer:
                        total = approved_amount + interest + initiation + service
                        installment_amount = total / installments
                        conn = get_connection()
                        conn.execute('''
                            INSERT INTO loan_offers(application_id,lender_id,approved_amount,interest_amount,initiation_fee,service_fee,total_repayment,number_of_installments,installment_amount,first_payment_date,offer_status)
                            VALUES(?,?,?,?,?,?,?,?,?,?,'Pending')
                        ''', (match['application_id'],lender_id,approved_amount,interest,initiation,service,total,installments,installment_amount,first_payment.isoformat()))
                        conn.execute("UPDATE lender_matches SET match_status='Offered' WHERE application_id=? AND lender_id=?", (match['application_id'], lender_id))
                        conn.execute("UPDATE loan_applications SET status='Offers Received' WHERE id=?", (match['application_id'],))
                        conn.commit(); conn.close(); st.rerun()
                else:
                    st.info('An offer already exists for this application.')

    elif page == 'My Offers':
        st.title('My Offers')
        conn = get_connection()
        rows = conn.execute('''SELECT o.*,a.application_number,b.first_name||' '||b.surname AS borrower FROM loan_offers o JOIN loan_applications a ON a.id=o.application_id JOIN borrowers b ON b.id=a.borrower_id WHERE o.lender_id=? ORDER BY o.id DESC''', (lender_id,)).fetchall()
        conn.close()
        st.dataframe([dict(x) for x in rows], use_container_width=True) if rows else st.info('No offers.')

    elif page == 'My Loans':
        st.title('My Loans')
        conn = get_connection()
        loans = conn.execute('''SELECT ln.*,b.first_name||' '||b.surname AS borrower,pm.mandate_status FROM loans ln JOIN borrowers b ON b.id=ln.borrower_id LEFT JOIN payment_mandates pm ON pm.loan_id=ln.id WHERE ln.lender_id=? ORDER BY ln.id DESC''', (lender_id,)).fetchall()
        conn.close()
        if not loans:
            st.info('No loans.')
        for loan in loans:
            with st.container(border=True):
                st.subheader(f"{loan['loan_number']} — {loan['borrower']}")
                a,b,c,d = st.columns(4)
                a.metric('Principal', money(loan['principal_amount']))
                b.metric('Total Repayment', money(loan['total_repayment']))
                c.metric('Balance', money(loan['outstanding_balance']))
                d.metric('Status', loan['loan_status'])
                st.write(f"Mandate: **{loan['mandate_status']}**")
                if loan['mandate_status']=='Not Sent' and st.button('Send Mandate', key=f"send_{loan['id']}"):
                    conn=get_connection(); conn.execute("UPDATE payment_mandates SET mandate_status='Sent',payment_provider='TEST PROVIDER',provider_reference=? WHERE loan_id=?", ('MAND-'+uuid.uuid4().hex[:10].upper(), loan['id'])); conn.commit(); conn.close(); st.rerun()
                elif loan['mandate_status']=='Sent':
                    x,y=st.columns(2)
                    if x.button('Simulate Approved', key=f"appr_{loan['id']}"):
                        conn=get_connection(); conn.execute("UPDATE payment_mandates SET mandate_status='Approved' WHERE loan_id=?",(loan['id'],)); conn.execute("UPDATE loans SET loan_status='Ready for Payout' WHERE id=?",(loan['id'],)); conn.commit(); conn.close(); st.rerun()
                    if y.button('Simulate Declined', key=f"decl_{loan['id']}"):
                        conn=get_connection(); conn.execute("UPDATE payment_mandates SET mandate_status='Declined' WHERE loan_id=?",(loan['id'],)); conn.commit(); conn.close(); st.rerun()
                if loan['loan_status']=='Ready for Payout' and st.button('Confirm Borrower Paid Out', key=f"pay_{loan['id']}"):
                    conn=get_connection(); conn.execute("UPDATE loans SET loan_status='Active',start_date=? WHERE id=?",(date.today().isoformat(),loan['id'])); conn.commit(); conn.close(); st.rerun()

    elif page == 'Repayments':
        st.title('Repayments')
        conn=get_connection()
        rows=conn.execute('''SELECT rs.*,ln.loan_number,ln.outstanding_balance,b.first_name||' '||b.surname AS borrower FROM repayment_schedule rs JOIN loans ln ON ln.id=rs.loan_id JOIN borrowers b ON b.id=ln.borrower_id WHERE ln.lender_id=? AND ln.loan_status IN ('Active','Arrears') ORDER BY rs.due_date''',(lender_id,)).fetchall()
        conn.close()
        if not rows: st.info('No active repayments.')
        for r in rows:
            with st.container(border=True):
                st.write(f"### {r['loan_number']} — {r['borrower']}")
                a,b,c=st.columns(3); a.metric('Amount Due',money(r['amount_due'])); b.metric('Due Date',r['due_date']); c.metric('Status',r['status'])
                if r['status']!='Paid':
                    provider_fee=st.number_input('Provider Fee',min_value=0.0,value=6.50,key=f"pf_{r['id']}")
                    platform_fee=st.number_input('Platform Fee',min_value=0.0,value=15.0,key=f"plf_{r['id']}")
                    x,y=st.columns(2)
                    if x.button('Successful Collection',key=f"success_{r['id']}"):
                        amount=float(r['amount_due']); new_balance=max(float(r['outstanding_balance'])-amount,0); new_status='Paid Up' if new_balance<=0.01 else 'Active'
                        conn=get_connection(); conn.execute('''INSERT INTO payment_transactions(loan_id,repayment_schedule_id,lender_id,transaction_reference,amount,provider_fee,platform_fee,transaction_status) VALUES(?,?,?,?,?,?,?,'Successful')''',(r['loan_id'],r['id'],lender_id,'TXN-'+uuid.uuid4().hex[:10].upper(),amount,provider_fee,platform_fee)); conn.execute("UPDATE repayment_schedule SET amount_paid=amount_due,status='Paid' WHERE id=?",(r['id'],)); conn.execute("UPDATE loans SET outstanding_balance=?,loan_status=? WHERE id=?",(new_balance,new_status,r['loan_id'])); conn.commit(); conn.close(); st.rerun()
                    if y.button('Failed Collection',key=f"fail_{r['id']}"):
                        conn=get_connection(); conn.execute("UPDATE repayment_schedule SET status='Failed' WHERE id=?",(r['id'],)); conn.execute("UPDATE loans SET loan_status='Arrears' WHERE id=?",(r['loan_id'],)); conn.commit(); conn.close(); st.rerun()


# ============================================================
# SUPERUSER
# ============================================================
elif st.session_state.portal == 'superuser':
    superuser = get_superuser()
    st.sidebar.title('Superuser')
    page = st.sidebar.radio('Navigation', ['Dashboard','Add Lender','Lenders','All Applications','All Loans','Platform Revenue'])
    if st.sidebar.button('Exit Superuser'):
        clear_portal()

    if page == 'Dashboard':
        st.title('Platform Dashboard')
        conn=get_connection()
        lender_count=conn.execute('SELECT COUNT(*) AS total FROM lenders').fetchone()['total']
        app_count=conn.execute('SELECT COUNT(*) AS total FROM loan_applications').fetchone()['total']
        loan_count=conn.execute('SELECT COUNT(*) AS total FROM loans').fetchone()['total']
        outstanding=conn.execute("SELECT COALESCE(SUM(outstanding_balance),0) AS total FROM loans WHERE loan_status!='Paid Up'").fetchone()['total']
        revenue=conn.execute("SELECT COALESCE(SUM(platform_fee),0) AS total FROM payment_transactions WHERE transaction_status='Successful'").fetchone()['total']
        conn.close()
        a,b,c,d=st.columns(4); a.metric('Lenders',lender_count); b.metric('Applications',app_count); c.metric('Loans',loan_count); d.metric('Outstanding Loan Book',money(outstanding)); st.metric('Platform Revenue',money(revenue))

    elif page == 'Add Lender':
        st.title('Add Lender')
        st.info('Lender access uses Lender Code + registered cellphone. No password for now.')
        with st.form('add_lender'):
            business_name=st.text_input('Business Name *')
            registration_number=st.text_input('Company Registration Number')
            ncr_number=st.text_input('NCR Number')
            contact_person=st.text_input('Contact Person *')
            registered_cellphone=st.text_input('Registered Cellphone *')
            email=st.text_input('Email')
            address=st.text_area('Business Address')
            province=st.selectbox('Province',['Gauteng','Limpopo','Mpumalanga','North West','Free State','KwaZulu-Natal','Eastern Cape','Western Cape','Northern Cape'])
            subscription_plan=st.selectbox('Subscription Plan',['Basic','Professional','Enterprise'])
            st.subheader('Settlement Bank Details')
            bank_name=st.text_input('Bank')
            bank_account_name=st.text_input('Account Holder')
            bank_account_number=st.text_input('Account Number')
            bank_branch_code=st.text_input('Branch Code')
            create=st.form_submit_button('Create Lender')
        if create:
            if not business_name.strip() or not contact_person.strip() or not registered_cellphone.strip():
                st.error('Business name, contact person and registered cellphone are required.')
            else:
                lender_code=generate_lender_code(); conn=get_connection()
                try:
                    cur=conn.execute('''INSERT INTO lenders(lender_code,business_name,registration_number,ncr_number,contact_person,registered_cellphone,email,address,province,bank_name,bank_account_name,bank_account_number,bank_branch_code,subscription_plan,subscription_status,created_by_superuser,approved_by,approved_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Approved',?,?,?)''',(lender_code,business_name,registration_number,ncr_number,contact_person,normalise_cell(registered_cellphone),email,address,province,bank_name,bank_account_name,bank_account_number,bank_branch_code,subscription_plan,superuser['id'],superuser['id'],datetime.now().isoformat(timespec='seconds')))
                    lender_id=cur.lastrowid; conn.execute('INSERT INTO lender_rules(lender_id) VALUES(?)',(lender_id,)); conn.commit()
                    st.success('Lender created successfully.'); st.markdown(f"### Lender Code: `{lender_code}`"); st.write(f"Registered Cellphone: **{normalise_cell(registered_cellphone)}**")
                except Exception as e:
                    conn.rollback(); st.error(f'Could not create lender: {e}')
                finally:
                    conn.close()

    elif page == 'Lenders':
        st.title('Registered Lenders'); conn=get_connection(); rows=conn.execute('SELECT lender_code,business_name,ncr_number,contact_person,registered_cellphone,email,subscription_plan,subscription_status,created_at FROM lenders ORDER BY id DESC').fetchall(); conn.close(); st.dataframe([dict(x) for x in rows],use_container_width=True) if rows else st.info('No lenders registered.')
    elif page == 'All Applications':
        st.title('All Applications'); conn=get_connection(); rows=conn.execute("SELECT a.application_number,b.first_name||' '||b.surname AS borrower,b.cellphone,a.requested_amount,a.requested_term,a.disposable_income,a.status,a.created_at FROM loan_applications a JOIN borrowers b ON b.id=a.borrower_id ORDER BY a.id DESC").fetchall(); conn.close(); st.dataframe([dict(x) for x in rows],use_container_width=True) if rows else st.info('No applications.')
    elif page == 'All Loans':
        st.title('All Loans'); conn=get_connection(); rows=conn.execute("SELECT ln.loan_number,l.business_name AS lender,b.first_name||' '||b.surname AS borrower,ln.principal_amount,ln.total_repayment,ln.outstanding_balance,ln.loan_status FROM loans ln JOIN lenders l ON l.id=ln.lender_id JOIN borrowers b ON b.id=ln.borrower_id ORDER BY ln.id DESC").fetchall(); conn.close(); st.dataframe([dict(x) for x in rows],use_container_width=True) if rows else st.info('No loans.')
    elif page == 'Platform Revenue':
        st.title('Platform Revenue'); conn=get_connection(); rows=conn.execute('''SELECT pt.transaction_date,l.business_name AS lender,ln.loan_number,pt.amount AS repayment_amount,pt.provider_fee,pt.platform_fee,pt.transaction_status FROM payment_transactions pt JOIN lenders l ON l.id=pt.lender_id JOIN loans ln ON ln.id=pt.loan_id ORDER BY pt.id DESC''').fetchall(); conn.close(); st.dataframe([dict(x) for x in rows],use_container_width=True) if rows else st.info('No payment transactions yet.')
