import streamlit as st
import json
import logging
from typing import Dict, Any

def developer_console(api_client):
    """
    Owner-only Developer Console to test the internal FastAPI app
    with raw JSON requests/responses.
    """
    st.subheader("🛠️ Internal FastAPI API Tester")
    st.info("This console allows testing the In-Process FastAPI app directly.")

    # 1. Select Route
    route = st.selectbox(
        "Select API Route",
        ["/health", "/process-record", "/process-batch", "/clear-cache"],
        index=0
    )

    # 2. Method
    method = st.radio("HTTP Method", ["GET", "POST"], horizontal=True)

    # 3. Payload Editor (only for POST)
    payload_str = "{}"
    if method == "POST":
        if route == "/process-record":
            payload_str = json.dumps({
                "district": "અમદાવાદ",
                "taluka": "બાવળા",
                "village": "બાવળા",
                "survey_number": "101"
            }, indent=2, ensure_ascii=False)
        
        payload_str = st.text_area("Request Payload (JSON)", value=payload_str, height=200)

    # 4. Execute Request
    if st.button("🚀 Execute Internal Request"):
        try:
            # Parse payload if POST
            payload = json.loads(payload_str) if method == "POST" else None
            
            with st.spinner(f"Calling {route}..."):
                # Use the underlying TestClient inside the InProcessTSRClient
                # (Accessing private _client for developer testing)
                if method == "GET":
                    response = api_client._client.get(route)
                else:
                    response = api_client._client.post(route, json=payload)

                # Display Results
                st.divider()
                st.write(f"**Status Code:** `{response.status_code}`")
                
                # Headers
                with st.expander("Response Headers"):
                    st.json(dict(response.headers))
                
                # Content
                if "application/json" in response.headers.get("content-type", ""):
                    st.write("**JSON Response Body:**")
                    st.json(response.json())
                elif "application/zip" in response.headers.get("content-type", ""):
                    st.success("✅ Success: Received ZIP (DOCX + PDF)")
                    st.write(f"Size: {len(response.content) / 1024:.2f} KB")
                else:
                    st.write("**Raw Response Body (first 500 chars):**")
                    st.code(response.text[:500])

        except json.JSONDecodeError:
            st.error("❌ Invalid JSON payload.")
        except Exception as e:
            st.error(f"❌ Error executing request: {str(e)}")
            logging.error(f"Developer Console Error: {e}", exc_info=True)
