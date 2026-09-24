import streamlit as st

st.set_page_config(page_title="Market dashboard", layout="wide")

nav = st.navigation(
    [
        st.Page("pages/overview.py", title="Overview", default=True),
        st.Page("pages/market_map.py", title="Market map"),
    ]
)
nav.run()
