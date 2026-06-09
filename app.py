import requests
import streamlit as st

st.set_page_config(
    page_title="Memora",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="auto"
)

def chat_api_stream(session_id, message):
    response = requests.post(
        "http://localhost:8000/chat/stream",
        json={
            "session_id": session_id,
            "message": message
        },
        stream=True)
    return response

def create_session_api(username):
    response = requests.post(
        "http://localhost:8000/sessions",
        json={"username": username})
    return response.json()

def get_sessions_api(username):
    response = requests.get(
    f"http://localhost:8000/users/{username}/sessions")
    return response.json()

def load_messages_api(session_id):
    response = requests.get(
        f"http://localhost:8000/sessions/{session_id}/messages"
    )
    return response.json()

def upload_document_api(username, file):
    try:
        response = requests.post(
            "http://localhost:8000/documents/upload",
            data={"username": username},
            files={"file": (file.name, file, "application/pdf")}
        )
        st.write(f"Status code: {response.status_code}") 
        st.write(f"Response: {response.text}")             
        return response.json()
    except Exception as e:
        st.error(f"Request failed: {e}")
        return {}
    
def get_documents_api(username):
    response = requests.get(
        f"http://localhost:8000/documents/{username}")
    return response.json()

def delete_document_api(document_id):
    response = requests.delete(
        f"http://localhost:8000/documents/{document_id}")
    return response.json()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "sessions" not in st.session_state:
    st.session_state.sessions = []
if "documents" not in st.session_state:
    st.session_state.documents = []

if not st.session_state.logged_in:
    st.title("Memora")
    st.markdown("#### Your personal AI assistant that actually remembers you.")
    st.divider()

    username = st.text_input("Username", placeholder="Enter your username")
    
    
    if st.button("Login", use_container_width=True):
        if username.strip():
            st.session_state.username = username.strip().lower()
            st.session_state.logged_in = True
            st.session_state.messages = []
            st.session_state.sessions = get_sessions_api(st.session_state.username)
            st.session_state.documents = get_documents_api(st.session_state.username)
            if st.session_state.sessions:
                    st.session_state.session_id = (st.session_state.sessions[0]["id"])
                    st.session_state.messages = (load_messages_api(st.session_state.session_id))
            st.rerun()
        else:
            st.error("Please enter a username")      
else:
    with st.sidebar:

        if st.button("+ New Chat"):
            data = create_session_api(st.session_state.username)
            st.session_state.session_id = data["session_id"]
            st.session_state.messages = []
            st.session_state.sessions = (get_sessions_api(st.session_state.username))
            st.session_state.documents = get_documents_api(st.session_state.username)
            st.rerun()

        for session in st.session_state.sessions:
            if st.button(session["title"], key=session["id"]):
                st.session_state.session_id = session["id"]
                st.session_state.messages = load_messages_api(session["id"])
                st.rerun()

        st.divider()
        st.markdown("**Documents**")

        # File uploader
        uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])
        if uploaded_file:
            if st.button("Upload", use_container_width=True):
                with st.spinner("Processing..."):
                    result = upload_document_api(
                        st.session_state.username,
                        uploaded_file
                    )
                    st.write(result) 
                    if "document_id" in result:
                        st.success(f"Uploaded — {result['chunks_count']} chunks")
                        st.session_state.documents = get_documents_api(
                            st.session_state.username
                        )
                        st.rerun()
                    else:
                        st.error("Upload failed")

        # List documents
        if st.session_state.documents:
            for doc in st.session_state.documents:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(doc["filename"])
                with col2:
                    if st.button("x", key=f"del_{doc['id']}"):
                        delete_document_api(doc["id"])
                        st.session_state.documents = get_documents_api(
                            st.session_state.username
                        )
                        st.rerun()
        else:
            st.caption("No documents uploaded yet")

        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.messages = []
            st.session_state.session_id = None
            st.session_state.sessions = []
            st.rerun()

    st.title(f"Hey {st.session_state.username.capitalize()}!")
    st.divider()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    
    if prompt := st.chat_input("Type a message..."):
        st.session_state.messages.append({"role": "user", "content": prompt.text if hasattr(prompt, 'text') else prompt})

        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            if st.session_state.session_id is None:
                st.error("Create or select a chat first.")
                st.stop()
            response = chat_api_stream(st.session_state.session_id, prompt)

            if response:
                full_response = st.write_stream(response.iter_content(chunk_size=None, decode_unicode=True))
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            else:
                st.error("Connection error")