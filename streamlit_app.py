import os
import streamlit as st
import pandas as pd
import io
import zipfile
from requests import request

# === Streamlit Page Config ===
st.set_page_config(
    page_title="Coupa Invoice Downloader",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# === Custom Dark Theme Styling ===
st.markdown("""
    <style>
        /* Remove Streamlit header and toolbar */
        header, .st-emotion-cache-18ni7ap {
            display: none;
        }

        body {
            color: #000000;
            background-color: #ffffff;
        }
        .stApp {
            background-color: #ffffff;
            font-family: 'Segoe UI', sans-serif;
            padding: 2em;
        }
        h1, h2, h3, h4, h5, p, span, label, div {
            color: #000000;
        }
        .stButton > button {
            background-color: #ff5500;
            color: #ffffff;
            border: none;
            border-radius: 6px;
            height: 3em;
            width: 200px;
            font-weight: bold;
            margin-top: 1em;
            cursor: pointer;
            font-size: 1em;
            transition: background-color 0.3s ease;
        }
        .stButton > button:hover {
            background-color: #e64a00;
        }
        .stTextInput > div > input {
            background-color: #ffffff;
            color: #000000;
            border: 1px solid #ccc;
            padding: 0.5em;
            border-radius: 4px;
            width: 100%;
        }
        .top-right {
            position: absolute;
            top: 10px;
            right: 20px;
            color: #ff5500;
            font-weight: 500;
            font-size: 125%;
        }
        .custom-upload {
            width: 25%;
        }
    </style>
    <div class='top-right'>Hayden Meyer</div>
""", unsafe_allow_html=True)

# === UI Title ===
st.markdown("<h1 style='color:#ff5500;'>Coupa Invoice Downloader</h1>", unsafe_allow_html=True)
st.markdown("Upload your invoice CSV and automatically save PDF scans to a ZIP file for download.")

# === Step 1: Upload CSV ===
st.subheader("Step 1: Upload CSV File")
st.markdown('<div class="custom-upload">', unsafe_allow_html=True)
uploaded_file = st.file_uploader("Choose a CSV file with an 'Invoice ID' column", type=["csv"])
st.markdown('</div>', unsafe_allow_html=True)

# === Step 2: Run Script ===
st.subheader("Step 2: Run Script")
run_clicked = st.button("Run")

if uploaded_file and run_clicked:
    try:
        st.success("Running script...")

        identifier = os.environ.get("IDENTIFIER")
        grant_type = os.environ.get("GRANT_TYPE", "client_credentials")  # default fallback
        secret = os.environ.get("SECRET")
        COUPA_INSTANCE = os.environ.get("COUPA_INSTANCE")

        st.write(f"Identifier: {identifier}")
        st.write(f"Grant Type: {grant_type}")
        st.write(f"Coupa Instance URL: {COUPA_INSTANCE}")

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
                    scan_url = f"https://{COUPA_INSTANCE}.coupahost.com/api/invoices/{invoice_id}/retrieve_image_scan"
                    resp = request("GET", scan_url, headers=headers)

                    if resp.status_code == 200:
                        pdf_bytes = resp.content
                        zip_file.writestr(f"{invoice_id}_scan.pdf", pdf_bytes)
                        status.success(f"✅ Downloaded {invoice_id}")
                    else:
                        status.warning(f"⚠️ Failed to download {invoice_id} (Status: {resp.status_code})")

                    progress.progress((i + 1) / len(invoice_ids))

            zip_buffer.seek(0)
            st.success(f"✅ All done! Download the ZIP file containing all PDFs below.")
            st.download_button(
                label="📥 Download ZIP",
                data=zip_buffer,
                file_name="coupa_invoice_scans.zip",
                mime="application/zip"
            )

    except Exception as e:
        st.error(f"❌ Error: {e}")
