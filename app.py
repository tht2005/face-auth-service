import streamlit as st
import numpy as np
from extract import retrieve_face_emb_from_webcam
from auth import register, validation

st.set_page_config(page_title="Face Recognization", layout="centered")
st.title("Face Recognization System")

tab_register, tab_login = st.tabs(["Register", "Login"])

if "reg_embedding" not in st.session_state:
    st.session_state.reg_embedding = None
if "reg_preview_img" not in st.session_state:
    st.session_state.reg_preview_img = None

with tab_register:
    st.subheader("Register new account")
    
    reg_username = st.text_input("Username", key="reg_user")
    reg_fullname = st.text_input("Fullname", key="reg_name")
    st.write("---")
    st.write("**Register the FaceID:**")
    
    col_status, col_btn = st.columns([3, 1])
    
    with col_status:
        if st.session_state.reg_embedding is None:
            st.info("Status: ⚪ Undone!")
        else:
            st.success("Status: 🟢 Done!")

    with col_btn:
        trigger_scan = st.button("Turn on Camera")

    camera_placeholder = st.empty()

    if trigger_scan:
        with st.spinner("..."):
            emb, preview_img = retrieve_face_emb_from_webcam(st_frame=camera_placeholder)
            if emb is not None:
                st.session_state.reg_embedding = emb
                st.session_state.reg_preview_img = preview_img
                camera_placeholder.empty()
                st.rerun()
            else:
                st.error("Can not extract the face, please retry.")

    if st.session_state.reg_preview_img is not None:
        st.write("**FaceID Preview:**")
        st.image(st.session_state.reg_preview_img, width=350, caption="FaceID Preview")

    st.write("---")
    if st.button("Register", type="primary"):
        if not reg_username or not reg_fullname:
            st.warning("Please fill all the needed information.")
        elif st.session_state.reg_embedding is None:
            st.warning("Please scan your face.")
        else:
            try:
                register(reg_username, reg_fullname, st.session_state.reg_embedding)
                st.balloons()
                st.success(f"Congratulations! Account '{reg_username}' has been registered successfully.")
                
                st.session_state.reg_embedding = None
                st.session_state.reg_preview_img = None
            except Exception as e:
                st.error(f"Register unsuccessfully. Error: {e}")

with tab_login:
    st.subheader("Authenication")
    login_username = st.text_input("Username")
    
    if st.button("Face Scan", type="primary"):
        if not login_username:
            st.warning("Please fill the username.")
        else:
            login_camera_placeholder = st.empty()
            with st.spinner("Opening webcam..."):
                live_emb, _ = retrieve_face_emb_from_webcam(st_frame=login_camera_placeholder)
                login_camera_placeholder.empty()
                
                if live_emb is not None:
                    try:
                        is_match = validation(login_username, live_emb)
                        if is_match:
                            st.success(f"Login successfully! Welcome back, {login_username}.")
                        else:
                            st.error("Authenicate unsuccessfully: The face do not match.")
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.error("Can not detect the face.")
