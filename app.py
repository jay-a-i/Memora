import requests, bcrypt #uv add requests bcrypt
import streamlit as st #uv add streamlit
import streamlit_authenticator as stauth #uv add streamlit-authenticator

st.set_page_config(
    page_title="Memora",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="auto"
)

API_URL = "https://memora-tmek.onrender.com"

def chat_api_stream(session_id, message):
    try:
        response = requests.post(
            f"{API_URL}/chat/stream",
            json={
                "session_id": session_id,
                "message": message
            },
            stream=True)
        if response.status_code==200:
            return response
        else:
            st.error(f"Failed to Stream Chat. Status code: {response.status_code}")
            return None
    except Exception as e:
        st.error("Something went wrong.")
        return None

def register_new_user_api(username, name, email, hashed_password):
    try:
        response = requests.post(
            f"{API_URL}/register_new_user",
            json={
                "username": username,
                "name": name,
                "email": email,
                "password": hashed_password
            }
        )
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to Register. Status code: {response.status_code}")
            return None
    except Exception as e:
        st.error("Something went wrong.")
        return None

@st.cache_data(ttl=10)
def load_credential_api():
    try:
        response = requests.get(f"{API_URL}/load_credentials")
        if response.status_code == 200:
            return response.json() 
        else:
            st.error(f"Failed to fetch credentials. Status code: {response.status_code}")
            return None
    except Exception as e:
        st.error("Something went wrong.")
        return None

def create_session_api(username):
    try:
        response = requests.post(
            f"{API_URL}/sessions",
            json={"username": username})
        if response.status_code==200:
            return response.json()
        else:
            st.error(f"Failed to Create Session. Status Code: {response.status_code}")
            return None
    except Exception as e:
        st.error("Something went wrong.")
        return None
    
def get_sessions_api(username):
    try:
        response = requests.get(
        f"{API_URL}/users/{username}/sessions")
        if response.status_code==200:
            return response.json()
        else:
            st.error(f"Failed to Get Session. Status Code: {response.status_code}")
            return None
    except Exception as e:
        st.error("Something went wrong.")
        return None
    
def load_messages_api(session_id):
    try:
        response = requests.get(
            f"{API_URL}/sessions/{session_id}/messages"
        )
        if response.status_code==200:
            return response.json()
        else:
            st.error(f"Failed to Load Messages. Status Code: {response.status_code}")
            return None
    except Exception as e:
        st.error("Something went wrong.")
        return None

def upload_document_api(username, file):
    try:
        response = requests.post(
            f"{API_URL}/documents/upload",
            data={"username": username},
            files={"file": (file.name, file, "application/pdf")}
        )            
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to upload file!. Status Code: {response.status_code}")
            return None
    except Exception as e:
        st.error("Something went wrong.")
        return None
    
def get_documents_api(username):
    try:
        response = requests.get(
            f"{API_URL}/documents/{username}")
        if response.status_code==200:
            return response.json()
        else:
            st.error(f"Failed to Fetch Documents. Status Code: {response.status_code}")
            return None
    except Exception as e:
        st.error("Something went wrong.")
        return None

def delete_document_api(document_id):
    try:
        response = requests.delete(
            f"{API_URL}/documents/{document_id}")
        if response.status_code==200:
            return response.json()
        else:
            st.error(f"Failed to Delete Document. Status Code: {response.status_code}")
            return None
    except Exception as e:
        st.error("Something went wrong.")
        return None

if "credentials_data" not in st.session_state:
    db_credentials = load_credential_api()
    if db_credentials:
        st.session_state["credentials_data"] = {"usernames": db_credentials}
    else:
        st.session_state["credentials_data"] = {"usernames": {}}

authenticator = stauth.Authenticate(
    credentials=st.session_state["credentials_data"],
    cookie_name="memora_auth_cookie",
    cookie_key="memora_signature_key_2026",
    cookie_expiry_days=15,
    auto_hash=False
    )

if not st.session_state.get("authentication_status"):
    st.title("Memora")
    st.markdown("#### Your personal AI assistant that actually remembers you.")
    st.divider()

    tab1, tab2 = st.tabs(["🔑 Sign In", "📝 Create Account"])

    with tab1:
        authenticator.login(location="main")
    with tab2:
        reg_name     = st.text_input("Full Name", key="reg_name")
        reg_username = st.text_input("Username", key="reg_username")
        reg_email    = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        reg_password2 = st.text_input("Confirm Password", type="password", key="reg_password2")

        if st.button("Create Account", use_container_width=True):
            if not all([reg_name, reg_username, reg_email, reg_password]):
                st.error("Please fill in all fields")
            elif reg_password != reg_password2:
                st.error("Passwords do not match")
            elif len(reg_password) < 8:
                st.error("Password must be at least 8 characters")
            else:
                hashed = bcrypt.hashpw(
                    reg_password.encode(), 
                    bcrypt.gensalt()
                ).decode()

                api_response = register_new_user_api(
                    username=reg_username.strip().lower(),
                    name=reg_name.strip(),
                    email=reg_email.strip().lower(),
                    hashed_password=hashed
                )

                if api_response:
                    load_credential_api.clear()
                    st.rerun()
                    st.success("Account created successfully!\nGo to Login Page")
                    

else: #Authentication Successfull
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = None
    if "session" not in st.session_state:
        st.session_state["session"] = []
    if "documents" not in st.session_state:
        st.session_state["documents"] = []
 
    with st.sidebar:
        if not st.session_state["session"]:
            st.session_state["session"] = get_sessions_api(st.session_state["username"])
            
        if st.button("+ New Chat"):
            data = create_session_api(st.session_state["username"])
            if data:
                st.session_state["session_id"] = data["session_id"]
                st.session_state["messages"] = []
                st.session_state["session"] = (get_sessions_api(st.session_state["username"]))
                st.session_state["documents"] = get_documents_api(st.session_state["username"])
                st.rerun()

        if st.session_state["session"]:    
            for session in st.session_state["session"]:
                if st.button(session["title"], key=session["id"]):
                    st.session_state["session_id"] = session["id"]
                    st.session_state["messages"] = load_messages_api(session["id"])
                    st.rerun()

        st.divider()
        st.markdown("**Documents**")
        if not st.session_state["documents"]:
            st.session_state["documents"] = get_documents_api(st.session_state["username"])

        # File uploader
        uploaded_file = st.file_uploader("Upload PDF", type=["pdf"], key="pdf_uploader")
        if uploaded_file:
            if st.button("Upload", use_container_width=True):
                with st.spinner("Processing..."):
                    result = upload_document_api(st.session_state["username"], uploaded_file)

                    if result and "document_id" in result:
                        st.success(f"Uploaded — {result['chunks_count']} chunks")
                        st.session_state["documents"] = get_documents_api(st.session_state["username"])

                        if "pdf_uploader" in st.session_state:
                            del st.session_state["pdf_uploader"]
                        st.rerun()

                    else:
                        st.error("Upload failed")

        # List documents
        if st.session_state["documents"]:
            for doc in st.session_state["documents"]:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(doc["filename"])
                with col2:
                    if st.button("x", key=f"del_{doc['id']}"):
                        delete_document_api(doc["id"])
                        st.session_state["documents"] = get_documents_api(
                            st.session_state["username"]
                        )
                        st.rerun()
        else:
            st.caption("No documents uploaded yet")

        if st.button("Logout", use_container_width=True):
            authenticator.cookie_controller.delete_cookie()
            st.session_state.clear()
            st.rerun()

    st.title(f"Hey {st.session_state['username'].capitalize()}!")
    st.divider()
    if not st.session_state["session"]:
        st.info("Create your first chat.")

    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    
    if prompt := st.chat_input("Type a message..."):
        if st.session_state["session_id"] is None:
                st.error("Create or select a chat first.")
                st.stop()
        st.session_state["messages"].append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            response = chat_api_stream(st.session_state["session_id"], prompt)

            if response:
                full_response = st.write_stream(response.iter_content(chunk_size=None, decode_unicode=True))
                st.session_state["messages"].append({"role": "assistant", "content": full_response})
            else:
                st.error("Connection error")