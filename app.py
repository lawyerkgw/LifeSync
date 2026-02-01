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
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
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
    # 전문가의 페르소나와 구체적인 출력 구조를 프롬프트에 주입
    prompt = f"""
    당신은 따뜻하고 유능한 라이프 코치입니다. 
    사용자가 지금 {minutes}분 정도의 여유가 있고, 난이도 '{level}'의 활동을 원합니다.
    사용자에게 동기를 부여할 수 있도록 5개의 스낵 챌린지를 추천해주세요.
    
    [응답 규칙]
    1. 각 챌린지는 '제목', '소요시간', '이 활동이 좋은 이유(Why)', '구체적인 방법(How)'을 포함하세요.
    2. 말투는 친절하고 격려하는 느낌으로 작성하세요.
    3. 반드시 아래 JSON 리스트 형식으로만 응답하세요.
    
    JSON 형식:
    [
      {{
        "title": "챌린지 제목",
        "duration": "{minutes}분",
        "why": "이 활동이 당신의 뇌나 기분에 주는 긍정적 효과",
        "how": "지금 바로 따라 할 수 있는 아주 구체적인 첫 번째 단계"
      }}
    ]
    """
    try:
        response = model.generate_content(prompt)
        res_text = response.text
        
        # JSON 블록 추출 로직
        import re
        json_match = re.search(r'(\[.*\])', res_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        return json.loads(res_text)
    except Exception as e:
        st.error(f"AI 조언자가 스낵을 준비하다가 실수를 했네요: {e}")
        return None

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

# (2) 오늘의 할 일 탭 수정 버전
elif menu == "📅 오늘의 할 일":
    st.header("📅 LifeSync 실행 센터")
    
    # 상단 탭으로 뷰 전환
    view_tab1, view_tab2 = st.tabs(["📑 리스트형 일정", "🗺️ 로드맵 흐름도"])
    
    goals = supabase.table("goals").select("*").order("created_at", desc=True).execute().data
    if not goals:
        st.info("등록된 목표가 없습니다. '새 로드맵 설계'에서 시작하세요!")
    else:
        selected_goal_title = st.selectbox("집중할 목표 선택", [g['title'] for g in goals])
        target_goal = next(g for g in goals if g['title'] == selected_goal_title)
        actions = supabase.table("actions").select("*").eq("goal_id", target_goal['id']).execute().data

        # --- [VIEW 1: 리스트형 일정] ---
        with view_tab1:
            st.subheader(f"📌 {selected_goal_title}의 할 일")
            # 일정을 Phase별로 묶어서 보여줌
            for a in actions:
                col_t1, col_t2 = st.columns([4, 1])
                status = "✅" if a['is_completed'] else "⏳"
                if col_t1.button(f"{status} {a['title']}", key=f"list_{a['id']}", use_container_width=True):
                    st.session_state['active_action'] = a
                if a['is_completed']:
                    col_t2.caption("완료됨")
            
            st.divider()
            # 조언자 패널 (이전과 동일하게 유지)
            if 'active_action' in st.session_state:
                render_advisor_panel(st.session_state['active_action'])

        # --- [VIEW 2: 로드맵 흐름도 (Mermaid)] ---
        with view_tab2:
            st.subheader("📍 전체 플로우차트")
            st.write("목표의 단계별 연결성을 확인하세요.")
            
            # Mermaid 문법 생성
            mermaid_code = "graph TD\n"
            mermaid_code += f"  Start(({selected_goal_title})) --> P1\n"
            
            # 실제 데이터를 기반으로 노드 연결 (단순화 버전)
            phases = list(dict.fromkeys([a['title'].split(']')[0] + ']' for a in actions]))
            for i, p in enumerate(phases):
                color = "fill:#dfd,stroke:#3c3" if "완료" in p else "fill:#fff,stroke:#333"
                mermaid_code += f"  P{i}[{p}]\n"
                if i < len(phases) - 1:
                    mermaid_code += f"  P{i} --> P{i+1}\n"
            
            # Mermaid 렌더링 (HTML 사용)
            import streamlit.components.v1 as components
            html_code = f"""
                <pre class="mermaid">
                    {mermaid_code}
                </pre>
                <script type="module">
                    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                    mermaid.initialize({{ startOnLoad: true }});
                </script>
            """
            components.html(html_code, height=400, scrolling=True)
            st.caption("💡 각 단계는 선후 관계를 나타내며, 순차적으로 달성하는 것을 권장합니다.")

# (3) 스낵 챌린지
elif menu == "🍪 스낵 챌린지":
    st.header("🍪 LifeSync Snack Bar")
    st.write("당신의 소중한 자투리 시간을 위한 AI 조언자의 맞춤형 제안입니다.")
    
    t_limit = st.select_slider("지금 여유 시간 (분)", options=[1, 5, 10, 15, 20, 30])
    level = st.select_slider("난이도", options=["매우 쉬움", "보통", "도전적"])
    
    if st.button("오늘의 맞춤 스낵 5개 뽑기"):
        with st.spinner("AI 조언자가 당신의 상황에 맞는 활동을 고민 중입니다..."):
            st.session_state['snack_list'] = generate_snack_ai(t_limit, level)
            
    if 'snack_list' in st.session_state:
        for s in st.session_state['snack_list']:
            with st.container(border=True):
                sc1, sc2 = st.columns([4, 1])
                with sc1:
                    st.subheader(f"✨ {s['title']} ({s['duration']})")
                    st.markdown(f"**💡 왜 해야 하나요?**\n{s.get('why', '잠시 숨을 돌리며 에너지를 충전해보세요.')}")
                    st.info(f"**🚀 실천 가이드:** {s.get('how', '지금 바로 시작해보세요!')}")
                
                with sc2:
                    st.write("") # 간격 조절
                    if st.button("완료!", key=f"snk_{s['title']}"):
                        st.balloons()
                        st.toast(f"'{s['title']}' 완료! 당신의 삶이 한 뼘 더 성장했습니다.")
