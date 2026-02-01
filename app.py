import streamlit as st
from supabase import create_client, Client
import google.generativeai as genai
import json
from datetime import datetime

# --- [SECTION 1: CONFIGURATION] ---
# 웹 브라우저 탭에 표시될 이름과 아이콘을 설정합니다.
st.set_page_config(page_title="LifeSync | 목표와 일상의 동기화", page_icon="🔄", layout="wide")

# Initialize Clients
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-2.0-flash-lite-preview-02-05')

# --- [SECTION 2: AI ENGINE] ---
def ai_generate_roadmap(goal_title):
    prompt = f"""
    당신은 전략적 라이프 코치입니다. 목표 '{goal_title}'를 분석하여 JSON으로만 응답하세요.
    1. 4개의 Phase로 나누고 각 Phase별 3개의 Action 도출.
    2. 각 Action에는 구체적인 'advisor_checkpoints' 3개 포함.
    3. 도메인 선정: [CAREER_GROWTH, HEALTH, FINANCE, LIFE_SPACE, SOCIAL_CONNECT, SELF_CARE] 중 택1.
    JSON 구조 예시:
    {{
      "domain": "카테고리명",
      "roadmap": [
        {{ "phase": "단계명", "actions": [ {{ "title": "할일", "checkpoints": ["팁1", "팁2"] }} ] }}
      ]
    }}
    """
    response = model.generate_content(prompt)
    # JSON 파싱 방어 코드
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

def ai_generate_snacks(time_limit, difficulty):
    prompt = f"{time_limit}분 내외로 할 수 있는 난이도 '{difficulty}'의 스낵 챌린지 3개를 JSON 리스트로 추천해줘. [{{'title': '내용', 'duration': '분'}}] 형식."
    response = model.generate_content(prompt)
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

# --- [SECTION 3: DATABASE CRUD] ---
def save_goal(goal_data, title):
    res = supabase.table("goals").insert({"title": title, "domain": goal_data['domain']}).execute()
    g_id = res.data[0]['id']
    for p in goal_data['roadmap']:
        for a in p['actions']:
            supabase.table("actions").insert({
                "goal_id": g_id,
                "title": f"[{p['phase']}] {a['title']}",
                "advisor_data": {"checkpoints": a['checkpoints'], "candidates": [], "notes": ""}
            }).execute()


# --- [SECTION 4: UI COMPONENTS] ---
def render_sidebar():
    # 사이드바 상단에 브랜드 로고 느낌의 텍스트 배치
    st.sidebar.markdown("# 🔄 LifeSync")
    st.sidebar.caption("Sync Your Vision, Step by Step")
    st.sidebar.divider()
    return st.sidebar.radio("Menu", ["📅 오늘의 할 일", "🎯 새 로드맵 설계", "🍪 스낵 챌린지"])

def main():
    menu = render_sidebar()
    
    # 각 페이지 진입 시 브랜드명 노출
    if menu == "새 로드맵 설계":
        st.header("🎯 새로운 인생 목표 설정")
        goal_title = st.text_input("이루고 싶은 목표는 무엇인가요?", placeholder="예: 스페인어 마스터하기")
        if st.button("AI 설계도 생성"):
            with st.spinner("AI 조언자가 전략을 짜는 중..."):
                try:
                    data = ai_generate_roadmap(goal_title)
                    save_goal(data, goal_title)
                    st.success("로드맵이 서버에 저장되었습니다!")
                except Exception as e:
                    st.error(f"오류 발생: {e}")

    # 2. 오늘의 할 일 (리스트 & 가이드맵)
    elif menu == "오늘의 할 일":
        st.header("📅 실행 및 의사결정")
        cols = st.columns([1, 1])
        
        # 가이드맵 (간이 텍스트 플로우차트)
        with cols[0]:
            st.subheader("📍 가이드맵 (Flow)")
            goals = supabase.table("goals").select("*").execute().data
            if goals:
                selected_goal = st.selectbox("진행 중인 목표 선택", [g['title'] for g in goals])
                g_id = next(g['id'] for g in goals if g['title'] == selected_goal)
                actions = supabase.table("actions").select("*").eq("goal_id", g_id).execute().data
                
                for a in actions:
                    status = "✅" if a['is_completed'] else "⏳"
                    if st.button(f"{status} {a['title']}", key=a['id']):
                        st.session_state['selected_action'] = a
            else:
                st.info("먼저 로드맵을 설계해주세요.")

        # 조언자 패널 & 의사결정 메모
        with cols[1]:
            st.subheader("💡 조언자 & 기록")
            if 'selected_action' in st.session_state:
                act = st.session_state['selected_action']
                st.info(act['title'])
                
                # 조언자 체크포인트
                st.write("**조언자의 체크리스트:**")
                for cp in act['advisor_data']['checkpoints']:
                    st.checkbox(cp, key=f"cp_{act['id']}_{cp}")
                
                # 후보군 비교 메모
                st.write("---")
                st.write("**📝 비교 메모 및 별점**")
                memo = st.text_area("후보군이나 생각을 기록하세요", value=act['advisor_data'].get('notes', ""), key=f"memo_{act['id']}")
                score = st.slider("나의 확신 점수", 0, 100, 50, key=f"score_{act['id']}")
                
                if st.button("진행상황 저장"):
                    new_data = act['advisor_data']
                    new_data['notes'] = memo
                    new_data['last_score'] = score
                    supabase.table("actions").update({"advisor_data": new_data}).eq("id", act['id']).execute()
                    st.toast("서버에 저장되었습니다!")
            else:
                st.write("왼쪽 로드맵에서 항목을 선택하세요.")

    # 3. 스낵 챌린지
    elif menu == "스낵 챌린지":
        st.header("🍪 Snack Challenge")
        st.write("자투리 시간을 활용해 작은 성취감을 느껴보세요.")
        
        t_limit = st.select_slider("가용 시간 (분)", options=[1, 5, 10, 15, 20, 30])
        diff = st.select_slider("난이도", options=["매우 쉬움", "보통", "도전적"])
        
        if st.button("챌린지 뽑기"):
            with st.spinner("스낵 준비 중..."):
                snacks = ai_generate_snacks(t_limit, diff)
                st.session_state['snacks'] = snacks
        
        if 'snacks' in st.session_state:
            for s in st.session_state['snacks']:
                with st.container():
                    col_s1, col_s2 = st.columns([4, 1])
                    col_s1.write(f"**{s['title']}** ({s['duration']})")
                    if col_s2.button("완료", key=f"snack_{s['title']}"):
                        st.balloons()
                        st.toast("스낵 챌린지 성공! 성취도가 0.1% 상승했습니다.")

if __name__ == "__main__":
    main()
