import streamlit as st
from supabase import create_client
import google.generativeai as genai
import json
import random

# --- [1. 기본 설정 및 보안 체크] ---
st.set_page_config(page_title="LifeSync | 목표와 일상의 동기화", page_icon="🔄", layout="wide")

def check_secrets():
    keys = ["GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]
    for k in keys:
        if k not in st.secrets:
            st.error(f"⚠️ Secrets 설정 누락: {k}를 확인하세요.")
            st.stop()

check_secrets()

# --- [2. 클라이언트 초기화] ---
@st.cache_resource
def init_clients():
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.0-flash-lite-preview-02-05')
    return supabase, model

supabase, model = init_clients()

# --- [3. AI 엔진 함수] ---
def generate_roadmap_ai(goal_title):
    prompt = f"""
    목표 '{goal_title}'를 분석하여 반드시 JSON 형식으로만 응답하세요.
    구조: {{
      "domain": "카테고리명",
      "roadmap": [
        {{ "phase": "단계명", "actions": [ {{ "title": "할일", "checkpoints": ["팁1", "팁2"] }} ] }}
      ]
    }}
    """
    response = model.generate_content(prompt)
    txt = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(txt)

def generate_snack_ai(minutes, level):
    prompt = f"{minutes}분 동안 할 수 있는 {level} 난이도의 짧은 자기계발 활동 3개를 JSON 리스트로 추천해줘. 형식: [{{'title': '내용', 'duration': '분'}}]"
    response = model.generate_content(prompt)
    txt = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(txt)

# --- [4. UI 사이드바] ---
st.sidebar.title("🔄 LifeSync")
st.sidebar.caption("Sync Your Vision, Step by Step")
menu = st.sidebar.radio("메뉴 선택", ["📅 오늘의 할 일", "🎯 새 로드맵 설계", "🍪 스낵 챌린지"])

# --- [5. 기능 구현] ---

# (1) 새 로드맵 설계
if menu == "🎯 새 로드맵 설계":
    st.header("🎯 새로운 인생 목표 설정")
    st.info("AI가 목표를 분석하여 실행 가능한 단계로 쪼개어 드립니다.")
    
    with st.form("goal_form"):
        goal_input = st.text_input("이루고 싶은 목표는?")
        submit = st.form_submit_button("AI 로드맵 생성")
    
    if submit and goal_input:
        with st.spinner("전략을 설계 중입니다..."):
            try:
                data = generate_roadmap_ai(goal_input)
                # DB 저장
                res = supabase.table("goals").insert({"title": goal_input, "domain": data['domain']}).execute()
                g_id = res.data[0]['id']
                
                for p in data['roadmap']:
                    for a in p['actions']:
                        supabase.table("actions").insert({
                            "goal_id": g_id,
                            "title": f"[{p['phase']}] {a['title']}",
                            "advisor_data": {"checkpoints": a['checkpoints'], "notes": ""}
                        }).execute()
                st.success("✅ 성공! '오늘의 할 일' 탭으로 이동하세요.")
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")

# (2) 오늘의 할 일
elif menu == "📅 오늘의 할 일":
    st.header("📅 나의 실행 로드맵")
    
    try:
        goals = supabase.table("goals").select("*").order("created_at", desc=True).execute().data
        if not goals:
            st.info("등록된 목표가 없습니다. '새 로드맵 설계'에서 시작하세요!")
        else:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📍 단계별 가이드")
                selected_goal_title = st.selectbox("목표 선택", [g['title'] for g in goals])
                target_goal = next(g for g in goals if g['title'] == selected_goal_title)
                
                actions = supabase.table("actions").select("*").eq("goal_id", target_goal['id']).execute().data
                for a in actions:
                    if st.button(f"{'✅' if a['is_completed'] else '⏳'} {a['title']}", key=a['id'], use_container_width=True):
                        st.session_state['active_action'] = a

            with col2:
                st.subheader("💡 조언자 패널")
                if 'active_action' in st.session_state:
                    act = st.session_state['active_action']
                    st.success(f"과업: {act['title']}")
                    
                    st.write("**체크포인트:**")
                    for cp in act['advisor_data'].get('checkpoints', []):
                        st.checkbox(cp, key=f"cp_{act['id']}_{cp}")
                    
                    memo = st.text_area("의사결정 메모", value=act['advisor_data'].get('notes', ""), key=f"memo_{act['id']}")
                    
                    c1, c2 = st.columns(2)
                    if c1.button("완료 상태 변경"):
                        new_status = not act['is_completed']
                        supabase.table("actions").update({"is_completed": new_status}).eq("id", act['id']).execute()
                        st.rerun()
                    if c2.button("메모 저장"):
                        new_adv = act['advisor_data']
                        new_adv['notes'] = memo
                        supabase.table("actions").update({"advisor_data": new_adv}).eq("id", act['id']).execute()
                        st.toast("저장되었습니다!")
                else:
                    st.write("왼쪽 리스트에서 과업을 선택해 상세 조언을 확인하세요.")
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")

# (3) 스낵 챌린지
elif menu == "🍪 스낵 챌린지":
    st.header("🍪 Snack Challenge")
    st.write("자투리 시간을 활용해 작은 성취감을 채우세요.")
    
    t_limit = st.select_slider("지금 여유 시간 (분)", options=[1, 5, 10, 15, 20, 30])
    level = st.select_slider("난이도", options=["매우 쉬움", "보통", "도전적"])
    
    if st.button("오늘의 스낵 추천"):
        with st.spinner("AI가 스낵을 준비합니다..."):
            st.session_state['snack_list'] = generate_snack_ai(t_limit, level)
            
    if 'snack_list' in st.session_state:
        for s in st.session_state['snack_list']:
            with st.container(border=True):
                sc1, sc2 = st.columns([4, 1])
                sc1.write(f"**{s['title']}** ({s['duration']}분)")
                if sc2.button("완료", key=f"snk_{s['title']}"):
                    st.balloons()
                    st.toast("작은 성취가 쌓여 큰 변화를 만듭니다!")
