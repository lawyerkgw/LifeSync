import streamlit as st
from supabase import create_client
import google.generativeai as genai
import json
import streamlit.components.v1 as components

# --- [1. 설정 및 초기화] ---
st.set_page_config(page_title="LifeSync", page_icon="🔄", layout="wide")

@st.cache_resource
def init_clients():
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    return supabase, model

supabase, model = init_clients()

# --- [2. 핵심 UI 컴포넌트 함수 (중요: NameError 방지)] ---
def render_advisor_panel(act):
    """선택된 액션의 상세 조언 및 메모를 렌더링"""
    st.success(f"🎯 선택된 과업: {act['title']}")
    
    # 조언자 체크포인트
    st.markdown("### 💡 조언자의 체크포인트")
    checkpoints = act['advisor_data'].get('checkpoints', [])
    if not checkpoints:
        st.info("이 과업에는 설정된 체크포인트가 없습니다.")
    else:
        for cp in checkpoints:
            st.checkbox(cp, key=f"cp_{act['id']}_{cp}")
    
    st.divider()
    
    # 의사결정 기록 메모
    st.markdown("### 📝 의사결정 및 비교 기록")
    memo = st.text_area("조언자의 가이드를 따라 진행하며 느낀 점이나 후보군 비교를 적으세요.", 
                        value=act['advisor_data'].get('notes', ""), 
                        key=f"memo_{act['id']}")
    
    col_b1, col_b2 = st.columns(2)
    if col_b1.button("✅ 완료 상태 변경", use_container_width=True):
        new_status = not act['is_completed']
        supabase.table("actions").update({"is_completed": new_status}).eq("id", act['id']).execute()
        st.rerun()
        
    if col_b2.button("💾 기록 저장", use_container_width=True):
        new_adv = act['advisor_data']
        new_adv['notes'] = memo
        supabase.table("actions").update({"advisor_data": new_adv}).eq("id", act['id']).execute()
        st.toast("서버에 기록이 안전하게 저장되었습니다.")

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

# --- [3. 메인 로직] ---
st.sidebar.title("🔄 LifeSync")
menu = st.sidebar.radio("메뉴", ["📅 오늘의 할 일", "🎯 새 로드맵 설계", "🍪 스낵 챌린지"])

if menu == "🎯 새 로드맵 설계":
    st.header("🎯 새로운 인생 목표 설정")
    goal_input = st.text_input("어떤 인생 목표를 동기화할까요?")
    if st.button("AI 전략 로드맵 생성") and goal_input:
        with st.spinner("AI 조언자가 최적의 경로를 계산 중..."):
            try:
                prompt = f"목표 '{goal_input}'를 분석하여 반드시 JSON으로만 응답하세요. 4개 Phase, 각 3개 Action 포함. 구조: {{'domain': '...', 'roadmap': [{{'phase': '...', 'actions': [{{'title': '...', 'checkpoints': []}}]}}]}}"
                response = model.generate_content(prompt)
                data = json.loads(response.text.replace("```json", "").replace("```", "").strip())
                
                res = supabase.table("goals").insert({"title": goal_input, "domain": data['domain']}).execute()
                g_id = res.data[0]['id']
                
                for p in data['roadmap']:
                    for a in p['actions']:
                        supabase.table("actions").insert({
                            "goal_id": g_id,
                            "title": f"[{p['phase']}] {a['title']}",
                            "advisor_data": {"checkpoints": a['checkpoints'], "notes": ""}
                        }).execute()
                st.success("로드맵 생성 완료! '오늘의 할 일' 탭을 확인하세요.")
            except Exception as e:
                st.error(f"생성 실패: {e}")

elif menu == "📅 오늘의 할 일":
    st.header("📅 LifeSync 실행 및 흐름")
    goals = supabase.table("goals").select("*").order("created_at", desc=True).execute().data
    
    if not goals:
        st.info("등록된 목표가 없습니다.")
    else:
        view_tab1, view_tab2 = st.tabs(["📑 리스트 및 조언", "🗺️ 플로우차트"])
        selected_goal_title = st.selectbox("목표 선택", [g['title'] for g in goals])
        target_goal = next(g for g in goals if g['title'] == selected_goal_title)
        actions = supabase.table("actions").select("*").eq("goal_id", target_goal['id']).execute().data

        with view_tab1:
            c1, c2 = st.columns([1, 1])
            with c1:
                st.subheader("과업 리스트")
                for a in actions:
                    label = f"{'✅' if a['is_completed'] else '⏳'} {a['title']}"
                    if st.button(label, key=f"btn_{a['id']}", use_container_width=True):
                        st.session_state['active_action'] = a
            with c2:
                if 'active_action' in st.session_state:
                    render_advisor_panel(st.session_state['active_action'])
                else:
                    st.info("왼쪽에서 과업을 선택하면 조언자가 나타납니다.")

        with view_tab2:
            st.subheader("📍 로드맵 흐름도")
            if not actions:
                st.warning("표시할 단계별 과업이 없습니다.")
            else:
                # 1. Mermaid 문법 생성 및 특수문자 완벽 제거
                mermaid_code = "graph TD\n"
                
                # 중복 제거된 Phase(단계) 리스트 생성
                raw_phases = []
                for a in actions:
                    # "[Phase 1] 할일" 형태에서 "Phase 1"만 추출
                    p_name = a['title'].split(']')[0].replace("[", "").strip()
                    if p_name not in raw_phases:
                        raw_phases.append(p_name)
                
                # 노드 정의 및 연결
                for i, p in enumerate(raw_phases):
                    # Mermaid 문법을 깨뜨리는 문자 제거
                    safe_name = p.replace('"', '').replace("'", "").replace("(", "").replace(")", "")
                    # 완료 여부에 따라 스타일 지정 가능 (향후 확장용)
                    mermaid_code += f'  P{i}["{safe_p_name if "safe_p_name" in locals() else safe_name}"]\n'
                    if i < len(raw_phases) - 1:
                        mermaid_code += f"  P{i} --> P{i+1}\n"
        
                # 2. HTML 및 JS 렌더링 (보안 및 로딩 최적화)
                html_code = f"""
                <div id="mermaid-container" style="display: flex; justify-content: center; background: white; padding: 20px;">
                    <pre class="mermaid">
                        {mermaid_code}
                    </pre>
                </div>
                <script type="module">
                    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                    // 에러 발생 시 콘솔에 출력하도록 설정
                    mermaid.initialize({{ 
                        startOnLoad: true, 
                        theme: 'neutral',
                        securityLevel: 'loose',
                        logLevel: 'error'
                    }});
                    // 명시적으로 다시 렌더링 시도
                    await mermaid.run();
                </script>
                """
                # height를 충분히 주어야 잘리지 않습니다.
                components.html(html_code, height=600, scrolling=True)
    

# (3) 스낵 챌린지 메뉴 부분
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
