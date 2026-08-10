"""Streamlit UI for the GitHub Repo Health Agent.

Talks to the backend over HTTP only (POST /analyze, POST /approve per
CONTRACTS.md) — never imports the graph, per the brief's hard requirement
that the UI must not run the graph itself.

Run the backend first, then this:
    uvicorn backend.api:app --port 8000
    streamlit run ui/app.py

The backend's base URL comes from FAHES_BACKEND (default
http://localhost:8000), so pointing this UI at a different server is a
change to .env, never to this file.
"""
import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("FAHES_BACKEND", "http://localhost:8000")
REQUEST_TIMEOUT = 120  # analysis runs multiple LLM calls, can take a while

_LANGUAGE_OPTIONS = [("en", "English"), ("ar", "العربية")]

_TEXT = {
    "en": {
        "page_title": "GitHub Repo Health Agent",
        "heading": "🔍 GitHub Repo Health Agent",
        "language_label": "Language",
        "repo_label": "Repository URL",
        "repo_placeholder": "https://github.com/owner/repo",
        "scan_button": "Scan",
        "scanning": "Scanning the repository — this can take a moment...",
        "empty_url_warning": "Enter a repository URL first.",
        "connection_error": "Could not reach the backend at {url}: {error}",
        "rejected_heading": "Request declined",
        "report_heading": "Report",
        "approval_heading": "Open an issue with these findings?",
        "approve_button": "Yes, open the issue",
        "decline_button": "No, report only",
        "opening": "Contacting the backend...",
        "issue_opened": "Issue opened:",
        "no_issue": "No issue was opened.",
        "new_scan": "New scan",
    },
    "ar": {
        "page_title": "وكيل فحص صحة مستودعات GitHub",
        "heading": "🔍 وكيل فحص صحة مستودعات GitHub",
        "language_label": "اللغة",
        "repo_label": "رابط المستودع",
        "repo_placeholder": "https://github.com/owner/repo",
        "scan_button": "افحص",
        "scanning": "جارٍ فحص المستودع — قد يستغرق هذا بعض الوقت...",
        "empty_url_warning": "أدخل رابط المستودع أولاً.",
        "connection_error": "تعذّر الوصول إلى الخادم على {url}: {error}",
        "rejected_heading": "الطلب مرفوض",
        "report_heading": "التقرير",
        "approval_heading": "هل تريد فتح بلاغ بهذه النتائج؟",
        "approve_button": "نعم، افتح البلاغ",
        "decline_button": "لا، اكتفِ بالتقرير",
        "opening": "جارٍ التواصل مع الخادم...",
        "issue_opened": "تم فتح البلاغ:",
        "no_issue": "لم يُفتح أي بلاغ.",
        "new_scan": "فحص جديد",
    },
}


def _t(key: str) -> str:
    return _TEXT[st.session_state.language][key]


def _inject_rtl() -> None:
    st.markdown(
        """
        <style>
        .stApp { direction: rtl; }
        .stApp [data-testid="stMarkdownContainer"],
        .stApp label, .stApp p, .stApp li { text-align: right; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _call_analyze(repo_url: str, language: str) -> dict:
    resp = requests.post(
        f"{BACKEND_URL}/analyze",
        json={"repo_url": repo_url, "language": language},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _call_approve(thread_id: str, approved: bool) -> dict:
    resp = requests.post(
        f"{BACKEND_URL}/approve",
        json={"thread_id": thread_id, "approved": approved},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _reset_scan_state() -> None:
    for key in ("analysis", "approval_result"):
        st.session_state.pop(key, None)


def _render_language_switch() -> None:
    codes = [code for code, _ in _LANGUAGE_OPTIONS]
    labels = [label for _, label in _LANGUAGE_OPTIONS]
    selected_label = st.selectbox(
        _t("language_label"),
        options=labels,
        index=codes.index(st.session_state.language),
        label_visibility="collapsed",
        key="language_select",
    )
    selected_code = codes[labels.index(selected_label)]
    if selected_code != st.session_state.language:
        st.session_state.language = selected_code
        st.rerun()


def main() -> None:
    st.set_page_config(page_title=_TEXT["en"]["page_title"], page_icon="🔍")

    if "language" not in st.session_state:
        st.session_state.language = "en"

    header_col, lang_col = st.columns([5, 1])
    with lang_col:
        _render_language_switch()

    if st.session_state.language == "ar":
        _inject_rtl()

    with header_col:
        st.title(_t("heading"))

    repo_url = st.text_input(
        _t("repo_label"), placeholder=_t("repo_placeholder"), key="repo_url_input"
    )

    if st.button(_t("scan_button"), type="primary"):
        if not repo_url.strip():
            st.warning(_t("empty_url_warning"))
        else:
            _reset_scan_state()
            with st.spinner(_t("scanning")):
                try:
                    st.session_state.analysis = _call_analyze(
                        repo_url.strip(), st.session_state.language
                    )
                except requests.RequestException as exc:
                    st.error(_t("connection_error").format(url=BACKEND_URL, error=exc))

    analysis = st.session_state.get("analysis")
    if analysis:
        if analysis["status"] == "rejected":
            st.subheader(_t("rejected_heading"))
            st.markdown(analysis["report"])
        elif analysis["status"] == "awaiting_approval":
            st.subheader(_t("report_heading"))
            st.markdown(analysis["report"])

            approval_result = st.session_state.get("approval_result")
            if approval_result is None:
                st.subheader(_t("approval_heading"))
                col_yes, col_no = st.columns(2)
                with col_yes:
                    approve_clicked = st.button(
                        _t("approve_button"), type="primary", key="approve_btn"
                    )
                with col_no:
                    decline_clicked = st.button(_t("decline_button"), key="decline_btn")

                if approve_clicked or decline_clicked:
                    with st.spinner(_t("opening")):
                        try:
                            st.session_state.approval_result = _call_approve(
                                analysis["thread_id"], approve_clicked
                            )
                        except requests.RequestException as exc:
                            st.error(_t("connection_error").format(url=BACKEND_URL, error=exc))
                    if "approval_result" in st.session_state:
                        st.rerun()
            else:
                if approval_result.get("issue_url"):
                    st.success(f"{_t('issue_opened')} {approval_result['issue_url']}")
                else:
                    st.info(_t("no_issue"))
                    # The backend explains an approved-but-unpublished outcome
                    # (no GITHUB_TOKEN, GitHub refused the write) in the user's
                    # language — showing it beats a bare "no issue was opened".
                    if approval_result.get("message"):
                        st.caption(approval_result["message"])

        if st.button(_t("new_scan")):
            _reset_scan_state()
            st.session_state.pop("repo_url_input", None)
            st.rerun()


if __name__ == "__main__":
    main()
