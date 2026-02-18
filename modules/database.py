import json
import streamlit as st
import pandas as pd
from google.cloud import firestore
from google.oauth2 import service_account

DOC_PATH = "finance_app/user_portfolio"


@st.cache_resource
def init_db():
    if "firebase_config" not in st.secrets:
        st.error("❌ 请在 Secrets 中配置 firebase_config")
        return None
    try:
        key_dict = dict(st.secrets["firebase_config"])
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"❌ 数据库初始化失败: {e}")
        return None


def sync_to_cloud(db):
    """清洗数据并强制同步到 Firebase"""
    if db:
        try:
            raw_favs = list(st.session_state.favorites)
            clean_list = json.loads(json.dumps(raw_favs, ensure_ascii=False))
            db.document(DOC_PATH).set({
                "funds": clean_list,
                "last_sync": str(pd.Timestamp.now())
            }, merge=True)
            st.toast("✅ 云端同步完成", icon="☁️")
        except Exception as e:
            st.error(f"❌ 云端同步失败: {e}")


def load_from_cloud(db):
    """启动时自动拉取云端数据"""
    if db and "initialized" not in st.session_state:
        try:
            res = db.document(DOC_PATH).get()
            if res.exists:
                st.session_state.favorites = res.to_dict().get("funds", [])
            st.session_state.initialized = True
        except Exception:
            st.session_state.favorites = []
