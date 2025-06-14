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
import streamlit as st

# Custom CSS for styling to match the screenshot
st.markdown("""
    <style>
        /* Hide Streamlit default header & footer */
        header, footer, .css-1v3fvcr {
            display: none;
        }

        /* Body style */
        body {
            font-family: 'Segoe UI', sans-serif;
            background-color: #fff;
            color: #000;
            padding: 2rem 3rem;
        }

        h1 {
            font-weight: 600;
            font-size: 1.8rem;
            margin-bottom: 1rem;
        }

        /* Bold labels in instructions */
        .bold-label {
            font-weight: 600;
            margin-right: 0.25rem;
        }

        /* Step container with margin */
        .step {
            margin-bottom: 1.5rem;
            line-height: 1.5;
        }

        /* Numbered steps with spacing */
        ol {
            padding-left: 1.25rem;
            margin-bottom: 2rem;
        }

        /* Inline container for button next to text */
        .inline-btn {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }

        /* Style for Download dropdown button */
        .download-btn select {
            height: 30px;
            border-radius: 3px;
            border: 1px solid #ccc;
            padding: 0 0.5rem;
        }

        /* Style file uploader width */
        .file-uploader {
            width: 280px;
            margin-top: 0.4rem;
        }

        /* Note text style */
        .note-text {
            font-size: 0.9rem;
            color: #444;
            margin-top: 0.5rem;
        }

        /* Start Upload button style */
        .stButton > button {
            background-color: #0b75c9;
            color: white;
            font-weight: 600;
            height: 35px;
            width: 120px;
            border-radius: 4px;
            float: right;
            margin-top: -40px;
        }
        .stButton > button:hover {
            background-color: #095a9d;
        }
    </style>
""", unsafe_allow_html=True)

# Title
st.markdown("<h1>Bulk Load Requisition</h1>", unsafe_allow_html=True)

# Instructions with steps and bold text formatting
st.markdown("""
    <ol>
        <li class="step">
            <span class="bold-label">Download</span> the CSV template (Based on the CSV File Field Separator in your Language and Region settings.)
            <div class="inline-btn download-btn">
                <select>
                    <option>Download</option>
                    <option>Template 1</option>
                    <option>Template 2</option>
                </select>
            </div>
        </li>

        <li class="step">
            <span class="bold-label">Fill in or update the CSV file.</span>
            <ul>
                <li>Fields marked with a <strong>"*"</strong> are mandatory.</li>
                <li>Each row uploaded will create a new requisition.</li>
                <li>Click Start Upload and the system will verify the file using the first 6 rows, and load the file if no errors are found.</li>
            </ul>
        </li>

        <li class="step">
            <span class="bold-label">Load the updated file</span>
            <div class="file-uploader">
""", unsafe_allow_html=True)

uploaded_file = st.file_uploader("", type=["csv"])

st.markdown("""
            </div>
        </li>
    </ol>
    <div class="note-text">
        Note: If you are loading csv files with non-English characters, please consult the following <a href="#" target="_blank">help note</a>.
    </div>
""", unsafe_allow_html=True)

start_upload = st.button("Start Upload")


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
