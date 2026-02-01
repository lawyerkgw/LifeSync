import streamlit as st
from supabase import create_client
import google.generativeai as genai
import json
import pandas as pd
import plotly.express as px
import streamlit.components.v1 as components
import re

# --- [1. 초기 설정 및 보안] ---
st.set_page_config(page_title="LifeSync | 전인적 목표 관리", page_icon="🔄", layout="wide")

@st.cache_resource
def init_clients():
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # 모델명 사용자 요청 고정: gemini-2.5-flash-lite
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    return supabase, model

supabase, model = init_clients()

# --- [2. 스타일 업그레이드: Premium UI CSS] ---
st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    :root {
        --main-bg: #0f172a;
        --card-bg: #1e293b;
        --accent: #38bdf8;
        --text-main: #f8fafc;
    }

    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    
    /* 카드형 컨테이너 스타일 */
    .st-expander, .stChatMessage, div[data-testid="stMetricValue"] {
        background-color: var(--card-bg) !important;
        border-radius: 12px !important;
    }

    /* 버튼 스타일 고도화 */
    .stButton>button {
        border-radius: 10px;
        transition: all 0.3s ease;
        font-weight: 600;
        width: 100%;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(56, 189, 248, 0.4);
    }
    
    /* 메트릭 박스 커스텀 */
    div[data-testid="stMetricValue"] { font-size: 28px !important; font-weight: 700 !important; color: var(--accent) !important; }
    
    /* 탭 메뉴 스타일 */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        background-color: #334155;
        border-radius: 8px 8px 0 0;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- [3. 핵심 비즈니스 로직 함수] ---

def clean_text(text):
    """Mermaid 문법 오류 방지를 위한 정규식 필터"""
    return re.sub(r'[^a-zA-Z0-9가-힣\s]', '', text)

def generate_hierarchical_roadmap(goal_title):
    """장기-중기-단기 목표 계층 생성"""
    prompt = f"""
    목표 '{goal_title}'를 [장기 비전 - 중기 마일스톤 - 단기 실행] 체계로 분석하여 JSON으로 응답하세요.
    1. domain: '건강', '커리어', '재테크', '관계', '자기계발', '즐거움' 중 하나 선택.
    2. vision: 1년 뒤의 구체적인 미래 모습.
    3. roadmap: 2개의 중기 마일스톤, 각 마일스톤당 3개의 아주 구체적인 단기 과업(actions).
    JSON 구조: {{ "domain": "", "vision": "", "roadmap": [ {{ "milestone": "", "actions": [ {{ "title": "", "why": "", "how": "" }} ] }} ] }}
    """
    response = model.generate_content(prompt)
    txt = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(txt)

def generate_snack_ai(minutes, level):
    """스낵 AI 챌린지 생성"""
    prompt = f"""
    따뜻하고 유능한 라이프 코치로서 {minutes}분 내외, 난이도 '{level}'의 스낵 챌린지 5개를 추천하세요.
    반드시 아래 JSON 리스트 형식으로만 응답하세요:
    [ {{ "title": "제목", "duration": "{minutes}분", "why": "이유", "how": "구체적 방법" }} ]
    """
    try:
        response = model.generate_content(prompt)
        res_text = response.text
        json_match = re.search(r'(\[.*\])', res_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        return json.loads(res_text)
    except Exception as e:
        st.error(f"스낵 생성 중 오류: {e}")
        return None

def render_advisor_panel(act):
    """실행 센터의 우측 조언자 패널"""
    with st.container(border=True):
        st.subheader(f"💡 AI 조언자의 가이드")
        st.info(f"**과업:** {act['title']}")
        st.write(f"**🎯 중요성:** {act['advisor_data'].get('why', '성장에 필수적입니다.')}")
        st.success(f"**🚀 첫 단계:** {act['advisor_data'].get('how', '지금 바로 시작해보세요!')}")
        
        memo = st.text_area("의사결정 및 실행 기록", value=act['advisor_data'].get('notes', ""), key=f"memo_{act['id']}")
        if st.button("✅ 기록 저장 및 완료 토글", use_container_width=True):
            new_status = not act['is_completed']
            new_adv = act['advisor_data']
            new_adv['notes'] = memo
            supabase.table("actions").update({"is_completed": new_status, "advisor_data": new_adv}).eq("id", act['id']).execute()
            st.rerun()

# --- [4. 메인 네비게이션 및 화면 구성] ---

st.sidebar.title("🔄 LifeSync Core")
menu = st.sidebar.radio("메뉴 선택", ["📊 인사이트 대시보드", "📅 마스터 실행 센터", "🎯 전략적 로드맵 설계", "🍪 스낵 챌린지"])

# (1) 인사이트 대시보드
if menu == "📊 인사이트 대시보드":
    st.header("📊 전인적 성장 통계")
    goals = supabase.table("goals").select("*").execute().data
    
    if not goals:
        st.info("데이터가 없습니다. '전략적 로드맵 설계'에서 첫 목표를 만들어보세요!")
    else:
        df_goals = pd.DataFrame(goals)
        actions = supabase.table("actions").select("goal_id, is_completed").execute().data
        df_actions = pd.DataFrame(actions) if actions else pd.DataFrame(columns=['goal_id', 'is_completed'])
        
        # 상단 핵심 수치
        c1, c2, c3 = st.columns(3)
        prog = df_actions['is_completed'].mean() * 100 if not df_actions.empty else 0
        c1.metric("전체 달성률", f"{prog:.1f}%")
        c2.metric("진행 중인 프로젝트", len(df_goals))
        c3.metric("오늘의 상태", "집중력 최상")

        st.divider()
        
        col_left, col_right = st.columns([1.2, 1])
        with col_left:
            st.subheader("🎡 인생의 수레바퀴")
            domains = ['건강', '커리어', '재테크', '관계', '자기계발', '즐거움']
            res = []
            for d in domains:
                d_goals = df_goals[df_goals['domain'] == d]
                if not d_goals.empty and not df_actions.empty:
                    d_ids = d_goals['id'].tolist()
                    d_acts = df_actions[df_actions['goal_id'].isin(d_ids)]
                    score = (d_acts['is_completed'].sum() / len(d_acts) * 100) if not d_acts.empty else 0
                else: score = 0
                res.append({"Domain": d, "Score": score})
            
            fig = px.line_polar(pd.DataFrame(res), r='Score', theta='Domain', line_close=True, range_r=[0, 100], template="plotly_dark")
            fig.update_traces(fill='toself', fillcolor='rgba(56, 189, 248, 0.4)', line_color='#38bdf8')
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.subheader("🏆 카테고리별 랭킹")
            st.dataframe(pd.DataFrame(res).sort_values(by="Score", ascending=False), hide_index=True, use_container_width=True)

# (2) 마스터 실행 센터
elif menu == "📅 마스터 실행 센터":
    st.header("📅 Execution Center")
    goals = supabase.table("goals").select("*").execute().data
    if goals:
        selected_title = st.selectbox("현재 집중할 프로젝트", [g['title'] for g in goals])
        target = next(g for g in goals if g['title'] == selected_title)
        
        st.info(f"**🔭 Vision:** {target.get('vision', '비전을 향해 나아가세요.')}")
        
        tab_list, tab_flow = st.tabs(["📑 상세 액션", "🗺️ 전략 플로우"])
        actions = supabase.table("actions").select("*").eq("goal_id", target['id']).execute().data
        
        with tab_list:
            col_act, col_adv = st.columns([1, 1])
            with col_act:
                for a in actions:
                    label = f"{'✅' if a['is_completed'] else '⏳'} {a['title']}"
                    if st.button(label, key=f"list_{a['id']}", use_container_width=True):
                        st.session_state['active_act'] = a
            with col_adv:
                if 'active_act' in st.session_state:
                    render_advisor_panel(st.session_state['active_act'])
                else:
                    st.write("액션을 선택하면 AI 조언자의 가이드가 나타납니다.")

        with tab_flow:
            st.subheader("🗺️ 로드맵 시각화")
            mermaid_lines = ["graph LR"]
            mermaid_lines.append(f'GOAL["🎯 {clean_text(target["title"])}"]')
            phases = list(dict.fromkeys([a['title'].split(']')[0].replace("[", "").strip() for a in actions]))
            for i, p in enumerate(phases):
                mermaid_lines.append(f'P{i}["📍 {clean_text(p)}"]')
                if i == 0: mermaid_lines.append(f"GOAL --> P0")
                else: mermaid_lines.append(f"P{i-1} --> P{i}")
            
            mermaid_code = "\n".join(mermaid_lines)
            components.html(f"""
                <div class="mermaid" style="display:flex; justify-content:center; background:#1e293b; padding:20px; border-radius:10px;">{mermaid_code}</div>
                <script type="module">
                    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.esm.min.mjs';
                    mermaid.initialize({{ startOnLoad: true, theme: 'dark', securityLevel: 'loose' }});
                    await mermaid.run();
                </script>
            """, height=400)

# (3) 전략적 로드맵 설계
elif menu == "🎯 전략적 로드맵 설계":
    st.header("🎯 AI Hierarchical Planning")
    with st.form("plan_form"):
        user_dream = st.text_input("당신의 거대한 목표는 무엇인가요?")
        submit = st.form_submit_button("AI 정밀 설계 시작")
        
    if submit and user_dream:
        with st.spinner("AI가 비전과 실행 계획을 수립 중입니다..."):
            data = generate_hierarchical_roadmap(user_dream)
            res = supabase.table("goals").insert({
                "title": user_dream, "domain": data['domain'], "vision": data['vision']
            }).execute()
            g_id = res.data[0]['id']
            for m in data['roadmap']:
                for a in m['actions']:
                    supabase.table("actions").insert({
                        "goal_id": g_id, "title": f"[{m['milestone']}] {a['title']}",
                        "advisor_data": {"why": a['why'], "how": a['how'], "notes": ""}
                    }).execute()
            st.success("새로운 로드맵이 생성되었습니다! 대시보드를 확인하세요.")

# (4) 스낵 챌린지
elif menu == "🍪 스낵 챌린지":
    st.header("🍪 LifeSync Snack Bar")
    st.write("자투리 시간을 활용한 성장의 기회입니다.")
    
    col_t, col_l = st.columns(2)
    with col_t: t_limit = st.select_slider("가용 시간(분)", options=[1, 5, 10, 15, 20, 30])
    with col_l: level = st.select_slider("난이도", options=["매우 쉬움", "보통", "도전적"])
    
    if st.button("오늘의 맞춤 스낵 5개 뽑기", use_container_width=True):
        with st.spinner("AI 조언자가 스낵을 고르는 중..."):
            st.session_state['snack_list'] = generate_snack_ai(t_limit, level)
            
    if 'snack_list' in st.session_state and st.session_state['snack_list']:
        for s in st.session_state['snack_list']:
            with st.container(border=True):
                st.subheader(f"✨ {s['title']} ({s['duration']})")
                st.write(f"**💡 효과:** {s['why']}")
                st.info(f"**🚀 가이드:** {s['how']}")
                if st.button(f"완료!", key=f"snack_{s['title']}"):
                    st.balloons()
                    st.toast("훌륭합니다! 에너지가 충전되었습니다.")
