import requests
import streamlit as st

st.set_page_config(
    page_title="Memora",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="auto"
)

def chat_api_stream(username: str, message: str):
    try:
        response = requests.post(
            url="http://localhost:8000/chat/stream",
            json={"username": username, "message": message},
            stream=True 
        )
        return response
    except Exception as e:
        return f"Oops! An error occurred: {e}", None

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None


if not st.session_state.logged_in:
    st.title("Memora")
    st.markdown("#### Your personal AI assistant that actually remembers you.")
    st.divider()

    username = st.text_input("Username", placeholder="Enter your username")

    if st.button("Start Chat", use_container_width=True):
        if username.strip():
            st.session_state.username = username.strip().lower()
            st.session_state.logged_in = True
            st.session_state.messages = []
            st.rerun()
        else:
            st.error("Please enter a username")

else:
    with st.sidebar:
        st.title("Memora")
        st.divider()
        st.markdown(f"'{st.session_state.username.capitalize()}'")
        if st.session_state.session_id:
            st.markdown(f"Session: `#{st.session_state.session_id}`")
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.messages = []
            st.session_state.session_id = None
            st.rerun()

    st.title(f"Hey {st.session_state.username.capitalize()}!")
    st.divider()


    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    
    if prompt := st.chat_input("Type a message..."):
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            response = chat_api_stream(st.session_state.username, prompt)
            
            if response:
                full_response = st.write_stream(response.iter_content(chunk_size=None, decode_unicode=True))
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            else:
                st.error("Connection error")