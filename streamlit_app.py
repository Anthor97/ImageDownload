import os
import streamlit as st
import pandas as pd
import io
import zipfile
import re
from requests import request

# === Streamlit Page Config ===
st.set_page_config(
    page_title="Coupa Invoice Downloader",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# === Custom Styling ===
st.markdown("""
<style>
    body, .stApp {
        background-color: #ffffff !important;
        color: #000000 !important;
        font-family: 'Segoe UI', sans-serif !important;
    }

    h1, h2, h3, h4, h5, p, span, div, label {
        color: #000000 !important;
    }

    .stButton>button, .stDownloadButton>button {
        background-color: #ff5500 !important;
        color: #ffffff !important;
        border-radius: 6px !important;
        height: 3em !important;
        width: 25% !important;
        font-weight: bold !important;
        font-size: 125% !important;
        margin-top: 1em !important;
    }

    .stTextInput>div>input {
        background-color: #ffffff !important;
        color: #000000 !important;
    }

    .stFileUploader > div:first-child {
        background-color: transparent !important;
    }

    .stFileUploader label,
    .stFileUploader div span,
    .stFileUploader div div {
        color: #ffffff !important;
    }

    header[data-testid="stHeader"] {
        background-color: #ffffff !important;
    }

    .top-right {
        position: absolute !important;
        top: 10px !important;
        right: 20px !important;
        color: #ff5500 !important;
        font-weight: 500 !important;
        font-size: 125% !important;
    }

    .custom-upload {
        width: 25% !important;
    }
</style>
<div class='top-right'>Hayden Meyer</div>
""", unsafe_allow_html=True)

# === State Initialization ===
if "zip_buffer" not in st.session_state:
    st.session_state.zip_buffer = None
if "processed" not in st.session_state:
    st.session_state.processed = False

# === UI Title ===
st.markdown("<h1 style='color:#000000;'>Coupa Invoice Downloader</h1>", unsafe_allow_html=True)
st.markdown("Upload your invoice CSV and automatically save PDF scans to a ZIP file for download.")

# === Step 1: Upload CSV ===
if not st.session_state.processed:
    st.subheader("Step 1: Upload CSV File")
    st.markdown('<div class="custom-upload">', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Choose a CSV file with an 'Invoice ID' column", type=["csv"])
    st.markdown('</div>', unsafe_allow_html=True)

    # === Step 2: Run Script ===
    st.subheader("Step 2: Run Extraction")
    run_clicked = st.button("Run")

    if uploaded_file and run_clicked:
        try:
            st.success("Running script...")

            identifier = os.environ.get("IDENTIFIER")
            grant_type = os.environ.get("GRANT_TYPE", "client_credentials")
            secret = os.environ.get("SECRET")
            COUPA_INSTANCE = os.environ.get("COUPA_INSTANCE")

            # === Authenticate with Coupa ===
            token_url = f"https://{COUPA_INSTANCE}.coupahost.com/oauth2/token"
            token_data = {
                "grant_type": "client_credentials",
                "scope": "core.invoice.read"
            }
            token_headers = {"Content-Type": "application/x-www-form-urlencoded"}

            with st.spinner("Authenticating with Coupa..."):
                response = request("POST", token_url, auth=(identifier, secret), data=token_data, headers=token_headers)
                response.raise_for_status()

            access_token = response.json()["access_token"]
            token_type = response.json().get("token_type", "Bearer")
            headers = {
                "Authorization": f"{token_type} {access_token}",
                "Accept": "application/json"
            }

            # === Load and normalize CSV ===
            raw_csv = uploaded_file.getvalue().decode("utf-8")
            delimiter = "\t" if "\t" in raw_csv else ","
            df = pd.read_csv(io.StringIO(raw_csv), delimiter=delimiter)

            original_columns = df.columns.tolist()
            col_map = {col.strip().lower(): col.strip() for col in original_columns}
            df.columns = [col_map.get(col.strip().lower(), col) for col in df.columns]

            expected = ["invoice id", "invoice #", "supplier", "created date"]
            column_mapping = {}
            for key in expected:
                match = [col for col in df.columns if col.strip().lower() == key]
                if match:
                    column_mapping[key] = match[0]

            missing_cols = [key for key in expected if key not in column_mapping]
            if missing_cols:
                st.error(f"CSV is missing required columns: {', '.join(missing_cols)}")
            else:
                invoice_ids = df[column_mapping["invoice id"]].dropna().astype(str).tolist()

                def sanitize_filename(s):
                    return re.sub(r'[\\/*?:"<>|]', "", str(s).strip())

                zip_buffer = io.BytesIO()
                failed_rows = []

                with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                    progress = st.progress(0)
                    status = st.empty()

                    for i, invoice_id in enumerate(invoice_ids):
                        row = df[df[column_mapping["invoice id"]].astype(str) == invoice_id].iloc[0]

                        invoice_num = sanitize_filename(row[column_mapping["invoice #"]])
                        supplier_name = sanitize_filename(row[column_mapping["supplier"]])
                        created_date_raw = str(row[column_mapping["created date"]])
                        created_date = sanitize_filename(created_date_raw.split("T")[0] if "T" in created_date_raw else created_date_raw)

                        filename = f"{supplier_name} - {invoice_num} - {created_date}.pdf"

                        scan_url = f"https://{COUPA_INSTANCE}.coupahost.com/api/invoices/{invoice_id}/retrieve_image_scan"
                        resp = request("GET", scan_url, headers=headers)

                        if resp.status_code == 200:
                            pdf_bytes = resp.content
                            zip_file.writestr(filename, pdf_bytes)
                            status.success(f"Downloaded {invoice_id}")
                        else:
                            status.warning(f"Failed to download {invoice_id} (Status: {resp.status_code})")
                            failed_row = row.to_dict()
                            failed_row["Download Status"] = f"Failed ({resp.status_code})"
                            failed_rows.append(failed_row)

                        progress.progress((i + 1) / len(invoice_ids))

                    if failed_rows:
                        failed_df = pd.DataFrame(failed_rows)
                        failed_csv = failed_df.to_csv(index=False).encode("utf-8")
                        zip_file.writestr("failed_invoices.csv", failed_csv)

                zip_buffer.seek(0)
                st.session_state.zip_buffer = zip_buffer
                st.session_state.processed = True

        except Exception as e:
            st.error(f"Error: {e}")

# === Show Download ===
if st.session_state.processed and st.session_state.zip_buffer:
    st.success("All done! Download the ZIP file containing PDFs and failed invoice report below.")
    st.download_button(
        label="Download ZIP",
        data=st.session_state.zip_buffer,
        file_name="coupa_invoice_scans.zip",
        mime="application/zip"
    )
