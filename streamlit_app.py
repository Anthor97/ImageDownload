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
    /* Global styling */
    body, .stApp {
        background-color: #ffffff !important;
        color: #000000 !important;
        font-family: 'Segoe UI', sans-serif !important;
    }

    h1, h2, h3, h4, h5, p, span, div, label {
        color: #000000 !important;
    }

    /* === BUTTON === */
    .stButton>button {
        background-color: #ff5500 !important;
        color: #ffffff !important;
        border-radius: 6px !important;
        height: 3em !important;
        width: 25% !important;
        font-weight: bold !important;
        font-size: 125% !important;
        margin-top: 0.5em !important;
    }

    /* === DOWNLOAD BUTTON === */
    .stDownloadButton>button {
        background-color: #ff5500 !important;
        color: #ffffff !important;
        border-radius: 6px !important;
        height: 3em !important;
        width: 25% !important;
        font-weight: bold !important;
        font-size: 125% !important;
        margin-top: 1em !important;
    }

    /* === TEXT INPUT === */
    .stTextInput>div>input {
        background-color: #ffffff !important;
        color: #000000 !important;
    }

    /* === FILE UPLOADER === */
    .stFileUploader > div:first-child {
        background-color: transparent !important;
    }

    .stFileUploader label,
    .stFileUploader div span,
    .stFileUploader div div {
        color: #ffffff !important;
    }

    /* === TOP BLACK BAR === */
    header[data-testid="stHeader"] {
        background-color: #ffffff !important;
    }

    /* === TOP-RIGHT NAME === */
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

# === UI Title ===
st.markdown("<h1 style='color:#000000;'>Coupa Invoice Downloader</h1>", unsafe_allow_html=True)
st.markdown("Upload your invoice CSV and automatically save PDF scans to a ZIP file for download.")

# === Step 1: Upload CSV ===
st.subheader("Step 1: Upload CSV File")
st.markdown('<div class="custom-upload">', unsafe_allow_html=True)
uploaded_file = st.file_uploader("Choose a CSV file with an 'Invoice ID' column", type=["csv"])
st.markdown('</div>', unsafe_allow_html=True)

# === Step 2: Run Script ===
st.subheader("Step 2: Run Extraction")
run_clicked = st.button("Run")

def sanitize_filename(s):
    # Remove characters that are invalid in file names
    return re.sub(r'[\\/*?:"<>|]', "", s)

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

        with st.spinner("🔐 Authenticating with Coupa..."):
            response = request("POST", token_url, auth=(identifier, secret), data=token_data, headers=token_headers)
            response.raise_for_status()

        access_token = response.json()["access_token"]
        token_type = response.json().get("token_type", "Bearer")
        headers = {
            "Authorization": f"{token_type} {access_token}",
            "Accept": "application/json"
        }

        # === Process Invoice IDs from CSV ===
        df = pd.read_csv(uploaded_file)
        if "Invoice ID" not in df.columns:
            st.error("❌ CSV must contain a column named 'Invoice ID'")
        else:
            invoice_ids = df["Invoice ID"].dropna().astype(str).tolist()

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                progress = st.progress(0)
                status = st.empty()

                for i, invoice_id in enumerate(invoice_ids):
                    # Get invoice details for Supplier Name, Invoice Number, Created Date
                    invoice_url = f"https://{COUPA_INSTANCE}.coupahost.com/api/invoices/{invoice_id}"
                    invoice_resp = request("GET", invoice_url, headers=headers)

                    if invoice_resp.status_code == 200:
                        invoice_data = invoice_resp.json()
                        supplier_name = invoice_data.get("supplier", {}).get("name", "UnknownSupplier")
                        invoice_number = invoice_data.get("invoice_number", invoice_id)
                        created_at = invoice_data.get("created_at", "")  # e.g. '2025-06-16T12:34:56Z'

                        created_date = created_at.split("T")[0] if "T" in created_at else created_at

                        # Sanitize for filename safety
                        supplier_name = sanitize_filename(supplier_name)
                        invoice_number = sanitize_filename(invoice_number)

                        # Get PDF scan
                        scan_url = f"https://{COUPA_INSTANCE}.coupahost.com/api/invoices/{invoice_id}/retrieve_image_scan"
                        resp = request("GET", scan_url, headers=headers)

                        if resp.status_code == 200:
                            pdf_bytes = resp.content
                            file_name = f"{supplier_name} - [{invoice_number}] - {created_date}.pdf"
                            zip_file.writestr(file_name, pdf_bytes)
                            status.success(f"✅ Downloaded {file_name}")
                        else:
                            status.warning(f"⚠️ Failed to download scan for {invoice_id} (Status: {resp.status_code})")
                    else:
                        status.warning(f"⚠️ Failed to retrieve invoice details for {invoice_id} (Status: {invoice_resp.status_code})")

                    progress.progress((i + 1) / len(invoice_ids))

            zip_buffer.seek(0)
            st.success(f"All done! Download the ZIP file containing PDFs below.")
            st.download_button(
                label="Download ZIP",
                data=zip_buffer,
                file_name="coupa_invoice_scans.zip",
                mime="application/zip"
            )

    except Exception as e:
        st.error(f"❌ Error: {e}")
