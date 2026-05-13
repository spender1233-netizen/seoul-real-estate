"""
환경변수 로드 유틸리티
로컬: .env 파일
Streamlit Cloud: st.secrets
"""

import os
from dotenv import load_dotenv

load_dotenv()


def get_secret(key: str, default: str = "") -> str:
    """환경변수를 로컬(.env) 또는 Streamlit Cloud(st.secrets)에서 가져온다."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)
